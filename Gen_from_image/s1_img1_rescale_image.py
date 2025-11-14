# File: scale_down.py (Đã cấu trúc lại thành hàm)
import os
from PIL import Image
from loguru import logger

class Resizer:

    def __init__(self):
        pass

    def resize_image(self, input_path: str, new_size: tuple, output_folder: str):
        """
        Thay đổi kích thước của một ảnh và lưu nó vào một thư mục.

        Hàm này sẽ tự động tạo thư mục output nếu nó không tồn tại
        và sẽ ghi đè (replace) file nếu đã có file trùng tên.

        Args:
            input_path (str): Đường dẫn đến file ảnh gốc (vd: "folder/anh_goc.png").
            new_size (tuple): Một tuple (width, height) cho kích thước mới (vd: (800, 600)).
            output_folder (str): Đường dẫn đến thư mục lưu kết quả (vd: "resized_images").
        """
        try:
            # 1. Đảm bảo thư mục output tồn tại
            # os.makedirs sẽ không báo lỗi nếu thư mục đã tồn tại (exist_ok=True)
            os.makedirs(output_folder, exist_ok=True)
            
            # 2. Tạo đường dẫn file output cuối cùng
            # Lấy tên file gốc (vd: "anh_goc.png")
            file_name = os.path.basename(input_path)
            # Nối với thư mục output (vd: "resized_images/anh_goc.png")
            output_path = os.path.join(output_folder, file_name)

            with Image.open(input_path) as img:
                logger.info(f"Đang xử lý: '{input_path}' (Kích thước gốc: {img.size})")
                
                # 3. Thay đổi kích thước (Đảm bảo là số nguyên)
                int_size = (int(new_size[0]), int(new_size[1]))
                
                # Image.Resampling.LANCZOS là bộ lọc chất lượng cao
                # nhất để giảm kích thước (scale down)
                resized_img = img.resize(int_size, Image.Resampling.LANCZOS)
                
                # 4. Lưu file (PIL.Image.save() tự động ghi đè)
                resized_img.save(output_path)
                logger.info(f"==> Đã lưu vào: '{output_path}' (Kích thước mới: {int_size})")
                return output_path

        except FileNotFoundError:
            logger.trace(f"Lỗi: Không tìm thấy file '{input_path}'")
        except Exception as e:
            logger.trace(f"Đã xảy ra lỗi khi xử lý {input_path}: {e}")

# --- CÁCH SỬ DỤNG (VÍ DỤ) ---
# Bạn có thể chạy file này trực tiếp để test
if __name__ == "__main__":
    
    # --- Cấu hình ví dụ ---
    INPUT_FILE_1 = "1_0_original_icons/ANCHOR.png" # Đổi tên file này
    # INPUT_FILE_2 = "anh_khac.jpg" # File test thứ 2
    
    OUTPUT_DIR = "1_1_icons" # Tên thư mục output
    
    TARGET_SIZE_1 = (50, 50)
    # TARGET_SIZE_2 = (100, 100) # Cắt ảnh 2 thành 100x100
    # ------------------------
    
    logger.info("--- Bắt đầu xử lý ---")

    resizer = Resizer()
    
    # Gọi hàm cho file 1
    resizer.resize_image(
        input_path=INPUT_FILE_1, 
        new_size=TARGET_SIZE_1, 
        output_folder=OUTPUT_DIR
    )
    
    # Gọi hàm cho file 2
    # resize_image(
    #     input_path=INPUT_FILE_2, 
    #     new_size=TARGET_SIZE_2, 
    #     output_folder=OUTPUT_DIR
    # )
    
    logger.info("--- Hoàn tất ---")