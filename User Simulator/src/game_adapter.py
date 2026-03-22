"""
Layer 2: GameAdapter — Arrow Escape specific game logic.

Wraps the board solver and arrow evaluation from engine.py.
Provides a standardized interface that UserModel interacts with.

Features:
  - Board-state-aware scan cost (density penalty + clearing speed bonus)
  - Cascade awareness (newly unlocked arrows affect frustration/momentum)
  - Level overhead (loading, celebration)
  - Booster system (Hint, Scissors, Magic Wand)
  - Combo interface (designed, not active for Arrow Escape)

To support a different game:
  - Create a new adapter implementing the same interface
  - Keep UserModel and CohortSimulator unchanged
"""

import math
import random
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

from config import BoosterConfig, ComboConfig, PlayerProfile, SimulationConfig
from engine import (
    Arrow,
    Board,
    BoardState,
    LevelMetrics,
    compute_level_metrics,
    load_level,
)
from user_model import AttemptResult, UserModel, ViewportModel, ViewportRegion


# ═══════════════════════════════════════════════════════════════════════════════
#  Booster System
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class BoosterInventory:
    """Tracks booster usage within one attempt.
    No defaults — must call reset(bcfg) before use to sync with BoosterConfig."""
    hints_remaining: int = 0
    scissors_remaining: int = 0
    wands_remaining: int = 0

    def reset(self, bcfg: BoosterConfig):
        self.hints_remaining = bcfg.hint_per_attempt
        self.scissors_remaining = bcfg.scissors_per_attempt
        self.wands_remaining = bcfg.wand_per_attempt


class BoosterModel:
    """
    Decides when and which booster to use.

    Decision depends on:
      - Player frustration level (higher = more likely)
      - Profile booster_willingness
      - Available inventory
      - Board state (how stuck the player is)
    """

    def __init__(self, board_state: BoardState, user: UserModel,
                 cfg: SimulationConfig, rng: random.Random):
        self.board_state = board_state
        self.user = user
        self.cfg = cfg
        self.bcfg = cfg.booster
        self.rng = rng
        self.inventory = BoosterInventory()

    def reset(self):
        self.inventory.reset(self.bcfg)

    def try_use_booster(self) -> Optional[str]:
        """
        Check if player should use a booster now.
        Returns booster name ("hint", "scissors", "wand") or None.

        Called when player is stuck (no solvable found in scan).
        """
        if not self.bcfg.enabled:
            return None

        frust = self.user.frustration
        willingness = self.user.base_profile.booster_willingness

        # Check each booster in priority order (cheapest first)
        # Hint: easiest to use, lowest threshold
        if (self.inventory.hints_remaining > 0
                and frust >= self.bcfg.hint_frustration_threshold
                and self.rng.random() < self.bcfg.hint_use_prob * willingness):
            return "hint"

        # Scissors: player picks an arrow to remove
        if (self.inventory.scissors_remaining > 0
                and frust >= self.bcfg.scissors_frustration_threshold
                and self.rng.random() < self.bcfg.scissors_use_prob * willingness):
            return "scissors"

        # Magic Wand: nuclear option, removes up to 3
        if (self.inventory.wands_remaining > 0
                and frust >= self.bcfg.wand_frustration_threshold
                and self.rng.random() < self.bcfg.wand_use_prob * willingness):
            return "wand"

        return None

    def apply_hint(self) -> Optional[int]:
        """Use Hint: remove 1 solvable arrow. Returns arrow_id or None."""
        if self.inventory.hints_remaining <= 0:
            return None
        solvable = self.board_state.get_solvable()
        if not solvable:
            return None
        self.inventory.hints_remaining -= 1
        target = self.rng.choice(solvable)
        self.board_state.remove_arrow(target.arrow_id)
        return target.arrow_id

    def apply_scissors(self) -> Optional[int]:
        """Use Scissors: remove 1 player-selected arrow (any). Returns arrow_id."""
        if self.inventory.scissors_remaining <= 0:
            return None
        if not self.board_state.remaining:
            return None
        self.inventory.scissors_remaining -= 1
        # Player picks the arrow that BLOCKS the most other arrows (biggest blocker).
        # Precompute blocking_map in O(N×W), then pick max — avoids O(N²×W).
        blocking_count = {}  # arrow_id → how many arrows it blocks
        for other in self.board_state.remaining.values():
            blocker = self.board_state.find_blocker(other)
            if blocker:
                blocking_count[blocker.arrow_id] = blocking_count.get(blocker.arrow_id, 0) + 1
        best = None
        best_score = -1
        for a in self.board_state.remaining.values():
            score = blocking_count.get(a.arrow_id, 0)
            if score > best_score:
                best_score = score
                best = a
        if best is None:
            # Fallback: pick random
            best = self.rng.choice(list(self.board_state.remaining.values()))
        self.board_state.remove_arrow(best.arrow_id)
        return best.arrow_id

    def apply_wand(self) -> List[int]:
        """
        Use Magic Wand: remove up to 3 arrows recursively.
        Removes solvable first, then recursively finds new solvable.
        Returns list of removed arrow_ids.
        """
        if self.inventory.wands_remaining <= 0:
            return []
        self.inventory.wands_remaining -= 1
        removed = []
        for _ in range(3):
            solvable = self.board_state.get_solvable()
            if not solvable:
                # No solvable left — force remove any
                if self.board_state.remaining:
                    victim = self.rng.choice(list(self.board_state.remaining.values()))
                    self.board_state.remove_arrow(victim.arrow_id)
                    removed.append(victim.arrow_id)
                break
            target = self.rng.choice(solvable)
            self.board_state.remove_arrow(target.arrow_id)
            removed.append(target.arrow_id)
        return removed


# ═══════════════════════════════════════════════════════════════════════════════
#  Arrow Escape Adapter
# ═══════════════════════════════════════════════════════════════════════════════

class ArrowEscapeAdapter:
    """
    Game-specific logic for Arrow Escape puzzle.

    Manages board state, arrow evaluation, tap execution,
    boosters, and within-level dynamics.
    """

    def __init__(
        self,
        board: Board,
        user: UserModel,
        sim_config: SimulationConfig,
    ):
        self.board = board
        self.user = user
        self.cfg = sim_config
        self.p = user.base_profile
        self.rng = user.rng

        # Board state (reset per attempt)
        self.board_state: Optional[BoardState] = None
        self.total_arrows = len(board.arrows)

        # Viewport
        self.viewport = ViewportModel(
            board.width, board.height, sim_config.viewport
        )

        # Booster model
        self.booster: Optional[BoosterModel] = None

        # Static metrics (computed once)
        self._metrics: Optional[LevelMetrics] = None

        # Cascade tracking
        self._prev_solvable_count: int = 0

    @property
    def metrics(self) -> LevelMetrics:
        if self._metrics is None:
            self._metrics = compute_level_metrics(self.board)
        return self._metrics

    # ── Board clearing ratio ───────────────────────────────────────────────

    def _clearing_ratio(self) -> float:
        """How much of the board has been cleared (0.0 = full, 1.0 = empty)."""
        if self.total_arrows == 0:
            return 1.0
        return 1.0 - len(self.board_state.remaining) / self.total_arrows

    def _current_density(self, region: ViewportRegion) -> float:
        """Arrow density within current viewport region."""
        area = max(1, (region.x1 - region.x0) * (region.y1 - region.y0))
        n_arrows = sum(
            1 for a in self.board_state.remaining.values()
            if region.x0 <= a.head_x < region.x1 and region.y0 <= a.head_y < region.y1
        )
        return n_arrows / area

    # ── Reset for new attempt ──────────────────────────────────────────────

    def reset(self, attempt_num: int):
        """Reset board state for a new attempt."""
        self.board_state = BoardState(self.board)
        self.viewport.reset(self.p.initial_zoom)
        self._prev_solvable_count = len(self.board_state.get_solvable())

        # Reset booster inventory
        self.booster = BoosterModel(self.board_state, self.user, self.cfg, self.rng)
        self.booster.reset()

    # ── Helpers ────────────────────────────────────────────────────────────

    def _arrows_in_region(self, region: ViewportRegion) -> List[Arrow]:
        result = []
        for a in self.board_state.remaining.values():
            if region.x0 <= a.head_x < region.x1 and region.y0 <= a.head_y < region.y1:
                result.append(a)
        return result

    def _sort_arrows(self, arrows: List[Arrow]) -> List[Arrow]:
        if self.p.scan_direction == "rtl_btt":
            return sorted(arrows, key=lambda a: (-a.head_y, -a.head_x))
        return sorted(arrows, key=lambda a: (a.head_y, a.head_x))

    def _fov_shifts(self, region: ViewportRegion) -> int:
        rw = region.x1 - region.x0
        rh = region.y1 - region.y0
        fw = self.cfg.eye.effective_fov_width
        fh = self.cfg.eye.effective_fov_height
        return max(1, math.ceil(rw / fw) * math.ceil(rh / fh))

    # ── Board-state-aware scan cost ────────────────────────────────────────

    def _scan_region_time(
        self, n_arrows: int, region: ViewportRegion, is_rescan: bool = False
    ) -> float:
        """
        Time to visually scan arrows in a region.

        Board-state-aware:
          - Dense regions: clutter penalty (more arrows = harder to distinguish)
          - Cleared boards: speed bonus (fewer arrows = easier to spot remaining)
        """
        fov_shifts = self._fov_shifts(region)
        saccade_total = fov_shifts * self.cfg.eye.saccade_time

        # Base scan per arrow
        base_scan = n_arrows * self.user.effective_scan_time * self.viewport.zoom_scan_speed()

        # Density clutter: more arrows visible = harder to parse each one
        density = self._current_density(region)
        clutter_mult = 1.0 + density * self.cfg.density_clutter_factor

        # Clearing bonus: as board empties, remaining arrows are easier to spot
        clearing = self._clearing_ratio()
        clearing_mult = 1.0 - clearing * self.cfg.clearing_speed_bonus

        scan_total = base_scan * clutter_mult * max(0.5, clearing_mult)

        if is_rescan:
            scan_total *= self.p.rescan_time_ratio

        return saccade_total + scan_total

    # ── Evaluate a single arrow ────────────────────────────────────────────

    def _eval_arrow_time(self, arrow: Arrow, region: ViewportRegion) -> float:
        head_time = (
            self.p.head_find_time_base * self.viewport.zoom_head_find_multiplier()
            + arrow.length * self.cfg.arrow_head_find_time_per_cell
        )
        trace_dist, is_blocked = self.board_state.trace_distance(arrow)
        trace_time = trace_dist * self.cfg.arrow_trace_time_per_cell

        rw = region.x1 - region.x0
        rh = region.y1 - region.y0
        trace_pan = 0.0
        if trace_dist > max(rw, rh):
            trace_pan = self.cfg.arrow_trace_pan_time

        block_time = self.cfg.arrow_block_recognition_time if is_blocked else 0

        decision_time = (
            self.user.effective_decision_time
            + arrow.bend_count * self.p.decision_time_per_bend
        )

        recheck_extra = 0.0
        if self.rng.random() < self.p.recheck_probability:
            recheck_extra = head_time * 0.5

        base = head_time + trace_time + trace_pan + block_time + decision_time + recheck_extra
        return base * self.viewport.zoom_eval_multiplier()

    def _effective_miss_prob(self) -> float:
        return min(0.95, self.user.effective_miss_prob + self.viewport.zoom_miss_bonus())

    # ── Execute a tap ──────────────────────────────────────────────────────

    def _do_tap(self, arrow: Arrow, is_solvable: bool, region: ViewportRegion):
        """Execute a tap. Includes cascade awareness."""
        eval_time = self._eval_arrow_time(arrow, region)
        tap_time = self.p.tap_time
        mistake_extra = 0.0

        # Snapshot solvable count before removal (for cascade detection)
        solvable_before = len(self.board_state.get_solvable())

        if is_solvable:
            self.board_state.remove_arrow(arrow.arrow_id)
            self.user.arrows_cleared += 1
            self.user.frustration = max(
                0, self.user.frustration - self.p.frustration_decay_after_solve
            )

            # ── Cascade awareness ──────────────────────────────
            solvable_after = len(self.board_state.get_solvable())
            newly_unlocked = solvable_after - solvable_before + 1  # +1 because we removed one

            if newly_unlocked >= 2:
                # Cascade! Multiple arrows became solvable → positive momentum
                self.user.frustration = max(
                    0, self.user.frustration - 0.03 * newly_unlocked
                )
            elif newly_unlocked <= 0 and self.board_state.remaining:
                # Dead end: cleared arrow but nothing new opened
                self.user.frustration += 0.005

        else:
            mistake_extra = self.p.mistake_penalty
            self.user.mistake_count += 1

        fatigue_mult = self.user.fatigue()
        step_time = (eval_time + tap_time + mistake_extra) * fatigue_mult

        self.user.total_time += step_time
        self.user.step_index += 1
        self.user.tap_count += 1

    # ── Booster usage ──────────────────────────────────────────────────────

    def _try_booster(self) -> bool:
        """
        Try to use a booster when stuck.
        Returns True if a booster was used (arrows removed).
        """
        if self.booster is None:
            return False

        choice = self.booster.try_use_booster()
        if choice is None:
            return False

        if choice == "hint":
            self.user.total_time += self.cfg.booster.hint_activation_ms * self.user.fatigue()
            aid = self.booster.apply_hint()
            if aid is not None:
                self.user.arrows_cleared += 1
                self.user.frustration = max(0, self.user.frustration - 0.1)
                return True

        elif choice == "scissors":
            self.user.total_time += self.cfg.booster.scissors_activation_ms * self.user.fatigue()
            aid = self.booster.apply_scissors()
            if aid is not None:
                self.user.arrows_cleared += 1
                self.user.frustration = max(0, self.user.frustration - 0.15)
                return True

        elif choice == "wand":
            self.user.total_time += self.cfg.booster.wand_activation_ms * self.user.fatigue()
            removed = self.booster.apply_wand()
            if removed:
                self.user.arrows_cleared += len(removed)
                self.user.frustration = max(0, self.user.frustration - 0.25)
                return True

        return False

    # ── Recursive unblock ──────────────────────────────────────────────────

    def _try_recursive_unblock(self, depth: int = 0) -> bool:
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

        think_time = self.p.recursion_think_time * self.user.fatigue()
        self.user.total_time += think_time

        blocker = self.board_state.find_blocker(target)
        if blocker is None:
            return False

        if self.board_state.is_solvable(blocker):
            region = self.viewport.current_region()
            self._do_tap(blocker, is_solvable=True, region=region)
            return True
        else:
            return self._try_recursive_unblock(depth + 1)

    # ── Scan & tap region ──────────────────────────────────────────────────

    def _scan_and_tap_region(self, region: ViewportRegion) -> bool:
        visible = self._arrows_in_region(region)
        if not visible:
            return False

        visible = self._sort_arrows(visible)

        scan_time = self._scan_region_time(len(visible), region)
        self.user.total_time += scan_time * self.user.fatigue()

        fail = self.user.should_fail_attempt()
        if fail:
            return False

        solvable_here = [a for a in visible if self.board_state.is_solvable(a)]

        miss_prob = self._effective_miss_prob()
        actually_found = [a for a in solvable_here if self.rng.random() >= miss_prob]

        if not actually_found:
            if visible and self.rng.random() < self.p.mistake_rate:
                non_solvable = [a for a in visible if not self.board_state.is_solvable(a)]
                if non_solvable:
                    victim = self.rng.choice(non_solvable)
                    self._do_tap(victim, is_solvable=False, region=region)
            return False

        # Batch tap
        found_any = False
        batch_count = 0
        while actually_found and batch_count < self.p.max_batch_before_pan:
            target = actually_found.pop(0)
            if target.arrow_id not in self.board_state.remaining:
                continue
            if not self.board_state.is_solvable(target):
                continue

            if self.viewport.is_zoomed_out() and not self.viewport.fits_zoomed_in:
                if self.rng.random() < self.p.zoom_in_to_tap_prob:
                    trans = self.viewport.switch_zoom("in")
                    self.user.total_time += trans * self.user.fatigue()
                    for ri, r in enumerate(self.viewport.zoom_in_regions):
                        if r.x0 <= target.head_x < r.x1 and r.y0 <= target.head_y < r.y1:
                            self.viewport.current_zi_idx = ri
                            region = r
                            break

            self._do_tap(target, is_solvable=True, region=region)
            found_any = True
            batch_count += 1

            fail = self.user.should_fail_attempt()
            if fail:
                return found_any

            # Quick rescan
            if batch_count < self.p.max_batch_before_pan:
                new_visible = self._arrows_in_region(region)
                rescan_time = self._scan_region_time(
                    len(new_visible), region, is_rescan=True
                )
                self.user.total_time += rescan_time * self.user.fatigue()

                new_solvable = [
                    a for a in new_visible if self.board_state.is_solvable(a)
                ]
                miss_prob = self._effective_miss_prob()
                actually_found = [
                    a for a in new_solvable if self.rng.random() >= miss_prob
                ]

        # Reactive zoom: viewport cleared → zoom out
        if found_any and not self.viewport.fits_zoomed_in:
            remaining_in_region = self._arrows_in_region(region)
            if not remaining_in_region:
                if self.rng.random() < self.p.viewport_cleared_zoom_out_prob:
                    trans = self.viewport.switch_zoom("out")
                    self.user.total_time += trans * self.user.fatigue()

        return found_any

    # ═══════════════════════════════════════════════════════════════════════
    #  Main attempt simulation
    # ═══════════════════════════════════════════════════════════════════════

    def simulate_attempt(self, attempt_num: int) -> AttemptResult:
        """
        Simulate one attempt at the level.

        Includes:
          - Level overhead (loading)
          - Board-state-aware scanning
          - Cascade awareness
          - Booster usage when stuck
          - Level overhead (celebration on win)
        """
        self.reset(attempt_num)
        self.user.reset_for_attempt(attempt_num)
        self.user.apply_retry_learning(attempt_num)

        # Level overhead: loading
        self.user.total_time += self.cfg.overhead.level_load_time_ms

        # Initial board scan
        self.user.total_time += self.p.board_scan_time

        while self.board_state.remaining:
            fail_reason = self.user.should_fail_attempt()
            if fail_reason:
                return AttemptResult(
                    won=False,
                    time_ms=round(self.user.total_time, 1),
                    taps=self.user.tap_count,
                    mistakes=self.user.mistake_count,
                    arrows_cleared=self.user.arrows_cleared,
                    total_arrows=self.total_arrows,
                    fail_reason=fail_reason,
                )

            found_any = False

            if self.viewport.is_zoomed_out() or self.viewport.fits_zoomed_in:
                if self.viewport.fits_zoomed_in:
                    found_any = self._scan_and_tap_region(self.viewport.zoom_in_regions[0])
                elif self.viewport.fits_zoomed_out:
                    found_any = self._scan_and_tap_region(self.viewport.zoom_out_regions[0])
                else:
                    zo_order = list(range(len(self.viewport.zoom_out_regions)))
                    if self.p.scan_direction == "rtl_btt":
                        zo_order.reverse()
                    for zo_idx in zo_order:
                        self.viewport.current_zo_idx = zo_idx
                        if zo_idx != zo_order[0]:
                            self.user.total_time += self.cfg.viewport.pan_time * self.user.fatigue()
                        if self._scan_and_tap_region(self.viewport.zoom_out_regions[zo_idx]):
                            found_any = True

                if not found_any and not self.viewport.fits_zoomed_in:
                    trans = self.viewport.switch_zoom("in")
                    self.user.total_time += trans * self.user.fatigue()

            else:
                region_order = list(range(len(self.viewport.zoom_in_regions)))
                if self.p.scan_direction == "rtl_btt":
                    region_order.reverse()

                for ridx in region_order:
                    self.viewport.current_zi_idx = ridx
                    region = self.viewport.zoom_in_regions[ridx]

                    if ridx != region_order[0]:
                        self.user.total_time += self.cfg.viewport.pan_time * self.user.fatigue()

                    region_found = self._scan_and_tap_region(region)
                    if region_found:
                        found_any = True
                        self.viewport.remembered_regions.add(ridx)

                    fail_reason = self.user.should_fail_attempt()
                    if fail_reason:
                        return AttemptResult(
                            won=False,
                            time_ms=round(self.user.total_time, 1),
                            taps=self.user.tap_count,
                            mistakes=self.user.mistake_count,
                            arrows_cleared=self.user.arrows_cleared,
                            total_arrows=self.total_arrows,
                            fail_reason=fail_reason,
                        )

                if not found_any and self.rng.random() < self.p.zoom_out_survey_prob:
                    trans = self.viewport.switch_zoom("out")
                    self.user.total_time += trans * self.user.fatigue()
                    continue

            # No solvable found → recovery strategies
            if not found_any:
                self.user.frustration += self.p.frustration_buildup_rate

                fail_reason = self.user.should_fail_attempt()
                if fail_reason:
                    return AttemptResult(
                        won=False,
                        time_ms=round(self.user.total_time, 1),
                        taps=self.user.tap_count,
                        mistakes=self.user.mistake_count,
                        arrows_cleared=self.user.arrows_cleared,
                        total_arrows=self.total_arrows,
                        fail_reason=fail_reason,
                    )

                # ── Try booster first (before other recovery) ──
                if self._try_booster():
                    continue

                # Recursive unblock
                if (self.user.frustration < 1.0
                        and self.rng.random() < self.p.recursive_solve_probability):
                    if self._try_recursive_unblock():
                        continue

                # Memory: try remembered region
                if (self.viewport.remembered_regions
                        and self.rng.random() < self.p.memory_probability):
                    if self.viewport.is_zoomed_out():
                        trans = self.viewport.switch_zoom("in")
                        self.user.total_time += trans * self.user.fatigue()
                    mem_region = self.rng.choice(list(self.viewport.remembered_regions))
                    self.viewport.current_zi_idx = mem_region
                    self.user.total_time += self.cfg.viewport.pan_time * self.user.fatigue()
                    continue

                # Preferred zoom fallback
                if not self.viewport.fits_zoomed_in:
                    preferred = self.p.preferred_zoom
                    if preferred == "adaptive":
                        target = "out" if not self.viewport.is_zoomed_out() else "in"
                    elif preferred == "out":
                        target = "out"
                    else:
                        target = "in"

                    trans = self.viewport.switch_zoom(target)
                    self.user.total_time += trans * self.user.fatigue()
                    self.user.total_time += self.p.board_scan_time * self.user.fatigue()
                else:
                    self.user.total_time += self.cfg.viewport.pan_time * 2 * self.user.fatigue()

                # Last resort: find any solvable globally
                solvable_global = self.board_state.get_solvable()
                if solvable_global:
                    extra_search = self.p.board_scan_time * 3 * self.user.fatigue()
                    self.user.total_time += extra_search
                    target = self.rng.choice(solvable_global)
                    region = self.viewport.current_region()
                    self._do_tap(target, is_solvable=True, region=region)
                else:
                    break

        # Level cleared — add celebration overhead
        self.user.total_time += self.cfg.overhead.win_celebration_ms

        return AttemptResult(
            won=True,
            time_ms=round(self.user.total_time, 1),
            taps=self.user.tap_count,
            mistakes=self.user.mistake_count,
            arrows_cleared=self.user.arrows_cleared,
            total_arrows=self.total_arrows,
        )
