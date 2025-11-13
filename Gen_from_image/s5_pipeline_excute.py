from s1_img1_rescale_image import Resizer
from s2_img2_image_to_board import ImageConverter
from s3_gen1_cli_generator import ClientGenerator
from s4_gen2_render_generated import Renderer
from helper import Args

from pathlib import Path
from itertools import product

import sys, os, datetime
import pandas as pd
import numpy as np

import concurrent.futures
from functools import partial
from rich.progress import track
from loguru import logger
log = logger.info
err = logger.error
warn = logger.warning
dbg = logger.debug

# === KHỐI LOGGING MỚI (AN TOÀN CHO ĐA XỬ LÝ) ===

def setup_logging():
    """
    Hàm này cấu hình loguru. 
    Nó sẽ được gọi bởi cả tiến trình chính và con.
    """
    
    # 1. Kiểm tra biến môi trường
    log_path_str = os.environ.get("MY_APP_LOG_PATH")
    
    if not log_path_str:
        # ---- Đây là TIẾN TRÌNH CHÍNH (chạy lần đầu) ----
        # 1a. Tạo timestamp và path MỘT LẦN
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        log_path = Path(f"logs/debug_{timestamp}.log")
        
        # 1b. SET BIẾN MÔI TRƯỜNG CHO CÁC TIẾN TRÌNH CON
        os.environ["MY_APP_LOG_PATH"] = str(log_path)
    else:
        # ---- Đây là TIẾN TRÌNH CON (đã được set env var) ----
        # 2. Chỉ cần đọc lại đường dẫn đã được tạo
        log_path = Path(log_path_str)
        
    log_path.parent.mkdir(parents=True, exist_ok=True)

    # 3. Cấu hình logger
    logger.remove() # Xóa handler mặc định
    
    # Sink 1: Terminal (dễ đọc)
    logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")
    
    # Sink 2: File (an toàn, đầy đủ)
    logger.add(
        log_path, 
        level="DEBUG",
        rotation="10 MB",
        enqueue=True,     # <-- CHÌA KHÓA cho đa xử lý
        format="{time:HH:mm:ss.SSS} | {level:<8} | {process.name} | {name}:{function}:{line} - {message}"
    )
    return log_path # Trả về path đã dùng

# 4. GỌI HÀM SETUP NGAY LẬP TỨC (Ở GLOBAL SCOPE)
# Tiến trình chính sẽ chạy, không thấy env var, tự tạo path và set env var.
# Tiến trình con sẽ chạy, *thấy* env var, và dùng path đó.
log_path = setup_logging()

# 7. In dòng log đầu tiên (sẽ chạy ở cả main và các core)
# Giờ đây tất cả sẽ in ra CÙNG MỘT TÊN FILE
logger.info(f"Logger đã được patch. Bắt đầu ghi log vào {log_path}")

# === KẾT THÚC KHỐI LOGGING ===


# --- ĐÂY LÀ HÀM MỚI (WORKER) ---
# (Hàm này phải nằm ở top-level, bên ngoài hàm excute_sequence_files)

def process_csv_row(row, original_args, styles_dict):
    """
    Hàm này xử lý MỘT dòng CSV. Nó sẽ được chạy song song.
    'row' bây giờ là một DICT.
    """
    try:
        # 1. Sao chép args và thiết lập thông số
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
                # Dùng 'warn' thay vì print
                warn(f"[Cảnh báo] Không tìm thấy style '{row['style']}' cho {row['level_name']}")
        
        # 3. Thực thi
        # Dùng 'log' (là logger.info) thay vì print
        log(f"[PID {os.getpid()}] Đang xử lý: {row['level_name']} (Style: {row['style'] or 'basic'})")
        excute_file(_args)
        
        # Trả về kết quả
        return (row['Index'], "Thành công", None)

    except Exception as e:
        # Dùng logger.exception() để tự động ghi traceback
        logger.exception(f"LỖI ở {row['level_name']}: {e}") 
        return (row['Index'], "Thất bại", str(e))
    # (Tôi đã xóa khối 'except' bị trùng lặp ở đây)
def excute_file(args: Args):

    resizer = Resizer()
    converter = ImageConverter()
    renderer = Renderer()

    logger.info(f"args: {args}")

    if hasattr(args, "alter_item_name"):
        item_name = args.alter_item_name
    else:
        item_name = args.item_name

    _img_resized_path = resizer.resize_image(
        input_path=args.item_path,
        new_size=args.size,
        output_folder=args.level_set_path / "1_1_icons"
    )

    _board_test_path = converter.convert_image_to_board(
        input_path=_img_resized_path,
        output_path=args.level_set_path / "1_board_test" / item_name.replace('.png', '.txt')
    )

    _generated_json_path = args.level_set_path / "2_result_test" / f"{item_name.replace('.png', '')}.json"
    _rendered_png_path = args.level_set_path / "3_render" / f"{item_name.replace('.png', '')}.png"

    args.input_file = _board_test_path
    args.output_file = _generated_json_path

    client_generator = ClientGenerator(args)
    client_generator.excute()

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
    # level_set_path = "level_set/level_set_2"
    # folder_path = f"{level_set_path}/1_0_original_icons"  # Replace with your target folder
    # Replace with your target folder
    # icons_folder_path = Path(f"{args.level_set_path}/1_0_original_icons")
    icons_folder_path = args.level_set_path / "1_0_original_icons"
    item_path = os.path.join(icons_folder_path, args.item_name)
    args.item_path = item_path
    excute_file(args)


def excute_sequence_files(args: Args):

    styles = {
        "Aztec": {
            "left_weight": 0.01,
            "right_weight": 5,
            "straight_weight": 5,
            "turn_probability": 0.5,
            "max_turns": 6,
        },
        "Basic": {
            "left_weight": 1.0,
            "right_weight": 1.0,
            "straight_weight": 1.0,
            "turn_probability": 0.3,
            "max_turns": 18,
        },
        "Spaghetti": {
            "left_weight": 1.0,
            "right_weight": 1.0,
            "straight_weight": 1.5,
            "turn_probability": 0.4,
            "max_turns": 29,
        },
        "Country": {
            "left_weight": 1.3,
            "right_weight": 1.1,
            "straight_weight": 1.0,
            "turn_probability": 0.25,
            "max_turns": 13,
        },
        "Loopy": {
            "left_weight": 2.7,
            "right_weight": 1.15,
            "straight_weight": 1.0,
            "turn_probability": 0.27,
            "max_turns": 14,
        },
        "Snake": {
            "left_weight": 1.6,
            "right_weight": 1.25,
            "straight_weight": 1.0,
            "turn_probability": 0.5,
            "max_turns": 42,
        },
    }

    # Aztec old
    # left_w = 0.25
    # right_w = 0.5
    # straight_w = 0.75
    # turn_p = 0.5
    # max_turn = 6



    # logger.info(args.csv)
    # 1. Chuẩn bị danh sách các tác vụ
    tasks = [row._asdict() for row in args.csv.itertuples()]
    max_workers = None 
    
    logger.info(f"--- Bắt đầu xử lý {len(tasks)} file song song trên (tối đa) {os.cpu_count()} core ---")

    # --- BẮT ĐẦU SỬA LỖI ---
    
    # 2. Tạo một bản sao 'args' SẠCH (không chứa DataFrame)
    # Hàm worker không cần toàn bộ file CSV, chỉ cần các settings khác
    args_for_workers = args.clone()
    args_for_workers.csv = None # <-- ĐÂY LÀ SỬA LỖI
    
    # 3. Tạo hàm "partial" với bản sao 'args' đã làm sạch
    worker_func = partial(process_csv_row, 
                          original_args=args_for_workers, # <-- Dùng bản sao sạch
                          styles_dict=styles)
    
    # --- KẾT THÚC SỬA LỖI ---

    # 3. Chạy pool (ĐÂY LÀ PHẦN THAY ĐỔI)
    results = [] # Nơi lưu trữ kết quả
    
    with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
        
        # A. Gửi tất cả các tác vụ vào pool
        # executor.submit() sẽ gửi 1 task và trả về 1 đối tượng 'Future'
        # 'Future' giống như một tờ giấy hẹn
        futures = {executor.submit(worker_func, task): task for task in tasks}

        # B. Dùng 'track' để theo dõi các 'Future' khi chúng hoàn thành
        # as_completed(futures) sẽ đợi và trả về 'Future' ngay khi nó
        # được một core xử lý xong (không theo thứ tự)
        for future in track(concurrent.futures.as_completed(futures), 
                            description="[green]Đang xử lý...", 
                            total=len(tasks)):
            
            try:
                # Lấy kết quả từ 'Future'
                result = future.result()
                results.append(result)
            except Exception as e:
                # 'task_failed' bây giờ là một dict
                task_failed = futures[future] 
                
                # --- THAY ĐỔI: DÙNG ['key'] THAY VÌ .key ---
                logger.info(f"LỖI (ngoài worker) ở {task_failed['level_name']}: {e}")
                results.append((task_failed['Index'], "Thất bại (executor)", str(e)))
                # --- KẾT THÚC THAY ĐỔI ---

    # 5. (Tùy chọn) Xử lý kết quả
    logger.info("--- Xử lý hoàn tất ---")
    success_count = 0
    fail_count = 0
    for (index, status, error_msg) in results:
        if status == "Thành công":
            success_count += 1
        else:
            fail_count += 1
            logger.info(f"[Lỗi] Dòng {index} thất bại: {error_msg}")
    
    logger.info(f"Tổng kết: {success_count} thành công, {fail_count} thất bại.")
    pass


if __name__ == "__main__":

    args = Args()
    args.level_set_path = ""
    args.length_step = 5
    args.min_length = 5
    args.size = (50, 50)

    # Các tham số mới cho advance generator
    args.start_length = 54
    args.turn_probability = 0.5
    args.left_weight = 1.3
    args.right_weight = 1.0
    args.straight_weight = 1.0
    args.max_turns = 18

    #                  | Aztec | Basic | Spaghetti | Country | Loopy | Snake |
    # ------------------------------------------------------------------------
    # start_length     | ##    | ##    | ##        |         |       |       |
    # left_weight      | 1.5   | 1.3   | 1.3       | 1.4     | 2.8   | 1.6   |
    # right_weight     | 1.2   | 1.0   | 1.0       | 1.1     | 1.2   | 1.25  |
    # straight_weight  | 1.0   | 1.0   | 1.0       | 1.0     | 1.0   | 1.0   |
    # turn_probability | 0.15  | 0.3   | 0.4       | 0.25    | 0.27  | 0.5   |
    # max_turns        | 9     | 18    | 29        | 89      | 14    | 42    |

    args.generate_mode = "advance"  # basic, advance

    # convert 1 file icon theo tên "item_name" trong folder "level_set/level_set_#/1_0_original_icons/" thành level
    # args.level_set_path = Path("level_set/level_set_1")
    # args.item_name = "Daily_328.png"
    # args.size = (30, 30)
    # excute_single_file(args)

    # convert toàn bộ file image trong toàn bộ folder "level_set/level_set_#/1_0_original_icons/" thành level
    # args.level_set_path = Path("level_set/level_set_2")
    # excute_folder(args)

    # convert theo data.csv
    # args.level_set_path = Path("level_set/level_set_4_csv_pictures")
    # args.csv_path = Path("level_set/level_set_4_csv_pictures/[Data] levels - test dataframe.csv")
    args.level_set_path = Path(__file__).parent / "level_set" / "level_set_5_csv"
    args.csv_path = Path(__file__).parent / "level_set" / "level_set_5_csv" / "[Data] levels - test dataframe.csv"
    args.csv = args.load_csv()
    excute_sequence_files(args)

    # test combination param để xem cái nào phù hợp nhất
    # args.level_set_path = Path("level_set/level_set_4 test combine param")
    # args.item_name = "HEART.png"
    # args.size = (25, 25)

    # turn_probability_values = np.linspace(0.25, 1.0, 4) # 0 to 1, step_num=4 -> step=0.25
    # straight_weight_values = np.linspace(0.25, 1.0, 4)
    # left_weight_values = np.linspace(0.25, 1.0, 4)
    # right_weight_values = np.linspace(0.25, 1.0, 4)
    # max_turns_values = np.linspace(2, 10, 5)
    # combinations = list(product(
    #     turn_probability_values,
    #     straight_weight_values,
    #     left_weight_values,
    #     right_weight_values,
    #     max_turns_values
    # ))

    # for (a, b, c, d, e) in combinations:
    #     args.turn_probability=a
    #     args.straight_weight=b
    #     args.left_weight=c
    #     args.right_weight=d
    #     args.max_turns=e
    #     args.alter_item_name = f"{args.item_name}_tp={a}_sw={b}_lw={c}_rw={d}_mt={e}"
    #     excute_single_file(args)
