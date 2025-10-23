# File: validator.py
# Chứa lớp Validator và lớp Arrow (là lớp phụ thuộc)
# Được trích xuất để phục vụ unit test.

# --- DATA STRUCTURES ---
class Arrow:
    """
    Một cấu trúc dữ liệu đơn giản để chứa thông tin mũi tên.
    Trích xuất từ file gốc.
    """
    def __init__(self, points, direction, layer_id, arrow_id, color):
        self.points = points
        self.direction = direction
        self.layer_id = layer_id
        self.id = arrow_id
        self.color = color

# --- LOGIC MODULES ---
class Validator:
    """
    Lớp logic Validator được trích xuất từ file gốc.
    """
    def __init__(self):
        self.memo = {}

    def clear_cache(self):
        self.memo.clear()

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
            arr for i, arr in enumerate(all_arrows) 
            if self._can_arrow_exit_cleanly(arr, all_arrows[:i] + all_arrows[i+1:], grid_w, grid_h)
        ]
    
    # === MODIFICATION START: Sử dụng logic "Greedy" (Xóa tất cả) ===
    def is_board_state_solvable(self, arrows, grid_w, grid_h):
        # 1. Tối ưu hóa: Dùng Memoization (vẫn rất quan trọng)
        board_key = frozenset(arr.id for arr in arrows)
        if board_key in self.memo: 
            return self.memo[board_key]

        # 2. Trường hợp cơ bản: Bảng trống -> Thành công
        if not arrows: 
            self.memo[board_key] = True
            return True

        # 3. Tìm TẤT CẢ các mũi tên giải được ở trạng thái này
        movable_arrows = self.find_movable_arrows(arrows, grid_w, grid_h)

        # 4. Trường hợp bế tắc (Stuck):
        if not movable_arrows:
            self.memo[board_key] = False
            return False

        # 5. LOGIC MỚI: Xóa TẤT CẢ mũi tên giải được cùng lúc
        movable_ids = {arr.id for arr in movable_arrows}
        next_state = [arr for arr in arrows if arr.id not in movable_ids]
        
        # 6. Đệ quy vào trạng thái tiếp theo
        result = self.is_board_state_solvable(next_state, grid_w, grid_h)
        
        # 7. Lưu kết quả và trả về
        self.memo[board_key] = result
        return result
    # === MODIFICATION END ===