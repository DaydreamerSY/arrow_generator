# File: generator.py
# Chứa logic tạo level từ hàm generate_hybrid_level.
# Đã được tái cấu trúc (refactored) để loại bỏ các phụ thuộc GUI
# và nhận các đối tượng cần thiết làm tham số để dễ dàng unit test.

import random
import progressbar
from validator import Validator
from helper import Arrow, Args
from loguru import logger

# --- LỚP GENERATOR ĐÃ TÁI CẤU TRÚC ---


class HybridLevelGeneratorTestable:
    """
    Bao bọc logic 'generate_hybrid_level' và các hàm phụ trợ của nó.
    Hàm chính đã được điều chỉnh để trả về kết quả thay vì sửa đổiÍÍÍ
    trạng thái GUI.
    """

    def __init__(self, args: Args):
        self.progress_bar = progressbar.ProgressBar()
        self.args = args
        pass  # Không cần trạng thái

    def _perform_random_walk(
        self,
        start_pos,
        all_occupied_points,
        editable_area,
        gen_grid_w,
        gen_grid_h,
        max_len=30,
    ):
        """
        Trích xuất trực tiếp từ lớp MainWindow.
        """
        path = [start_pos]
        visited = {start_pos}
        current_pos = start_pos
        for _ in range(int(max_len) - 1):
            x, y = current_pos
            neighbors = []
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                neighbor = (nx, ny)
                if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h):
                    continue
                if neighbor not in editable_area:
                    continue
                if neighbor not in all_occupied_points and neighbor not in visited:
                    neighbors.append(neighbor)
            if not neighbors:
                break
            next_pos = random.choice(neighbors)
            path.append(next_pos)
            visited.add(next_pos)
            current_pos = next_pos
        return path

    def generate_hybrid_level(
        self,
        validator,
        active_layer,
        all_arrows_on_board,
        start_arrow_id,
        num_to_gen,
        avg_length,
    ):
        """
        Phiên bản tái cấu trúc của MainWindow.generate_hybrid_level.
        Loại bỏ các lệnh gọi GUI (statusBar, QApplication) và nhận các
        đối tượng (validator, active_layer) làm tham số.

        Trả về: (list_of_new_arrows, last_arrow_id, status_message)
        """

        logger.info(f"Generating level in painted area... (This will be slow)")

        if not active_layer:
            return [], start_arrow_id, f"No active layer selected."

        editable_area = active_layer.editable_area
        if not editable_area:
            return (
                [],
                start_arrow_id,
                f"Active layer has no painted area to generate in.",
            )

        max_retries_per_arrow = 1000

        # 3. Tính toán ranh giới và độ lệch (offset) CỦA editable_area
        min_x = min(p[0] for p in editable_area)
        min_y = min(p[1] for p in editable_area)
        max_x = max(p[0] for p in editable_area)
        max_y = max(p[1] for p in editable_area)
        gen_offset_x = -min_x
        gen_offset_y = -min_y
        gen_grid_w = max_x - min_x + 1
        gen_grid_h = max_y - min_y + 1

        # 4. Dịch chuyển (shift) các đối tượng vào "Thế giới ảo"
        gen_editable_area = {
            (p[0] + gen_offset_x, p[1] + gen_offset_y) for p in editable_area
        }
        gen_arrows_on_board = []
        gen_occupied_points = set()
        for arrow in all_arrows_on_board:
            is_in_area = False
            shifted_points = []
            for p in arrow.points:
                if p in editable_area:
                    is_in_area = True
                shifted_points.append((p[0] + gen_offset_x, p[1] + gen_offset_y))
            if is_in_area:
                virtual_arrow = Arrow(
                    shifted_points,
                    arrow.direction,
                    arrow.layer_id,
                    arrow.id,
                    arrow.color,
                )
                gen_arrows_on_board.append(virtual_arrow)
                for p_shifted, p_original in zip(shifted_points, arrow.points):
                    if p_original in editable_area:
                        gen_occupied_points.add(p_shifted)

        newly_generated_arrows = []
        arrow_id_counter = start_arrow_id  # Sử dụng ID được truyền vào
        default_color = active_layer.color

        # === MODIFICATION START: Sử dụng Avg. Length từ UI ===
        # (Sử dụng avg_length được truyền vào)
        min_len = max(2, int(avg_length * 0.5))
        max_len = int(avg_length * 1.0)
        max_walk_len = max_len
        # === MODIFICATION END ===

        self.progress_bar = progressbar.ProgressBar(maxval=num_to_gen)
        self.progress_bar.start()
        for i in range(num_to_gen):
            self.progress_bar.update(i + 1)
            # logger.info(f"Trying to generate arrow {i+1}/{num_to_gen}...")
            found_arrow = False
            for retry in range(max_retries_per_arrow):
                p2_candidates = []
                for pos in gen_editable_area:
                    if pos not in gen_occupied_points:
                        p2_candidates.append(pos)
                if not p2_candidates:
                    break
                random.shuffle(p2_candidates)
                start_p2 = None
                p1 = None
                found_start_pair = False
                for p2_cand in p2_candidates:
                    p1_candidates = []
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        p1_cand = (p2_cand[0] + dx, p2_cand[1] + dy)
                        if (
                            p1_cand in gen_editable_area
                            and p1_cand not in gen_occupied_points
                        ):
                            p1_candidates.append(p1_cand)
                    if p1_candidates:
                        p1 = random.choice(p1_candidates)
                        start_p2 = p2_cand
                        found_start_pair = True
                        break
                if not found_start_pair:
                    break

                temp_occupied = gen_occupied_points.union({p1})
                path_body = self._perform_random_walk(
                    start_p2,
                    temp_occupied,
                    gen_editable_area,
                    gen_grid_w,
                    gen_grid_h,
                    max_len=max_walk_len - 1,
                )

                path = [p1] + path_body

                # === MODIFICATION START: Lọc độ dài ===
                if not (min_len <= len(path) <= max_len):
                    continue  # Path quá ngắn hoặc quá dài -> Hủy, thử lại
                # === MODIFICATION END ===

                direction = (p1[0] - start_p2[0], p1[1] - start_p2[1])
                temp_arrow = Arrow(
                    path, direction, active_layer.id, arrow_id_counter, default_color
                )

                hypothetical_board = (
                    gen_arrows_on_board + newly_generated_arrows + [temp_arrow]
                )
                validator.clear_cache()

                is_solvable = validator.is_board_state_solvable(
                    hypothetical_board, gen_grid_w, gen_grid_h
                )
                if is_solvable:
                    newly_generated_arrows.append(temp_arrow)
                    gen_occupied_points.update(path)
                    arrow_id_counter += 1
                    found_arrow = True
                    break

            if not found_arrow:
                status_msg = f"Could not find valid arrow {i+1}. Stopping."
                logger.warning(status_msg)
                # Phải dừng và trả về kết quả hiện tại
                break  # Thoát khỏi vòng lặp 'num_to_gen'

        if not newly_generated_arrows:
            return (
                [],
                arrow_id_counter,
                f"Generation complete, but 0 valid arrows found. Try again.",
            )

        final_arrows_to_add = []
        for arrow in newly_generated_arrows:
            original_points = [
                (p[0] - gen_offset_x, p[1] - gen_offset_y) for p in arrow.points
            ]
            real_arrow = Arrow(
                original_points, arrow.direction, active_layer.id, arrow.id, arrow.color
            )
            final_arrows_to_add.append(real_arrow)

        status_msg = f"Successfully generated {len(final_arrows_to_add)} arrows!"
        logger.info(status_msg)

        return final_arrows_to_add, arrow_id_counter, status_msg

    # -------------------------------------------------------------------
    # --- PHẦN MỚI THÊM: LOGIC TẠO LEVEL NÂNG CAO ---
    # -------------------------------------------------------------------

    def _perform_advance_walk_2(
        self,
        start_pos,
        prev_pos,
        all_occupied_points,
        editable_area,
        gen_grid_w,
        gen_grid_h,
        max_len=30,
        # Các tham số mới: Bỏ turn_probability
        straight_weight=1.5,
        left_weight=1.0,
        right_weight=1.0,
        max_turns=99,
    ):
        """
        Một hàm random walk có trạng thái, phiên bản 2.
        Trực tiếp chọn ngẫu nhiên giữa các hướng hợp lệ (Thẳng, Trái, Phải)
        dựa trên trọng số (weight) của chúng.

        Params:
        - straight_weight: (float) Trọng số cho việc đi thẳng.
        - left_weight: (float) Trọng số cho việc quẹo trái.
        - right_weight: (float) Trọng số cho việc quẹo phải.
        - max_turns: (int) Số lần quẹo tối đa trước khi dừng.
        """
        path = [start_pos]
        visited = {start_pos}
        current_pos = start_pos
        current_prev_pos = prev_pos  # Theo dõi vị trí trước đó
        turn_count = 0

        # Mapping các loại di chuyển tới trọng số của chúng
        weights_map = {
            "straight": straight_weight,
            "left": left_weight,
            "right": right_weight,
        }

        for _ in range(int(max_len) - 1):
            if turn_count >= max_turns:
                break  # Đã đạt giới hạn quẹo

            # 1. Tính hướng đi hiện tại (current_pos - current_prev_pos)
            dx = current_pos[0] - current_prev_pos[0]
            dy = current_pos[1] - current_prev_pos[1]
            current_dir = (dx, dy)

            # 2. Phân loại các bước đi (Thẳng, Trái, Phải)
            straight_dir = current_dir
            left_dir = (-dy, dx)
            right_dir = (dy, -dx)

            possible_moves = {
                "straight": (
                    current_pos[0] + straight_dir[0],
                    current_pos[1] + straight_dir[1],
                ),
                "left": (current_pos[0] + left_dir[0], current_pos[1] + left_dir[1]),
                "right": (current_pos[0] + right_dir[0], current_pos[1] + right_dir[1]),
            }

            # 3. Lọc các bước đi hợp lệ VÀ có trọng số > 0
            choices_list = []  # Sẽ chứa (neighbor, move_type)
            weights_list = []  # Sẽ chứa weight tương ứng

            for move_type, weight in weights_map.items():

                # Bỏ qua ngay nếu trọng số bằng 0 (hoặc âm)
                if weight <= 0:
                    continue

                # Lấy vị trí (pos) từ dict possible_moves
                pos = possible_moves.get(move_type)

                nx, ny = pos
                neighbor = (nx, ny)

                # Kiểm tra xem có hợp lệ không (giữ nguyên logic kiểm tra)
                if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h):
                    continue
                if neighbor not in editable_area:
                    continue
                if neighbor in all_occupied_points or neighbor in visited:
                    continue

                # Nếu hợp lệ VÀ có trọng số, thêm vào danh sách
                choices_list.append((neighbor, move_type))
                weights_list.append(weight)

            # 4. Kiểm tra nếu bị kẹt
            if not choices_list:
                # Bị kẹt. Không còn đường đi hợp lệ HOẶC tất cả
                # các đường hợp lệ đều có trọng số <= 0.
                break

            # 5. Chọn một bước đi (dựa trên trọng số)
            chosen_move, chosen_type = random.choices(choices_list, weights_list, k=1)[
                0
            ]

            # 6. Cập nhật trạng thái
            if chosen_type != "straight":
                turn_count += 1

            path.append(chosen_move)
            visited.add(chosen_move)
            current_prev_pos = current_pos  # Cập nhật
            current_pos = chosen_move

        return path

    def _perform_advanced_walk(
        self,
        start_pos,
        prev_pos,
        all_occupied_points,
        editable_area,
        gen_grid_w,
        gen_grid_h,
        max_len=30,
        # Các tham số mới
        turn_probability=0.5,
        straight_weight=1.5,
        left_weight=1.0,
        right_weight=1.0,
        max_turns=99,
    ):
        """
        Một hàm random walk có trạng thái, ưu tiên đi thẳng và
        kiểm soát số lần quẹo, có trọng số cho quẹo trái/phải.

        Params:
        - turn_probability: (float) 0.0-1.0, cơ hội để *xem xét* việc quẹo.
        - straight_weight: (float) Trọng số cho việc đi thẳng.
        - left_weight: (float) Trọng số cho việc quẹo trái (nếu được phép).
        - right_weight: (float) Trọng số cho việc quẹo phải (nếu được phép).
        - max_turns: (int) Số lần quẹo tối đa trước khi dừng.
        """
        path = [start_pos]
        visited = {start_pos}
        current_pos = start_pos
        current_prev_pos = prev_pos  # Theo dõi vị trí trước đó
        turn_count = 0

        for _ in range(int(max_len) - 1):
            if turn_count >= max_turns:
                break  # Đã đạt giới hạn quẹo

            # 1. Tính hướng đi hiện tại (current_pos - current_prev_pos)
            dx = current_pos[0] - current_prev_pos[0]
            dy = current_pos[1] - current_prev_pos[1]
            current_dir = (dx, dy)

            # 2. Phân loại các bước đi (Thẳng, Trái, Phải)
            # Hướng "Trái": (-dy, dx)
            # Hướng "Phải": (dy, -dx)
            straight_dir = current_dir
            left_dir = (-dy, dx)
            right_dir = (dy, -dx)

            possible_moves = {
                "straight": (
                    current_pos[0] + straight_dir[0],
                    current_pos[1] + straight_dir[1],
                ),
                "left": (current_pos[0] + left_dir[0], current_pos[1] + left_dir[1]),
                "right": (current_pos[0] + right_dir[0], current_pos[1] + right_dir[1]),
            }

            # 3. Lọc các bước đi hợp lệ và gán trọng số
            valid_moves = []
            weights = []

            for move_type, pos in possible_moves.items():
                nx, ny = pos
                neighbor = (nx, ny)

                # Kiểm tra xem có hợp lệ không
                if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h):
                    continue
                if neighbor not in editable_area:
                    continue
                if neighbor in all_occupied_points or neighbor in visited:
                    continue

                # Nếu hợp lệ, thêm vào danh sách lựa chọn
                valid_moves.append((neighbor, move_type))

                # 4. Áp dụng trọng số (bias)
                if move_type == "straight":
                    weights.append(straight_weight)  # Ưu tiên đi thẳng

                # Chỉ xem xét quẹo nếu tỉ lệ cho phép
                elif random.random() < turn_probability:
                    if move_type == "left":
                        weights.append(left_weight)
                    elif move_type == "right":
                        weights.append(right_weight)
                else:
                    weights.append(0.0)  # Không muốn quẹo lần này

            # Xử lý trường hợp bị kẹt: nếu đi thẳng bị chặn và tỉ lệ quẹo = 0,
            # cho phép quẹo để tránh dừng lại quá sớm.
            if valid_moves and all(w <= 0 for w in weights):
                # Gán lại trọng số cơ bản nếu tất cả đều bằng 0
                new_weights = []
                for _, move_type in valid_moves:
                    if move_type == "straight":
                        new_weights.append(straight_weight)
                    elif move_type == "left":
                        new_weights.append(left_weight)
                    elif move_type == "right":
                        new_weights.append(right_weight)
                weights = new_weights
                # Đảm bảo không có trọng số âm hoặc 0 nếu vẫn còn đường
                if all(w <= 0 for w in weights):
                    weights = [1.0] * len(valid_moves)

            if not valid_moves or not any(w > 0 for w in weights):
                break  # Bị kẹt

            # 5. Chọn một bước đi (dựa trên trọng số)
            chosen_move, chosen_type = random.choices(valid_moves, weights, k=1)[0]

            # 6. Cập nhật trạng thái
            if chosen_type != "straight":
                turn_count += 1

            path.append(chosen_move)
            visited.add(chosen_move)
            current_prev_pos = current_pos  # Cập nhật
            current_pos = chosen_move

        return path

    def generate_hybrid_level_advanced(
        self,
        validator,
        active_layer,
        all_arrows_on_board,
        start_arrow_id,
        num_to_gen,
        avg_length,
        # Các tham số mới
        turn_probability=0.5,
        straight_weight=1.5,
        left_weight=1.0,
        right_weight=1.0,
        max_turns=5,
    ):
        """
        Phiên bản NÂNG CAO của hàm generate_hybrid_level.
        Sử dụng _perform_advanced_walk để tạo các mũi tên có hình dạng
        được kiểm soát hơn.

        Trả về: (list_of_new_arrows, last_arrow_id, status_message)
        """

        level_name = "unknow"
        if hasattr(self.args, "alter_item_name"):
            level_name = self.args.alter_item_name

        logger.debug(
            f"Lv: {level_name} | Generating ADVANCED level in painted area... (This will be slow)"
        )

        if not active_layer:
            return [], start_arrow_id, f"Lv: {level_name} | No active layer selected."

        editable_area = active_layer.editable_area
        if not editable_area:
            return (
                [],
                start_arrow_id,
                f"Lv: {level_name} | Active layer has no painted area to generate in.",
            )

        max_retries_per_arrow = 100

        # 3. Tính toán ranh giới và độ lệch (offset) CỦA editable_area
        min_x = min(p[0] for p in editable_area)
        min_y = min(p[1] for p in editable_area)
        max_x = max(p[0] for p in editable_area)
        max_y = max(p[1] for p in editable_area)
        gen_offset_x = -min_x
        gen_offset_y = -min_y
        gen_grid_w = max_x - min_x + 1
        gen_grid_h = max_y - min_y + 1

        # 4. Dịch chuyển (shift) các đối tượng vào "Thế giới ảo"
        # (Logic này y hệt hàm gốc)
        gen_editable_area = {
            (p[0] + gen_offset_x, p[1] + gen_offset_y) for p in editable_area
        }
        gen_arrows_on_board = []
        gen_occupied_points = set()
        for arrow in all_arrows_on_board:
            is_in_area = False
            shifted_points = []
            for p in arrow.points:
                if p in editable_area:
                    is_in_area = True
                shifted_points.append((p[0] + gen_offset_x, p[1] + gen_offset_y))
            if is_in_area:
                virtual_arrow = Arrow(
                    shifted_points,
                    arrow.direction,
                    arrow.layer_id,
                    arrow.id,
                    arrow.color,
                )
                gen_arrows_on_board.append(virtual_arrow)
                for p_shifted, p_original in zip(shifted_points, arrow.points):
                    if p_original in editable_area:
                        gen_occupied_points.add(p_shifted)

        newly_generated_arrows = []
        arrow_id_counter = start_arrow_id
        default_color = active_layer.color

        min_len = max(2, int(avg_length * 0.5))
        max_len = int(avg_length * 1.0)
        max_walk_len = max_len

        # for i in range(num_to_gen):
        for i in range(num_to_gen):
            logger.info(f"Trying to generate (adv) arrow {i+1}/{num_to_gen}...")
            found_arrow = False
            for retry in range(max_retries_per_arrow):
                p2_candidates = []
                for pos in gen_editable_area:
                    if pos not in gen_occupied_points:
                        p2_candidates.append(pos)
                if not p2_candidates:
                    break
                random.shuffle(p2_candidates)
                start_p2 = None
                p1 = None
                found_start_pair = False
                for p2_cand in p2_candidates:
                    p1_candidates = []
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        p1_cand = (p2_cand[0] + dx, p2_cand[1] + dy)
                        if (
                            p1_cand in gen_editable_area
                            and p1_cand not in gen_occupied_points
                        ):
                            p1_candidates.append(p1_cand)
                    if p1_candidates:
                        p1 = random.choice(p1_candidates)
                        start_p2 = p2_cand
                        found_start_pair = True
                        break
                if not found_start_pair:
                    break

                temp_occupied = gen_occupied_points.union({p1})

                # --- THAY ĐỔI CHÍNH NẰM Ở ĐÂY ---
                path_body = self._perform_advance_walk_2(  # <--- GỌI HÀM WALK MỚI
                    start_p2,
                    prev_pos=p1,  # <--- Cung cấp vị trí trước đó
                    all_occupied_points=temp_occupied,
                    editable_area=gen_editable_area,
                    gen_grid_w=gen_grid_w,
                    gen_grid_h=gen_grid_h,
                    max_len=max_walk_len - 1,
                    # Truyền các tham số điều khiển
                    # turn_probability=turn_probability,
                    straight_weight=straight_weight,
                    left_weight=left_weight,
                    right_weight=right_weight,
                    max_turns=max_turns,
                )
                # --- HẾT THAY ĐỔI ---

                path = [p1] + path_body

                if not (min_len <= len(path) <= max_len):
                    continue

                direction = (p1[0] - start_p2[0], p1[1] - start_p2[1])
                temp_arrow = Arrow(
                    path, direction, active_layer.id, arrow_id_counter, default_color
                )

                hypothetical_board = (
                    gen_arrows_on_board + newly_generated_arrows + [temp_arrow]
                )
                validator.clear_cache()

                is_solvable = validator.is_board_state_solvable(
                    hypothetical_board, gen_grid_w, gen_grid_h
                )
                if is_solvable:
                    newly_generated_arrows.append(temp_arrow)
                    gen_occupied_points.update(path)
                    arrow_id_counter += 1
                    found_arrow = True
                    break

        #     found_arrow = False

        #     # 1. Tối ưu chọn điểm xuất phát (như câu trả lời trước)
        #     free_points_list = list(gen_editable_area - gen_occupied_points)
        #     if not free_points_list: break
        #     random.shuffle(free_points_list) # Shuffle 1 lần

        #     # Chỉ cần thử một vài điểm xuất phát, vì thuật toán Backtracking sẽ tự đào sâu
        #     # Giảm max_retries xuống còn 10-20 là đủ (thay vì 1000)
        #     for start_node in free_points_list: # Thử lần lượt các điểm trống

        #         # 1. Xác định các hướng khởi tạo hợp lệ (Để sửa North Bias)
        #         possible_start_dirs = []
        #         for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
        #             p1 = (start_node[0] + dx, start_node[1] + dy)
        #             # Check cơ bản p1
        #             if p1 in gen_editable_area and p1 not in gen_occupied_points:
        #                  possible_start_dirs.append((dx, dy))

        #         if not possible_start_dirs: continue
        #         random.shuffle(possible_start_dirs)

        #         arrow_found_for_node = False

        #         # 2. Thử sinh mũi tên từ các hướng này
        #         for start_dir in possible_start_dirs:
        #             p1 = (start_node[0] + start_dir[0], start_node[1] + start_dir[1])

        #             # Chuẩn bị dữ liệu cho đệ quy
        #             initial_path = [start_node, p1]

        #             # QUAN TRỌNG: Phải đánh dấu start_node và p1 là occupied trước khi gọi đệ quy
        #             # để Validator bên trong hàm đệ quy nhận diện đúng.
        #             gen_occupied_points.add(start_node)
        #             gen_occupied_points.add(p1)

        #             target_len = random.randint(min_len, max_len)
        #             weights = {"straight": straight_weight, "left": left_weight, "right": right_weight}

        #             # GỌI HÀM ĐỆ QUY MỚI
        #             # Lưu ý: Hàm này sẽ tự động check Validator ở TỪNG BƯỚC
        #             final_path = self._generate_arrow_backtracking_strict(
        #                 current_path=initial_path,
        #                 target_length=target_len,
        #                 editable_area=gen_editable_area,
        #                 occupied_points=gen_occupied_points, # Truyền set đang dùng (đã add p0, p1)
        #                 gen_grid_w=gen_grid_w, gen_grid_h=gen_grid_h,
        #                 weights=weights,
        #                 max_turns=max_turns, current_turns=0,
        #                 current_direction=start_dir, # Truyền hướng khởi tạo (Fix North Bias)
        #                 validator=validator,
        #                 all_fixed_arrows=newly_generated_arrows
        #             )

        #             if final_path:
        #                 # Thành công!
        #                 # Tạo Arrow Object
        #                 direction = (final_path[1][0] - final_path[0][0], final_path[1][1] - final_path[0][1])
        #                 new_arrow = Arrow(final_path, direction, active_layer.id, arrow_id_counter, default_color)
        #                 newly_generated_arrows.append(new_arrow)

        #                 # gen_occupied_points đã được update bên trong hàm đệ quy chưa?
        #                 # Do ta truyền tham chiếu set, nhưng trong đệ quy có bước remove khi backtrack.
        #                 # Khi return success, path vẫn nằm trong set nếu ta không remove ở bước cuối.
        #                 # Tuy nhiên, để an toàn, ta update lại toàn bộ path vào set occupied
        #                 gen_occupied_points.update(final_path)

        #                 arrow_id_counter += 1
        #                 found_arrow = True
        #                 arrow_found_for_node = True

        #                 # Cập nhật lại danh sách điểm trống cho vòng lặp ngoài
        #                 path_set = set(final_path)
        #                 free_points_list = [p for p in free_points_list if p not in path_set]

        #                 break # Xong hướng này -> Xong mũi tên này
        #             else:
        #                 # Thất bại hướng này -> Backtrack thủ công 2 điểm đầu
        #                 gen_occupied_points.remove(start_node)
        #                 gen_occupied_points.remove(p1)

        #         if arrow_found_for_node:
        #             break # Xong mũi tên này -> Qua mũi tên tiếp theo (for i in range(num_to_gen))

        if not newly_generated_arrows:
            return (
                [],
                arrow_id_counter,
                f"Lv: {level_name} | Generation complete, but 0 valid arrows found. Try again.",
            )

        final_arrows_to_add = []
        for arrow in newly_generated_arrows:
            original_points = [
                (p[0] - gen_offset_x, p[1] - gen_offset_y) for p in arrow.points
            ]
            real_arrow = Arrow(
                original_points, arrow.direction, active_layer.id, arrow.id, arrow.color
            )
            final_arrows_to_add.append(real_arrow)

        status_msg = f"Lv: {level_name} | Successfully generated {len(final_arrows_to_add)} arrows!"
        logger.debug(status_msg)

        return final_arrows_to_add, arrow_id_counter, status_msg

    def _generate_arrow_backtracking_strict(
        self,
        current_path,
        target_length,
        editable_area,
        occupied_points,
        gen_grid_w,
        gen_grid_h,
        weights,  # dict: straight, left, right
        max_turns,
        current_turns,
        current_direction,
        validator,  # Truyền Validator vào
        all_fixed_arrows,
    ):  # Các arrow cũ đã cố định

        # 1. ĐIỀU KIỆN DỪNG THÀNH CÔNG
        if len(current_path) >= target_length:
            return current_path

        current_pos = current_path[-1]
        dx, dy = current_direction  # Vector hướng hiện tại

        # 2. ĐỊNH NGHĨA CÁC HƯỚNG ĐI TƯƠNG ĐỐI
        # Lưu ý: Hệ tọa độ ảnh (y xuống dưới)
        # Straight: (dx, dy)
        # Left: (dy, -dx)
        # Right: (-dy, dx)

        moves = [
            {"type": "straight", "dir": (dx, dy), "weight": weights["straight"]},
            {"type": "left", "dir": (dy, -dx), "weight": weights["left"]},
            {"type": "right", "dir": (-dy, dx), "weight": weights["right"]},
        ]

        # 3. LỌC VÀ KIỂM TRA LOGIC (VALIDATOR CHECK)
        valid_candidates = []

        for move in moves:
            mdx, mdy = move["dir"]
            nx, ny = current_pos[0] + mdx, current_pos[1] + mdy
            next_pos = (nx, ny)

            # --- Check cơ bản (nhanh) ---
            if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h):
                continue
            if next_pos not in editable_area:
                continue
            if next_pos in occupied_points:
                continue
            if next_pos in current_path:
                continue

            new_turns = current_turns + (1 if move["type"] != "straight" else 0)
            if new_turns > max_turns:
                continue

            # --- CHECK NÂNG CAO: VALIDATOR (Chậm nhưng chắc) ---

            # 1. Tạo đường đi giả lập (Current path + Next pos)
            temp_path = current_path + [next_pos]

            # 2. Tính hướng giả lập (để tạo đối tượng Arrow hợp lệ)
            # Lấy điểm đầu và điểm thứ 2 để xác định vector hướng
            if len(temp_path) >= 2:
                temp_direction = (
                    temp_path[1][0] - temp_path[0][0],
                    temp_path[1][1] - temp_path[0][1],
                )
            else:
                temp_direction = (0, 1)  # Mặc định nếu chưa đủ dài

            # 3. Tạo đối tượng Arrow tạm thời
            # Lưu ý: ID phải là duy nhất hoặc xử lý cache kỹ. Ở đây dùng ID tạm 999999.
            temp_arrow = Arrow(temp_path, temp_direction, -1, 999999, "temp_color")

            # 4. Tạo board giả lập: Các arrow cũ + Arrow đang vẽ dở
            hypothetical_board = all_fixed_arrows + [temp_arrow]

            # QUAN TRỌNG: Phải clear cache vì vị trí của arrow 999999 thay đổi liên tục
            # validator.clear_cache()

            # 5. Gọi hàm kiểm tra đúng chuẩn (truyền list Arrow)
            is_safe = validator.is_board_state_solvable(
                hypothetical_board, gen_grid_w, gen_grid_h
            )

            if is_safe:
                # Random weight một chút để tạo biến thể
                w = move["weight"] * random.uniform(0.8, 1.2)
                valid_candidates.append((w, next_pos, new_turns, (mdx, mdy)))

        # 4. SẮP XẾP THEO TRỌNG SỐ (Greedy DFS)
        valid_candidates.sort(key=lambda x: x[0], reverse=True)

        # 5. ĐỆ QUY
        for _, next_pos, next_turn_count, next_dir in valid_candidates:

            # Update State
            current_path.append(next_pos)
            occupied_points.add(next_pos)  # Đánh dấu chiếm dụng cho đệ quy sâu hơn

            result = self._generate_arrow_backtracking_strict(
                current_path,
                target_length,
                editable_area,
                occupied_points,
                gen_grid_w,
                gen_grid_h,
                weights,
                max_turns,
                next_turn_count,
                next_dir,  # Truyền hướng mới
                validator,
                all_fixed_arrows,
            )

            if result is not None:
                return result  # Tìm thấy đường thành công!

            # Backtrack (Quay lui)
            current_path.pop()
            occupied_points.remove(next_pos)

        return None  # Bế tắc
