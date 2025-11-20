import os
import json
import random
import plotly.graph_objects as go
from loguru import logger

# ================= CONFIG =================
# Tên file JSON đã tạo bởi cli_generator.py
INPUT_JSON = "2_result_test/result.json" 

# Tên file ảnh PNG sẽ được xuất ra
OUTPUT_IMAGE = "3_render/render_result.png"

class Renderer:

    def __init__(self):
        pass

    def _get_random_color(self):
        """Tạo màu hex ngẫu nhiên cho Plotly"""
        return "#{:06x}".format(random.randint(0, 0xFFFFFF))

    def _draw_generated_level(self, level_data, output_path):
        """
        Sử dụng Plotly để vẽ level.
        """
        
        # Lấy thông tin từ file JSON
        XSize = level_data.get("XSize", 20)
        YSize = level_data.get("YSize", 20)
        all_arrows = level_data.get("Arrows", [])
        picture_name = level_data.get('PictureName', 'Unknown')
        
        # Lấy tên file để làm tiêu đề
        name = os.path.basename(output_path).replace(".png", "")

        logger.info(f"--- Đang render (Plotly): {name} ({XSize}x{YSize}) ---")

        # Khởi tạo Figure
        fig = go.Figure()

        # Giữ seed để màu sắc ổn định qua các lần chạy
        random.seed(42) 

        # --- VẼ CÁC MŨI TÊN ---
        for a in all_arrows:
            color = self._get_random_color()

            # 1. Xử lý phần thân (Polyline)
            pts = [(idx % XSize, idx // XSize) for idx in a.get("Indices", [])]
            
            if pts:
                xs, ys = zip(*pts)
                
                # Vẽ đường đi (Path)
                fig.add_trace(go.Scatter(
                    x=xs, 
                    y=ys,
                    mode='lines',
                    line=dict(color=color, width=3), # Tăng width lên chút cho rõ
                    showlegend=False,
                    hoverinfo='x+y'
                ))

            # 2. Xử lý đầu mũi tên (Arrow Head)
            # Matplotlib vẽ mũi tên bằng vector, Plotly chúng ta dùng Marker hình tam giác
            # và xoay nó theo hướng Dx, Dy.
            
            dx, dy = a["Dx"], a["Dy"]
            
            # Tính góc xoay cho marker (Plotly 0 độ là hướng lên trên - Bắc)
            # Vì trục Y đảo ngược (0 ở trên cùng), nên tính toán góc như sau:
            angle = 0
            if dx == 0 and dy == -1:   angle = 0    # Lên (Up)
            elif dx == 1 and dy == 0:  angle = 90   # Phải (Right)
            elif dx == 0 and dy == 1:  angle = 180  # Xuống (Down)
            elif dx == -1 and dy == 0: angle = 270  # Trái (Left)
            # Xử lý các hướng chéo nếu có (ví dụ: dx=1, dy=1)
            elif dx == 1 and dy == 1:  angle = 135
            elif dx == -1 and dy == 1: angle = 225
            elif dx == -1 and dy == -1: angle = 315
            elif dx == 1 and dy == -1:  angle = 45

            # Vẽ đầu mũi tên bằng Marker
            fig.add_trace(go.Scatter(
                x=[a["X"]], 
                y=[a["Y"]],
                mode='markers',
                marker=dict(
                    symbol='triangle-up', # Luôn dùng tam giác hướng lên, rồi xoay
                    size=12,
                    color=color,
                    angle=angle, # Xoay theo hướng tính được
                    line=dict(width=1, color='black') # Viền đen cho đầu mũi tên nổi bật
                ),
                showlegend=False,
                hoverinfo='skip'
            ))

        # --- CẤU HÌNH LAYOUT ---
        # Tính toán kích thước ảnh output (pixel) dựa trên grid size
        # Ví dụ: mỗi ô grid chiếm 40 pixel
        scale_factor = 40 
        width_px = XSize * scale_factor
        height_px = YSize * scale_factor

        fig.update_layout(
            title=dict(
                text=f"{name} — ({len(all_arrows)} arrows) - {picture_name}",
                font=dict(size=20),
                y=0.98
            ),
            # Ẩn trục và lưới
            xaxis=dict(
                range=[-0.5, XSize - 0.5], 
                showgrid=False, 
                zeroline=False, 
                visible=False
            ),
            yaxis=dict(
                range=[YSize - 0.5, -0.5], # Đảo ngược trục Y (số nhỏ ở trên)
                showgrid=False, 
                zeroline=False, 
                visible=False,
                autorange=False # Bắt buộc tắt auto range để dùng range thủ công ở trên
            ),
            width=width_px,
            height=height_px,
            plot_bgcolor='white',
            margin=dict(l=10, r=10, t=40, b=10)
        )

        # --- LƯU ẢNH ---
        # scale=1 nghĩa là giữ nguyên kích thước width/height đã set
        # scale > 1 sẽ tăng độ phân giải (DPI cao hơn)
        fig.write_image(output_path, scale=2) 
        
        logger.info(f"✅ Đã lưu hình ảnh vào: {output_path}")

    def draw_generated_level(self, input_path, output_path):
        if not os.path.exists(input_path):
            logger.error(f"Lỗi: Không tìm thấy file input '{input_path}'.")
            return

        try:
            data = json.load(open(input_path, "r", encoding="utf-8"))
            
            # Đảm bảo thư mục output tồn tại
            os.makedirs(os.path.dirname(output_path), exist_ok=True)

            renderer = Renderer()
            renderer._draw_generated_level(data, output_path)
            
        except Exception as e:
            logger.error(f"Đã xảy ra lỗi khi render: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":

    _filename = [
        "HEART_tp=0.0_sw0.0_lw0.0_rw0.0_mt0.0.json",
        # ... (Thêm các file khác của bạn vào đây)
    ]
    
    # Để test nhanh, bạn có thể comment list trên và dùng 1 file mẫu nếu muốn
    # _filename = ["demo.json"] 

    base_path = "level_set/level_set_4 test combine param"

    for file_name in _filename:
        INPUT_JSON = f"{base_path}/2_result_test/{file_name}" 
        OUTPUT_IMAGE = f"{base_path}/3_render/{file_name.replace('json', 'png')}"

        renderer = Renderer()
        renderer.draw_generated_level(INPUT_JSON, OUTPUT_IMAGE)