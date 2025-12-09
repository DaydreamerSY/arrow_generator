# File: image_to_board.py
# Chuyển đổi file PNG (có kênh alpha) thành file .txt
# Pixel CÓ MÀU (alpha > 0) -> '1'
# Pixel TRONG SUỐT (alpha == 0) -> '.'

from PIL import Image
import sys
from loguru import logger

# --- CONFIG ---
INPUT_IMAGE_FILE = "1_1_icons/CROWN.png"
OUTPUT_BOARD_FILE = "1_board_test/my_board.txt"

# ================= MODIFICATION START =================
# NGƯỠNG ALPHA (0-255)
# 0   = Chỉ pixel trong suốt 100% mới là EMPTY (logic cũ)
# 128 = 50% (Khuyến nghị)
# 255 = Mọi pixel (kể cả đục) đều là EMPTY
#
# Bất kỳ pixel nào có giá trị alpha DƯỚI ngưỡng này sẽ là EMPTY ('.')
alpha_threshold = 128
# ================= MODIFICATION END ===================

# Ký tự cho vùng vẽ được (non-transparent)
editable_char = '1'
# Ký tự cho vùng trống (transparent)
empty_char = '.'
# --- END CONFIG ---

class ImageConverter:

    def __init__(self):
        self.editable_char = '1'
        self.empty_char = '.'
        self.alpha_threshold = 128
        pass

    def convert_image_to_board(self, input_path, output_path):
        """
        Đọc file ảnh và chuyển đổi dựa trên một ngưỡng alpha (threshold).
        """
        try:
            # Mở ảnh và đảm bảo nó ở chế độ RGBA
            img = Image.open(input_path).convert("RGBA")
        except FileNotFoundError:
            logger.trace(f"Lỗi: Không tìm thấy file ảnh '{input_path}'.")
            return
        except Exception as e:
            logger.trace(f"Lỗi khi mở ảnh: {e}")
            return

        width, height = img.size
        logger.info(f"Đã tải ảnh '{input_path}' (Kích thước: {width}x{height})")
        logger.info(f"Sử dụng ngưỡng Alpha: {self.alpha_threshold}")

        pixels = img.load()
        board_lines = []

        for y in range(height):
            line_str = ""
            for x in range(width):
                # Lấy giá trị (R, G, B, A)
                rgba = pixels[x, y]
                alpha = rgba[3]
                
                # === LOGIC MỚI ===
                # Nếu alpha thấp hơn ngưỡng, coi là trống
                if alpha < self.alpha_threshold:
                    line_str += self.empty_char
                else:
                    # Nếu alpha lớn hơn hoặc bằng ngưỡng, coi là vẽ được
                    line_str += self.editable_char
            
            board_lines.append(line_str)

        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write("\n".join(board_lines))
            logger.info(f"Hoàn thành! Đã lưu board vào '{output_path}'.")
            return output_path
            
        except Exception as e:
            logger.trace(f"Lỗi khi ghi file: {e}")

# --- Hàm chạy chính ---
if __name__ == "__main__":
    # Bạn có thể thay đổi tên file ở đây hoặc truyền qua command line
    # Ví dụ: python image_to_board.py my_icon.png my_level.txt
    
    in_file = "1_1_icons/ANCHOR.png"
    out_file = "1_board_test/my_board.txt"
    
    # if len(sys.argv) == 3:
    #     in_file = sys.argv[1]
    #     out_file = sys.argv[2]

    converter = ImageConverter()
        
    converter.convert_image_to_board(in_file, out_file)