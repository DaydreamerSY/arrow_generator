# File: test_logic.py
# Unit test cho validator.py và generator.py

import unittest
import random

# Import các lớp từ các file đã trích xuất
from validator import Arrow, Validator

# Lớp Layer giả lập (mock object) cần thiết cho generator
class MockLayer:
    def __init__(self, layer_id, color, editable_area_set):
        self.id = layer_id
        self.color = color
        self.editable_area = editable_area_set # Phải là một set các (x, y)
        self.arrows = [] # Generator không dùng cái này, nhưng để cho đủ

# Phải import generator SAU khi định nghĩa MockLayer nếu nó cần
from generator import HybridLevelGeneratorTestable

# Định nghĩa một số màu giả lập
COLOR_BLUE = (0, 0, 255)
COLOR_RED = (255, 0, 0)

class TestValidatorLogic(unittest.TestCase):
    """Test các chức năng cốt lõi của lớp Validator."""

    def setUp(self):
        """Hàm này chạy trước mỗi test case."""
        self.validator = Validator()
        self.grid_w = 10
        self.grid_h = 10

    def tearDown(self):
        """Dọn dẹp sau mỗi test case."""
        self.validator.clear_cache()

    def test_can_arrow_exit_cleanly(self):
        """Kiểm tra logic một mũi tên có thể thoát hay không."""
        # Mũi tên A: (0,0) -> (1,0) -> (2,0)
        arrow_A = Arrow(points=[(0,0), (1,0), (2,0)], direction=(0,-1), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        # Mũi tên B: (0,2) -> (1,2)
        arrow_B = Arrow(points=[(0,2), (1,2)], direction=(0,1), layer_id=0, arrow_id=2, color=COLOR_RED)
        
        all_arrows = [arrow_A, arrow_B]
        
        # Test A: Bị B cản ở (0,2) -> Sai
        arrow_A_blocked = Arrow(points=[(0,0), (0,1), (0,2)], direction=(0,1), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        self.assertFalse(
            self.validator._can_arrow_exit_cleanly(arrow_A_blocked, [arrow_B], self.grid_w, self.grid_h)
        )
        
        # Test A: Không bị cản -> Đúng
        arrow_A_clear = Arrow(points=[(5,5), (5,4)], direction=(0,-1), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        self.assertTrue(
            self.validator._can_arrow_exit_cleanly(arrow_A_clear, [arrow_B], self.grid_w, self.grid_h)
        )
        
        # Test A: Bị cản bởi chính thân của nó -> Sai
        # Head (0,0), body (0,1), (0,2). Direction (0,1).
        # Nó sẽ cố đi tới (0,1) và va vào thân nó.
        arrow_A_self_block = Arrow(points=[(0,0), (0,1), (0,2)], direction=(0,1), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        # Thân của A là [(0,1), (0,2)]. Chướng ngại vật khác là [].
        self.assertFalse(
            self.validator._can_arrow_exit_cleanly(arrow_A_self_block, [], self.grid_w, self.grid_h)
        )

    def test_find_movable_arrows(self):
        """Kiểm tra tìm tất cả mũi tên di chuyển được."""
        # A: (0,0) -> (1,0), hướng (1,0) -> Bị B cản
        arrow_A = Arrow(points=[(0,0), (1,0)], direction=(1,0), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        # B: (2,0) -> (3,0), hướng (1,0) -> Tự do
        arrow_B = Arrow(points=[(2,0), (3,0)], direction=(1,0), layer_id=0, arrow_id=2, color=COLOR_RED)
        
        all_arrows = [arrow_A, arrow_B]
        movable = self.validator.find_movable_arrows(all_arrows, self.grid_w, self.grid_h)
        
        self.assertEqual(len(movable), 1)
        self.assertEqual(movable[0].id, 2) # Chỉ có mũi tên B di chuyển được

    def test_is_board_state_solvable_simple(self):
        """Test trường hợp đơn giản, giải được."""
        # A: (0,0), hướng (1,0)
        arrow_A = Arrow(points=[(0,0)], direction=(1,0), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        self.assertTrue(
            self.validator.is_board_state_solvable([arrow_A], self.grid_w, self.grid_h)
        )

    def test_is_board_state_solvable_unsolvable(self):
        """Test trường hợp bế tắc, không giải được."""
        # A: (0,0), hướng (1,0)
        arrow_A = Arrow(points=[(0,0)], direction=(1,0), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        # B: (1,0), hướng (-1,0)
        arrow_B = Arrow(points=[(1,0)], direction=(-1,0), layer_id=0, arrow_id=2, color=COLOR_RED)
        
        all_arrows = [arrow_A, arrow_B]
        self.assertFalse(
            self.validator.is_board_state_solvable(all_arrows, self.grid_w, self.grid_h)
        )

    def test_is_board_state_solvable_greedy(self):
        """Test logic Greedy (xóa tất cả)."""
        # A: (0,1) -> (1,1), hướng (1,0). Bị C cản.
        arrow_A = Arrow(points=[(0,1), (1,1)], direction=(1,0), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        # B: (0,0) -> (1,0), hướng (1,0). Bị C cản.
        arrow_B = Arrow(points=[(0,0), (1,0)], direction=(1,0), layer_id=0, arrow_id=2, color=COLOR_RED)
        # C: (2,0) -> (2,1), hướng (0,-1). TỰ DO.
        arrow_C = Arrow(points=[(2,0), (2,1)], direction=(0,-1), layer_id=0, arrow_id=3, color=COLOR_BLUE)
        
        # Logic cũ (xóa 1):
        # 1. Chỉ C giải được. Xóa C.
        # 2. Board còn A và B. Cả A và B đều tự do.
        # 3. Logic "Greedy" (xóa tất cả) cũng phải giải được.
        
        all_arrows = [arrow_A, arrow_B, arrow_C]
        self.assertTrue(
            self.validator.is_board_state_solvable(all_arrows, self.grid_w, self.grid_h)
        )

        # Trường hợp 2: A và B tự do, nhưng C (phía sau) bị A và B cản
        # A: (0,0), hướng (1,0). Tự do.
        arrow_A2 = Arrow(points=[(0,0)], direction=(1,0), layer_id=0, arrow_id=1, color=COLOR_BLUE)
        # B: (0,1), hướng (1,0). Tự do.
        arrow_B2 = Arrow(points=[(0,1)], direction=(1,0), layer_id=0, arrow_id=2, color=COLOR_RED)
        # C: (0,2), hướng (1,0). Bị A và B cản nếu chúng không di chuyển.
        arrow_C2 = Arrow(points=[(-1,0)], direction=(1,0), layer_id=0, arrow_id=3, color=COLOR_BLUE)
        
        # Logic Greedy:
        # 1. Tìm thấy A2 và B2 di chuyển được.
        # 2. Xóa A2 và B2 CÙNG LÚC.
        # 3. Board còn C2. C2 bây giờ tự do.
        # 4. Xóa C2.
        # 5. Board trống -> Solvable.
        all_arrows_2 = [arrow_A2, arrow_B2, arrow_C2]
        self.assertTrue(
            self.validator.is_board_state_solvable(all_arrows_2, self.grid_w, self.grid_h)
        )


class TestGeneratorLogic(unittest.TestCase):
    """Test logic tạo level của HybridLevelGeneratorTestable."""

    def setUp(self):
        self.generator = HybridLevelGeneratorTestable()
        self.validator = Validator() # Generator cần một validator thật
        
        # Tạo một vùng painted area giả lập 5x5
        self.editable_area_5x5 = set()
        for x in range(5):
            for y in range(5):
                self.editable_area_5x5.add((x, y))
        
        # Tạo một layer giả lập
        self.mock_layer = MockLayer(
            layer_id=0, 
            color=COLOR_BLUE, 
            editable_area_set=self.editable_area_5x5
        )
        
        # Cố định random seed để test có thể lặp lại
        random.seed(42)

    def tearDown(self):
        self.validator.clear_cache()

    def test_random_walk(self):
        """Test hàm phụ trợ _perform_random_walk."""
        occupied = {(0,0)} # Điểm (0,0) bị chiếm
        start_pos = (1,0)
        
        path = self.generator._perform_random_walk(
            start_pos=start_pos,
            all_occupied_points=occupied,
            editable_area=self.editable_area_5x5,
            gen_grid_w=5,
            gen_grid_h=5,
            max_len=10
        )
        
        self.assertIn(start_pos, path) # Phải chứa điểm bắt đầu
        self.assertNotIn((0,0), path) # Không được đi vào điểm bị chiếm
        for p in path:
            self.assertIn(p, self.editable_area_5x5) # Mọi điểm phải trong vùng
        
        self.assertLessEqual(len(path), 10) # Không được dài hơn max_len

    def test_generate_hybrid_level_simple(self):
        """Test hàm generate_hybrid_level chính."""
        
        # Tạo một vùng 10x10 ở tọa độ (10, 10) -> (19, 19)
        # để test logic "shift board"
        editable_area_shifted = set()
        for x in range(10, 20):
            for y in range(10, 20):
                editable_area_shifted.add((x, y))
        
        shifted_layer = MockLayer(0, COLOR_RED, editable_area_shifted)
        
        # Yêu cầu tạo 2 mũi tên, độ dài trung bình 5
        num_to_gen = 2
        avg_len = 5
        
        new_arrows, new_id_counter, status = self.generator.generate_hybrid_level(
            validator=self.validator,
            active_layer=shifted_layer,
            all_arrows_on_board=[], # Không có mũi tên nào có sẵn
            start_arrow_id=0,
            num_to_gen=num_to_gen,
            avg_length=avg_len
        )
        
        # 1. Kiểm tra kết quả trả về
        self.assertEqual(len(new_arrows), num_to_gen) # Phải tạo đủ 2 mũi tên
        self.assertEqual(new_id_counter, 2) # ID counter phải tăng lên 2
        self.assertIn("Successfully generated", status) # Status msg phải đúng

        # 2. Kiểm tra các mũi tên đã tạo
        all_points_generated = set()
        for arrow in new_arrows:
            self.assertEqual(arrow.id, 0 if arrow == new_arrows[0] else 1)
            self.assertEqual(arrow.color, COLOR_RED)
            
            for p in arrow.points:
                # Quan trọng: Điểm P phải nằm trong editable_area_shifted GỐC
                self.assertIn(p, editable_area_shifted)
                
                # Quan trọng: Điểm P không được trùng lặp
                self.assertNotIn(p, all_points_generated)
                all_points_generated.add(p)
                
            # Kiểm tra độ dài (min = 0.5*5 = 2, max = 1.5*5 = 7)
            self.assertTrue(2 <= len(arrow.points) <= 7)

# Đây là cách chạy test khi thực thi file trực tiếp
if __name__ == '__main__':
    unittest.main()