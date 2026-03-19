"""
Player profiles and simulation configuration.
Based on discuss.md design specification.
"""

from dataclasses import dataclass, field
from typing import Dict, List

# ─── Camera / Viewport defaults ───────────────────────────────────────────────
@dataclass
class CameraConfig:
    camera_width: int = 12          # cells visible horizontally
    camera_height: int = 16         # cells visible vertically
    viewport_overlap: int = 2       # overlap cells between adjacent regions
    pan_time: float = 400           # ms to pan to next region
    zoom_out_time: float = 600      # ms to zoom out for overview
    initial_position: str = "top_left"  # top_left | center

# ─── Eye model defaults ──────────────────────────────────────────────────────
@dataclass
class EyeConfig:
    effective_fov_width: int = 8    # cells player actually perceives
    effective_fov_height: int = 10
    fixation_time: float = 200      # ms per fixation point
    saccade_time: float = 80        # ms eye movement between fixations
    recheck_probability: float = 0.15
    color_confusion_penalty: float = 150  # ms

# ─── Arrow evaluation defaults ────────────────────────────────────────────────
@dataclass
class ArrowEvalConfig:
    head_find_time_base: float = 450      # ms base to locate head
    head_find_time_per_cell: float = 35   # ms per cell of arrow length
    trace_time_per_cell: float = 60       # ms per cell tracing exit path
    trace_pan_time: float = 300           # ms to pan when trace exceeds viewport
    block_recognition_time: float = 150   # ms to realize path is blocked
    miss_probability: float = 0.12        # chance to skip a solvable arrow

# ─── Player profile ──────────────────────────────────────────────────────────
@dataclass
class PlayerProfile:
    name: str = "default"
    # Core timing
    scan_time_per_arrow: float = 700
    decision_time_base: float = 1400
    decision_time_per_bend: float = 80
    tap_time: float = 200
    # Mistakes
    mistake_rate: float = 0.08
    mistake_penalty: float = 300       # fixed 300ms
    # Fatigue
    fatigue_factor: float = 1.015
    # Scan behavior
    board_scan_time: float = 500
    hesitation_threshold: int = 2
    scan_direction: str = "ltr_ttb"     # ltr_ttb | rtl_btt
    memory_probability: float = 0.4
    # Batch tap
    rescan_time_ratio: float = 0.5
    max_batch_before_pan: int = 4
    # Recursive unblock
    recursive_solve_probability: float = 0.4
    max_recursion_depth: int = 2
    recursion_think_time: float = 800
    frustration_buildup_rate: float = 0.03
    frustration_decay_after_solve: float = 0.15
    # Viewport
    zoom_out_probability: float = 0.15
    # Eye & Arrow eval (overrides from EyeConfig/ArrowEvalConfig)
    head_find_time_base: float = 450
    miss_probability: float = 0.12
    recheck_probability: float = 0.15


# ─── 4 Archetypes ────────────────────────────────────────────────────────────
PLAYER_PROFILES: Dict[str, PlayerProfile] = {
    "methodical": PlayerProfile(
        name="The Methodical",
        scan_time_per_arrow=900,
        head_find_time_base=500,
        decision_time_base=1800,
        decision_time_per_bend=100,
        tap_time=220,
        miss_probability=0.05,
        mistake_rate=0.04,
        recheck_probability=0.25,
        recursive_solve_probability=0.7,
        max_recursion_depth=3,
        frustration_buildup_rate=0.02,
        frustration_decay_after_solve=0.20,
        rescan_time_ratio=0.6,
        fatigue_factor=1.015,
        zoom_out_probability=0.05,
        memory_probability=0.5,
        max_batch_before_pan=4,
        scan_direction="ltr_ttb",
        board_scan_time=600,
        hesitation_threshold=2,
        recursion_think_time=900,
        mistake_penalty=300,
    ),
    "scanner": PlayerProfile(
        name="The Scanner",
        scan_time_per_arrow=450,
        head_find_time_base=300,
        decision_time_base=900,
        decision_time_per_bend=50,
        tap_time=150,
        miss_probability=0.20,
        mistake_rate=0.14,
        recheck_probability=0.08,
        recursive_solve_probability=0.25,
        max_recursion_depth=1,
        frustration_buildup_rate=0.06,
        frustration_decay_after_solve=0.10,
        rescan_time_ratio=0.4,
        fatigue_factor=1.025,
        zoom_out_probability=0.25,
        memory_probability=0.3,
        max_batch_before_pan=3,
        scan_direction="ltr_ttb",
        board_scan_time=350,
        hesitation_threshold=1,
        recursion_think_time=600,
        mistake_penalty=300,
    ),
    "comfortable": PlayerProfile(
        name="The Comfortable",
        scan_time_per_arrow=700,
        head_find_time_base=450,
        decision_time_base=1400,
        decision_time_per_bend=80,
        tap_time=200,
        miss_probability=0.12,
        mistake_rate=0.08,
        recheck_probability=0.15,
        recursive_solve_probability=0.4,
        max_recursion_depth=2,
        frustration_buildup_rate=0.01,
        frustration_decay_after_solve=0.18,
        rescan_time_ratio=0.5,
        fatigue_factor=1.005,
        zoom_out_probability=0.35,
        memory_probability=0.4,
        max_batch_before_pan=5,
        scan_direction="ltr_ttb",
        board_scan_time=500,
        hesitation_threshold=2,
        recursion_think_time=800,
        mistake_penalty=300,
    ),
    "struggler": PlayerProfile(
        name="The Struggler",
        scan_time_per_arrow=1200,
        head_find_time_base=700,
        decision_time_base=2500,
        decision_time_per_bend=120,
        tap_time=280,
        miss_probability=0.25,
        mistake_rate=0.22,
        recheck_probability=0.30,
        recursive_solve_probability=0.10,
        max_recursion_depth=1,
        frustration_buildup_rate=0.08,
        frustration_decay_after_solve=0.05,
        rescan_time_ratio=0.8,
        fatigue_factor=1.035,
        zoom_out_probability=0.05,
        memory_probability=0.15,
        max_batch_before_pan=2,
        scan_direction="ltr_ttb",
        board_scan_time=800,
        hesitation_threshold=3,
        recursion_think_time=1200,
        mistake_penalty=300,
    ),
}

# ─── Player mix weights ──────────────────────────────────────────────────────
PLAYER_MIX: Dict[str, float] = {
    "methodical":  0.32,
    "scanner":     0.22,
    "comfortable": 0.33,
    "struggler":   0.13,
}

# ─── Difficulty scoring weights ───────────────────────────────────────────────
DIFFICULTY_WEIGHTS: Dict[str, float] = {
    "total_arrows":                0.15,
    "avg_bend_count":              0.20,
    "min_solvable_per_iteration":  0.25,
    "max_depth":                   0.20,
    "board_density":               0.10,
    "path_complexity":             0.10,
}

# ─── Simulation config ───────────────────────────────────────────────────────
@dataclass
class SimulationConfig:
    runs_per_level: int = 100
    random_seed: int = 42
    output_percentiles: List[int] = field(default_factory=lambda: [25, 50, 75, 90])
    camera: CameraConfig = field(default_factory=CameraConfig)
    eye: EyeConfig = field(default_factory=EyeConfig)
    arrow_eval: ArrowEvalConfig = field(default_factory=ArrowEvalConfig)
