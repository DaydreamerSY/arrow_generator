"""
Core simulation engine: level loading, board solving, viewport model, player simulation.
Implements the full step-timeline formula from discuss.md.
"""

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from config import (
    ViewportConfig as CameraConfig,   # backward compat alias
    EyeConfig,
    PlayerProfile,
    SimulationConfig,
    DIFFICULTY_WEIGHTS,
)


# ═══════════════════════════════════════════════════════════════════════════════
#  Data Models
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Arrow:
    arrow_id: int
    dx: int                       # direction x component
    dy: int                       # direction y component
    head_x: int                   # X (column)
    head_y: int                   # Y (row)
    indices: List[int]            # cell indices occupied
    bend_count: int
    cells: Set[Tuple[int, int]] = field(default_factory=set)   # (x, y) set

    @property
    def length(self) -> int:
        return len(self.indices)


@dataclass
class Board:
    width: int      # XSize
    height: int     # YSize
    picture: str
    level_id: int
    arrows: List[Arrow]

    def index_to_xy(self, idx: int) -> Tuple[int, int]:
        return idx % self.width, idx // self.width


@dataclass
class ViewportRegion:
    """A rectangular region of the board visible in one camera position."""
    rx: int         # region grid col index
    ry: int         # region grid row index
    x0: int         # top-left cell x
    y0: int         # top-left cell y
    x1: int         # bottom-right cell x (exclusive)
    y1: int         # bottom-right cell y (exclusive)


@dataclass
class StepEvent:
    """One tap action by the player."""
    step_index: int
    arrow_id: int
    time_ms: float
    is_mistake: bool
    phase_detail: str   # human-readable breakdown


@dataclass
class SimulationResult:
    """Result of one simulation run on a single level."""
    level_id: int
    player_type: str
    run_id: int
    total_time_ms: float
    total_taps: int
    mistake_count: int
    steps: List[StepEvent]
    solve_iterations: int       # how many board-state iterations to clear


@dataclass
class LevelMetrics:
    """Static difficulty metrics for a level (no simulation needed)."""
    level_id: int
    total_arrows: int
    avg_bend_count: float
    max_bend_count: int
    min_solvable_per_iteration: int
    max_depth: int              # iterations to clear with greedy solve
    board_density: float        # arrows cells / total cells
    path_complexity: float      # average arrow length
    difficulty_score: float


# ═══════════════════════════════════════════════════════════════════════════════
#  Level Loader
# ═══════════════════════════════════════════════════════════════════════════════

def load_level(filepath: str) -> Board:
    """Load a level JSON file and return a Board object."""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    board = Board(
        width=data["XSize"],
        height=data["YSize"],
        picture=data.get("PictureName", ""),
        level_id=data["LevelID"],
        arrows=[],
    )

    for i, a in enumerate(data["Arrows"]):
        arrow = Arrow(
            arrow_id=i,
            dx=a["Dx"],
            dy=a["Dy"],
            head_x=a["X"],
            head_y=a["Y"],
            indices=a["Indices"],
            bend_count=a["BendCount"],
        )
        # Pre-compute cell set
        arrow.cells = {board.index_to_xy(idx) for idx in a["Indices"]}
        board.arrows.append(arrow)

    return board


# ═══════════════════════════════════════════════════════════════════════════════
#  Board Solver  (determines which arrows are solvable)
# ═══════════════════════════════════════════════════════════════════════════════

class BoardState:
    """Mutable board state tracking remaining arrows and occupied cells."""

    def __init__(self, board: Board):
        self.board = board
        self.remaining: Dict[int, Arrow] = {a.arrow_id: a for a in board.arrows}
        self._rebuild_occupied()

    def _rebuild_occupied(self):
        """Rebuild the global occupied-cell set from remaining arrows."""
        self.occupied: Set[Tuple[int, int]] = set()
        for a in self.remaining.values():
            self.occupied |= a.cells

    def is_solvable(self, arrow: Arrow) -> bool:
        """Check if arrow's exit path is clear to board edge."""
        # Cells occupied by OTHER arrows (exclude self)
        other_cells = self.occupied - arrow.cells
        x, y = arrow.head_x, arrow.head_y
        dx, dy = arrow.dx, arrow.dy
        # Trace from head+1 step outward
        cx, cy = x + dx, y + dy
        while 0 <= cx < self.board.width and 0 <= cy < self.board.height:
            if (cx, cy) in other_cells:
                return False
            cx += dx
            cy += dy
        return True

    def trace_distance(self, arrow: Arrow) -> Tuple[int, bool]:
        """
        Trace exit path from arrow head.
        Returns (distance_in_cells, is_blocked).
        distance = cells traced before hitting edge or blocker.
        """
        other_cells = self.occupied - arrow.cells
        x, y = arrow.head_x, arrow.head_y
        dx, dy = arrow.dx, arrow.dy
        dist = 0
        cx, cy = x + dx, y + dy
        while 0 <= cx < self.board.width and 0 <= cy < self.board.height:
            dist += 1
            if (cx, cy) in other_cells:
                return dist, True
            cx += dx
            cy += dy
        return dist, False

    def find_blocker(self, arrow: Arrow) -> Optional[Arrow]:
        """Find the first arrow blocking this arrow's exit path."""
        other_cells = self.occupied - arrow.cells
        x, y = arrow.head_x, arrow.head_y
        dx, dy = arrow.dx, arrow.dy
        cx, cy = x + dx, y + dy
        while 0 <= cx < self.board.width and 0 <= cy < self.board.height:
            if (cx, cy) in other_cells:
                # Find which arrow owns this cell
                for a in self.remaining.values():
                    if a.arrow_id != arrow.arrow_id and (cx, cy) in a.cells:
                        return a
                return None
            cx += dx
            cy += dy
        return None

    def get_solvable(self) -> List[Arrow]:
        """Return all currently solvable arrows."""
        return [a for a in self.remaining.values() if self.is_solvable(a)]

    def remove_arrow(self, arrow_id: int):
        """Remove an arrow from the board."""
        if arrow_id in self.remaining:
            del self.remaining[arrow_id]
            self._rebuild_occupied()

    def count_blockers(self, arrow: Arrow) -> int:
        """Count how many unique arrows block this arrow (within recursion depth 1)."""
        blockers = 0
        other_cells = self.occupied - arrow.cells
        x, y = arrow.head_x, arrow.head_y
        dx, dy = arrow.dx, arrow.dy
        seen_arrows: Set[int] = set()
        cx, cy = x + dx, y + dy
        while 0 <= cx < self.board.width and 0 <= cy < self.board.height:
            if (cx, cy) in other_cells:
                for a in self.remaining.values():
                    if a.arrow_id != arrow.arrow_id and (cx, cy) in a.cells:
                        if a.arrow_id not in seen_arrows:
                            seen_arrows.add(a.arrow_id)
                            blockers += 1
                        break
            cx += dx
            cy += dy
        return blockers


# ═══════════════════════════════════════════════════════════════════════════════
#  Viewport Model — Two-State Zoom
#
#  Derived from actual game screenshots:
#  - Zoom-in (example-zoom-in-max.jpeg): ~10×17 cells visible, clear arrows
#  - Zoom-out (example-zoom-out-max.jpeg): entire board visible, small arrows
# ═══════════════════════════════════════════════════════════════════════════════

def compute_zoom_in_regions(
    board_w: int, board_h: int, cam: CameraConfig
) -> List[ViewportRegion]:
    """
    Divide board into overlapping regions for zoom-in state.
    Uses zoom_in_width × zoom_in_height as the camera window.
    If board fits in zoom-in camera, return a single region.
    """
    cw, ch = cam.zoom_in_width, cam.zoom_in_height
    if board_w <= cw and board_h <= ch:
        return [ViewportRegion(0, 0, 0, 0, board_w, board_h)]

    regions = []
    step_x = max(1, cw - cam.viewport_overlap)
    step_y = max(1, ch - cam.viewport_overlap)

    ry = 0
    y0 = 0
    while y0 < board_h:
        rx = 0
        x0 = 0
        y1 = min(y0 + ch, board_h)
        while x0 < board_w:
            x1 = min(x0 + cw, board_w)
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


def compute_zoom_out_regions(
    board_w: int, board_h: int, cam: CameraConfig
) -> List[ViewportRegion]:
    """
    Compute viewport regions for zoom-out state.
    If board fits within zoom_out_width × zoom_out_height → single region.
    Otherwise, divide into overlapping regions (super-large boards still need panning).
    """
    cow, coh = cam.zoom_out_width, cam.zoom_out_height
    if board_w <= cow and board_h <= coh:
        return [ViewportRegion(0, 0, 0, 0, board_w, board_h)]

    regions = []
    step_x = max(1, cow - cam.viewport_overlap)
    step_y = max(1, coh - cam.viewport_overlap)

    ry = 0
    y0 = 0
    while y0 < board_h:
        rx = 0
        x0 = 0
        y1 = min(y0 + coh, board_h)
        while x0 < board_w:
            x1 = min(x0 + cow, board_w)
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


def arrows_in_region(
    arrows: Dict[int, Arrow], region: ViewportRegion
) -> List[Arrow]:
    """Return arrows whose head falls inside the given viewport region."""
    result = []
    for a in arrows.values():
        if region.x0 <= a.head_x < region.x1 and region.y0 <= a.head_y < region.y1:
            result.append(a)
    return result


def sort_arrows_by_scan(arrows: List[Arrow], direction: str) -> List[Arrow]:
    """Sort arrows by scan direction based on head position."""
    if direction == "rtl_btt":
        return sorted(arrows, key=lambda a: (-a.head_y, -a.head_x))
    # Default: ltr_ttb
    return sorted(arrows, key=lambda a: (a.head_y, a.head_x))


# ═══════════════════════════════════════════════════════════════════════════════
#  Static Level Metrics
# ═══════════════════════════════════════════════════════════════════════════════

def compute_level_metrics(board: Board) -> LevelMetrics:
    """Compute static difficulty metrics by running a greedy solve."""
    total_arrows = len(board.arrows)
    if total_arrows == 0:
        return LevelMetrics(board.level_id, 0, 0, 0, 0, 0, 0, 0, 0)

    avg_bend = sum(a.bend_count for a in board.arrows) / total_arrows
    max_bend = max(a.bend_count for a in board.arrows)
    avg_length = sum(a.length for a in board.arrows) / total_arrows
    total_cells = board.width * board.height
    occupied_cells = sum(a.length for a in board.arrows)
    density = occupied_cells / total_cells if total_cells > 0 else 0

    # Greedy solve to find iterations and min-solvable
    state = BoardState(board)
    min_solvable = total_arrows
    iterations = 0

    while state.remaining:
        solvable = state.get_solvable()
        if not solvable:
            break  # unsolvable (shouldn't happen with valid levels)
        min_solvable = min(min_solvable, len(solvable))
        iterations += 1
        for a in solvable:
            state.remove_arrow(a.arrow_id)

    # Difficulty score (weighted)
    w = DIFFICULTY_WEIGHTS
    # Normalize each metric to ~0-1 range (rough heuristics)
    norm_arrows = min(total_arrows / 50.0, 1.0)
    norm_bend = min(avg_bend / 10.0, 1.0)
    norm_min_solv = 1.0 - min(min_solvable / max(total_arrows, 1), 1.0)
    norm_depth = min(iterations / 20.0, 1.0)
    norm_density = min(density / 0.8, 1.0)
    norm_path = min(avg_length / 25.0, 1.0)

    score = (
        w["total_arrows"] * norm_arrows
        + w["avg_bend_count"] * norm_bend
        + w["min_solvable_per_iteration"] * norm_min_solv
        + w["max_depth"] * norm_depth
        + w["board_density"] * norm_density
        + w["path_complexity"] * norm_path
    )

    return LevelMetrics(
        level_id=board.level_id,
        total_arrows=total_arrows,
        avg_bend_count=round(avg_bend, 2),
        max_bend_count=max_bend,
        min_solvable_per_iteration=min_solvable,
        max_depth=iterations,
        board_density=round(density, 3),
        path_complexity=round(avg_length, 2),
        difficulty_score=round(score, 4),
    )


# ═══════════════════════════════════════════════════════════════════════════════
#  Player Simulator
# ═══════════════════════════════════════════════════════════════════════════════

class PlayerSimulator:
    """
    Simulates a single player playing a single level.
    Implements the full step-timeline formula with two-state zoom viewport,
    eye model, and cognitive models from discuss.md.

    Two-state zoom:
      - Zoom-in: player sees ~10×17 cells (region-based panning needed for large boards)
      - Zoom-out: player sees entire board (no panning, but arrows small → harder eval)
    """

    def __init__(
        self,
        board: Board,
        profile: PlayerProfile,
        sim_config: SimulationConfig,
        run_id: int = 0,
    ):
        self.board = board
        self.p = profile
        self.cfg = sim_config
        self.run_id = run_id
        self.rng = random.Random(sim_config.random_seed + run_id)

        # Build viewport regions for both zoom states
        self.zoom_in_regions = compute_zoom_in_regions(
            board.width, board.height, sim_config.camera
        )
        self.zoom_out_regions = compute_zoom_out_regions(
            board.width, board.height, sim_config.camera
        )

        # Does the board fit in zoom-in camera? (no panning needed even zoomed in)
        self.board_fits_zoomed_in = len(self.zoom_in_regions) == 1
        # Does the board fit in zoom-out camera? (super-large boards may not)
        self.board_fits_zoomed_out = len(self.zoom_out_regions) == 1

        # Zoom state: "in" or "out"
        self.zoom_state = profile.initial_zoom

        # State
        self.board_state = BoardState(board)
        self.total_time = 0.0
        self.step_index = 0
        self.frustration = 0.0
        self.steps: List[StepEvent] = []
        self.mistake_count = 0
        self.solve_iterations = 0
        self.current_region_idx = 0        # zoom-in region index
        self.current_zo_region_idx = 0      # zoom-out region index
        self.remembered_regions: Set[int] = set()

    # ── Zoom state helpers ────────────────────────────────────────────────
    def _is_zoomed_out(self) -> bool:
        return self.zoom_state == "out"

    def _switch_zoom(self, target: str):
        """Switch zoom state, adding transition time."""
        if self.zoom_state != target:
            self.zoom_state = target
            self.total_time += self.cfg.camera.zoom_transition_time * self._fatigue()

    # ── Zoom-dependent multipliers ────────────────────────────────────────
    def _zoom_eval_multiplier(self) -> float:
        """Eval time multiplier based on zoom state."""
        if self._is_zoomed_out() and not self.board_fits_zoomed_in:
            return self.cfg.camera.zoom_out_eval_multiplier
        return 1.0

    def _zoom_head_find_multiplier(self) -> float:
        """Head-finding multiplier (small arrows harder to parse)."""
        if self._is_zoomed_out() and not self.board_fits_zoomed_in:
            return self.cfg.camera.zoom_out_head_find_multiplier
        return 1.0

    def _zoom_miss_bonus(self) -> float:
        """Extra miss probability when zoomed out."""
        if self._is_zoomed_out() and not self.board_fits_zoomed_in:
            return self.cfg.camera.zoom_out_miss_bonus
        return 0.0

    def _zoom_scan_speed(self) -> float:
        """Scan speed factor (< 1.0 means faster per-arrow scan when zoomed out)."""
        if self._is_zoomed_out() and not self.board_fits_zoomed_in:
            return self.cfg.camera.zoom_out_scan_speed
        return 1.0

    # ── Fatigue multiplier ────────────────────────────────────────────────
    def _fatigue(self) -> float:
        return self.p.fatigue_factor ** self.step_index

    # ── FOV shifts needed within a viewport region ────────────────────────
    def _fov_shifts(self, region: ViewportRegion) -> int:
        rw = region.x1 - region.x0
        rh = region.y1 - region.y0
        fw = self.cfg.eye.effective_fov_width
        fh = self.cfg.eye.effective_fov_height
        return max(1, math.ceil(rw / fw) * math.ceil(rh / fh))

    # ── Compute time to scan arrows in a viewport region ──────────────────
    def _scan_region_time(self, n_arrows: int, region: ViewportRegion,
                          is_rescan: bool = False) -> float:
        """Time to visually scan all arrows in a viewport region."""
        fov_shifts = self._fov_shifts(region)
        saccade_total = fov_shifts * self.cfg.eye.saccade_time
        scan_total = n_arrows * self.p.scan_time_per_arrow * self._zoom_scan_speed()
        if is_rescan:
            scan_total *= self.p.rescan_time_ratio
        return saccade_total + scan_total

    # ── Compute time to evaluate one arrow ────────────────────────────────
    def _eval_arrow_time(self, arrow: Arrow, region: ViewportRegion) -> float:
        """Time to find head, trace exit path, and make decision."""
        head_time = (
            self.p.head_find_time_base * self._zoom_head_find_multiplier()
            + arrow.length * self.cfg.arrow_eval.head_find_time_per_cell
        )
        trace_dist, is_blocked = self.board_state.trace_distance(arrow)
        trace_time = trace_dist * self.cfg.arrow_eval.trace_time_per_cell

        # Does trace exceed current viewport?
        rw = region.x1 - region.x0
        rh = region.y1 - region.y0
        max_visible = max(rw, rh)
        trace_pan = 0.0
        if trace_dist > max_visible:
            trace_pan = self.cfg.arrow_eval.trace_pan_time

        block_time = self.cfg.arrow_eval.block_recognition_time if is_blocked else 0

        decision_time = (
            self.p.decision_time_base
            + arrow.bend_count * self.p.decision_time_per_bend
        )

        # Recheck penalty
        recheck_extra = 0.0
        if self.rng.random() < self.p.recheck_probability:
            recheck_extra = head_time * 0.5

        base = head_time + trace_time + trace_pan + block_time + decision_time + recheck_extra
        return base * self._zoom_eval_multiplier()

    # ── Effective miss probability ────────────────────────────────────────
    def _effective_miss_prob(self) -> float:
        return min(0.95, self.p.miss_probability + self._zoom_miss_bonus())

    # ── Tap action ────────────────────────────────────────────────────────
    def _do_tap(self, arrow: Arrow, is_solvable: bool,
                region: ViewportRegion) -> StepEvent:
        """Execute a tap on an arrow. Returns the step event."""
        eval_time = self._eval_arrow_time(arrow, region)
        tap_time = self.p.tap_time

        is_mistake = False
        mistake_extra = 0.0

        if is_solvable:
            self.board_state.remove_arrow(arrow.arrow_id)
            self.frustration = max(0, self.frustration - self.p.frustration_decay_after_solve)
        else:
            is_mistake = True
            mistake_extra = self.p.mistake_penalty
            self.mistake_count += 1

        fatigue_mult = self._fatigue()
        step_time = (eval_time + tap_time + mistake_extra) * fatigue_mult

        zoom_tag = "ZO" if self._is_zoomed_out() else "ZI"
        event = StepEvent(
            step_index=self.step_index,
            arrow_id=arrow.arrow_id,
            time_ms=round(step_time, 1),
            is_mistake=is_mistake,
            phase_detail=(
                f"[{zoom_tag}] eval={eval_time:.0f}ms tap={tap_time:.0f}ms "
                f"{'MISS ' if is_mistake else ''}fatigue=x{fatigue_mult:.3f}"
            ),
        )
        self.total_time += step_time
        self.step_index += 1
        self.steps.append(event)
        return event

    # ── Recursive unblock attempt ─────────────────────────────────────────
    def _try_recursive_unblock(self, depth: int = 0) -> bool:
        """
        Attempt to find and solve a blocking chain.
        Returns True if at least one arrow was solved.
        """
        if depth >= self.p.max_recursion_depth:
            return False

        candidates = []
        for a in self.board_state.remaining.values():
            n_blockers = self.board_state.count_blockers(a)
            if n_blockers > 0:
                candidates.append((n_blockers, a))

        if not candidates:
            return False

        candidates.sort(key=lambda x: x[0])
        target = candidates[0][1]

        think_time = self.p.recursion_think_time * self._fatigue()
        self.total_time += think_time

        blocker = self.board_state.find_blocker(target)
        if blocker is None:
            return False

        if self.board_state.is_solvable(blocker):
            # Use current active region for eval
            region = self._current_active_region()
            self._do_tap(blocker, is_solvable=True, region=region)
            return True
        else:
            return self._try_recursive_unblock(depth + 1)

    def _current_active_region(self) -> ViewportRegion:
        """Return the current viewport region based on zoom state."""
        if self._is_zoomed_out():
            return self.zoom_out_regions[min(self.current_zo_region_idx, len(self.zoom_out_regions) - 1)]
        return self.zoom_in_regions[self.current_region_idx]

    # ── Scan a single region, find and tap solvable arrows ────────────────
    def _scan_and_tap_region(self, region: ViewportRegion) -> bool:
        """
        Scan a region for solvable arrows and batch-tap them.
        Returns True if any arrow was tapped.
        """
        visible = arrows_in_region(self.board_state.remaining, region)
        if not visible:
            return False

        visible = sort_arrows_by_scan(visible, self.p.scan_direction)

        # Scan time
        scan_time = self._scan_region_time(len(visible), region)
        self.total_time += scan_time * self._fatigue()

        # Find solvable
        solvable_here = [a for a in visible if self.board_state.is_solvable(a)]

        # Miss probability (zoom-adjusted)
        miss_prob = self._effective_miss_prob()
        actually_found = [a for a in solvable_here if self.rng.random() >= miss_prob]

        if not actually_found:
            # Mistake: might tap non-solvable
            if visible and self.rng.random() < self.p.mistake_rate:
                non_solvable = [a for a in visible if not self.board_state.is_solvable(a)]
                if non_solvable:
                    victim = self.rng.choice(non_solvable)
                    self._do_tap(victim, is_solvable=False, region=region)
            return False

        # ── Batch tap ──────────────────────────────────────────────
        found_any = False
        batch_count = 0
        while actually_found and batch_count < self.p.max_batch_before_pan:
            target = actually_found.pop(0)
            if target.arrow_id not in self.board_state.remaining:
                continue
            if not self.board_state.is_solvable(target):
                continue

            # When zoomed out, player might zoom in before tapping
            if self._is_zoomed_out() and not self.board_fits_zoomed_in:
                if self.rng.random() < self.p.zoom_in_to_tap_prob:
                    self._switch_zoom("in")
                    # Find the zoom-in region containing this arrow's head
                    for ri, r in enumerate(self.zoom_in_regions):
                        if r.x0 <= target.head_x < r.x1 and r.y0 <= target.head_y < r.y1:
                            self.current_region_idx = ri
                            region = r
                            break

            self._do_tap(target, is_solvable=True, region=region)
            found_any = True
            batch_count += 1
            self.solve_iterations += 1

            # Quick rescan
            if batch_count < self.p.max_batch_before_pan:
                new_visible = arrows_in_region(self.board_state.remaining, region)
                rescan_time = self._scan_region_time(
                    len(new_visible), region, is_rescan=True
                )
                self.total_time += rescan_time * self._fatigue()

                new_solvable = [
                    a for a in new_visible
                    if self.board_state.is_solvable(a)
                ]
                miss_prob = self._effective_miss_prob()
                actually_found = [
                    a for a in new_solvable
                    if self.rng.random() >= miss_prob
                ]

        return found_any

    # ── Main simulation loop ──────────────────────────────────────────────
    def simulate(self) -> SimulationResult:
        """
        Run the full simulation with two-state zoom model.

        Flow:
        1. Initial board scan (zoom-out overview or zoom-in first region)
        2. Main loop:
           a. If zoomed out → scan entire board as one region
           b. If zoomed in → iterate through zoom-in regions with panning
           c. If nothing found → consider switching zoom state
           d. If still stuck → recursive unblock / memory / fallback
        """

        # Initial board scan
        self.total_time += self.p.board_scan_time

        while self.board_state.remaining:
            found_any = False

            if self._is_zoomed_out() or self.board_fits_zoomed_in:
                # ── ZOOM-OUT STATE (or small board) ───────────────────
                if self.board_fits_zoomed_in:
                    # Small board: single region, no zoom distinction
                    found_any = self._scan_and_tap_region(self.zoom_in_regions[0])
                elif self.board_fits_zoomed_out:
                    # Board fits in zoom-out viewport: single region scan
                    found_any = self._scan_and_tap_region(self.zoom_out_regions[0])
                else:
                    # Super-large board: even zoom-out needs panning
                    zo_order = list(range(len(self.zoom_out_regions)))
                    if self.p.scan_direction == "rtl_btt":
                        zo_order.reverse()
                    for zo_idx in zo_order:
                        self.current_zo_region_idx = zo_idx
                        if zo_idx != zo_order[0]:
                            self.total_time += self.cfg.camera.pan_time * self._fatigue()
                        if self._scan_and_tap_region(self.zoom_out_regions[zo_idx]):
                            found_any = True

                if not found_any and not self.board_fits_zoomed_in:
                    # Nothing found zoomed out → zoom in for closer look
                    self._switch_zoom("in")

            else:
                # ── ZOOM-IN STATE ─────────────────────────────────────
                region_order = list(range(len(self.zoom_in_regions)))
                if self.p.scan_direction == "rtl_btt":
                    region_order.reverse()

                for ridx in region_order:
                    self.current_region_idx = ridx
                    region = self.zoom_in_regions[ridx]

                    # Pan time between regions
                    if ridx != region_order[0]:
                        self.total_time += self.cfg.camera.pan_time * self._fatigue()

                    region_found = self._scan_and_tap_region(region)
                    if region_found:
                        found_any = True
                        self.remembered_regions.add(ridx)

                # After full scan of all regions, consider zoom out for survey
                if not found_any and self.rng.random() < self.p.zoom_out_survey_prob:
                    self._switch_zoom("out")
                    continue  # retry with zoom-out view

            # ── No solvable found → recovery strategies ───────────────
            if not found_any:
                self.frustration += self.p.frustration_buildup_rate

                # Try recursive unblock
                if (self.frustration < 1.0
                        and self.rng.random() < self.p.recursive_solve_probability):
                    solved = self._try_recursive_unblock()
                    if solved:
                        continue

                # Memory: try a remembered region (zoom in first)
                if (self.remembered_regions
                        and self.rng.random() < self.p.memory_probability):
                    if self._is_zoomed_out():
                        self._switch_zoom("in")
                    mem_region = self.rng.choice(list(self.remembered_regions))
                    self.current_region_idx = mem_region
                    self.total_time += self.cfg.camera.pan_time * self._fatigue()
                    continue

                # Fallback: zoom-out survey if not already, or random pan
                if not self._is_zoomed_out() and not self.board_fits_zoomed_in:
                    self._switch_zoom("out")
                    self.total_time += self.p.board_scan_time * self._fatigue()
                else:
                    # Already zoomed out or small board → random pan
                    self.total_time += self.cfg.camera.pan_time * 2 * self._fatigue()

                # Safety: force-solve one to avoid infinite loop
                solvable_global = self.board_state.get_solvable()
                if solvable_global:
                    extra_search_time = (
                        self.p.board_scan_time * 3 * self._fatigue()
                    )
                    self.total_time += extra_search_time
                    target = self.rng.choice(solvable_global)
                    region = self._current_active_region()
                    self._do_tap(target, is_solvable=True, region=region)
                else:
                    break  # truly stuck (invalid level)

        return SimulationResult(
            level_id=self.board.level_id,
            player_type=self.p.name,
            run_id=self.run_id,
            total_time_ms=round(self.total_time, 1),
            total_taps=len(self.steps),
            mistake_count=self.mistake_count,
            steps=self.steps,
            solve_iterations=self.solve_iterations,
        )


# ═══════════════════════════════════════════════════════════════════════════════
#  Batch Runner
# ═══════════════════════════════════════════════════════════════════════════════

def run_simulation_batch(
    board: Board,
    profile: PlayerProfile,
    sim_config: SimulationConfig,
) -> List[SimulationResult]:
    """Run N simulation runs for one level + one player profile."""
    results = []
    for run_id in range(sim_config.runs_per_level):
        sim = PlayerSimulator(board, profile, sim_config, run_id=run_id)
        results.append(sim.simulate())
    return results


def compute_percentiles(
    values: List[float], percentiles: List[int]
) -> Dict[int, float]:
    """Compute given percentiles from a list of values."""
    if not values:
        return {p: 0.0 for p in percentiles}
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    result = {}
    for p in percentiles:
        idx = (p / 100.0) * (n - 1)
        lo = int(math.floor(idx))
        hi = int(math.ceil(idx))
        if lo == hi:
            result[p] = sorted_vals[lo]
        else:
            frac = idx - lo
            result[p] = sorted_vals[lo] * (1 - frac) + sorted_vals[hi] * frac
    return result
