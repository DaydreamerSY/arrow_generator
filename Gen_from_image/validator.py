# File: validator.py
# Chứa lớp Validator và lớp Arrow (là lớp phụ thuộc)
# Được trích xuất để phục vụ unit test.

from helper import Arrow
class Validator:
    def __init__(self):
        self.memo = {}
    def clear_cache(self):
        self.memo.clear()
    def _can_arrow_exit_cleanly(self, arrow_to_check, other_arrows, grid_w, grid_h):
        obstacle_points = {p for arr in other_arrows for p in arr.points}
        self_body_points = set(arrow_to_check.points[1:])
        all_obstacles = obstacle_points.union(self_body_points)
        head = arrow_to_check.points[0]; direction = arrow_to_check.direction
        current_pos = (head[0] + direction[0], head[1] + direction[1])
        while 0 <= current_pos[0] < grid_w and 0 <= current_pos[1] < grid_h:
            if current_pos in all_obstacles: return False
            current_pos = (current_pos[0] + direction[0], current_pos[1] + direction[1])
        return True
    def find_movable_arrows(self, all_arrows, grid_w, grid_h):
        return [arr for i, arr in enumerate(all_arrows) if self._can_arrow_exit_cleanly(arr, all_arrows[:i] + all_arrows[i+1:], grid_w, grid_h)]
    def is_board_state_solvable(self, arrows, grid_w, grid_h):
        board_key = frozenset(arr.id for arr in arrows)
        if board_key in self.memo: return self.memo[board_key]
        if not arrows: self.memo[board_key] = True; return True
        movable_arrows = self.find_movable_arrows(arrows, grid_w, grid_h)
        if not movable_arrows: self.memo[board_key] = False; return False
        movable_ids = {arr.id for arr in movable_arrows}
        next_state = [arr for arr in arrows if arr.id not in movable_ids]
        result = self.is_board_state_solvable(next_state, grid_w, grid_h)
        self.memo[board_key] = result; return result
