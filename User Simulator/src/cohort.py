"""
Layer 3: CohortSimulator — Orchestrates N players through level sequence.

Spawns a cohort of simulated users, runs them through levels,
tracks churn/engagement, and outputs CSV matching Feed data format.

Output columns match:
  - Level playtime.csv: level, Avg/Median time, cumulative, attempts, multi-attempt%
  - Level engagement.csv: level, start, Start/Complete Level%, Win Rate%, During/Between Level%, fail/churn rate%
"""

import csv
import math
import random
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from config import (
    PLAYER_MIX,
    PLAYER_PROFILES,
    PlayerProfile,
    SimulationConfig,
)
from engine import Board, load_level, compute_level_metrics, LevelMetrics
from game_adapter import ArrowEscapeAdapter
from user_model import AttemptResult, LevelResult, UserModel, compute_perceived_difficulty


# ═══════════════════════════════════════════════════════════════════════════════
#  Per-Level Aggregated Metrics
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class LevelAggregation:
    """Aggregated metrics for one level across the cohort."""
    level_id: int

    # Playtime metrics
    all_times_minutes: List[float] = field(default_factory=list)    # total time per player (all attempts)
    all_attempt_counts: List[int] = field(default_factory=list)     # attempts per player

    # Engagement metrics
    started: int = 0            # players who started this level
    completed: int = 0          # players who won this level
    churned_during: int = 0     # players who gave up on this level
    churned_between: int = 0    # players who quit after winning, before next level

    # Match-level fail tracking (for fail rate)
    total_matches: int = 0      # total attempts across all players
    total_wins: int = 0         # total winning attempts

    def add_player_result(self, result: LevelResult):
        """Record one player's result on this level."""
        self.started += 1
        total_time_min = result.total_time_ms / 60_000.0
        self.all_times_minutes.append(total_time_min)
        self.all_attempt_counts.append(result.attempt_count)

        # Track all attempts for fail rate
        for attempt in result.attempts:
            self.total_matches += 1
            if attempt.won:
                self.total_wins += 1

        if result.won:
            self.completed += 1
        if result.churned_during:
            self.churned_during += 1

    def mark_between_churn(self):
        """Record a between-level churn (player won but quit before next level)."""
        self.churned_between += 1


def compute_cohort_csvs(
    aggregations: Dict[int, LevelAggregation],
    level_ids: List[int],
    cohort_size: int,
) -> Tuple[List[Dict], List[Dict]]:
    """
    Compute the two output CSVs from aggregated data.

    Returns:
        (playtime_rows, engagement_rows) — each a list of dicts matching Feed data columns.
    """
    playtime_rows = []
    engagement_rows = []
    cumulative_avg = 0.0

    prev_winners = None  # for Between Level %

    for level_id in level_ids:
        agg = aggregations.get(level_id)
        if agg is None or agg.started == 0:
            continue

        # ── Playtime CSV ────────────────────────────────────────────────
        times = agg.all_times_minutes
        attempts = agg.all_attempt_counts

        avg_time = statistics.mean(times) if times else 0.0
        med_time = statistics.median(times) if times else 0.0
        cumulative_avg += avg_time

        multi_attempt_count = sum(1 for a in attempts if a > 1)
        pct_multi_attempt = multi_attempt_count / len(attempts) if attempts else 0.0
        avg_attempts = statistics.mean(attempts) if attempts else 1.0
        med_attempts = statistics.median(attempts) if attempts else 1.0

        playtime_rows.append({
            "level": level_id,
            "Avg time spent (minutes)": avg_time,
            "Median time spent (minutes)": med_time,
            "Cumulative avg time spent (minutes)": cumulative_avg,
            "%User having more than one attempt": pct_multi_attempt,
            "avg attempts": avg_attempts,
            "median attempts": med_attempts,
        })

        # ── Engagement CSV ──────────────────────────────────────────────
        start_pct = agg.started / cohort_size
        complete_pct = agg.completed / cohort_size
        win_rate = agg.completed / agg.started if agg.started > 0 else 0.0
        # During Level %: fraction of starters who gave up during this level
        during_pct = (agg.started - agg.completed) / agg.started if agg.started > 0 else 0.0
        fail_rate = 1.0 - (agg.total_wins / agg.total_matches) if agg.total_matches > 0 else 0.0
        # Churn during level: players who started but gave up (not just failed)
        churn_during_rate = agg.churned_during / agg.started if agg.started > 0 else 0.0

        # Between Level %: (start(N+1) - winners(N)) / winners(N)
        # Computed relative to PREVIOUS level's winners
        if prev_winners is not None and prev_winners > 0:
            between_pct = (agg.started - prev_winners) / prev_winners
        else:
            between_pct = None  # first level or no previous winners

        engagement_rows.append({
            "level": level_id,
            "start": agg.started,
            "Start Level %": start_pct,
            "Complete Level %": complete_pct,
            "Win Rate %": win_rate,
            "During Level %": during_pct,
            "Between Level %": between_pct if between_pct is not None else "null",
            "fail rate %": fail_rate,
            "churn rate %": churn_during_rate,
        })

        prev_winners = agg.completed

    return playtime_rows, engagement_rows


# ═══════════════════════════════════════════════════════════════════════════════
#  Cohort Simulator
# ═══════════════════════════════════════════════════════════════════════════════

class CohortSimulator:
    """
    Simulate a cohort of N players progressing through levels.

    Each player:
      1. Is assigned a profile (weighted random from PLAYER_MIX)
      2. Plays levels in order (level 1, 2, 3, ...)
      3. Can fail attempts, retry, give up (during-level churn)
      4. Can quit between levels (between-level churn)
      5. Once churned, never returns
    """

    def __init__(
        self,
        level_files: List[str],
        sim_config: SimulationConfig,
    ):
        self.sim_config = sim_config
        self.rng = random.Random(sim_config.random_seed)

        # Load and sort levels by ID
        self.boards: List[Board] = []
        self.metrics_cache: Dict[int, LevelMetrics] = {}
        for lf in level_files:
            board = load_level(lf)
            self.boards.append(board)
        self.boards.sort(key=lambda b: b.level_id)

        self.level_ids = [b.level_id for b in self.boards]

        # Pre-compute metrics
        for board in self.boards:
            self.metrics_cache[board.level_id] = compute_level_metrics(board)

        # Results
        self.aggregations: Dict[int, LevelAggregation] = {
            b.level_id: LevelAggregation(b.level_id) for b in self.boards
        }

    def _assign_profile(self) -> PlayerProfile:
        """Assign a player profile based on PLAYER_MIX weights."""
        profiles = list(PLAYER_PROFILES.keys())
        weights = [PLAYER_MIX[p] for p in profiles]
        chosen = self.rng.choices(profiles, weights=weights, k=1)[0]
        return PLAYER_PROFILES[chosen]

    def _simulate_player_on_level(
        self, user: UserModel, board: Board
    ) -> LevelResult:
        """
        Simulate one player on one level (with retry logic).
        Returns LevelResult.
        """
        acfg = self.sim_config.attempt
        adapter = ArrowEscapeAdapter(board, user, self.sim_config)
        metrics = self.metrics_cache[board.level_id]

        attempts: List[AttemptResult] = []
        total_time_ms = 0.0
        won = False
        gave_up = False

        for attempt_num in range(acfg.max_attempts):
            result = adapter.simulate_attempt(attempt_num)
            attempts.append(result)
            total_time_ms += result.time_ms

            if result.won:
                won = True
                break

            # Decide whether to retry or give up
            if user.should_give_up(attempt_num + 1):
                gave_up = True
                break

        # churned_during = player CHOSE to quit (not just exhausted attempts)
        return LevelResult(
            level_id=board.level_id,
            won=won,
            total_time_ms=total_time_ms,
            attempts=attempts,
            churned_during=gave_up,
        )

    def run(self, progress_interval: int = 500) -> Tuple[List[Dict], List[Dict]]:
        """
        Run the full cohort simulation.

        Returns (playtime_rows, engagement_rows).
        """
        cohort_size = self.sim_config.cohort_size
        print(f"Simulating {cohort_size} players across {len(self.boards)} levels...")
        t0 = time.time()

        active_count = cohort_size

        for ui in range(cohort_size):
            if ui > 0 and ui % progress_interval == 0:
                elapsed = time.time() - t0
                rate = ui / elapsed if elapsed > 0 else 0
                print(f"  Player {ui}/{cohort_size} "
                      f"({active_count} active, {elapsed:.1f}s, {rate:.0f} players/s)")

            profile = self._assign_profile()
            user = UserModel(ui, profile, self.sim_config)

            for board in self.boards:
                if not user.active:
                    break

                # Play the level
                level_result = self._simulate_player_on_level(user, board)
                self.aggregations[board.level_id].add_player_result(level_result)

                user.update_after_level(level_result)

                if level_result.churned_during:
                    # Player gave up on this level
                    user.mark_churned()
                    active_count -= 1
                    break

                # Between-level churn decision
                metrics = self.metrics_cache[board.level_id]
                if user.should_churn_between(
                    level_result.attempts,
                    metrics.difficulty_score,
                ):
                    self.aggregations[board.level_id].mark_between_churn()
                    user.mark_churned()
                    active_count -= 1
                    break

        elapsed = time.time() - t0
        print(f"Simulation complete: {elapsed:.1f}s total")

        # Compute CSV data
        return compute_cohort_csvs(
            self.aggregations, self.level_ids, cohort_size
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  CSV Writer
# ═══════════════════════════════════════════════════════════════════════════════

def write_csv(rows: List[Dict], filepath: str):
    """Write list of dicts to CSV file."""
    if not rows:
        return
    fieldnames = list(rows[0].keys())
    with open(filepath, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
