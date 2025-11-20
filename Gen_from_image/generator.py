# File: generator.py
# Chứa logic tạo level từ hàm generate_hybrid_level.
# Đã được tái cấu trúc (refactored) để loại bỏ các phụ thuộc GUI
# và nhận các đối tượng cần thiết làm tham số để dễ dàng unit test.

import random
import progressbar
from validator import Validator
from helper import Arrow
from loguru import logger

# --- DATA STRUCTURES (Phụ thuộc) ---
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

# --- LOGIC (Phụ thuộc) ---
# Lớp Validator cũng cần thiết ở đây vì generator gọi nó.
# Bạn có thể import từ file validator.py thay vì định nghĩa lại.
# (Để file này độc lập, tôi sẽ sao chép nó vào đây)

# class Validator:
#     def __init__(self):
#         self.memo = {}
#     def clear_cache(self):
#         self.memo.clear()
#     def _can_arrow_exit_cleanly(self, arrow_to_check, other_arrows, grid_w, grid_h):
#         obstacle_points = {p for arr in other_arrows for p in arr.points}
#         self_body_points = set(arrow_to_check.points[1:])
#         all_obstacles = obstacle_points.union(self_body_points)
#         head = arrow_to_check.points[0]; direction = arrow_to_check.direction
#         current_pos = (head[0] + direction[0], head[1] + direction[1])
#         while 0 <= current_pos[0] < grid_w and 0 <= current_pos[1] < grid_h:
#             if current_pos in all_obstacles: return False
#             current_pos = (current_pos[0] + direction[0], current_pos[1] + direction[1])
#         return True
#     def find_movable_arrows(self, all_arrows, grid_w, grid_h):
#         return [arr for i, arr in enumerate(all_arrows) if self._can_arrow_exit_cleanly(arr, all_arrows[:i] + all_arrows[i+1:], grid_w, grid_h)]
#     def is_board_state_solvable(self, arrows, grid_w, grid_h):
#         board_key = frozenset(arr.id for arr in arrows)
#         if board_key in self.memo: return self.memo[board_key]
#         if not arrows: self.memo[board_key] = True; return True
#         movable_arrows = self.find_movable_arrows(arrows, grid_w, grid_h)
#         if not movable_arrows: self.memo[board_key] = False; return False
#         movable_ids = {arr.id for arr in movable_arrows}
#         next_state = [arr for arr in arrows if arr.id not in movable_ids]
#         result = self.is_board_state_solvable(next_state, grid_w, grid_h)
#         self.memo[board_key] = result; return result

# --- LỚP GENERATOR ĐÃ TÁI CẤU TRÚC ---

class HybridLevelGeneratorTestable:
    """
    Bao bọc logic 'generate_hybrid_level' và các hàm phụ trợ của nó.
    Hàm chính đã được điều chỉnh để trả về kết quả thay vì sửa đổi
    trạng thái GUI.
    """
    
    def __init__(self):
        self.progress_bar = progressbar.ProgressBar()
        pass # Không cần trạng thái

    def _perform_random_walk(self, start_pos, all_occupied_points, editable_area, gen_grid_w, gen_grid_h, max_len=30):
        """
        Trích xuất trực tiếp từ lớp MainWindow.
        """
        path = [start_pos]; visited = {start_pos}; current_pos = start_pos
        for _ in range(int(max_len) - 1):
            x, y = current_pos; neighbors = []
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy; neighbor = (nx, ny)
                if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h): continue
                if neighbor not in editable_area: continue
                if neighbor not in all_occupied_points and neighbor not in visited: neighbors.append(neighbor)
            if not neighbors: break
            next_pos = random.choice(neighbors)
            path.append(next_pos); visited.add(next_pos); current_pos = next_pos
        return path
        
    def generate_hybrid_level(self, validator, active_layer, all_arrows_on_board, start_arrow_id, num_to_gen, avg_length):
        """
        Phiên bản tái cấu trúc của MainWindow.generate_hybrid_level.
        Loại bỏ các lệnh gọi GUI (statusBar, QApplication) và nhận các
        đối tượng (validator, active_layer) làm tham số.
        
        Trả về: (list_of_new_arrows, last_arrow_id, status_message)
        """
        logger.info("Generating level in painted area... (This will be slow)")
        
        if not active_layer:
            return [], start_arrow_id, "No active layer selected."
        
        editable_area = active_layer.editable_area
        if not editable_area:
            return [], start_arrow_id, "Active layer has no painted area to generate in."

        max_retries_per_arrow = 1000
        
        # 3. Tính toán ranh giới và độ lệch (offset) CỦA editable_area
        min_x = min(p[0] for p in editable_area); min_y = min(p[1] for p in editable_area)
        max_x = max(p[0] for p in editable_area); max_y = max(p[1] for p in editable_area)
        gen_offset_x = -min_x; gen_offset_y = -min_y
        gen_grid_w = max_x - min_x + 1; gen_grid_h = max_y - min_y + 1
        
        # 4. Dịch chuyển (shift) các đối tượng vào "Thế giới ảo"
        gen_editable_area = {(p[0] + gen_offset_x, p[1] + gen_offset_y) for p in editable_area}
        gen_arrows_on_board = []; gen_occupied_points = set()
        for arrow in all_arrows_on_board:
            is_in_area = False; shifted_points = []
            for p in arrow.points:
                if p in editable_area: is_in_area = True
                shifted_points.append((p[0] + gen_offset_x, p[1] + gen_offset_y))
            if is_in_area:
                virtual_arrow = Arrow(shifted_points, arrow.direction, arrow.layer_id, arrow.id, arrow.color)
                gen_arrows_on_board.append(virtual_arrow)
                for p_shifted, p_original in zip(shifted_points, arrow.points):
                    if p_original in editable_area: gen_occupied_points.add(p_shifted)
        
        newly_generated_arrows = []
        arrow_id_counter = start_arrow_id # Sử dụng ID được truyền vào
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
                    if pos not in gen_occupied_points: p2_candidates.append(pos)
                if not p2_candidates: break
                random.shuffle(p2_candidates)
                start_p2 = None; p1 = None; found_start_pair = False
                for p2_cand in p2_candidates:
                    p1_candidates = []
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        p1_cand = (p2_cand[0] + dx, p2_cand[1] + dy)
                        if p1_cand in gen_editable_area and p1_cand not in gen_occupied_points:
                            p1_candidates.append(p1_cand)
                    if p1_candidates:
                        p1 = random.choice(p1_candidates); start_p2 = p2_cand
                        found_start_pair = True; break
                if not found_start_pair: break

                temp_occupied = gen_occupied_points.union({p1}) 
                path_body = self._perform_random_walk(
                    start_p2, temp_occupied, gen_editable_area, 
                    gen_grid_w, gen_grid_h, 
                    max_len=max_walk_len - 1
                )
                
                path = [p1] + path_body
                
                # === MODIFICATION START: Lọc độ dài ===
                if not (min_len <= len(path) <= max_len):
                    continue # Path quá ngắn hoặc quá dài -> Hủy, thử lại
                # === MODIFICATION END ===
                    
                direction = (p1[0] - start_p2[0], p1[1] - start_p2[1])
                temp_arrow = Arrow(path, direction, active_layer.id, arrow_id_counter, default_color)

                hypothetical_board = gen_arrows_on_board + newly_generated_arrows + [temp_arrow]
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
                break # Thoát khỏi vòng lặp 'num_to_gen'

        if not newly_generated_arrows:
            return [], arrow_id_counter, "Generation complete, but 0 valid arrows found. Try again."
            
        final_arrows_to_add = []
        for arrow in newly_generated_arrows:
            original_points = [(p[0] - gen_offset_x, p[1] - gen_offset_y) for p in arrow.points]
            real_arrow = Arrow(original_points, arrow.direction, active_layer.id, arrow.id, arrow.color)
            final_arrows_to_add.append(real_arrow)
        
        status_msg = f"Successfully generated {len(final_arrows_to_add)} arrows!"
        logger.success(status_msg)
        
        return final_arrows_to_add, arrow_id_counter, status_msg
    

    # -------------------------------------------------------------------
    # --- PHẦN MỚI THÊM: LOGIC TẠO LEVEL NÂNG CAO ---
    # -------------------------------------------------------------------

    def _perform_advance_walk_2(self, start_pos, prev_pos, all_occupied_points, editable_area, 
                                gen_grid_w, gen_grid_h, max_len=30,
                                # Các tham số mới: Bỏ turn_probability
                                straight_weight=1.5,
                                left_weight=1.0,
                                right_weight=1.0,
                                max_turns=99):
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
        current_prev_pos = prev_pos # Theo dõi vị trí trước đó
        turn_count = 0

        # Mapping các loại di chuyển tới trọng số của chúng
        weights_map = {
            "straight": straight_weight,
            "left": left_weight,
            "right": right_weight
        }

        for _ in range(int(max_len) - 1):
            if turn_count >= max_turns:
                break # Đã đạt giới hạn quẹo

            # 1. Tính hướng đi hiện tại (current_pos - current_prev_pos)
            dx = current_pos[0] - current_prev_pos[0]
            dy = current_pos[1] - current_prev_pos[1]
            current_dir = (dx, dy)

            # 2. Phân loại các bước đi (Thẳng, Trái, Phải)
            straight_dir = current_dir
            left_dir = (-dy, dx)
            right_dir = (dy, -dx)

            possible_moves = {
                "straight": (current_pos[0] + straight_dir[0], current_pos[1] + straight_dir[1]),
                "left": (current_pos[0] + left_dir[0], current_pos[1] + left_dir[1]),
                "right": (current_pos[0] + right_dir[0], current_pos[1] + right_dir[1]),
            }

            # 3. Lọc các bước đi hợp lệ VÀ có trọng số > 0
            choices_list = [] # Sẽ chứa (neighbor, move_type)
            weights_list = [] # Sẽ chứa weight tương ứng

            for move_type, weight in weights_map.items():
                
                # Bỏ qua ngay nếu trọng số bằng 0 (hoặc âm)
                if weight <= 0:
                    continue
                
                # Lấy vị trí (pos) từ dict possible_moves
                pos = possible_moves.get(move_type)
                
                nx, ny = pos
                neighbor = (nx, ny)
                
                # Kiểm tra xem có hợp lệ không (giữ nguyên logic kiểm tra)
                if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h): continue
                if neighbor not in editable_area: continue
                if neighbor in all_occupied_points or neighbor in visited: continue

                # Nếu hợp lệ VÀ có trọng số, thêm vào danh sách
                choices_list.append((neighbor, move_type))
                weights_list.append(weight)

            # 4. Kiểm tra nếu bị kẹt
            if not choices_list:
                # Bị kẹt. Không còn đường đi hợp lệ HOẶC tất cả
                # các đường hợp lệ đều có trọng số <= 0.
                break 

            # 5. Chọn một bước đi (dựa trên trọng số)
            chosen_move, chosen_type = random.choices(choices_list, weights_list, k=1)[0]
            
            # 6. Cập nhật trạng thái
            if chosen_type != "straight":
                turn_count += 1

            path.append(chosen_move)
            visited.add(chosen_move)
            current_prev_pos = current_pos # Cập nhật
            current_pos = chosen_move
            
        return path

    def _perform_advanced_walk(self, start_pos, prev_pos, all_occupied_points, editable_area, 
                                gen_grid_w, gen_grid_h, max_len=30,
                                # Các tham số mới
                                turn_probability=0.5, 
                                straight_weight=1.5,
                                left_weight=1.0,
                                right_weight=1.0,
                                max_turns=99):
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
        current_prev_pos = prev_pos # Theo dõi vị trí trước đó
        turn_count = 0

        for _ in range(int(max_len) - 1):
            if turn_count >= max_turns:
                break # Đã đạt giới hạn quẹo

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
                "straight": (current_pos[0] + straight_dir[0], current_pos[1] + straight_dir[1]),
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
                if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h): continue
                if neighbor not in editable_area: continue
                if neighbor in all_occupied_points or neighbor in visited: continue

                # Nếu hợp lệ, thêm vào danh sách lựa chọn
                valid_moves.append((neighbor, move_type))
                
                # 4. Áp dụng trọng số (bias)
                if move_type == "straight":
                    weights.append(straight_weight) # Ưu tiên đi thẳng
                
                # Chỉ xem xét quẹo nếu tỉ lệ cho phép
                elif random.random() < turn_probability:
                    if move_type == "left":
                        weights.append(left_weight)
                    elif move_type == "right":
                        weights.append(right_weight)
                else:
                    weights.append(0.0) # Không muốn quẹo lần này

            # Xử lý trường hợp bị kẹt: nếu đi thẳng bị chặn và tỉ lệ quẹo = 0,
            # cho phép quẹo để tránh dừng lại quá sớm.
            if valid_moves and all(w <= 0 for w in weights):
                # Gán lại trọng số cơ bản nếu tất cả đều bằng 0
                new_weights = []
                for _, move_type in valid_moves:
                    if move_type == 'straight': new_weights.append(straight_weight)
                    elif move_type == 'left': new_weights.append(left_weight)
                    elif move_type == 'right': new_weights.append(right_weight)
                weights = new_weights
                # Đảm bảo không có trọng số âm hoặc 0 nếu vẫn còn đường
                if all(w <= 0 for w in weights):
                    weights = [1.0] * len(valid_moves)


            if not valid_moves or not any(w > 0 for w in weights):
                break # Bị kẹt

            # 5. Chọn một bước đi (dựa trên trọng số)
            chosen_move, chosen_type = random.choices(valid_moves, weights, k=1)[0]
            
            # 6. Cập nhật trạng thái
            if chosen_type != "straight":
                turn_count += 1

            path.append(chosen_move)
            visited.add(chosen_move)
            current_prev_pos = current_pos # Cập nhật
            current_pos = chosen_move
            
        return path

    def generate_hybrid_level_advanced(self, validator, active_layer, all_arrows_on_board, 
                                        start_arrow_id, num_to_gen, avg_length,
                                        # Các tham số mới
                                        turn_probability=0.5, 
                                        straight_weight=1.5,
                                        left_weight=1.0,
                                        right_weight=1.0,
                                        max_turns=5):
        """
        Phiên bản NÂNG CAO của hàm generate_hybrid_level.
        Sử dụng _perform_advanced_walk để tạo các mũi tên có hình dạng
        được kiểm soát hơn.
        
        Trả về: (list_of_new_arrows, last_arrow_id, status_message)
        """
        logger.info("Generating ADVANCED level in painted area... (This will be slow)")
        
        if not active_layer:
            return [], start_arrow_id, "No active layer selected."
        
        editable_area = active_layer.editable_area
        if not editable_area:
            return [], start_arrow_id, "Active layer has no painted area to generate in."

        max_retries_per_arrow = 100
        
        # 3. Tính toán ranh giới và độ lệch (offset) CỦA editable_area
        min_x = min(p[0] for p in editable_area); min_y = min(p[1] for p in editable_area)
        max_x = max(p[0] for p in editable_area); max_y = max(p[1] for p in editable_area)
        gen_offset_x = -min_x; gen_offset_y = -min_y
        gen_grid_w = max_x - min_x + 1; gen_grid_h = max_y - min_y + 1
        
        # 4. Dịch chuyển (shift) các đối tượng vào "Thế giới ảo"
        # (Logic này y hệt hàm gốc)
        gen_editable_area = {(p[0] + gen_offset_x, p[1] + gen_offset_y) for p in editable_area}
        gen_arrows_on_board = []; gen_occupied_points = set()
        for arrow in all_arrows_on_board:
            is_in_area = False; shifted_points = []
            for p in arrow.points:
                if p in editable_area: is_in_area = True
                shifted_points.append((p[0] + gen_offset_x, p[1] + gen_offset_y))
            if is_in_area:
                virtual_arrow = Arrow(shifted_points, arrow.direction, arrow.layer_id, arrow.id, arrow.color)
                gen_arrows_on_board.append(virtual_arrow)
                for p_shifted, p_original in zip(shifted_points, arrow.points):
                    if p_original in editable_area: gen_occupied_points.add(p_shifted)
        
        newly_generated_arrows = []
        arrow_id_counter = start_arrow_id
        default_color = active_layer.color
        
        min_len = max(2, int(avg_length * 0.5)) 
        max_len = int(avg_length * 1.0)
        max_walk_len = max_len 

        # for i in range(num_to_gen):
        for i in range(num_to_gen):
            # logger.info(f"Trying to generate (adv) arrow {i+1}/{num_to_gen}...")
            # found_arrow = False
            # for retry in range(max_retries_per_arrow):
            #     p2_candidates = []
            #     for pos in gen_editable_area:
            #         if pos not in gen_occupied_points: p2_candidates.append(pos)
            #     if not p2_candidates: break
            #     random.shuffle(p2_candidates)
            #     start_p2 = None; p1 = None; found_start_pair = False
            #     for p2_cand in p2_candidates:
            #         p1_candidates = []
            #         for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            #             p1_cand = (p2_cand[0] + dx, p2_cand[1] + dy)
            #             if p1_cand in gen_editable_area and p1_cand not in gen_occupied_points:
            #                 p1_candidates.append(p1_cand)
            #         if p1_candidates:
            #             p1 = random.choice(p1_candidates); start_p2 = p2_cand
            #             found_start_pair = True; break
            #     if not found_start_pair: break

            #     temp_occupied = gen_occupied_points.union({p1}) 
                
            #     # --- THAY ĐỔI CHÍNH NẰM Ở ĐÂY ---
            #     path_body = self._perform_advance_walk_2( # <--- GỌI HÀM WALK MỚI
            #         start_p2, 
            #         prev_pos=p1, # <--- Cung cấp vị trí trước đó
            #         all_occupied_points=temp_occupied, 
            #         editable_area=gen_editable_area, 
            #         gen_grid_w=gen_grid_w, 
            #         gen_grid_h=gen_grid_h, 
            #         max_len=max_walk_len - 1,
            #         # Truyền các tham số điều khiển
            #         # turn_probability=turn_probability,
            #         straight_weight=straight_weight,
            #         left_weight=left_weight,
            #         right_weight=right_weight,
            #         max_turns=max_turns
            #     )
            #     # --- HẾT THAY ĐỔI ---
                
            #     path = [p1] + path_body
                
            #     if not (min_len <= len(path) <= max_len):
            #         continue 
                    
            #     direction = (p1[0] - start_p2[0], p1[1] - start_p2[1])
            #     temp_arrow = Arrow(path, direction, active_layer.id, arrow_id_counter, default_color)

            #     hypothetical_board = gen_arrows_on_board + newly_generated_arrows + [temp_arrow]
            #     validator.clear_cache()
                
            #     is_solvable = validator.is_board_state_solvable(
            #         hypothetical_board, gen_grid_w, gen_grid_h
            #     )
            #     if is_solvable:
            #         newly_generated_arrows.append(temp_arrow)
            #         gen_occupied_points.update(path)
            #         arrow_id_counter += 1
            #         found_arrow = True
            #         break 

            found_arrow = False

            # 1. Tối ưu chọn điểm xuất phát (như câu trả lời trước)
            free_points_list = list(gen_editable_area - gen_occupied_points)
            if not free_points_list: break
            random.shuffle(free_points_list) # Shuffle 1 lần

            # Chỉ cần thử một vài điểm xuất phát, vì thuật toán Backtracking sẽ tự đào sâu
            # Giảm max_retries xuống còn 10-20 là đủ (thay vì 1000)
            for start_node in free_points_list[:20]: 
                
                # Khởi tạo path ban đầu với điểm start
                initial_path = [start_node]
                
                # Chọn ngẫu nhiên 1 điểm p1 hợp lệ để tạo hướng ban đầu
                # (Đoạn này giữ logic cũ để tìm p1)
                p1_candidates = []
                for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                    p1_cand = (start_node[0] + dx, start_node[1] + dy)
                    if p1_cand in gen_editable_area and p1_cand not in gen_occupied_points:
                        p1_candidates.append(p1_cand)
                        
                if not p1_candidates: continue
                p1 = random.choice(p1_candidates)
                initial_path.append(p1)

                # --- GỌI HÀM BACKTRACKING ---
                # Chúng ta muốn độ dài ngẫu nhiên trong khoảng min-max
                target_len = random.randint(min_len, max_len)
                
                generated_path = self._generate_arrow_backtracking(
                    current_path=initial_path,
                    target_length=target_len,
                    editable_area=gen_editable_area,
                    occupied_points=gen_occupied_points,
                    gen_grid_w=gen_grid_w, 
                    gen_grid_h=gen_grid_h,
                    straight_weight=straight_weight,
                    left_weight=left_weight,
                    right_weight=right_weight,
                    max_turns=max_turns,
                    current_turns=0
                )

                if generated_path:
                    # Tạo mũi tên tạm để check Validator toàn cục
                    direction = (generated_path[1][0] - generated_path[0][0], generated_path[1][1] - generated_path[0][1])
                    temp_arrow = Arrow(generated_path, direction, active_layer.id, arrow_id_counter, default_color)
                    
                    # Check Validator (Vẫn cần check để đảm bảo không chặn đường các ô trống còn lại)
                    hypothetical_board = gen_arrows_on_board + newly_generated_arrows + [temp_arrow]
                    validator.clear_cache()
                    if validator.is_board_state_solvable(hypothetical_board, gen_grid_w, gen_grid_h):
                        newly_generated_arrows.append(temp_arrow)
                        gen_occupied_points.update(generated_path)
                        arrow_id_counter += 1
                        found_arrow = True
                        break # Xong mũi tên này, qua mũi tên tiếp theo
            
            if not found_arrow:
                status_msg = f"Could not find valid arrow {i+1}. Stopping."
                logger.warning(status_msg)
                break 

        if not newly_generated_arrows:
            return [], arrow_id_counter, "Generation complete, but 0 valid arrows found. Try again."
            
        final_arrows_to_add = []
        for arrow in newly_generated_arrows:
            original_points = [(p[0] - gen_offset_x, p[1] - gen_offset_y) for p in arrow.points]
            real_arrow = Arrow(original_points, arrow.direction, active_layer.id, arrow.id, arrow.color)
            final_arrows_to_add.append(real_arrow)
        
        status_msg = f"Successfully generated {len(final_arrows_to_add)} arrows!"
        logger.info(status_msg)
        
        return final_arrows_to_add, arrow_id_counter, status_msg
    
    def _generate_arrow_backtracking(self, current_path, target_length, 
                                     editable_area, occupied_points, 
                                     gen_grid_w, gen_grid_h,
                                     straight_weight, left_weight, right_weight, 
                                     max_turns, current_turns):
        """
        Hàm đệ quy để sinh mũi tên theo cơ chế Quay lui (Backtracking).
        Trả về Path hoàn chỉnh nếu thành công, hoặc None nếu thất bại.
        """
        # 1. ĐIỀU KIỆN DỪNG (THÀNH CÔNG)
        # Nếu đã đạt độ dài mong muốn (hoặc nằm trong khoảng cho phép)
        if len(current_path) >= target_length:
            return current_path

        # 2. LẤY VỊ TRÍ HIỆN TẠI VÀ TRƯỚC ĐÓ
        current_pos = current_path[-1]
        # Nếu mới có 1 điểm, giả lập điểm "ảo" để có hướng ban đầu
        prev_pos = current_path[-2] if len(current_path) >= 2 else (current_pos[0], current_pos[1]-1)

        # 3. TÍNH TOÁN CÁC NƯỚC ĐI TIẾP THEO (MOVES)
        dx = current_pos[0] - prev_pos[0]
        dy = current_pos[1] - prev_pos[1]
        
        # Định nghĩa 3 hướng tương đối
        moves = [
            {"type": "straight", "pos": (current_pos[0] + dx, current_pos[1] + dy), "weight": straight_weight},
            {"type": "left",     "pos": (current_pos[0] - dy, current_pos[1] + dx), "weight": left_weight},
            {"type": "right",    "pos": (current_pos[0] + dy, current_pos[1] - dx), "weight": right_weight}
        ]

        # 4. LỌC VÀ SẮP XẾP CÁC NƯỚC ĐI
        valid_moves = []
        for move in moves:
            # Kiểm tra biên và vật cản
            nx, ny = move["pos"]
            if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h): continue
            if (nx, ny) not in editable_area: continue
            if (nx, ny) in occupied_points: continue
            if (nx, ny) in current_path: continue # Không được tự cắn đuôi mình

            # Kiểm tra giới hạn Turn (Quẹo)
            new_turns = current_turns + (1 if move["type"] != "straight" else 0)
            if new_turns > max_turns: continue

            # Thêm yếu tố ngẫu nhiên vào weight để không phải lúc nào cũng đi thẳng tắp
            # Randomize weight một chút: weight * random(0.8 -> 1.2)
            adjusted_weight = move["weight"] * random.uniform(0.8, 1.2)
            valid_moves.append((adjusted_weight, move["pos"], new_turns))

        # Sắp xếp: Ưu tiên nước đi có weight cao nhất trước (Greedy DFS)
        # Điều này giúp giữ "Style" (ví dụ ưu tiên đi thẳng)
        valid_moves.sort(key=lambda x: x[0], reverse=True)

        # 5. ĐỆ QUY (THỬ VÀ QUAY LUI)
        for _, next_pos, next_turn_count in valid_moves:
            
            # --- Thử bước tới ---
            current_path.append(next_pos)
            
            # Gọi đệ quy
            result = self._generate_arrow_backtracking(
                current_path, target_length, 
                editable_area, occupied_points, 
                gen_grid_w, gen_grid_h,
                straight_weight, left_weight, right_weight,
                max_turns, next_turn_count
            )

            # Nếu tìm thấy đường thành công ở nhánh dưới, trả về ngay
            if result is not None:
                return result
            
            # --- Quay lui (Backtrack) ---
            # Nếu nhánh này thất bại (không đi tiếp được đến target_length),
            # xóa điểm vừa thêm và thử move tiếp theo trong vòng lặp
            current_path.pop()

        # Nếu thử hết các hướng mà vẫn bế tắc -> Trả về None (Báo thất bại cho bước trước)
        return None