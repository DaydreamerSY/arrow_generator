# File: cli_generator.py
# ĐÃ CẬP NHẬT: Lặp lại ở min_length cho đến khi không thể tạo thêm.

import json
import sys
import argparse
from collections import defaultdict
from loguru import logger

# Import logic đã trích xuất
from validator import Validator, Arrow
from generator import HybridLevelGeneratorTestable
from helper import Args

# --- LỚP GIẢ LẬP (MOCK OBJECT) ---
class MockLayer:
    def __init__(self, layer_id, color, editable_area_set):
        self.id = layer_id
        self.color = color 
        self.editable_area = editable_area_set
        self.arrows = []

# --- HÀM HELPER (Không thay đổi) ---
class ClientGenerator:
    def __init__(self, fake_args: Args):
        self.args = fake_args
        pass

    def load_board_from_file(self, filepath):
        """Đọc file .txt và chuyển nó thành một set các tọa độ (x, y)."""
        logger.info(f"--- Đang tải board từ: {filepath} ---")
        editable_area = set()
        try:
            with open(filepath, 'r') as f:
                for y, line in enumerate(f):
                    line = line.strip().upper()
                    for x, char in enumerate(line):
                        if char == '1' or char == 'X':
                            editable_area.add((x, y))
            
            if not editable_area:
                logger.info("Lỗi: Không tìm thấy ô nào được vẽ ('1' hoặc 'X') trong file input.")
                return None
                
            logger.info(f"Đã tải thành công {len(editable_area)} ô 'editable'.")
            return editable_area
            
        except FileNotFoundError:
            logger.error(f"Lỗi: Không tìm thấy file input '{filepath}'.")
            return None
        except Exception as e:
            logger.error(f"Lỗi khi đọc file: {e}")
            return None

    def suggest_arrow_count(self, total_cells, avg_length):
        """Hàm logic được trích ra từ UI để đề xuất số lượng mũi tên."""
        if avg_length <= 0:
            return 1
        suggested_count = round(total_cells / avg_length)
        if suggested_count == 0: 
            suggested_count = 1
        return suggested_count

    def save_arrows_to_json(self, all_arrows, filename, args):
        """Lưu danh sách các mũi tên ra file JSON chuẩn của game."""
        logger.info(f"--- Đang lưu kết quả ra: {filename} ---")
        all_arrow_points = {p for arr in all_arrows for p in arr.points}
        if not all_arrow_points:
            logger.info("Không có mũi tên nào được tạo để lưu.")
            return

        min_x = min(p[0] for p in all_arrow_points)
        min_y = min(p[1] for p in all_arrow_points)
        max_x = max(p[0] for p in all_arrow_points)
        max_y = max(p[1] for p in all_arrow_points)
        
        offset_x = -min_x
        offset_y = -min_y
        new_x_size = max_x - min_x + 1
        new_y_size = max_y - min_y + 1

        if hasattr(args, 'template_name'):
            output_data = {"XSize": new_x_size, "YSize": new_y_size, "PictureName": args.template_name.replace(".png", ""), "LevelID": args.level_id,"Arrows": []}
        else:
            output_data = {"XSize": new_x_size, "YSize": new_y_size, "PictureName": args.item_name,"Arrows": []}
        
        for arrow in all_arrows:
            if not arrow.points: continue
            new_points = [(p[0] + offset_x, p[1] + offset_y) for p in arrow.points]
            indices = [y * new_x_size + x for x, y in new_points]
            tail_x = new_points[0][0]; tail_y = new_points[0][1]
            bend_count = 0
            if len(arrow.points) >= 3:
                for k in range(len(arrow.points) - 2):
                    p1, p2, p3 = arrow.points[k], arrow.points[k+1], arrow.points[k+2]
                    dir1 = (p2[0] - p1[0], p2[1] - p1[1])
                    dir2 = (p3[0] - p2[0], p3[1] - p2[1])
                    if dir1 != dir2: bend_count += 1
            arrow_dict = {
                "Dx": arrow.direction[0], "Dy": arrow.direction[1], "X": tail_x, 
                "Y": tail_y, "Indices": indices, "BendCount": bend_count
            }
            output_data["Arrows"].append(arrow_dict)

        try:
            with open(filename, 'w') as f:
                json.dump(output_data, f, separators=(',', ':'))
            logger.info(f"Đã lưu thành công level {new_x_size}x{new_y_size} với {len(all_arrows)} mũi tên.")
        except Exception as e:
            logger.info(f"Lỗi khi lưu file JSON: {e}")

    def _get_unicode_body_char(self, p_prev, p_curr, p_next):
        """
        Hàm trợ giúp để xác định đúng ký tự Unicode (─, │, ┌, ┐, └, ┘)
        bằng cách xem xét 3 điểm.
        """
        # 1. Tính toán vector "vào" (từ prev -> curr)
        dx_in = p_curr[0] - p_prev[0]
        dy_in = p_curr[1] - p_prev[1]
        
        # 2. Tính toán vector "ra" (từ curr -> next)
        dx_out = p_next[0] - p_curr[0]
        dy_out = p_next[1] - p_curr[1]

        # 3. Trường hợp đi thẳng
        if (dx_in != 0 and dx_out != 0): return '─' # Ngang
        if (dy_in != 0 and dy_out != 0): return '│' # Dọc

        # 4. Trường hợp góc
        # (dx_in, dy_in) -> (dx_out, dy_out)
        
        # Lên -> Phải or (Trái -> Xuống)
        if (dy_in == -1 and dx_out == 1) or (dx_in == -1 and dy_out == 1):
            return '┌'
        
        # Phải -> Lên or (Xuống -> Trái)
        if (dx_in == 1 and dy_out == -1) or (dy_in == 1 and dx_out == -1):
            return '┘'
        
        # Lên -> Trái or (Phải -> Xuống)
        if (dy_in == -1 and dx_out == -1) or (dx_in == 1 and dy_out == 1):
            return '┐'

        # Xuống -> Phải or (Trái -> Lên)
        if (dy_in == 1 and dx_out == 1) or (dx_in == -1 and dy_out == -1):
            return '└'
        
        # Fallback (không nên xảy ra với di chuyển 8 hướng)
        return '+'

    def visualize_in_console(self, arrows, editable_area):
        """(Tùy chọn) In một bản đồ ASCII của kết quả ra console."""
        logger.info("--- Bản đồ kết quả (Unicode) ---")
        points_map = defaultdict(lambda: ' ')
        
        # 1. Tính toán ranh giới
        all_points_for_bounds = set(editable_area)
        for arr in arrows: all_points_for_bounds.update(arr.points)
        if not all_points_for_bounds:
            logger.info("(Trống)"); return
            
        min_x = min(p[0] for p in all_points_for_bounds) - 1
        max_x = max(p[0] for p in all_points_for_bounds) + 1
        min_y = min(p[1] for p in all_points_for_bounds) - 1
        max_y = max(p[1] for p in all_points_for_bounds) + 1

        # 2. Vẽ khu vực edit (luôn vẽ cái này trước)
        for y in range(min_y, max_y + 1):
            for x in range(min_x, max_x + 1):
                if (x,y) in editable_area: points_map[(x,y)] = ' ' 
        
        # 3. Vẽ các mũi tên
        for arr in arrows:
            path = arr.points
            n = len(path)
            
            if n == 0: continue

            # --- VẼ THÂN (BODY) MŨI TÊN (từ điểm 1 đến n-2) ---
            # Chúng ta cần 3 điểm để vẽ 1 ký tự,
            # nên vòng lặp này chỉ chạy cho các điểm ở giữa.
            for i in range(1, n - 1):
                p_prev = path[i-1]
                p_curr = path[i]
                p_next = path[i+1]
                
                # Bỏ qua nếu có di chuyển chéo (logic này chỉ xử lý 4 hướng)
                if (p_prev[0] != p_curr[0] and p_prev[1] != p_curr[1]) or \
                   (p_curr[0] != p_next[0] and p_curr[1] != p_next[1]):
                   points_map[p_curr] = '*' # Dùng '*' cho đường chéo
                   continue
                   
                char = self._get_unicode_body_char(p_prev, p_curr, p_next)
                points_map[p_curr] = char

            # --- VẼ ĐUÔI (TAIL) (điểm cuối cùng n-1) ---
            # Đuôi chỉ cần biết hướng đi từ điểm áp chót
            if n > 1:
                p_tail = path[n-1]
                p_prev = path[n-2]
                
                # Kiểm tra xem có ghi đè lên đầu mũi tên khác không
                # (Chúng ta muốn đầu mũi tên luôn thắng)
                if points_map[p_tail] not in ['↑', '↓', '←', '→']:
                    dx = p_tail[0] - p_prev[0]
                    if dx != 0:
                        points_map[p_tail] = '─' # Ngang
                    else:
                        points_map[p_tail] = '│' # Dọc

            # --- VẼ ĐẦU (HEAD) (điểm 0) ---
            # Vẽ sau cùng để đảm bảo nó ghi đè lên mọi thứ
            head = path[0]; d = arr.direction
            if d == (0, -1): char = '↑'
            elif d == (0, 1): char = '↓'
            elif d == (-1, 0): char = '←'
            elif d == (1, 0): char = '→'
            else: char = 'O' # Chéo
            
            points_map[head] = char
        
        # 4. In kết quả ra console
        for y in range(min_y, max_y + 1):
            line = ""
            for x in range(min_x, max_x + 1): 
                line += points_map[(x,y)]
            logger.info(line)

    def excute(self):
        # args = FakeParser({
        #     "input_file": "1_board_test\\my_board.txt",
        #     "output_file": "2_result_test\\result.json",
        #     "start_length": 16,
        #     "length_step": 2,
        #     "min_length": 4,
        # })

        # client_generator = ClientGenerator()

        # 1. Tải board (chỉ một lần)
        editable_area = self.load_board_from_file(self.args.input_file)
        if editable_area is None:
            sys.exit(1)
        
        total_editable_cells = len(editable_area)
        logger.info(f"Tổng số ô có thể vẽ: {total_editable_cells}")

        # 2. Khởi tạo trạng thái cho vòng lặp
        all_generated_arrows = [] 
        # current_arrow_id = self.args.id
        current_arrow_id = 0
        current_length = self.args.start_length
        
        validator = Validator()
        generator = HybridLevelGeneratorTestable()
        mock_color = (0, 82, 204)

        # 3. Bắt đầu vòng lặp generator
        # Vòng lặp sẽ tiếp tục miễn là length >= min_length
        while current_length >= self.args.min_length:
            # logger.info("\n" + "="*40)
            logger.info(f"--- BẮT ĐẦU VÒNG LẶP (Length = {current_length}) ---")
            
            # 3a. Tính toán các ô còn trống
            occupied_cells = {p for arr in all_generated_arrows for p in arr.points}
            available_cells = editable_area.difference(occupied_cells)
            num_available_cells = len(available_cells)

            logger.info(f"Ô đã chiếm: {len(occupied_cells)} / Ô còn trống: {num_available_cells}")
            
            # 3b. Kiểm tra điều kiện dừng (nếu không còn ô trống)
            if num_available_cells == 0:
                logger.info("Toàn bộ board đã được lấp đầy. Dừng generator.")
                break # Thoát khỏi vòng lặp while

            # 3c. Đề xuất số lượng mũi tên cho vòng này
            num_to_gen = self.suggest_arrow_count(num_available_cells, current_length)
            logger.info(f"Đề xuất tạo {num_to_gen} mũi tên cho vòng lặp này...")
            
            # 3d. Tạo MockLayer
            mock_layer = MockLayer(0, mock_color, editable_area)

            newly_found_arrows, new_id_counter, status_msg = "", "", ""

            if self.args.generate_mode == "basic":

                # 3e. Chạy Generator
                newly_found_arrows, new_id_counter, status_msg = generator.generate_hybrid_level(
                    validator=validator,
                    active_layer=mock_layer,
                    all_arrows_on_board=all_generated_arrows, 
                    start_arrow_id=current_arrow_id,          
                    num_to_gen=num_to_gen,
                    avg_length=current_length
                )
            
            elif self.args.generate_mode == "advance":
                # 3e. Chạy Generator Advance
                newly_found_arrows, new_id_counter, status_msg = generator.generate_hybrid_level_advanced(
                    validator=validator,
                    active_layer=mock_layer,
                    all_arrows_on_board=all_generated_arrows, 
                    start_arrow_id=current_arrow_id,          
                    num_to_gen=num_to_gen,
                    avg_length=current_length,
                    # Các tham số mới
                    turn_probability=self.args.turn_probability, 
                    straight_weight=self.args.straight_weight,
                    left_weight=self.args.left_weight,
                    right_weight=self.args.right_weight,
                    max_turns=self.args.max_turns
                )
            
            logger.info(f"Kết quả vòng lặp: {status_msg}")

            # === MODIFICATION START: Logic lặp lại tại min_length ===
            
            if newly_found_arrows:
                # 3f. Cập nhật trạng thái
                all_generated_arrows.extend(newly_found_arrows)
                current_arrow_id = new_id_counter # Cập nhật ID cho vòng lặp tiếp theo
                
                # 3g. Quyết định độ dài tiếp theo
                # CHỈ giảm độ dài nếu chúng ta CHƯA ở mức tối thiểu
                if current_length > self.args.min_length:
                    logger.info(f"Giảm độ dài từ {current_length}...")
                    current_length -= self.args.length_step
                    # Đảm bảo không bị "hụt" (overshoot)
                    if current_length < self.args.min_length:
                        current_length = self.args.min_length
                    logger.info(f"Độ dài vòng tiếp theo: {current_length}")
                else:
                    # Nếu current_length == min_length,
                    # KHÔNG LÀM GÌ CẢ. Vòng lặp while sẽ tự động 
                    # chạy lại với CÙNG một min_length.
                    logger.info(f"Tiếp tục lặp lại ở độ dài tối thiểu ({current_length})...")
                    
            else:
                # 3f. Không tìm thấy mũi tên nào
                logger.info("Không thể tạo thêm mũi tên ở độ dài này.")
                
                # 3g. Quyết định độ dài tiếp theo
                # Nếu chúng ta đã ở mức tối thiểu VÀ không thể tạo thêm,
                # thì đã đến lúc DỪNG HẲN.
                if current_length == self.args.min_length:
                    logger.info("Đã đạt độ dài tối thiểu và không thể tạo thêm. Dừng.")
                    break # Thoát khỏi vòng lặp while
                else:
                    # Nếu chưa ở mức tối thiểu, cứ giảm độ dài
                    logger.info(f"Giảm độ dài từ {current_length}...")
                    current_length -= self.args.length_step
                    if current_length < self.args.min_length:
                        current_length = self.args.min_length
                    logger.info(f"Độ dài vòng tiếp theo: {current_length}")

            # === MODIFICATION END ===
        
        # 4. Kết thúc vòng lặp
        # logger.info("\n" + "="*40)
        logger.info("--- ĐÃ HOÀN TẤT TẤT CẢ CÁC VÒNG LẶP ---")
        logger.info(f"Tổng cộng đã tạo: {len(all_generated_arrows)} mũi tên.")
        
        occupied_cells = {p for arr in all_generated_arrows for p in arr.points}
        fill_percent = (len(occupied_cells) / total_editable_cells) * 100
        logger.info(f"Đã lấp đầy {len(occupied_cells)} / {total_editable_cells} ô ({fill_percent:.1f}%)")

        # 5. Lưu và hiển thị kết quả (chỉ một lần)
        if all_generated_arrows:
            self.save_arrows_to_json(all_generated_arrows, self.args.output_file, self.args)
            self.visualize_in_console(all_generated_arrows, editable_area)
        else:
            logger.info("Không có mũi tên nào được tạo.")

if __name__ == "__main__":


    # args = FakeParser({
    #     "input_file": "1_board_test/my_board.txt",
    #     "output_file": "2_result_test/result.json",
    #     "start_length": 16,
    #     "length_step": 2,
    #     "min_length": 4,
    # })

    # args = Args()
    # args.input_file = "1_board_test/my_board.txt"
    # args.output_file = "2_result_test/result.json"
    # args.start_length = 16
    # args.length_step = 2
    # args.min_length = 4

    # client_generator = ClientGenerator(args)
    # client_generator.excute()

    pass

    


# python3 cli_generator.py 1_board_test/my_board.txt 2_result_test/result.json --start_length 20 --length_step 2
# python3 render_generated.py