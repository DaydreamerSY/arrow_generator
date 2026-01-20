import os
from PIL import Image

class ImageTools:
    def __init__(self):
        pass

    def process_image_to_points(self, input_path, target_width, target_height, alpha_threshold=128):
        """
        Quy trình xử lý ảnh đầy đủ:
        1. Resize ảnh về kích thước lưới mong muốn.
        2. Quét pixel để xác định vùng vẽ (dựa trên độ trong suốt Alpha).
        3. Trả về tập hợp các điểm (x, y) để UI hiển thị.
        """
        try:
            # 1. Mở và Resize ảnh
            img = Image.open(input_path).convert("RGBA")
            
            # Sử dụng LANCZOS để resize chất lượng cao
            img_resized = img.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            width, height = img_resized.size
            pixels = img_resized.load()
            
            editable_points = set()
            
            # 2. Quét pixel
            for y in range(height):
                for x in range(width):
                    # Lấy giá trị (R, G, B, A)
                    rgba = pixels[x, y]
                    alpha = rgba[3]
                    
                    # Logic xác định vùng vẽ:
                    # Nếu độ đục (alpha) >= ngưỡng -> Là vùng vẽ được
                    if alpha >= alpha_threshold:
                        editable_points.add((x, y))
            
            return {
                "success": True,
                "width": width,
                "height": height,
                "points": editable_points,
                "message": f"Đã chuyển đổi thành công! Tìm thấy {len(editable_points)} ô vẽ."
            }

        except Exception as e:
            return {
                "success": False,
                "message": f"Lỗi xử lý ảnh: {str(e)}"
            }