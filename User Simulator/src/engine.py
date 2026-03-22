"""
Core simulation engine: level loading, board state, static metrics.

Data models (Arrow, Board, BoardState, LevelMetrics) and pure functions
(load_level, compute_level_metrics). No simulation logic — that lives in
game_adapter.py (Layer 2) and user_model.py (Layer 1).
"""

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from config import (
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
        # Reverse index: cell → count of arrows using it (for O(K) removal)
        self._cell_count: Dict[Tuple[int, int], int] = {}
        self.occupied: Set[Tuple[int, int]] = set()
        for a in board.arrows:
            for cell in a.cells:
                self._cell_count[cell] = self._cell_count.get(cell, 0) + 1
                self.occupied.add(cell)

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
        """Remove an arrow from the board. O(K) via cell_count reverse index."""
        if arrow_id in self.remaining:
            arrow = self.remaining.pop(arrow_id)
            for cell in arrow.cells:
                self._cell_count[cell] -= 1
                if self._cell_count[cell] == 0:
                    self.occupied.discard(cell)
                    del self._cell_count[cell]

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
#  NOTE: Legacy PlayerSimulator, run_simulation_batch, compute_percentiles
#  were removed (2026-03-22). They referenced stale config fields
#  (sim_config.camera, sim_config.arrow_eval, sim_config.runs_per_level)
#  that no longer exist after the 3-layer refactor.
#  Active simulation logic lives in game_adapter.py (Layer 2).
# ═══════════════════════════════════════════════════════════════════════════════
