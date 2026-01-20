import os
import json
import shutil
from pathlib import Path
from types import SimpleNamespace

# Import các module của bạn
# Đảm bảo các file này nằm cùng thư mục
try:
    from s1_solve_levels_parallel import LevelSolver
    from s2_render_visuals import Renderer
    from s3_analyze_solved_data import Analyzer
    from core.helper import Args
except ImportError as e:
    print(f"Error importing analysis modules: {e}")

class AnalysisManager:
    def __init__(self, output_dir="analysis_output"):
        self.base_dir = Path(output_dir)
        self.input_dir = self.base_dir / "input_temp"
        self.solved_dir = self.base_dir / "solved_data"
        self.render_dir = self.base_dir / "debug_results"
        self.csv_path = self.base_dir / "report.csv"
        
        # Đảm bảo thư mục tồn tại
        self.setup_directories()

    def setup_directories(self):
        for p in [self.input_dir, self.solved_dir, self.render_dir]:
            os.makedirs(p, exist_ok=True)

    def prepare_level(self, level_data, level_id):
        """Lưu dữ liệu level hiện tại từ UI xuống file json để solver đọc"""
        # Xóa dữ liệu cũ để tránh nhầm lẫn
        self.clean_directory(self.input_dir)
        self.clean_directory(self.solved_dir)
        # self.clean_directory(self.render_dir) # Có thể giữ lại ảnh cũ nếu muốn

        filename = f"level_{int(level_id):04d}.json"
        save_path = self.input_dir / filename
        
        with open(save_path, 'w', encoding='utf-8') as f:
            json.dump(level_data, f)
        
        return save_path

    def clean_directory(self, path):
        for item in os.listdir(path):
            item_path = os.path.join(path, item)
            try:
                if os.path.isfile(item_path): os.unlink(item_path)
                elif os.path.isdir(item_path): shutil.rmtree(item_path)
            except Exception as e:
                print(f"Error cleaning {item_path}: {e}")

    def run_analysis(self, level_data, level_id, render_visuals=False):
        # 1. Prepare
        print("--- [Analysis] Step 1: Preparing Input ---")
        self.prepare_level(level_data, level_id)

        # Tạo Args giả lập
        args = Args()
        args.solver_input_folder = self.input_dir
        args.solver_solved_data = self.solved_dir
        args.render_debug_results = self.render_dir
        args.render_debug_mode = "solve_only"
        args.analyze_output_csv_path = self.csv_path

        # 2. Solve (S1)
        print("--- [Analysis] Step 2: Solving ---")
        solver = LevelSolver()
        # Lưu ý: LevelSolver dùng ProcessPoolExecutor, 
        # nên gọi nó trực tiếp trong UI thread có thể gây đơ nhẹ. 
        # Tốt nhất nên chạy trong QThread (sẽ làm ở UI).
        solver.excute(args)

        # 3. Render (S2) - Optional
        if render_visuals:
            print("--- [Analysis] Step 3: Rendering ---")
            renderer = Renderer()
            renderer.excute(args)

        # 4. Analyze (S3)
        print("--- [Analysis] Step 4: Statistics ---")
        analyzer = Analyzer()
        
        # Chúng ta sẽ tùy chỉnh Analyzer một chút để lấy kết quả trả về trực tiếp
        # thay vì chỉ đọc từ CSV.
        results = []
        files = [f for f in os.listdir(self.solved_dir) if f.endswith(".json")]
        
        report_text = "No analysis data."
        summary_data = {}

        for file in files:
            path = os.path.join(self.solved_dir, file)
            try:
                data = analyzer.load_json(path)
                info = analyzer.analyze_level(data, file)
                results.append(info)
                
                # Tạo báo cáo text nhanh
                summary_data = info
                report_text = (
                    f"Level: {info['name']}\n"
                    f"States: {info['total_states']}\n"
                    f"Total Arrows: {info['total_arrows']}\n"
                    f"Solvable Ratio: {info['solvable_ratio']}\n"
                    f"Unused Points: {info['unused_points']}\n"
                    f"Avg Length: {info['avg_len']}"
                )
            except Exception as e:
                report_text = f"Error: {e}"

        return report_text, summary_data, self.render_dir