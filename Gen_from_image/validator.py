# File: validator.py
# Chứa lớp Validator và lớp Arrow (là lớp phụ thuộc)
# Được trích xuất để phục vụ unit test.

from helper import Arrow


class Validator:
    def __init__(self):
        # Không cần khởi tạo cache nữa
        pass

    def clear_cache(self):
        # Giữ lại hàm này (nhưng không làm gì) để tương thích với generator.py
        # Vì generator.py vẫn đang gọi validator.clear_cache()
        pass

    def _can_arrow_exit_cleanly(self, arrow_to_check, other_arrows, grid_w, grid_h):
        obstacle_points = {p for arr in other_arrows for p in arr.points}
        # Thân của chính mũi tên đó cũng là vật cản (trừ đầu mũi tên)
        self_body_points = set(arrow_to_check.points[1:])
        all_obstacles = obstacle_points.union(self_body_points)

        head = arrow_to_check.points[0]
        direction = arrow_to_check.direction
        current_pos = (head[0] + direction[0], head[1] + direction[1])

        while 0 <= current_pos[0] < grid_w and 0 <= current_pos[1] < grid_h:
            if current_pos in all_obstacles:
                return False
            current_pos = (current_pos[0] + direction[0], current_pos[1] + direction[1])
        return True

    def find_movable_arrows(self, all_arrows, grid_w, grid_h):
        return [
            arr
            for i, arr in enumerate(all_arrows)
            if self._can_arrow_exit_cleanly(
                arr, all_arrows[:i] + all_arrows[i + 1 :], grid_w, grid_h
            )
        ]

    def is_board_state_solvable(self, arrows, grid_w, grid_h):
        # --- Logic thuần túy không Cache ---

        # 1. Base case: Nếu danh sách rỗng, tức là đã giải hết -> True
        if not arrows:
            return True

        # 2. Tìm danh sách các mũi tên có thể thoát ngay lập tức
        movable_arrows = self.find_movable_arrows(arrows, grid_w, grid_h)

        # 3. Nếu còn mũi tên nhưng không con nào di chuyển được -> Deadlock -> False
        if not movable_arrows:
            return False

        # 4. Tạo trạng thái tiếp theo: Loại bỏ các mũi tên đã di chuyển được
        movable_ids = {arr.id for arr in movable_arrows}
        next_state = [arr for arr in arrows if arr.id not in movable_ids]

        # 5. Đệ quy
        return self.is_board_state_solvable(next_state, grid_w, grid_h)
