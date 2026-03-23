# File: validator.py
# Cập nhật:
# 1. Cấu trúc lại bằng vòng lặp While (Khử đệ quy).
# 2. Thay thế cấp phát Set O(N^2) bằng Mảng phẳng 1D (In-place Memory).
# 3. Tối ưu hóa kiểm tra Raycast xuống chi phí O(1) cho mỗi bước.

from helper import Arrow

class Validator:
    def __init__(self):
        pass

    def clear_cache(self):
        # Hàm này được giữ lại để tương thích với API của Generator
        # Tuy nhiên, kiến trúc mới không sinh rác nên không cần cache clear.
        pass

    def check_global_constraints(self, current_arrows, new_arrow_candidate, grid_w, grid_h, min_width=None, max_width=None, initial_width=None):
        """
        Đánh giá tính hợp lệ của toàn bộ bảng sử dụng thuật toán Greedy Mô phỏng.
        Tối ưu hóa: Không cấp phát bộ nhớ động trong vòng lặp.

        initial_width: Nếu != None, ở bước ĐẦU TIÊN của greedy simulation,
                        phải có ít nhất initial_width arrows removable.
                        → Kiểm soát "initial removable count".
        """
        hypothetical_board = current_arrows + [new_arrow_candidate]

        # Chuyển giao logic kiểm tra cho hàm lặp
        return self._is_board_state_solvable_iterative(
            hypothetical_board, grid_w, grid_h,
            min_width=min_width, max_width=max_width,
            initial_width=initial_width
        )

    def _is_board_state_solvable_iterative(self, arrows, grid_w, grid_h, min_width, max_width, initial_width=None):
        if not arrows:
            return True

        # 1. Cấp phát bản đồ tĩnh 1D (O(W * H) Không gian cố định)
        grid_size = grid_w * grid_h
        occupied = [False] * grid_size

        # 2. Ánh xạ toàn bộ tọa độ mũi tên lên bản đồ tĩnh (Thực thi 1 lần duy nhất)
        for arr in arrows:
            for x, y in arr.points:
                if 0 <= x < grid_w and 0 <= y < grid_h:
                    occupied[y * grid_w + x] = True

        # Duy trì mảng quản lý các mũi tên chưa được giải
        remaining_arrows = list(arrows)
        is_first_step = True  # Flag cho initial_width check

        # 3. Vòng lặp Mô phỏng Greedy
        while remaining_arrows:
            movable_arrows = []
            movable_indices = []

            # 3A. Quét Raycast để tìm mũi tên có thể di chuyển
            for i, arr in enumerate(remaining_arrows):
                head_x, head_y = arr.points[0]
                dx, dy = arr.direction
                cx, cy = head_x + dx, head_y + dy

                can_exit = True
                # Mô phỏng đường đạn bay ra khỏi bảng
                while 0 <= cx < grid_w and 0 <= cy < grid_h:
                    if occupied[cy * grid_w + cx]:
                        can_exit = False
                        break
                    cx += dx
                    cy += dy

                if can_exit:
                    movable_arrows.append(arr)
                    movable_indices.append(i)

            current_width = len(movable_arrows)

            # 3B. Đánh giá tính hợp lệ (Deadlock & Ràng buộc Branching Factor)
            if current_width == 0:
                return False

            if max_width is not None and current_width > max_width:
                return False

            if min_width is not None and len(remaining_arrows) >= min_width:
                if current_width < min_width:
                    return False

            # 3B+. Kiểm tra Initial Width (chỉ ở bước đầu tiên)
            # Đảm bảo ở trạng thái ban đầu có đủ arrows removable
            if is_first_step and initial_width is not None:
                if current_width < initial_width:
                    return False
                is_first_step = False

            # 3C. Giải phóng mặt bằng (Sửa đổi bộ nhớ tại chỗ)
            # Tắt cờ occupied của các mũi tên vừa thoát để mở đường cho vòng lặp tiếp theo
            for arr in movable_arrows:
                for x, y in arr.points:
                    if 0 <= x < grid_w and 0 <= y < grid_h:
                        occupied[y * grid_w + x] = False

            # Xóa các mũi tên đã thoát khỏi danh sách chờ (Duyệt ngược để tránh lệch Index)
            for idx in reversed(movable_indices):
                remaining_arrows.pop(idx)

        # Toàn bộ mũi tên đã thoát thành công
        return True