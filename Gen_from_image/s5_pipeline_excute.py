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
import multiprocessing, gc

import concurrent.futures
from functools import partial
from rich.progress import Progress, BarColumn, TextColumn, TimeElapsedColumn, track
from loguru import logger
# log = logger.info
# err = logger.error
# warn = logger.warning
# dbg = logger.debug

# === KHỐI LOGGING MỚI (AN TOÀN CHO ĐA XỬ LÝ) ===
def setup_loguru(log_path_str: str, tui_mode: bool = False):
    """
    Cấu hình logger.
    - tui_mode=False: Log ra cả file và terminal (mặc định)
    - tui_mode=True: Chỉ log ra file (dùng khi chạy dashboard TUI)
    """
    logger.remove() # Xóa handler mặc định

    logger.level("WARNING", color="<yellow>")
    logger.level("ERROR", color="<red>")
    
    if not tui_mode:
        # Nếu KHÔNG ở chế độ TUI, thêm sink cho terminal
        logger.add(
            sys.stderr, 
            level="INFO", 
            format="<level>{message}</level>"
        )

    os.environ["LOGURU_ERROR_COLOR"] = "<red>"
    
    # Sink 2: File (luôn luôn được thêm)
    # (Đảm bảo log_path_str là string hoặc Path)
    log_path = Path(log_path_str)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    
    logger.add(
        log_path, 
        level="TRACE",
        rotation="10 MB",
        enqueue=True,     # <-- CHÌA KHÓA cho đa xử lý
        format="{time:HH:mm:ss.SSS} | {level:<8} | {message}",
        colorize=False # (Mặc định là False cho file)
    )
    logger.info(f"Logger đã cấu hình (TUI Mode: {tui_mode}). Ghi log vào {log_path}")

# 4. GỌI HÀM SETUP NGAY LẬP TỨC (Ở GLOBAL SCOPE)
# Tiến trình chính sẽ chạy, không thấy env var, tự tạo path và set env var.
# Tiến trình con sẽ chạy, *thấy* env var, và dùng path đó.
# log_path = setup_loguru()

# 7. In dòng log đầu tiên (sẽ chạy ở cả main và các core)
# Giờ đây tất cả sẽ in ra CÙNG MỘT TÊN FILE
# logger.info(f"Logger đã được patch. Bắt đầu ghi log vào {log_path}")

# === KẾT THÚC KHỐI LOGGING ===


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
    
    # 1. Cấu hình logging cho worker này (ở chế độ TUI)
    if not _WORKER_LOGGING_INITIALIZED:
        # BẮT BUỘC tui_mode=True để worker không làm hỏng dashboard
        setup_loguru(log_path_str, tui_mode=True) 
        _WORKER_LOGGING_INITIALIZED = True

    try:
        # Lấy ID của core (ví dụ: 'SpawnProcess-5')
        process_name = multiprocessing.current_process().name
        
        # 2. Báo cáo bắt đầu
        # Gửi tin nhắn: (Tên core, 0% tiến độ, thông báo)
        progress_queue.put((process_name, 0.0, f"Bắt đầu {row['level_name']}..."))

        # 1. Định nghĩa callback cho TUI
        def tui_callback(step, total, msg):
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

        try:
            _args.min_width = row['min_width']
            _args.max_width = row['max_width']

            if row['min_width'] == row['min_width'] == "":
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
        excute_file(_args, progress_callback=tui_callback)
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
    # level_set_path = "level_set/level_set_2"
    # folder_path = f"{level_set_path}/1_0_original_icons"  # Replace with your target folder
    # Replace with your target folder
    # icons_folder_path = Path(f"{args.level_set_path}/1_0_original_icons")
    icons_folder_path = args.level_set_path / "1_0_original_icons"
    item_path = os.path.join(icons_folder_path, args.item_name)
    args.item_path = item_path
    excute_file(args)

def excute_tui_dashboard(args: Args, log_path: Path):
    """
    Chạy xử lý hàng loạt file CSV với giao diện Dashboard TUI.
    """
    
    # 1. Lấy Styles (hoặc tải từ file)
    styles = {
        "Aztec": {
            "left_weight": 0,
            "right_weight": 2.5,
            "straight_weight": 5,
            "turn_probability": 0.5,
            "max_turns": 12,
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

    # 2. Lấy Tasks (từ args.csv)
    try:
        tasks = [row._asdict() for row in args.csv.itertuples()]
    except AttributeError:
        logger.trace("Không tìm thấy 'args.csv'. Bạn đã tải file CSV chưa?")
        return

    total_tasks = len(tasks)
    logger.info(f"Bắt đầu TUI Dashboard. Xử lý {total_tasks} tác vụ...")

    # 3. Chuẩn bị args cho worker
    args_for_workers = args.clone()
    args_for_workers.csv = None 

    # 4. Tạo các đối tượng giao tiếp
    manager = multiprocessing.Manager()

    with multiprocessing.Manager() as manager:
        progress_queue = manager.Queue() # Hàng đợi giao tiếp

        
        progress_ui = Progress(
            TextColumn("[bold blue]{task.fields[process_name]}", justify="right"),
            BarColumn(bar_width=None),
            "[progress.percentage]{task.percentage:>3.0f}%",
            TextColumn("{task.description}"),
            TimeElapsedColumn(),
            expand=True
        )

        # 5. Chuẩn bị hàm worker
        worker_func = partial(process_csv_row, 
                            original_args=args_for_workers,
                            styles_dict=styles,
                            log_path_str=str(log_path),
                            progress_queue=progress_queue)

        # 6. Chạy Dashboard
        tasks_submitted = 0
        tasks_completed = 0
        core_tasks = {} 
        
        # Lấy số core tối đa, ví dụ 8 -> default 8 adjust to 4 on low-end pc or want stable core 
        num_workers = min(os.cpu_count(), 10) or 4
        # num_workers = 6

        with concurrent.futures.ProcessPoolExecutor(max_workers=num_workers) as executor:
            with progress_ui: # Khởi chạy giao diện rich Live

                # --- BẮT ĐẦU THAY ĐỔI ---
                # Thêm một thanh tiến trình "TỔNG"
                total_progress_bar = progress_ui.add_task(
                    "[bold bright_green]Tổng tiến độ", 
                    total=total_tasks, 
                    process_name="OVERALL" # Tên nội bộ
                )
                # --- KẾT THÚC THAY ĐỔI ---
                
                # Gửi các task đầu tiên (lấp đầy các core)
                for i in range(min(num_workers, total_tasks)):
                    executor.submit(worker_func, tasks[i])
                    # tasks_submitted += 1
                
                # Vòng lặp chính: Chạy cho đến khi hoàn thành
                while tasks_completed < total_tasks:
                    
                    try:
                        # Lấy tin nhắn tiến độ
                        msg = progress_queue.get()
                        process_name, progress_pct, description = msg
                    except (EOFError, BrokenPipeError):
                        logger.trace("Mất kết nối với hàng đợi (Queue)!")
                        break # Thoát vòng lặp
                    
                    # Cập nhật hoặc tạo mới thanh tiến trình
                    if process_name not in core_tasks:
                        core_tasks[process_name] = progress_ui.add_task(
                            f"[bold bright_green] {description}", total=1.0, process_name=process_name
                        )
                    
                    task_id = core_tasks[process_name]
                    
                    if progress_pct == -1.0: # Lỗi
                        progress_ui.update(task_id, description=f"[red]{description}", completed=1.0)
                    else:
                        progress_ui.update(task_id, description=description, completed=progress_pct)

                    # Nếu một core hoàn thành
                    if progress_pct == 1.0 or progress_pct == -1.0:
                        tasks_completed += 1

                        # --- BẮT ĐẦU THAY ĐỔI ---
                        # Cập nhật thanh "TỔNG"
                        progress_ui.update(total_progress_bar, completed=tasks_completed, 
                                        description=f"{tasks_completed}/{total_tasks} files")
                        # --- KẾT THÚC THAY ĐỔI ---
                        
                        # Gửi task TIẾP THEO cho core vừa rảnh
                        if tasks_submitted < total_tasks:
                            executor.submit(worker_func, tasks[tasks_submitted])
                            tasks_submitted += 1

    # --- ĐOẠN CODE MỚI CẦN THÊM VÀO CUỐI ---
    logger.info("Đã xử lý xong logic. Đang chờ ghi log xuống đĩa...")
    
    # Tạo một cột tiến trình mới dạng Spinner (xoay xoay)
    log_task_id = progress_ui.add_task("[bold yellow]Đang lưu file log (Disk I/O)...", total=None)
    
    # Buộc loguru xả hết hàng đợi xuống ổ cứng trước khi thoát
    # Hàm này sẽ block cho đến khi ghi xong
    logger.complete()
    
    # Cập nhật trạng thái đã xong
    progress_ui.update(log_task_id, description="[bold green]Đã lưu log xong!", completed=1)
    
    # --- KẾT THÚC ĐOẠN MỚI ---

    gc.collect()
    setup_loguru(log_path, tui_mode=False)
    logger.info(f"Dashboard hoàn tất. Tổng cộng: {tasks_completed} tác vụ.")


if __name__ == "__main__":

    # ----------------------------------------------------
    # CHỌN CHẾ ĐỘ CHẠY CỦA BẠN Ở ĐÂY
    # ----------------------------------------------------
    # MODE = "TUI_DASHBOARD"  # Chạy 600 file CSV với dashboard
    MODE = "TUI_DASHBOARD"       # Chạy 1 thư mục (chế độ log cuộn)
    # MODE = "SINGLE_FILE"    # Chạy 1 file (chế độ log cuộn)
    # ----------------------------------------------------

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

    # 2. Cấu hình Logging (DỰA TRÊN CHẾ ĐỘ)
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = Path(__file__).parent / "logs" / f"debug_{timestamp}.log"
    
    # Nếu là TUI, bật tui_mode=True (tắt log ra terminal)
    # Nếu không, tui_mode=False (vẫn log ra terminal)
    setup_loguru(log_path, tui_mode=(MODE == "TUI_DASHBOARD"))

    logger.info(f"--- CHẠY Ở CHẾ ĐỘ: {MODE} ---")
    logger.info(f"--- Log file: {log_path} ---")

    # 3. Chạy chế độ đã chọn
    try:
        if MODE == "TUI_DASHBOARD":
            # Tải CSV (chỉ TUI mới cần)
            args.level_set_path = Path(__file__).parent / "level_set" / "level_set_7_collection"
            # args.level_set_path = Path(__file__).parent / "level_set" / "level_set_4_csv_pictures"
            args.csv_path = args.level_set_path / "[Data] levels - test dataframe.csv"
            args.csv = args.load_csv()

            print(args.level_set_path)
            
            # Gọi hàm TUI
            excute_tui_dashboard(args, log_path)

        elif MODE == "FOLDER":
            # args.level_set_path = Path("level_set/level_set_2")
            args.level_set_path = Path(__file__).parent / "level_set" / "level_set_2"
            excute_folder(args)

        elif MODE == "SINGLE_FILE":
            # args.level_set_path = Path("level_set/level_set_1")
            args.level_set_path = Path(__file__).parent / "level_set" / "level_set_1"
            args.item_name = "Daily_328.png"
            args.size = (30, 30)
            excute_single_file(args)
            
    except Exception as e:
        logger.trace("--- LỖI NGHIÊM TRỌNG Ở MAIN ---")

    logger.info(f"--- KẾT THÚC CHẾ ĐỘ: {MODE} ---")

















    # MODE = "TUI_DASHBOARD"

    # # 2. Cấu hình Logging (DỰA TRÊN CHẾ ĐỘ)
    # timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    # log_path = Path(f"logs/debug_{timestamp}.log")
    
    # # Nếu là TUI, bật tui_mode=True (tắt log ra terminal)
    # # Nếu không, tui_mode=False (vẫn log ra terminal)
    # setup_loguru(log_path, tui_mode=(MODE == "TUI_DASHBOARD"))
    # logger.info(f"--- CHẠY Ở CHẾ ĐỘ: {MODE} ---")
    # logger.info(f"--- Log file: {log_path} ---")

    

    # args.generate_mode = "advance"  # basic, advance

    # # convert 1 file icon theo tên "item_name" trong folder "level_set/level_set_#/1_0_original_icons/" thành level
    # # args.level_set_path = Path("level_set/level_set_1")
    # # args.item_name = "Daily_328.png"
    # # args.size = (30, 30)
    # # excute_single_file(args)

    # # convert toàn bộ file image trong toàn bộ folder "level_set/level_set_#/1_0_original_icons/" thành level
    # # args.level_set_path = Path("level_set/level_set_2")
    # # excute_folder(args)

    # # convert theo data.csv
    # # args.level_set_path = Path("level_set/level_set_4_csv_pictures")
    # # args.csv_path = Path("level_set/level_set_4_csv_pictures/[Data] levels - test dataframe.csv")
    # args.level_set_path = str(Path(__file__).parent / "level_set" / "level_set_5_csv")
    # args.csv_path = str(Path(__file__).parent / "level_set" / "level_set_5_csv" / "[Data] levels - test dataframe.csv")
    # args.csv = args.load_csv()
    # # Gọi hàm TUI
    # excute_tui_dashboard(args, log_path)
    # # excute_sequence_files(args)

    # # test combination param để xem cái nào phù hợp nhất
    # # args.level_set_path = Path("level_set/level_set_4 test combine param")
    # # args.item_name = "HEART.png"
    # # args.size = (25, 25)

    # # turn_probability_values = np.linspace(0.25, 1.0, 4) # 0 to 1, step_num=4 -> step=0.25
    # # straight_weight_values = np.linspace(0.25, 1.0, 4)
    # # left_weight_values = np.linspace(0.25, 1.0, 4)
    # # right_weight_values = np.linspace(0.25, 1.0, 4)
    # # max_turns_values = np.linspace(2, 10, 5)
    # # combinations = list(product(
    # #     turn_probability_values,
    # #     straight_weight_values,
    # #     left_weight_values,
    # #     right_weight_values,
    # #     max_turns_values
    # # ))

    # # for (a, b, c, d, e) in combinations:
    # #     args.turn_probability=a
    # #     args.straight_weight=b
    # #     args.left_weight=c
    # #     args.right_weight=d
    # #     args.max_turns=e
    # #     args.alter_item_name = f"{args.item_name}_tp={a}_sw={b}_lw={c}_rw={d}_mt={e}"
    # #     excute_single_file(args)
