"""
Configuration for User Simulator — Tier 2 architecture.

3-layer design:
  Layer 1: UserModel (reusable across games)
  Layer 2: GameAdapter (game-specific)
  Layer 3: CohortSimulator (orchestrator)

Player profiles, engagement model, churn model, and simulation settings.

Calibration round 1: applied from calibrate.py suggestions
  - Timing params ×0.25 (sim was 4.1x slower than feed)
  - base_between_churn 0.025 → 0.005 (sim churned 5x faster)
  - engagement_churn_weight 0.08 → 0.02
  - give_up_base_prob 0.10 → 0.03
  - give_up_increment 0.15 → 0.05
  - frustration_buildup_rate reduced ~30% (win rate 2.5pp low)
"""

from dataclasses import dataclass, field
from typing import Dict, List


# ═══════════════════════════════════════════════════════════════════════════════
#  Layer 1 — User Model Config (reusable across games)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class ViewportConfig:
    """
    Two-state zoom model for mobile phone viewport.
    Derived from actual game screenshots.
    Reusable: any grid-based mobile game with zoom.
    """
    # Zoom-in: visible cells
    zoom_in_width: int = 10
    zoom_in_height: int = 17

    # Zoom-out: visible cells
    zoom_out_width: int = 31
    zoom_out_height: int = 53

    # Zoom-out penalties (smaller elements harder to parse)
    zoom_out_eval_multiplier: float = 1.5
    zoom_out_head_find_multiplier: float = 1.8
    zoom_out_miss_bonus: float = 0.10
    zoom_out_scan_speed: float = 0.7

    # Timing — calibrated round 4 (further reduced for large boards)
    zoom_transition_time: float = 80.0      # ms
    pan_time: float = 60.0                  # ms
    viewport_overlap: int = 2
    initial_position: str = "top_left"


@dataclass
class EyeConfig:
    """
    Human eye/vision model for target demographic (female 45-60).
    Reusable: same person, different game.
    """
    effective_fov_width: int = 8        # cells within focus
    effective_fov_height: int = 10
    fixation_time: float = 30           # ms per fixation
    saccade_time: float = 12            # ms eye movement
    recheck_probability: float = 0.15
    color_confusion_penalty: float = 40   # ms — NOT YET IMPLEMENTED: extra scan time when arrows share visual similarity


@dataclass
class EngagementConfig:
    """
    Engagement curve model — inverted U shape.
    Controls churn based on perceived difficulty.

    Calibrated round 1: reduced churn rates to match feed data retention.
    """
    sweet_spot: float = 0.35
    spread: float = 0.30                # wider flow zone (was 0.25)
    peak_engagement: float = 0.98
    floor_engagement: float = 0.70      # higher floor (was 0.60)

    # Between-level churn — calibrated round 3
    base_between_churn: float = 0.001   # round 3 (was 0.003)
    engagement_churn_weight: float = 0.005  # round 3 (was 0.01)


@dataclass
class AttemptConfig:
    """
    Attempt/retry model — calibrated round 1.
    """
    # Fail triggers
    frustration_cap: float = 1.0
    max_attempt_time_ms: float = 900_000    # 15 minutes

    # Retry behavior
    max_attempts: int = 5
    retry_learning_factor: float = 0.85
    retry_frustration_carry: float = 0.25
    retry_scan_improvement: float = 0.95

    # Give-up probability — calibrated round 3
    give_up_base_prob: float = 0.01          # round 3 (was 0.02)
    give_up_increment: float = 0.02          # round 3 (was 0.03)


@dataclass
class SkillConfig:
    """
    Cross-level skill progression model.
    """
    scan_growth_rate: float = 0.998
    miss_growth_rate: float = 0.997
    decision_growth_rate: float = 0.999
    skill_floor: float = 0.60
    mastery_engagement_bonus: float = 0.02


@dataclass
class LevelOverheadConfig:
    """Fixed time costs per level from UI/loading, not gameplay."""
    level_load_time_ms: float = 1500        # loading screen + level title
    win_celebration_ms: float = 2000         # win animation at end


@dataclass
class BoosterConfig:
    """
    Booster system — power-ups players can use during a level.

    Arrow Escape boosters:
      - Hint: removes 1 solvable arrow automatically
      - Scissors: removes 1 player-selected arrow (any)
      - Magic Wand: removes up to 3 arrows recursively

    Interface designed for extensibility — other games can add
    different boosters by subclassing or adding new types.
    """
    enabled: bool = True

    # Player booster usage behavior
    # Frustration threshold: player considers boosters when frustration >= this
    hint_frustration_threshold: float = 0.4
    scissors_frustration_threshold: float = 0.6
    wand_frustration_threshold: float = 0.8

    # Usage probability (per check, when threshold met)
    hint_use_prob: float = 0.15
    scissors_use_prob: float = 0.08
    wand_use_prob: float = 0.05

    # Inventory limits (per level attempt, 0 = unlimited)
    hint_per_attempt: int = 5
    scissors_per_attempt: int = 5
    wand_per_attempt: int = 5

    # Time cost to activate booster (thinking + UI interaction)
    hint_activation_ms: float = 800
    scissors_activation_ms: float = 1200     # player needs to pick which arrow
    wand_activation_ms: float = 600          # just tap the button


@dataclass
class ComboConfig:
    """
    Combo system — chain clears within time window give bonuses.

    NOT IMPLEMENTED for Arrow Escape (no combo mechanic).
    Placeholder for future games (match-3, etc.). Do not remove.
    """
    enabled: bool = False
    combo_window_ms: float = 2000            # time to maintain combo chain
    speed_bonus_per_level: float = 0.05      # scan speed boost per combo level
    mistake_risk_per_level: float = 0.02     # extra mistake chance when rushing
    max_combo_level: int = 10
    frustration_decay_per_combo: float = 0.03  # frustration reduced per combo


@dataclass
class PlayerProfile:
    """
    Player archetype — cognitive and behavioral parameters.
    Calibration round 1: all timing params ×0.25.
    """
    name: str = "default"

    # ── Cognitive timing (calibrated ×0.25) ─────────────────────
    scan_time_per_arrow: float = 175        # ms (was 700)
    decision_time_base: float = 350         # ms (was 1400)
    decision_time_per_bend: float = 20      # ms (was 80)
    tap_time: float = 200                   # ms (physical tap — not scaled)

    # ── Error rates ─────────────────────────────────────────────
    miss_probability: float = 0.12
    mistake_rate: float = 0.08
    mistake_penalty: float = 300            # fixed animation penalty

    # ── Fatigue ─────────────────────────────────────────────────
    fatigue_factor: float = 1.008           # reduced (was 1.015)

    # ── Scan behavior (calibrated ×0.25) ────────────────────────
    board_scan_time: float = 125            # ms (was 500)
    hesitation_threshold: int = 2  # NOT YET IMPLEMENTED: when solvable_count <= threshold, multiply decision_time
    scan_direction: str = "ltr_ttb"
    memory_probability: float = 0.4
    recheck_probability: float = 0.15

    # ── Batch behavior ──────────────────────────────────────────
    rescan_time_ratio: float = 0.5
    max_batch_before_pan: int = 4

    # ── Problem-solving (calibrated) ────────────────────────────
    recursive_solve_probability: float = 0.4
    max_recursion_depth: int = 2
    recursion_think_time: float = 200       # ms (was 800)
    frustration_buildup_rate: float = 0.02  # reduced (was 0.03)
    frustration_decay_after_solve: float = 0.15

    # ── Zoom behavior ───────────────────────────────────────────
    initial_zoom: str = "out"
    zoom_out_survey_prob: float = 0.30
    zoom_in_to_tap_prob: float = 0.80
    zoom_out_tap_prob: float = 0.30
    viewport_cleared_zoom_out_prob: float = 0.85
    preferred_zoom: str = "adaptive"

    # ── Skill progression ───────────────────────────────────────
    skill: SkillConfig = None  # type: ignore

    # ── Booster tendency (how likely this profile uses boosters) ──
    booster_willingness: float = 0.5        # 0=never uses, 1=uses eagerly

    # ── Game-specific ───────────────────────────────────────────
    head_find_time_base: float = 112        # ms (was 450)

    def __post_init__(self):
        if self.skill is None:
            self.skill = SkillConfig()


# ═══════════════════════════════════════════════════════════════════════════════
#  4 Archetypes — Calibrated round 1 (timing ×0.25, frustration reduced)
# ═══════════════════════════════════════════════════════════════════════════════

PLAYER_PROFILES: Dict[str, PlayerProfile] = {
    "methodical": PlayerProfile(
        name="The Methodical",
        scan_time_per_arrow=225,             # was 900
        head_find_time_base=125,             # was 500
        decision_time_base=450,              # was 1800
        decision_time_per_bend=25,           # was 100
        tap_time=220,
        miss_probability=0.05,
        mistake_rate=0.04,
        recheck_probability=0.25,
        recursive_solve_probability=0.7,
        max_recursion_depth=3,
        frustration_buildup_rate=0.015,      # was 0.02
        frustration_decay_after_solve=0.20,
        rescan_time_ratio=0.6,
        fatigue_factor=1.008,                # was 1.015
        initial_zoom="in",
        zoom_out_survey_prob=0.15,
        zoom_in_to_tap_prob=0.95,
        zoom_out_tap_prob=0.05,
        viewport_cleared_zoom_out_prob=0.70,
        preferred_zoom="in",
        memory_probability=0.5,
        max_batch_before_pan=4,
        scan_direction="ltr_ttb",
        board_scan_time=150,                 # was 600
        hesitation_threshold=2,
        recursion_think_time=225,            # was 900
        mistake_penalty=300,
        booster_willingness=0.3,         # prefers solving without help
        skill=SkillConfig(
            scan_growth_rate=0.997,
            miss_growth_rate=0.996,
            decision_growth_rate=0.998,
            skill_floor=0.55,
            mastery_engagement_bonus=0.03,
        ),
    ),
    "scanner": PlayerProfile(
        name="The Scanner",
        scan_time_per_arrow=112,             # was 450
        head_find_time_base=75,              # was 300
        decision_time_base=225,              # was 900
        decision_time_per_bend=12,           # was 50
        tap_time=150,
        miss_probability=0.20,
        mistake_rate=0.14,
        recheck_probability=0.08,
        recursive_solve_probability=0.25,
        max_recursion_depth=1,
        frustration_buildup_rate=0.04,       # was 0.06
        frustration_decay_after_solve=0.10,
        rescan_time_ratio=0.4,
        fatigue_factor=1.012,                # was 1.025
        initial_zoom="out",
        zoom_out_survey_prob=0.50,
        zoom_in_to_tap_prob=0.70,
        zoom_out_tap_prob=0.40,
        viewport_cleared_zoom_out_prob=0.95,
        preferred_zoom="out",
        memory_probability=0.3,
        max_batch_before_pan=3,
        scan_direction="ltr_ttb",
        board_scan_time=88,                  # was 350
        hesitation_threshold=1,
        recursion_think_time=150,            # was 600
        mistake_penalty=300,
        booster_willingness=0.4,         # uses when impatient
        skill=SkillConfig(
            scan_growth_rate=0.996,
            miss_growth_rate=0.998,
            decision_growth_rate=0.997,
            skill_floor=0.65,
            mastery_engagement_bonus=0.02,
        ),
    ),
    "comfortable": PlayerProfile(
        name="The Comfortable",
        scan_time_per_arrow=175,             # was 700
        head_find_time_base=112,             # was 450
        decision_time_base=350,              # was 1400
        decision_time_per_bend=20,           # was 80
        tap_time=200,
        miss_probability=0.12,
        mistake_rate=0.08,
        recheck_probability=0.15,
        recursive_solve_probability=0.4,
        max_recursion_depth=2,
        frustration_buildup_rate=0.007,      # was 0.01
        frustration_decay_after_solve=0.18,
        rescan_time_ratio=0.5,
        fatigue_factor=1.003,                # was 1.005
        initial_zoom="out",
        zoom_out_survey_prob=0.60,
        zoom_in_to_tap_prob=0.50,
        zoom_out_tap_prob=0.50,
        viewport_cleared_zoom_out_prob=0.80,
        preferred_zoom="adaptive",
        memory_probability=0.4,
        max_batch_before_pan=5,
        scan_direction="ltr_ttb",
        board_scan_time=125,                 # was 500
        hesitation_threshold=2,
        recursion_think_time=200,            # was 800
        mistake_penalty=300,
        booster_willingness=0.6,         # happy to use help
        skill=SkillConfig(
            scan_growth_rate=0.999,
            miss_growth_rate=0.998,
            decision_growth_rate=0.999,
            skill_floor=0.70,
            mastery_engagement_bonus=0.025,
        ),
    ),
    "struggler": PlayerProfile(
        name="The Struggler",
        scan_time_per_arrow=300,             # was 1200
        head_find_time_base=175,             # was 700
        decision_time_base=625,              # was 2500
        decision_time_per_bend=30,           # was 120
        tap_time=280,
        miss_probability=0.25,
        mistake_rate=0.22,
        recheck_probability=0.30,
        recursive_solve_probability=0.10,
        max_recursion_depth=1,
        frustration_buildup_rate=0.055,      # was 0.08
        frustration_decay_after_solve=0.05,
        rescan_time_ratio=0.8,
        fatigue_factor=1.018,                # was 1.035
        initial_zoom="in",
        zoom_out_survey_prob=0.10,
        zoom_in_to_tap_prob=0.90,
        zoom_out_tap_prob=0.10,
        viewport_cleared_zoom_out_prob=0.50,
        preferred_zoom="in",
        memory_probability=0.15,
        max_batch_before_pan=2,
        scan_direction="ltr_ttb",
        board_scan_time=200,                 # was 800
        hesitation_threshold=3,
        recursion_think_time=300,            # was 1200
        mistake_penalty=300,
        booster_willingness=0.8,         # relies heavily on boosters
        skill=SkillConfig(
            scan_growth_rate=0.9995,
            miss_growth_rate=0.9993,
            decision_growth_rate=0.9995,
            skill_floor=0.80,
            mastery_engagement_bonus=0.04,
        ),
    ),
}

# ── Player mix weights ──────────────────────────────────────────────────────
PLAYER_MIX: Dict[str, float] = {
    "methodical":  0.32,
    "scanner":     0.22,
    "comfortable": 0.33,
    "struggler":   0.13,
}

# ── Difficulty scoring weights (game-specific) ──────────────────────────────
DIFFICULTY_WEIGHTS: Dict[str, float] = {
    "total_arrows":                0.15,
    "avg_bend_count":              0.20,
    "min_solvable_per_iteration":  0.25,
    "max_depth":                   0.20,
    "board_density":               0.10,
    "path_complexity":             0.10,
}


# ═══════════════════════════════════════════════════════════════════════════════
#  Simulation Config (orchestrator level)
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class SimulationConfig:
    """Top-level simulation parameters."""
    cohort_size: int = 4936
    random_seed: int = 42
    output_percentiles: List[int] = field(default_factory=lambda: [25, 50, 75, 90])
    # NOTE: timing_multiplier only scales OUTPUT time (runner.py post-multiply).
    # It does NOT affect internal decisions (fatigue, frustration, timeout, should_give_up).
    # Good enough for rough calibration. For behavior-accurate scaling, modify profile timing params directly.
    timing_multiplier: float = 1.0

    # Sub-configs
    viewport: ViewportConfig = field(default_factory=ViewportConfig)
    eye: EyeConfig = field(default_factory=EyeConfig)
    engagement: EngagementConfig = field(default_factory=EngagementConfig)
    attempt: AttemptConfig = field(default_factory=AttemptConfig)
    overhead: LevelOverheadConfig = field(default_factory=LevelOverheadConfig)
    booster: BoosterConfig = field(default_factory=BoosterConfig)
    combo: ComboConfig = field(default_factory=ComboConfig)

    # Game-specific arrow eval (calibrated ×0.25)
    arrow_head_find_time_per_cell: float = 9     # was 35
    arrow_trace_time_per_cell: float = 15        # was 60
    arrow_trace_pan_time: float = 75             # was 300
    arrow_block_recognition_time: float = 38     # was 150

    # Board-state-aware scan: density clutter penalty
    density_clutter_factor: float = 0.5    # extra scan time multiplier at density=1.0
    clearing_speed_bonus: float = 0.3      # max scan speed improvement as board empties
