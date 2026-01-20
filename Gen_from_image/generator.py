# File: generator.py
# Cập nhật:
# 1. Lấy min_width, max_width từ args.
# 2. Truyền vào validator.
# 3. Logic retry (tạo lại arrow) đã có sẵn trong vòng lặp 'retry', không cần sửa đổi cấu trúc.

import random
import progressbar
from validator import Validator
from helper import Arrow, Args
from loguru import logger

class HybridLevelGeneratorTestable:
    def __init__(self, args: Args):
        self.progress_bar = progressbar.ProgressBar()
        self.args = args

    def _perform_random_walk(self, start_pos, all_occupied_points, editable_area, gen_grid_w, gen_grid_h, max_len=30):
        path = [start_pos]
        visited = {start_pos}
        current_pos = start_pos
        for _ in range(int(max_len) - 1):
            x, y = current_pos
            neighbors = []
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx, ny = x + dx, y + dy
                neighbor = (nx, ny)
                if not (0 <= nx < gen_grid_w and 0 <= ny < gen_grid_h): continue
                if neighbor not in editable_area: continue
                if neighbor not in all_occupied_points and neighbor not in visited:
                    neighbors.append(neighbor)
            if not neighbors: break
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
        logger.info(f"Generating level in painted area...")
        if not active_layer: return [], start_arrow_id, "No active layer."
        editable_area = active_layer.editable_area
        if not editable_area: return [], start_arrow_id, "No editable area."
        
        min_x = min(p[0] for p in editable_area)
        min_y = min(p[1] for p in editable_area)
        max_x = max(p[0] for p in editable_area)
        max_y = max(p[1] for p in editable_area)
        gen_offset_x = -min_x
        gen_offset_y = -min_y
        gen_grid_w = max_x - min_x + 1
        gen_grid_h = max_y - min_y + 1
        gen_editable_area = {(p[0] + gen_offset_x, p[1] + gen_offset_y) for p in editable_area}
        
        gen_arrows_on_board = []
        gen_occupied_points = set()
        for arrow in all_arrows_on_board:
            is_in_area = False
            shifted_points = []
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

        # [UPDATE] Lấy config width từ Args
        # Mặc định là None (không giới hạn) nếu không có trong args
        cfg_min_width = getattr(self.args, 'min_width', 5)
        cfg_max_width = getattr(self.args, 'max_width', 10)

        logger.debug(f"DEBUG CHECK: Min={cfg_min_width}, Max={cfg_max_width}")

        self.progress_bar = progressbar.ProgressBar(maxval=num_to_gen)
        self.progress_bar.start()
        max_retries_per_arrow = 1000

        for i in range(num_to_gen):
            self.progress_bar.update(i + 1)
            found_arrow = False
            
            # --- VÒNG LẶP RETRY ---
            # Nếu generate thất bại (do va chạm HOẶC do width constraint),
            # code sẽ quay lại đầu vòng lặp này để thử tạo arrow mới.
            # Dữ liệu `newly_generated_arrows` (các arrow đã tạo trước đó) vẫn được giữ nguyên.
            for retry in range(max_retries_per_arrow):
                p2_candidates = [pos for pos in gen_editable_area if pos not in gen_occupied_points]
                if not p2_candidates: break
                random.shuffle(p2_candidates)
                start_p2 = None
                p1 = None
                found_start_pair = False
                for p2_cand in p2_candidates:
                    p1_candidates = []
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        p1_cand = (p2_cand[0] + dx, p2_cand[1] + dy)
                        if p1_cand in gen_editable_area and p1_cand not in gen_occupied_points:
                            p1_candidates.append(p1_cand)
                    if p1_candidates:
                        p1 = random.choice(p1_candidates)
                        start_p2 = p2_cand
                        found_start_pair = True
                        break
                if not found_start_pair: break

                temp_occupied = gen_occupied_points.union({p1})
                path_body = self._perform_random_walk(
                    start_p2, temp_occupied, gen_editable_area, gen_grid_w, gen_grid_h, max_len=max_walk_len - 1
                )
                path = [p1] + path_body
                if not (min_len <= len(path) <= max_len): continue

                direction = (p1[0] - start_p2[0], p1[1] - start_p2[1])
                temp_arrow = Arrow(path, direction, active_layer.id, arrow_id_counter, default_color)

                # --- CHECK GLOBAL CONSTRAINT ---
                hypothetical_board = gen_arrows_on_board + newly_generated_arrows
                validator.clear_cache()
                
                is_valid = validator.check_global_constraints(
                    hypothetical_board, temp_arrow, gen_grid_w, gen_grid_h, 
                    min_width=cfg_min_width, 
                    max_width=cfg_max_width
                )
                
                if is_valid:
                    newly_generated_arrows.append(temp_arrow)
                    gen_occupied_points.update(path)
                    arrow_id_counter += 1
                    found_arrow = True
                    break # Break retry loop -> Move to next arrow
                
                # Nếu is_valid == False: Vòng lặp for retry tiếp tục chạy -> Tạo arrow khác

            if not found_arrow:
                logger.warning(f"Could not find valid arrow {i+1}. Stopping.")
                break

        if not newly_generated_arrows:
             return [], arrow_id_counter, "Generation complete, but 0 valid arrows found."
        
        final_arrows_to_add = []
        for arrow in newly_generated_arrows:
            original_points = [(p[0] - gen_offset_x, p[1] - gen_offset_y) for p in arrow.points]
            real_arrow = Arrow(original_points, arrow.direction, active_layer.id, arrow.id, arrow.color)
            final_arrows_to_add.append(real_arrow)

        return final_arrows_to_add, arrow_id_counter, f"Successfully generated {len(final_arrows_to_add)} arrows!"

    def _perform_advance_walk_2(self, start_pos, prev_pos, all_occupied_points, editable_area, gen_grid_w, gen_grid_h, max_len=30, straight_weight=1.5, left_weight=1.0, right_weight=1.0, max_turns=99):
         path = [start_pos]
         visited = {start_pos}
         current_pos = start_pos
         current_prev_pos = prev_pos
         turn_count = 0
         weights_map = {"straight": straight_weight, "left": left_weight, "right": right_weight}
         for _ in range(int(max_len) - 1):
            if turn_count >= max_turns: break
            dx = current_pos[0] - current_prev_pos[0]
            dy = current_pos[1] - current_prev_pos[1]
            current_dir = (dx, dy)
            straight_dir = current_dir
            left_dir = (-dy, dx)
            right_dir = (dy, -dx)
            possible_moves = {
                "straight": (current_pos[0] + straight_dir[0], current_pos[1] + straight_dir[1]),
                "left": (current_pos[0] + left_dir[0], current_pos[1] + left_dir[1]),
                "right": (current_pos[0] + right_dir[0], current_pos[1] + right_dir[1]),
            }
            choices_list = []
            weights_list = []
            for move_type, weight in weights_map.items():
                if weight <= 0: continue
                pos = possible_moves.get(move_type)
                if not (0 <= pos[0] < gen_grid_w and 0 <= pos[1] < gen_grid_h): continue
                if pos not in editable_area: continue
                if pos in all_occupied_points or pos in visited: continue
                choices_list.append((pos, move_type))
                weights_list.append(weight)
            if not choices_list: break
            chosen_move, chosen_type = random.choices(choices_list, weights_list, k=1)[0]
            if chosen_type != "straight": turn_count += 1
            path.append(chosen_move)
            visited.add(chosen_move)
            current_prev_pos = current_pos
            current_pos = chosen_move
         return path

    def generate_hybrid_level_advanced(
        self,
        validator: Validator,
        active_layer,
        all_arrows_on_board,
        start_arrow_id,
        num_to_gen,
        avg_length,
        turn_probability=0.5,
        straight_weight=1.5,
        left_weight=1.0,
        right_weight=1.0,
        max_turns=5,
    ):
        level_name = "unknown"
        if hasattr(self.args, "alter_item_name"): level_name = self.args.alter_item_name
        logger.debug(f"Lv: {level_name} | Generating ADVANCED level...")
        if not active_layer: return [], start_arrow_id, "No active layer."
        editable_area = active_layer.editable_area
        if not editable_area: return [], start_arrow_id, "No editable area."
        
        min_x = min(p[0] for p in editable_area)
        min_y = min(p[1] for p in editable_area)
        max_x = max(p[0] for p in editable_area)
        max_y = max(p[1] for p in editable_area)
        gen_offset_x = -min_x
        gen_offset_y = -min_y
        gen_grid_w = max_x - min_x + 1
        gen_grid_h = max_y - min_y + 1
        gen_editable_area = {(p[0] + gen_offset_x, p[1] + gen_offset_y) for p in editable_area}
        gen_arrows_on_board = []
        gen_occupied_points = set()
        for arrow in all_arrows_on_board:
            is_in_area = False
            shifted_points = []
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

        # [UPDATE] Lấy config width
        cfg_min_width = getattr(self.args, 'min_width', 3)
        cfg_max_width = getattr(self.args, 'max_width', 5)

        for i in range(num_to_gen):
            # logger.info(f"Trying to generate (adv) arrow {i+1}/{num_to_gen}...")
            found_arrow = False
            
            # --- VÒNG LẶP RETRY ---
            for retry in range(100):
                p2_candidates = [pos for pos in gen_editable_area if pos not in gen_occupied_points]
                if not p2_candidates: break
                random.shuffle(p2_candidates)
                start_p2 = None
                p1 = None
                found_start_pair = False
                for p2_cand in p2_candidates:
                    p1_candidates = []
                    for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                        p1_cand = (p2_cand[0] + dx, p2_cand[1] + dy)
                        if p1_cand in gen_editable_area and p1_cand not in gen_occupied_points:
                            p1_candidates.append(p1_cand)
                    if p1_candidates:
                        p1 = random.choice(p1_candidates)
                        start_p2 = p2_cand
                        found_start_pair = True
                        break
                if not found_start_pair: break

                temp_occupied = gen_occupied_points.union({p1})
                path_body = self._perform_advance_walk_2(
                    start_p2, p1, temp_occupied, gen_editable_area, gen_grid_w, gen_grid_h,
                    max_len=max_walk_len - 1, straight_weight=straight_weight,
                    left_weight=left_weight, right_weight=right_weight, max_turns=max_turns
                )
                path = [p1] + path_body
                if not (min_len <= len(path) <= max_len): continue

                direction = (p1[0] - start_p2[0], p1[1] - start_p2[1])
                temp_arrow = Arrow(path, direction, active_layer.id, arrow_id_counter, default_color)

                # --- CHECK GLOBAL CONSTRAINT ---
                hypothetical_board = gen_arrows_on_board + newly_generated_arrows
                validator.clear_cache()
                
                is_valid = validator.check_global_constraints(
                    hypothetical_board, temp_arrow, gen_grid_w, gen_grid_h,
                    min_width=cfg_min_width,
                    max_width=cfg_max_width
                )

                if is_valid:
                    newly_generated_arrows.append(temp_arrow)
                    gen_occupied_points.update(path)
                    arrow_id_counter += 1
                    found_arrow = True
                    # logger.debug(f"Success state with: Min-{cfg_min_width}")
                    break # Break retry

        if not newly_generated_arrows:
            return [], arrow_id_counter, f"Lv: {level_name} | Generation complete, but 0 valid arrows."
        final_arrows_to_add = []
        for arrow in newly_generated_arrows:
            original_points = [(p[0] - gen_offset_x, p[1] - gen_offset_y) for p in arrow.points]
            real_arrow = Arrow(original_points, arrow.direction, active_layer.id, arrow.id, arrow.color)
            final_arrows_to_add.append(real_arrow)

        return final_arrows_to_add, arrow_id_counter, f"Lv: {level_name} | Successfully generated {len(final_arrows_to_add)} arrows!"

    def _generate_arrow_backtracking_strict(self, current_path, target_length, editable_area, occupied_points, gen_grid_w, gen_grid_h, weights, max_turns, current_turns, current_direction, validator, all_fixed_arrows):
         # Logic cũ, chưa được sử dụng
         return None