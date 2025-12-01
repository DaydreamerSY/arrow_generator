import os
import json
import matplotlib.pyplot as plt
import random
from PIL import Image, ImageDraw
from loguru import logger

# ================= CONFIG =================
# Các đường dẫn mặc định (có thể bị ghi đè bởi pipeline)
INPUT_JSON = "2_result_test/result.json" 
OUTPUT_IMAGE = "3_render/render_result.png"

# Kích thước mỗi ô lưới (pixel)
CELL_SIZE = 10
LINE_SIZE = 2
HEAD_SIZE = 2

class Renderer:

    def __init__(self):
        pass

    def _get_random_color(self):
        """Tạo màu RGB ngẫu nhiên cho Pillow"""
        return (
            random.randint(0, 200), # R (giới hạn 200 để màu không quá nhạt trên nền trắng)
            random.randint(0, 200), # G
            random.randint(0, 200)  # B
        )

    def _draw_generated_level(self, level_data, output_path):
        """
        Sử dụng Pillow để vẽ level siêu tốc.
        """
        # 1. Lấy thông tin Grid
        XSize = level_data.get("XSize", 20)
        YSize = level_data.get("YSize", 20)
        all_arrows = level_data.get("Arrows", [])
        
        # Tính toán kích thước ảnh
        width_px = XSize * CELL_SIZE
        height_px = YSize * CELL_SIZE

        # 2. Tạo ảnh mới (Nền trắng)
        # "RGB" mode, màu nền (255, 255, 255)
        img = Image.new("RGB", (width_px, height_px), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        # Giữ seed để màu sắc ổn định qua các lần chạy
        random.seed(42)

        logger.info(f"--- Đang render (Pillow): {os.path.basename(output_path)} ---")

        # 3. Vẽ từng mũi tên
        for arrow in all_arrows:
            color = self._get_random_color()
            indices = arrow.get("Indices", [])
            
            if not indices:
                continue

            # Chuyển đổi Index -> Tọa độ Pixel (Tâm ô)
            # Index = y * Width + x
            points_px = []
            for idx in indices:
                grid_x = idx % XSize
                grid_y = idx // XSize
                
                # Tọa độ pixel (lấy tâm ô)
                px = grid_x * CELL_SIZE + CELL_SIZE // 2
                py = grid_y * CELL_SIZE + CELL_SIZE // 2
                points_px.append((px, py))

            # A. Vẽ đường nối (Thân mũi tên)
            if len(points_px) > 1:
                draw.line(points_px, fill=color, width=LINE_SIZE)

            # B. Vẽ đầu mũi tên (Đánh dấu điểm đầu tiên)
            # Đơn giản hóa: Vẽ một hình tròn nhỏ hoặc vuông tại điểm đầu
            head_x, head_y = points_px[0]
            r = HEAD_SIZE # Bán kính đầu mũi tên
            
            # Vẽ hình tròn (Ellipse) tại đầu
            draw.ellipse(
                (head_x - r, head_y - r, head_x + r, head_y + r),
                fill=color,
                outline="black" # Viền đen cho dễ nhìn
            )
            
            # (Tùy chọn) Vẽ dấu chấm nhỏ ở đuôi để biết chiều
            # tail_x, tail_y = points_px[-1]
            # draw.point((tail_x, tail_y), fill="black")

        # 4. Lưu ảnh
        # Pillow lưu file cực nhanh (binary stream trực tiếp)
        try:
            # Đảm bảo thư mục tồn tại
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path)
            logger.info(f"✅ Đã lưu hình ảnh vào: {output_path}")
        except Exception as e:
            logger.error(f"Lỗi khi lưu ảnh Pillow: {e}")

    def draw_generated_level(self, input_path, output_path):
        if not os.path.exists(input_path):
            logger.error(f"render | Lỗi: Không tìm thấy file input '{input_path}'.")
            return

        try:
            with open(input_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            renderer = Renderer()
            renderer._draw_generated_level(data, output_path)
            
        except Exception as e:
            logger.error(f"Đã xảy ra lỗi khi render: {e}")
            # In full traceback nếu cần debug
            # import traceback; traceback.print_exc()

if __name__ == "__main__":
    # Test nhanh nếu chạy trực tiếp file này
    
    # Tìm thử một file json trong thư mục mẫu để test
    test_dir = "level_set/level_set_2/2_result_test"
    if os.path.exists(test_dir):
        files = [f for f in os.listdir(test_dir) if f.endswith(".json")]
        if files:
            test_file = files[0]
            INPUT_JSON = os.path.join(test_dir, test_file)
            OUTPUT_IMAGE = INPUT_JSON.replace("2_result_test", "3_render").replace(".json", ".png")
            
            print(f"Testing render with: {INPUT_JSON}")
            renderer = Renderer()
            renderer.draw_generated_level(INPUT_JSON, OUTPUT_IMAGE)
    else:
        print("Không tìm thấy thư mục test mặc định. Hãy cấu hình đường dẫn thủ công.")
