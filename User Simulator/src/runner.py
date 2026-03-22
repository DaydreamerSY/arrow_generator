"""
Shared per-level simulation runner.
Used by both server.py and calibrate.py to avoid code duplication.
"""

import random
import statistics
from typing import Dict

from config import SimulationConfig, PlayerProfile
from user_model import UserModel
from game_adapter import ArrowEscapeAdapter
from engine import Board


def simulate_level(
    board: Board,
    sim_config: SimulationConfig,
    n_players: int,
    seed: int,
    profiles: Dict[str, PlayerProfile],
    mix: Dict[str, float],
) -> dict:
    """
    Run per-level simulation for n_players using given profiles/mix.

    Returns dict with: avg_time, med_time, avg_attempts, win_rate, fail_rate.
    Times are in minutes.
    """
    rng = random.Random(seed)
    acfg = sim_config.attempt
    all_times_ms, all_attempts = [], []
    wins, total_matches, total_wins = 0, 0, 0

    profiles_list = list(profiles.keys())
    weights = [mix[p] for p in profiles_list]

    for ui in range(n_players):
        chosen = rng.choices(profiles_list, weights=weights, k=1)[0]
        user = UserModel(ui + seed, profiles[chosen], sim_config)
        adapter = ArrowEscapeAdapter(board, user, sim_config)
        total_time, won = 0.0, False

        for att_num in range(acfg.max_attempts):
            result = adapter.simulate_attempt(att_num)
            total_time += result.time_ms
            total_matches += 1
            if result.won:
                won = True
                total_wins += 1
                break
            if user.should_give_up(att_num + 1):
                break

        if won:
            wins += 1
        # Apply global timing multiplier (post-multiply output only, does NOT affect
        # internal decisions like fatigue/frustration/timeout — see config.py note)
        all_times_ms.append(total_time * sim_config.timing_multiplier)
        all_attempts.append(att_num + 1)

    times_min = [t / 60_000.0 for t in all_times_ms]
    return {
        "avg_time": statistics.mean(times_min) if times_min else 0,
        "med_time": statistics.median(times_min) if times_min else 0,
        "avg_attempts": statistics.mean(all_attempts) if all_attempts else 1,
        "win_rate": wins / n_players if n_players > 0 else 0,
        "fail_rate": 1 - (total_wins / total_matches) if total_matches > 0 else 0,
    }
