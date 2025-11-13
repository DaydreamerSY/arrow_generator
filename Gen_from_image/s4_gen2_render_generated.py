import os
import json
import matplotlib.pyplot as plt
import random
from loguru import logger

# ================= CONFIG =================
# Tên file JSON đã tạo bởi cli_generator.py
INPUT_JSON = "2_result_test/result.json" 

# Tên file ảnh PNG sẽ được xuất ra
OUTPUT_IMAGE = "3_render/render_result.png"

class Renderer:

    def __init__(self):
        pass

    # ================= DRAW FUNCTION (Đã sửa đổi) =================
    def _draw_generated_level(self, level_data, output_path):
        """
        Hàm này được điều chỉnh từ 'draw_state' của bạn.
        Nó đọc file JSON đầu ra của generator và vẽ trạng thái cuối cùng.
        """
        
        # Lấy thông tin từ file JSON
        XSize = level_data.get("XSize", 20)
        YSize = level_data.get("YSize", 20)
        all_arrows = level_data.get("Arrows", [])
        
        # Lấy tên file (không có .json) để làm tiêu đề
        name = os.path.basename(output_path).replace(".png", "")

        logger.info(f"--- Đang render: {name} ({XSize}x{YSize}) ---")

        # --- Setup Matplotlib (Giữ nguyên từ file mẫu) ---
        plt.figure(figsize=(XSize / 5, YSize / 5))
        ax = plt.gca()
        ax.set_xlim(-0.5, XSize - 0.9)
        ax.set_ylim(-0.5, YSize - 0.9)
        ax.set_aspect("equal")
        ax.invert_yaxis() # Trục Y đi xuống
        plt.axis("off")
        plt.title(f"{name} — ({len(all_arrows)} arrows) - {level_data.get('PictureName')}", fontsize=9)

        # --- Tạo màu ngẫu nhiên (Giữ nguyên từ file mẫu) ---
        random.seed(42) # Giữ seed để màu sắc ổn định
        colors = [(random.random(), random.random(), random.random()) for _ in all_arrows]

        # --- Vẽ tất cả arrow (polyline + đầu mũi tên) ---
        # Logic này giống hệt file mẫu của bạn, nhưng dùng 'all_arrows'
        # thay vì 'state['remaining_arrows']'
        for i, a in enumerate(all_arrows):
            
            # Giải mã 'Indices' để lấy tọa độ (x, y)
            # Đây là logic cốt lõi từ file gốc của bạn
            pts = [(idx % XSize, idx // XSize) for idx in a.get("Indices", [])]
            if not pts:
                continue
                
            xs, ys = zip(*pts)
            ax.plot(xs, ys, color=colors[i], linewidth=1)

            # Vẽ đầu mũi tên (Giữ nguyên từ file mẫu)
            # File JSON của chúng ta lưu tọa độ ĐẦU MŨI TÊN (đã offset)
            # trong 'X' và 'Y'.
            ax.arrow(
                a["X"], a["Y"], 
                a["Dx"] * 0.001, a["Dy"] * 0.001, # Dùng 0.001 để chỉ vẽ cái đầu
                head_width=0.35, head_length=0.35,
                fc="black", ec="none", zorder=3
            )

        # --- Không cần vẽ ray cast (debug) vì file JSON không có thông tin này ---

        # --- Save figure ---
        plt.savefig(output_path, dpi=200, bbox_inches="tight", pad_inches=0.05)
        plt.close()
        logger.info(f"✅ Đã lưu hình ảnh vào: {output_path}")

    def draw_generated_level(self, input_path, output_path):
        if not os.path.exists(input_path):
            logger.info(f"Lỗi: Không tìm thấy file input '{input_path}'.")
            logger.info(f"Hãy chạy 'cli_generator.py ... {input_path} ...' trước.")

        try:
            # Mở file JSON kết quả
            data = json.load(open(input_path, "r", encoding="utf-8"))
            
            # Truyền dữ liệu vào hàm vẽ
            renderer = Renderer()
            renderer._draw_generated_level(data, output_path)
            
        except Exception as e:
            logger.info(f"Đã xảy ra lỗi khi render: {e}")
            import traceback
            traceback.print_exc()
            pass


if __name__ == "__main__":

    _filename = [
        "HEART_tp=0.0_sw0.0_lw0.0_rw0.0_mt0.0.json",
        "HEART_tp=0.0_sw0.0_lw0.0_rw0.0_mt0.3333333333333333.json",
        "HEART_tp=0.0_sw0.0_lw0.0_rw0.0_mt0.6666666666666666.json",
        "HEART_tp=0.0_sw0.0_lw0.0_rw0.0_mt1.0.json",
        "HEART_tp=0.0_sw0.0_lw0.0_rw0.3333333333333333_mt0.0.json",
        "HEART_tp=0.0_sw0.0_lw0.0_rw0.6666666666666666.0.json",
    ]

    for file_name in _filename:

        # Tên file JSON đã tạo bởi cli_generator.py
        INPUT_JSON = f"level_set/level_set_4 test combine param/2_result_test/{file_name}" 

        # Tên file ảnh PNG sẽ được xuất ra
        OUTPUT_IMAGE = f"level_set/level_set_4 test combine param/3_render/{file_name.replace('json', 'png')}"

        # Truyền dữ liệu vào hàm vẽ
        renderer = Renderer()
        renderer.draw_generated_level(INPUT_JSON, OUTPUT_IMAGE)