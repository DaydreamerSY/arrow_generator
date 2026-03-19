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
    CameraConfig,
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
#  Viewport Model
# ═══════════════════════════════════════════════════════════════════════════════

def compute_viewport_regions(
    board_w: int, board_h: int, cam: CameraConfig
) -> List[ViewportRegion]:
    """
    Divide board into overlapping viewport regions.
    If board fits in camera, return a single region.
    """
    if board_w <= cam.camera_width and board_h <= cam.camera_height:
        return [ViewportRegion(0, 0, 0, 0, board_w, board_h)]

    regions = []
    step_x = max(1, cam.camera_width - cam.viewport_overlap)
    step_y = max(1, cam.camera_height - cam.viewport_overlap)

    ry = 0
    y0 = 0
    while y0 < board_h:
        rx = 0
        x0 = 0
        y1 = min(y0 + cam.camera_height, board_h)
        while x0 < board_w:
            x1 = min(x0 + cam.camera_width, board_w)
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
    Implements the full step-timeline formula with viewport, eye, and
    cognitive models from discuss.md.
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

        # Build viewport regions
        self.regions = compute_viewport_regions(
            board.width, board.height, sim_config.camera
        )
        self.single_viewport = len(self.regions) == 1

        # State
        self.board_state = BoardState(board)
        self.total_time = 0.0
        self.step_index = 0
        self.frustration = 0.0
        self.steps: List[StepEvent] = []
        self.mistake_count = 0
        self.solve_iterations = 0
        self.current_region_idx = 0
        self.remembered_regions: Set[int] = set()

    # ── Fatigue multiplier ────────────────────────────────────────────────
    def _fatigue(self) -> float:
        return self.p.fatigue_factor ** self.step_index

    # ── FOV shifts needed within current viewport ─────────────────────────
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
        scan_total = n_arrows * self.p.scan_time_per_arrow
        if is_rescan:
            scan_total *= self.p.rescan_time_ratio
        return saccade_total + scan_total

    # ── Compute time to evaluate one arrow ────────────────────────────────
    def _eval_arrow_time(self, arrow: Arrow) -> float:
        """Time to find head, trace exit path, and make decision."""
        head_time = (
            self.p.head_find_time_base
            + arrow.length * self.cfg.arrow_eval.head_find_time_per_cell
        )
        trace_dist, is_blocked = self.board_state.trace_distance(arrow)
        trace_time = trace_dist * self.cfg.arrow_eval.trace_time_per_cell

        # Does trace exceed current viewport?
        region = self.regions[self.current_region_idx]
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
            recheck_extra = head_time * 0.5  # re-scan costs half

        return head_time + trace_time + trace_pan + block_time + decision_time + recheck_extra

    # ── Tap action ────────────────────────────────────────────────────────
    def _do_tap(self, arrow: Arrow, is_solvable: bool) -> StepEvent:
        """Execute a tap on an arrow. Returns the step event."""
        eval_time = self._eval_arrow_time(arrow)
        tap_time = self.p.tap_time

        is_mistake = False
        mistake_extra = 0.0

        if is_solvable:
            # Occasionally player taps wrong even on solvable
            # (modeled as fumble, very rare)
            self.board_state.remove_arrow(arrow.arrow_id)
            self.frustration = max(0, self.frustration - self.p.frustration_decay_after_solve)
        else:
            # Mistake tap on non-solvable arrow
            is_mistake = True
            mistake_extra = self.p.mistake_penalty
            self.mistake_count += 1

        fatigue_mult = self._fatigue()
        step_time = (eval_time + tap_time + mistake_extra) * fatigue_mult

        event = StepEvent(
            step_index=self.step_index,
            arrow_id=arrow.arrow_id,
            time_ms=round(step_time, 1),
            is_mistake=is_mistake,
            phase_detail=(
                f"eval={eval_time:.0f}ms tap={tap_time:.0f}ms "
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

        # Find arrow with fewest blockers ("nearly solvable")
        candidates = []
        for a in self.board_state.remaining.values():
            n_blockers = self.board_state.count_blockers(a)
            if n_blockers > 0:
                candidates.append((n_blockers, a))

        if not candidates:
            return False

        candidates.sort(key=lambda x: x[0])
        target = candidates[0][1]

        # Think time for recursion
        think_time = self.p.recursion_think_time * self._fatigue()
        self.total_time += think_time

        # Find the blocker arrow
        blocker = self.board_state.find_blocker(target)
        if blocker is None:
            return False

        # Is the blocker solvable?
        if self.board_state.is_solvable(blocker):
            self._do_tap(blocker, is_solvable=True)
            return True
        else:
            # Recurse deeper
            return self._try_recursive_unblock(depth + 1)

    # ── Main simulation loop ──────────────────────────────────────────────
    def simulate(self) -> SimulationResult:
        """Run the full simulation. Returns result with timing breakdown."""

        # Initial board scan
        self.total_time += self.p.board_scan_time

        while self.board_state.remaining:
            found_any = False

            # Iterate through viewport regions
            region_order = list(range(len(self.regions)))
            if self.p.scan_direction == "rtl_btt":
                region_order.reverse()

            for ridx in region_order:
                self.current_region_idx = ridx
                region = self.regions[ridx]

                # Pan time (skip for first region or single viewport)
                if ridx != region_order[0] and not self.single_viewport:
                    # Check if player zooms out instead of panning
                    if self.rng.random() < self.p.zoom_out_probability:
                        self.total_time += self.cfg.camera.zoom_out_time
                    else:
                        self.total_time += self.cfg.camera.pan_time

                # Get arrows visible in this region
                visible = arrows_in_region(self.board_state.remaining, region)
                if not visible:
                    continue

                # Sort by scan direction
                visible = sort_arrows_by_scan(visible, self.p.scan_direction)

                # Scan time for this region
                scan_time = self._scan_region_time(len(visible), region)
                self.total_time += scan_time * self._fatigue()

                # Find solvable arrows in this region
                solvable_here = [a for a in visible if self.board_state.is_solvable(a)]

                # Miss probability: player might skip some solvable arrows
                actually_found = []
                for a in solvable_here:
                    if self.rng.random() >= self.p.miss_probability:
                        actually_found.append(a)

                if not actually_found:
                    # Mistake: might tap a non-solvable
                    if visible and self.rng.random() < self.p.mistake_rate:
                        non_solvable = [a for a in visible if not self.board_state.is_solvable(a)]
                        if non_solvable:
                            victim = self.rng.choice(non_solvable)
                            self._do_tap(victim, is_solvable=False)
                    continue

                # ── Batch tap within this region ──────────────────────
                batch_count = 0
                while actually_found and batch_count < self.p.max_batch_before_pan:
                    target = actually_found.pop(0)
                    if target.arrow_id not in self.board_state.remaining:
                        continue

                    # Double-check still solvable (board changed)
                    if not self.board_state.is_solvable(target):
                        continue

                    self._do_tap(target, is_solvable=True)
                    found_any = True
                    batch_count += 1
                    self.solve_iterations += 1

                    # Quick rescan for newly solvable arrows
                    if batch_count < self.p.max_batch_before_pan:
                        new_visible = arrows_in_region(
                            self.board_state.remaining, region
                        )
                        rescan_time = self._scan_region_time(
                            len(new_visible), region, is_rescan=True
                        )
                        self.total_time += rescan_time * self._fatigue()

                        new_solvable = [
                            a for a in new_visible
                            if self.board_state.is_solvable(a)
                        ]
                        actually_found = [
                            a for a in new_solvable
                            if self.rng.random() >= self.p.miss_probability
                        ]

                if found_any:
                    self.remembered_regions.add(ridx)

            # If no solvable found in any region → try recursive unblock
            if not found_any:
                self.frustration += self.p.frustration_buildup_rate

                if (self.frustration < 1.0
                        and self.rng.random() < self.p.recursive_solve_probability):
                    solved = self._try_recursive_unblock()
                    if solved:
                        continue

                # Memory: try a remembered region
                if (self.remembered_regions
                        and self.rng.random() < self.p.memory_probability):
                    mem_region = self.rng.choice(list(self.remembered_regions))
                    self.current_region_idx = mem_region
                    self.total_time += self.cfg.camera.pan_time * self._fatigue()
                    # Will retry in next outer loop iteration
                    continue

                # Fallback: random pan + re-scan
                self.total_time += self.cfg.camera.pan_time * 2 * self._fatigue()

                # Safety: if truly stuck (all arrows blocked, no recursion works)
                # force-solve one arrow to avoid infinite loop
                solvable_global = self.board_state.get_solvable()
                if solvable_global:
                    # Player eventually finds one
                    extra_search_time = (
                        self.p.board_scan_time * 3 * self._fatigue()
                    )
                    self.total_time += extra_search_time
                    target = self.rng.choice(solvable_global)
                    self._do_tap(target, is_solvable=True)
                else:
                    # Level truly stuck (invalid level) — break to prevent infinite
                    break

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
