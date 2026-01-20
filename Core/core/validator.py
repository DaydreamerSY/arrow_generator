# File: validator.py
# Cập nhật:
# 1. Loại bỏ max_depth.
# 2. Thêm logic kiểm tra min_width và max_width chặt chẽ.

from helper import Arrow


class Validator:
    def __init__(self):
        pass

    def clear_cache(self):
        pass

    def _can_arrow_exit_cleanly(self, arrow_to_check, other_arrows, grid_w, grid_h):
        obstacle_points = {p for arr in other_arrows for p in arr.points}
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

    def is_board_state_solvable(self, arrows, grid_w, grid_h, min_width=None, max_width=None):
        """
        Kiểm tra tính giải được và ràng buộc Width (Branching Factor).
        Hàm đệ quy này sẽ mô phỏng việc giải cho đến khi hết bàn cờ.
        """
        # 1. Base case: Hết mũi tên -> Success
        if not arrows:
            return True

        # 2. Tìm danh sách các mũi tên có thể di chuyển
        movable_arrows = self.find_movable_arrows(arrows, grid_w, grid_h)
        current_width = len(movable_arrows)

        # 3. Deadlock check (Cơ bản)
        if current_width == 0:
            return False

        # 4. --- WIDTH CONSTRAINT CHECK ---
        
        # Check Max Width (Quá dễ/lỏng lẻo)
        if max_width is not None:
            if current_width > max_width:
                return False

        # Check Min Width (Quá chặt/tuyến tính)
        # Chỉ check khi số lượng mũi tên còn lại ĐỦ để đáp ứng min_width
        # Ví dụ: min_width=3, nhưng trên bàn chỉ còn 2 con -> Không thể bắt lỗi được.
        if min_width is not None:
            if len(arrows) >= min_width:
                if current_width < min_width:
                    return False
        # ---------------------------------

        # 5. Greedy Reduction
        # Giả lập người chơi loại bỏ tất cả các mũi tên có thể đi được
        # (Cách này nhanh nhưng làm giảm width của bước tiếp theo rất mạnh)
        # Nếu muốn chính xác hơn về width của từng bước đơn lẻ, ta chỉ nên loại bỏ 1 con, 
        # nhưng như thế sẽ rất chậm (O(N!)). 
        # Với generator, ta chấp nhận mô hình Greedy: "Giải phóng mặt bằng tối đa".
        
        movable_ids = {arr.id for arr in movable_arrows}
        next_state = [arr for arr in arrows if arr.id not in movable_ids]

        # Safety check: Nếu không loại bỏ được gì (đã check ở bước 3, nhưng check lại cho chắc)
        if len(next_state) == len(arrows):
            return False

        # 6. Đệ quy
        return self.is_board_state_solvable(next_state, grid_w, grid_h, min_width, max_width)

    def check_global_constraints(self, current_arrows, new_arrow_candidate, grid_w, grid_h, min_width=None, max_width=None):
        """
        Wrapper function để gọi từ Generator.
        """
        hypothetical_board = current_arrows + [new_arrow_candidate]
        return self.is_board_state_solvable(
            hypothetical_board, grid_w, grid_h, 
            min_width=min_width, max_width=max_width
        )