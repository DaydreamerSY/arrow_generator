from s1_img1_rescale_image import Resizer
from s2_img2_image_to_board import ImageConverter
from s3_gen1_cli_generator import ClientGenerator
from s4_gen2_render_generated import Renderer
from helper import Args

from pathlib import Path

import sys, os, datetime
import multiprocessing
import concurrent.futures
from functools import partial
from loguru import logger

# === KHỐI LOGGING (AN TOÀN CHO ĐA XỬ LÝ) ===
def setup_loguru(log_path_str: str, disable_logging: bool = False, enable_stderr: bool = True):
    """
    Cấu hình hoặc vô hiệu hóa hoàn toàn logger.
    - disable_logging=True: Gỡ bỏ mọi output và chặn xử lý log.
    - enable_stderr=True: Cho phép log ra terminal (tắt trong worker process).
    """
    logger.remove()

    if disable_logging:
        logger.disable("")
        return

    logger.level("WARNING", color="<yellow>")
    logger.level("ERROR", color="<red>")

    if enable_stderr:
        logger.add(
            sys.stderr,
            level="INFO",
            format="<level>{message}</level>"
        )

    log_path = Path(log_path_str)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path,
        level="TRACE",
        rotation="10 MB",
        enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level:<8} | {message}",
        colorize=False
    )


# --- ĐÂY LÀ HÀM MỚI (WORKER) ---
# (Hàm này phải nằm ở top-level, bên ngoài hàm excute_sequence_files)

# Thêm cờ (flag) để đảm bảo worker chỉ setup 1 lần
_WORKER_LOGGING_INITIALIZED = False

def process_csv_row(row, original_args, styles_dict, log_path_str, progress_queue):
    """
    Hàm worker xử lý 1 dòng CSV.
    - Gửi log vào file qua loguru.
    - Gửi tiến độ qua progress_queue.
    """
    global _WORKER_LOGGING_INITIALIZED
    
    # 1. Cấu hình logging cho worker (tắt stderr để không nhiễu GUI)
    if not _WORKER_LOGGING_INITIALIZED:
        setup_loguru(log_path_str, enable_stderr=False)
        _WORKER_LOGGING_INITIALIZED = True

    try:
        # Lấy ID của core (ví dụ: 'SpawnProcess-5')
        process_name = multiprocessing.current_process().name
        
        # 2. Báo cáo bắt đầu
        # Gửi tin nhắn: (Tên core, 0% tiến độ, thông báo)
        progress_queue.put((process_name, 0.0, f"Bắt đầu {row['level_name']}..."))

        # 1. Định nghĩa callback gửi tiến độ qua queue
        def on_progress(step, total, msg):
            if total > 0:
                percent = step / total
                progress_queue.put((process_name, percent, f"({row['level_name']}) {msg}"))
            elif step == -1: # Mã lỗi
                progress_queue.put((process_name, -1.0, f"LỖI {row['level_name']}!"))

        _args = original_args.clone()
        _args.generate_mode = "basic"
        icons_folder_path = Path(f"{_args.level_set_path}/1_0_original_icons")

        _args.item_name = row['template_name']
        _args.template_name = row['template_name']
        _args.level_id = row['level_name']
        _args.alter_item_name = f"{int(row['level_name']):04d}"
        _args.item_path = os.path.join(icons_folder_path, _args.item_name)
        
        _args.start_length = row['start_length']
        _args.length_step = row['length_step']
        _args.min_length = row['min_length']
        _args.size = (row['size_x'], row['size_y'])
        _args.border = True 
        try:
            _args.min_width = row['min_width']
            _args.max_width = row['max_width']

            if row['min_width'] == "" and row['max_width'] == "":
                _args.min_width = 0.0
                _args.max_width = 10000.0

        except:
            _args.min_width = 0.0
            _args.max_width = 10000.0

        # 2. Áp dụng style (nếu có)
        if row['style'] != "":
            _args.generate_mode = "advance"
            style_params = styles_dict.get(row['style']) 
            
            if style_params:
                _args.left_weight = style_params["left_weight"]
                _args.right_weight = style_params["right_weight"]
                _args.straight_weight = style_params["straight_weight"]
                _args.turn_probability = style_params["turn_probability"]
                _args.max_turns = style_params["max_turns"]
            else:
                logger.trace(f"pipline_excute | [Cảnh báo] Không tìm thấy style '{row['style']}' cho {row['level_name']}")
        
        # 3. Thực thi
        logger.info(f"pipline_excute | [PID {os.getpid()}] Đang xử lý: {row['level_name']} (Style: {row['style'] or 'basic'})")
        excute_file(_args, progress_callback=on_progress)
        # 5. Báo cáo hoàn thành
        # Gửi tin nhắn: (Tên core, 100% tiến độ, thông báo)
        progress_queue.put((process_name, 1.0, f"pipline_excute | Hoàn thành {row['level_name']}!"))
        
        return (row['Index'], f"pipline_excute | Thành công", None)

    except Exception as e:
        logger.trace(f"pipline_excute | LỖI ở {row['level_name']} {e}")
        progress_queue.put((process_name, -1.0, f"LỖI {row['level_name']}!")) # -1 là lỗi
        return (row['Index'], f"pipline_excute | Thất bại", str(e))
    


def excute_file(args: Args, progress_callback=None):

    def _report(step, total, msg):
        if progress_callback:
            progress_callback(step, total, msg)

    resizer = Resizer()
    converter = ImageConverter()
    renderer = Renderer()

    args.level_set_path = Path(args.level_set_path)

    logger.info(f"args: {args}")

    item_name = ""

    if hasattr(args, "alter_item_name"):
        item_name = args.alter_item_name
    else:
        item_name = args.item_name

    _report(1, 10, f"Lv: {item_name} | Resizing {item_name}...")
    _img_resized_path = resizer.resize_image(
        input_path=args.item_path,
        new_size=args.size,
        output_folder=args.level_set_path / "1_1_icons"
    )

    _report(2, 10, f"Lv: {item_name} | Converting {item_name}...")
    _board_test_path = converter.convert_image_to_board(
        input_path=_img_resized_path,
        output_path=args.level_set_path / "1_board_test" / item_name.replace('.png', '.txt')
    )

    _report(3, 10, f"Lv: {item_name} | Generating {item_name}...")
    _generated_json_path = args.level_set_path / "2_result_test" / f"{item_name.replace('.png', '')}.json"
    _rendered_png_path = args.level_set_path / "3_render" / f"{item_name.replace('.png', '')}.png"

    args.input_file = _board_test_path
    args.output_file = _generated_json_path

    # Tạo một "callback lồng" (nested callback)
    # để chuyển tiến độ của Generator (0-100%)
    # thành tiến độ của bước 3 (từ 75% -> 85%)
    def generator_callback(step, total, msg):
        # Tính toán tiến độ tổng thể
        # (Bước 3 chiếm từ 75% đến 95% của tổng thể) -> chiếm từ 40% đến 90%
        # 75% (đã xong 3/4) + (tiến độ của generator * 20%) -> 3/10 đã xong + (tiến độ generator) * 60%
        overall_progress = (3/10) + (step / total) * 0.60 
        
        if progress_callback:
            # Báo cáo tiến độ tổng thể (ví dụ: 0.80 = 80%)
            progress_callback(overall_progress * 100, 100, msg)

    client_generator = ClientGenerator(args)
    client_generator.excute(progress_callback=generator_callback)

    _report(10, 10, f"Lv: {item_name} | Rendering {item_name}...")
    renderer.draw_generated_level(
        input_path=_generated_json_path,
        output_path=_rendered_png_path
    )


def excute_folder(args: Args):
    # icons_folder_path = Path(f"{args.level_set_path}/1_0_original_icons")
    icons_folder_path = args.level_set_path / "1_0_original_icons"

    for item_name in os.listdir(icons_folder_path):
        if item_name == ".DS_Store":
            continue
        item_path = os.path.join(icons_folder_path, item_name)
        if os.path.isfile(item_path):  # Check if it's a file, not a subdirectory
            logger.info(item_path)
            args.item_name = item_name
            args.item_path = item_path
            excute_file(args)


def excute_single_file(args: Args):
    icons_folder_path = args.level_set_path / "1_0_original_icons"
    item_path = os.path.join(icons_folder_path, args.item_name)
    args.item_path = item_path
    excute_file(args)



if __name__ == "__main__":

    # ----------------------------------------------------
    # CHỌN CHẾ ĐỘ CHẠY CỦA BẠN Ở ĐÂY
    # ----------------------------------------------------
    MODE = "FOLDER"
    # MODE = "SINGLE_FILE"
    # ----------------------------------------------------
    ENABLE_LOGS = False

    args = Args()
    args.level_set_path = ""
    args.length_step = 5
    args.min_length = 5
    args.size = (50, 50)

    args.start_length = 54
    args.turn_probability = 0.5
    args.left_weight = 1.3
    args.right_weight = 1.0
    args.straight_weight = 1.0
    args.max_turns = 18

    # 2. Cấu hình Logging
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = Path(__file__).parent / "logs" / f"debug_{timestamp}.log"
    setup_loguru(str(log_path), disable_logging=not ENABLE_LOGS)

    logger.info(f"--- CHẠY Ở CHẾ ĐỘ: {MODE} ---")
    logger.info(f"--- Log file: {log_path} ---")

    # 3. Chạy chế độ đã chọn
    try:
        if MODE == "FOLDER":
            args.level_set_path = Path(__file__).parent / "level_set" / "level_set_2"
            excute_folder(args)

        elif MODE == "SINGLE_FILE":
            args.level_set_path = Path(__file__).parent / "level_set" / "level_set_1"
            args.item_name = "Daily_328.png"
            args.size = (30, 30)
            excute_single_file(args)

    except Exception as e:
        logger.trace("--- LỖI NGHIÊM TRỌNG Ở MAIN ---")

    logger.info(f"--- KẾT THÚC CHẾ ĐỘ: {MODE} ---")
