"""
Layer 1: UserModel — Reusable human simulation model.

Models a single human player with persistent state across multiple levels.
Handles: viewport/eye scanning, cognitive timing, fatigue, frustration,
engagement, learning, and churn decisions.

This layer is GAME-AGNOSTIC. It receives actions from a GameAdapter
and makes decisions based on human psychology, not game mechanics.
"""

import math
import random
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

from config import (
    AttemptConfig,
    EngagementConfig,
    EyeConfig,
    PlayerProfile,
    SimulationConfig,
    SkillConfig,
    ViewportConfig,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Data Models — Attempt & Level results
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class AttemptResult:
    """Result of one attempt at a level."""
    won: bool
    time_ms: float
    taps: int
    mistakes: int
    arrows_cleared: int
    total_arrows: int
    fail_reason: Optional[str] = None   # "frustration" | "timeout" | None

    @property
    def clear_ratio(self) -> float:
        """Fraction of level cleared before win/fail."""
        if self.total_arrows == 0:
            return 1.0
        return self.arrows_cleared / self.total_arrows


@dataclass
class LevelResult:
    """Result of a player playing a level (possibly multiple attempts)."""
    level_id: int
    won: bool
    total_time_ms: float            # sum of ALL attempt times
    attempts: List[AttemptResult]
    churned_during: bool = False     # gave up on this level
    churned_between: bool = False    # quit after winning, before next level

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def total_mistakes(self) -> int:
        return sum(a.mistakes for a in self.attempts)


# ═══════════════════════════════════════════════════════════════════════════════
#  Viewport & Eye Model (reusable)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ViewportRegion:
    """A rectangular region visible in one camera position."""
    rx: int         # region grid col
    ry: int         # region grid row
    x0: int
    y0: int
    x1: int         # exclusive
    y1: int         # exclusive


def compute_regions(
    board_w: int, board_h: int,
    cam_w: int, cam_h: int, overlap: int
) -> List[ViewportRegion]:
    """Divide board into overlapping camera regions."""
    if board_w <= cam_w and board_h <= cam_h:
        return [ViewportRegion(0, 0, 0, 0, board_w, board_h)]

    regions = []
    step_x = max(1, cam_w - overlap)
    step_y = max(1, cam_h - overlap)

    ry = 0
    y0 = 0
    while y0 < board_h:
        rx = 0
        x0 = 0
        y1 = min(y0 + cam_h, board_h)
        while x0 < board_w:
            x1 = min(x0 + cam_w, board_w)
            regions.append(ViewportRegion(rx, ry, x0, y0, x1, y1))
            rx += 1
            x0 += step_x
            if x1 >= board_w:
                break
        ry += 1
        y0 += step_y
        if y1 >= board_h:
            break

    return regions


class ViewportModel:
    """
    Manages viewport state and scanning for a board.
    Reusable: any grid-based game with zoom.
    """

    def __init__(self, board_w: int, board_h: int, cfg: ViewportConfig):
        self.cfg = cfg
        self.board_w = board_w
        self.board_h = board_h

        # Compute regions for both zoom states
        self.zoom_in_regions = compute_regions(
            board_w, board_h,
            cfg.zoom_in_width, cfg.zoom_in_height, cfg.viewport_overlap
        )
        self.zoom_out_regions = compute_regions(
            board_w, board_h,
            cfg.zoom_out_width, cfg.zoom_out_height, cfg.viewport_overlap
        )

        self.fits_zoomed_in = len(self.zoom_in_regions) == 1
        self.fits_zoomed_out = len(self.zoom_out_regions) == 1

        # State
        self.zoom_state = "out"     # set by player profile
        self.current_zi_idx = 0
        self.current_zo_idx = 0
        self.remembered_regions: Set[int] = set()

    def reset(self, initial_zoom: str):
        """Reset viewport state for new attempt."""
        self.zoom_state = initial_zoom
        self.current_zi_idx = 0
        self.current_zo_idx = 0
        self.remembered_regions.clear()

    def is_zoomed_out(self) -> bool:
        return self.zoom_state == "out"

    def switch_zoom(self, target: str) -> float:
        """Switch zoom state. Returns transition time in ms (0 if no switch)."""
        if self.zoom_state == target:
            return 0.0
        self.zoom_state = target
        return self.cfg.zoom_transition_time

    def current_region(self) -> ViewportRegion:
        if self.is_zoomed_out():
            idx = min(self.current_zo_idx, len(self.zoom_out_regions) - 1)
            return self.zoom_out_regions[idx]
        return self.zoom_in_regions[self.current_zi_idx]

    def zoom_eval_multiplier(self) -> float:
        if self.is_zoomed_out() and not self.fits_zoomed_in:
            return self.cfg.zoom_out_eval_multiplier
        return 1.0

    def zoom_head_find_multiplier(self) -> float:
        if self.is_zoomed_out() and not self.fits_zoomed_in:
            return self.cfg.zoom_out_head_find_multiplier
        return 1.0

    def zoom_miss_bonus(self) -> float:
        if self.is_zoomed_out() and not self.fits_zoomed_in:
            return self.cfg.zoom_out_miss_bonus
        return 0.0

    def zoom_scan_speed(self) -> float:
        if self.is_zoomed_out() and not self.fits_zoomed_in:
            return self.cfg.zoom_out_scan_speed
        return 1.0


# ═══════════════════════════════════════════════════════════════════════════════
#  Engagement Model (reusable)
# ═══════════════════════════════════════════════════════════════════════════════

def compute_engagement(
    perceived_difficulty: float,
    cfg: EngagementConfig,
) -> float:
    """
    Inverted-U engagement curve.
    Returns engagement score in [floor, peak].

    perceived_difficulty: 0.0 (trivial) to 1.0 (impossible)
    """
    # Gaussian bell centered on sweet_spot
    exponent = -((perceived_difficulty - cfg.sweet_spot) ** 2) / (
        2 * cfg.spread ** 2
    )
    raw = cfg.peak_engagement * math.exp(exponent)
    return max(cfg.floor_engagement, raw)


def compute_perceived_difficulty(
    attempt_results: List[AttemptResult],
    static_difficulty: float,
) -> float:
    """
    Compute perceived difficulty from attempt outcomes.
    Blends static level difficulty with actual player experience.

    Returns 0.0 (trivial) to 1.0 (impossible).
    """
    if not attempt_results:
        return static_difficulty

    # Factors from player experience
    num_attempts = len(attempt_results)
    won = attempt_results[-1].won
    avg_clear_ratio = sum(a.clear_ratio for a in attempt_results) / num_attempts
    avg_mistake_rate = (
        sum(a.mistakes for a in attempt_results)
        / max(1, sum(a.taps for a in attempt_results))
    )

    # Blend: experience-based difficulty
    # More attempts → harder. Lower clear ratio → harder. More mistakes → harder.
    attempt_factor = min(1.0, (num_attempts - 1) / 4.0)  # 0 at 1 attempt, 1 at 5+
    clear_factor = 1.0 - avg_clear_ratio                  # 0 if fully cleared
    mistake_factor = min(1.0, avg_mistake_rate * 5)        # scaled
    win_factor = 0.0 if won else 0.3                       # didn't win = harder

    experience_diff = (
        0.3 * attempt_factor
        + 0.3 * clear_factor
        + 0.2 * mistake_factor
        + 0.2 * win_factor
    )

    # Blend static and experience (experience dominates when available)
    return 0.4 * static_difficulty + 0.6 * experience_diff


def compute_between_churn_prob(
    engagement: float,
    cfg: EngagementConfig,
) -> float:
    """
    Probability of churning between levels.
    Base rate + penalty for low engagement.
    """
    engagement_penalty = cfg.engagement_churn_weight * (1.0 - engagement)
    return min(0.95, cfg.base_between_churn + engagement_penalty)


# ═══════════════════════════════════════════════════════════════════════════════
#  UserModel — Persistent player across levels
# ═══════════════════════════════════════════════════════════════════════════════

class UserModel:
    """
    One simulated human player with persistent state.

    Reusable across different games — this models the PERSON,
    not the game they're playing. Game-specific logic is in GameAdapter.
    """

    def __init__(
        self,
        user_id: int,
        profile: PlayerProfile,
        sim_config: SimulationConfig,
    ):
        self.user_id = user_id
        self.base_profile = profile
        self.sim_config = sim_config
        self.rng = random.Random(sim_config.random_seed + user_id)

        # ── Persistent state (cross-level) ──────────────────────
        self.active = True                      # not churned
        self.levels_played: int = 0
        self.levels_won: int = 0
        self.cumulative_frustration: float = 0.0  # decays between levels

        # Skill progression — separate modifiers for different abilities
        scfg = profile.skill
        self.scan_skill: float = 1.0            # multiplier for scan_time
        self.miss_skill: float = 1.0            # multiplier for miss_prob
        self.decision_skill: float = 1.0        # multiplier for decision_time

        # Per-attempt temporary modifier (retry learning, stacks on top of cross-level skill)
        self._retry_scan_mod: float = 1.0
        self._retry_miss_mod: float = 1.0

        # ── Current attempt state (reset per attempt) ───────────
        self.frustration: float = 0.0
        self.step_index: int = 0
        self.total_time: float = 0.0
        self.mistake_count: int = 0
        self.tap_count: int = 0
        self.arrows_cleared: int = 0

    # ── Profile with modifiers applied ─────────────────────────────────────

    @property
    def effective_miss_prob(self) -> float:
        """Miss probability adjusted by cross-level skill + retry learning."""
        return self.base_profile.miss_probability * self.miss_skill * self._retry_miss_mod

    @property
    def effective_scan_time(self) -> float:
        """Scan time adjusted by cross-level skill + retry learning."""
        return self.base_profile.scan_time_per_arrow * self.scan_skill * self._retry_scan_mod

    @property
    def effective_decision_time(self) -> float:
        """Decision time adjusted by cross-level skill."""
        return self.base_profile.decision_time_base * self.decision_skill

    @property
    def mastery_level(self) -> float:
        """How much the player has improved (0.0 = no improvement, 1.0 = max)."""
        avg_skill = (self.scan_skill + self.miss_skill + self.decision_skill) / 3
        return max(0.0, 1.0 - avg_skill)  # 0 when skill=1.0, increases as skill decreases

    # ── Fatigue multiplier ─────────────────────────────────────────────────

    def fatigue(self) -> float:
        return self.base_profile.fatigue_factor ** self.step_index

    # ── Reset for new attempt ──────────────────────────────────────────────

    def reset_for_attempt(self, attempt_num: int):
        """Reset per-attempt state. Apply learning from previous attempts."""
        acfg = self.sim_config.attempt

        # Carry some frustration from previous attempts
        if attempt_num > 0:
            self.frustration = self.frustration * acfg.retry_frustration_carry
        else:
            self.frustration = 0.0

        self.step_index = 0
        self.total_time = 0.0
        self.mistake_count = 0
        self.tap_count = 0
        self.arrows_cleared = 0

        # Reset retry modifiers
        self._retry_scan_mod = 1.0
        self._retry_miss_mod = 1.0

    def apply_retry_learning(self, attempt_num: int):
        """
        Apply learning effect for retry attempts.
        Player remembers mistakes and improves slightly.
        Stacks ON TOP of cross-level skill progression.
        """
        if attempt_num <= 0:
            return
        acfg = self.sim_config.attempt
        # Each retry reduces miss_prob and scan_time temporarily
        self._retry_miss_mod = max(0.5, acfg.retry_learning_factor ** attempt_num)
        self._retry_scan_mod = max(0.5, acfg.retry_scan_improvement ** attempt_num)

    # ── Attempt fail checks ────────────────────────────────────────────────

    def should_fail_attempt(self) -> Optional[str]:
        """
        Check if current attempt should fail.
        Returns fail reason or None.
        """
        acfg = self.sim_config.attempt

        if self.frustration >= acfg.frustration_cap:
            return "frustration"

        if self.total_time >= acfg.max_attempt_time_ms:
            return "timeout"

        return None

    # ── Give-up decision after failed attempt ──────────────────────────────

    def should_give_up(self, failed_attempts: int) -> bool:
        """
        Decide whether to quit the level after a failed attempt.
        Probability increases with each failed attempt.
        """
        acfg = self.sim_config.attempt
        prob = acfg.give_up_base_prob + (failed_attempts - 1) * acfg.give_up_increment
        prob = min(0.95, prob)
        return self.rng.random() < prob

    # ── Between-level churn decision ───────────────────────────────────────

    def should_churn_between(
        self,
        attempt_results: List[AttemptResult],
        static_difficulty: float,
    ) -> bool:
        """
        Decide whether to stop playing after completing a level.
        Based on engagement curve + mastery bonus.
        """
        if not self.active:
            return True

        ecfg = self.sim_config.engagement
        scfg = self.base_profile.skill

        perceived_diff = compute_perceived_difficulty(
            attempt_results, static_difficulty
        )
        engagement = compute_engagement(perceived_diff, ecfg)

        # Mastery bonus: skilled players are more engaged
        mastery_bonus = self.mastery_level * scfg.mastery_engagement_bonus * 10
        engagement = min(ecfg.peak_engagement, engagement + mastery_bonus)

        churn_prob = compute_between_churn_prob(engagement, ecfg)

        return self.rng.random() < churn_prob

    # ── Post-level state update ────────────────────────────────────────────

    def update_after_level(self, level_result: LevelResult):
        """Update persistent state after completing/failing a level."""
        self.levels_played += 1
        if level_result.won:
            self.levels_won += 1

        # Frustration decays between levels but doesn't fully reset
        self.cumulative_frustration = (
            self.cumulative_frustration * 0.7 + self.frustration * 0.3
        )

        # ── Cross-level skill progression ──────────────────────
        # Only improve if the player actually played (won or lost)
        scfg = self.base_profile.skill
        self.scan_skill = max(scfg.skill_floor, self.scan_skill * scfg.scan_growth_rate)
        self.miss_skill = max(scfg.skill_floor, self.miss_skill * scfg.miss_growth_rate)
        self.decision_skill = max(scfg.skill_floor, self.decision_skill * scfg.decision_growth_rate)

    def mark_churned(self):
        """Mark this user as permanently churned."""
        self.active = False
