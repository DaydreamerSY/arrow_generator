# File: pipeline.py
# Gộp toàn bộ pipeline: resize → convert → generate → render → orchestrate.
# Thay thế: s1_img1_rescale_image.py, s2_img2_image_to_board.py,
#            s3_gen1_cli_generator.py, s4_gen2_render_generated.py,
#            s5_pipeline_excute.py

import json
import os
import sys
import datetime
import random
import multiprocessing
import concurrent.futures
from functools import partial
from pathlib import Path
from collections import defaultdict

from PIL import Image, ImageDraw
from loguru import logger

from helper import Args, Arrow
from validator import Validator
from generator import HybridLevelGeneratorTestable
from boundary_tracer import generate_boundary_arrows, fix_boundary_directions


# ==============================================================================
# SECTION 1: IMAGE PROCESSING (resize + convert to board)
# ==============================================================================

def resize_image(input_path, new_size, output_folder):
    """Resize ảnh PNG về kích thước mới, lưu vào output_folder."""
    try:
        os.makedirs(output_folder, exist_ok=True)
        file_name = os.path.basename(input_path)
        output_path = os.path.join(output_folder, file_name)

        with Image.open(input_path) as img:
            logger.info(f"Đang resize: '{input_path}' ({img.size})")
            int_size = (int(new_size[0]), int(new_size[1]))
            resized_img = img.resize(int_size, Image.Resampling.LANCZOS)
            resized_img.save(output_path)
            logger.info(f"==> Đã lưu: '{output_path}' ({int_size})")
            return output_path

    except FileNotFoundError:
        logger.trace(f"Lỗi: Không tìm thấy file '{input_path}'")
    except Exception as e:
        logger.trace(f"Lỗi khi resize {input_path}: {e}")


def convert_image_to_board(input_path, output_path, alpha_threshold=128):
    """Chuyển ảnh PNG (RGBA) thành file board .txt. Pixel alpha >= threshold → '1'."""
    try:
        img = Image.open(input_path).convert("RGBA")
    except FileNotFoundError:
        logger.trace(f"Lỗi: Không tìm thấy '{input_path}'.")
        return
    except Exception as e:
        logger.trace(f"Lỗi khi mở ảnh: {e}")
        return

    width, height = img.size
    logger.info(f"Đã tải ảnh '{input_path}' ({width}x{height}), alpha threshold={alpha_threshold}")

    pixels = img.load()
    board_lines = []

    for y in range(height):
        line = ""
        for x in range(width):
            alpha = pixels[x, y][3]
            line += '1' if alpha >= alpha_threshold else '.'
        board_lines.append(line)

    try:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write("\n".join(board_lines))
        logger.info(f"Đã lưu board: '{output_path}'")
        return output_path
    except Exception as e:
        logger.trace(f"Lỗi khi ghi file board: {e}")


# ==============================================================================
# SECTION 2: LEVEL GENERATION (load board → generate arrows → save JSON)
# ==============================================================================

class MockLayer:
    """Mock object giả lập Layer cho generator."""
    def __init__(self, layer_id, color, editable_area_set):
        self.id = layer_id
        self.color = color
        self.editable_area = editable_area_set
        self.arrows = []


def load_board_from_file(filepath, level_name=""):
    """Đọc file .txt, trả về set các tọa độ (x, y) editable."""
    logger.info(f"Lv: {level_name} | Đang tải board từ: {filepath}")
    editable_area = set()
    try:
        with open(filepath, 'r') as f:
            for y, line in enumerate(f):
                line = line.strip().upper()
                for x, char in enumerate(line):
                    if char == '1' or char == 'X':
                        editable_area.add((x, y))

        if not editable_area:
            logger.trace(f"Lv: {level_name} | Không tìm thấy ô '1'/'X' trong file input.")
            return None

        logger.info(f"Lv: {level_name} | Đã tải {len(editable_area)} ô editable.")
        return editable_area

    except FileNotFoundError:
        logger.trace(f"Lv: {level_name} | Không tìm thấy file '{filepath}'.")
        return None
    except Exception as e:
        logger.trace(f"Lv: {level_name} | Lỗi khi đọc file: {e}")
        return None


def suggest_arrow_count(total_cells, avg_length):
    """Đề xuất số lượng mũi tên dựa trên tổng cells và avg_length."""
    if avg_length <= 0:
        return 1
    count = round(total_cells / avg_length)
    return max(count, 1)


def save_arrows_to_json(all_arrows, filename, args, level_name=""):
    """Lưu danh sách arrows ra file JSON chuẩn game."""
    logger.info(f"Lv: {level_name} | Đang lưu: {filename}")
    all_arrow_points = {p for arr in all_arrows for p in arr.points}
    if not all_arrow_points:
        logger.warning(f"Lv: {level_name} | Không có mũi tên nào để lưu.")
        return

    min_x = min(p[0] for p in all_arrow_points)
    min_y = min(p[1] for p in all_arrow_points)
    max_x = max(p[0] for p in all_arrow_points)
    max_y = max(p[1] for p in all_arrow_points)

    offset_x = -min_x
    offset_y = -min_y
    new_x_size = max_x - min_x + 1
    new_y_size = max_y - min_y + 1

    picture_name = ""
    if hasattr(args, 'template_name'):
        picture_name = args.template_name.replace(".png", "")
    elif hasattr(args, 'item_name'):
        picture_name = args.item_name

    output_data = {
        "XSize": new_x_size,
        "YSize": new_y_size,
        "PictureName": picture_name,
        "LevelID": getattr(args, 'level_id', ''),
        "Arrows": []
    }

    for arrow in all_arrows:
        if not arrow.points:
            continue
        new_points = [(p[0] + offset_x, p[1] + offset_y) for p in arrow.points]
        indices = [y * new_x_size + x for x, y in new_points]
        tail_x, tail_y = new_points[0]

        # Đếm bend
        bend_count = 0
        if len(arrow.points) >= 3:
            for k in range(len(arrow.points) - 2):
                p1, p2, p3 = arrow.points[k], arrow.points[k + 1], arrow.points[k + 2]
                dir1 = (p2[0] - p1[0], p2[1] - p1[1])
                dir2 = (p3[0] - p2[0], p3[1] - p2[1])
                if dir1 != dir2:
                    bend_count += 1

        output_data["Arrows"].append({
            "Dx": arrow.direction[0], "Dy": arrow.direction[1],
            "X": tail_x, "Y": tail_y,
            "Indices": indices, "BendCount": bend_count
        })

    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        with open(filename, 'w') as f:
            json.dump(output_data, f, separators=(',', ':'))
            f.flush()
            os.fsync(f.fileno())
        logger.info(f"Lv: {level_name} | Đã lưu level {new_x_size}x{new_y_size} với {len(all_arrows)} mũi tên.")
    except Exception as e:
        logger.trace(f"Lv: {level_name} | Lỗi khi lưu JSON: {e}")


def generate_level(args, progress_callback=None):
    """
    Main generation loop: load board → boundary (optional) → generate arrows → save JSON.
    Tương đương ClientGenerator.excute() cũ.
    """
    level_name = getattr(args, 'alter_item_name', '')

    # 1. Load board
    editable_area = load_board_from_file(args.input_file, level_name)
    if editable_area is None:
        raise FileNotFoundError(f"Không thể tải board: {args.input_file}")

    total_editable_cells = len(editable_area)
    logger.debug(f"Lv: {level_name} | Tổng ô editable: {total_editable_cells}")

    # 2. Khởi tạo
    all_generated_arrows = []
    boundary_arrows = []
    current_arrow_id = 0
    current_length = args.start_length

    validator = Validator()
    generator = HybridLevelGeneratorTestable(args)
    mock_color = (0, 82, 204)

    # 2b. Boundary Generation (nếu bật)
    enable_boundary = getattr(args, 'enable_boundary', False)
    if enable_boundary:
        all_xs = [p[0] for p in editable_area]
        all_ys = [p[1] for p in editable_area]
        board_w = max(all_xs) - min(all_xs) + 1
        board_h = max(all_ys) - min(all_ys) + 1

        boundary_max_length = getattr(args, 'boundary_max_length', 20)
        boundary_min_parts = getattr(args, 'boundary_min_parts', 1)

        boundary_arrows = generate_boundary_arrows(
            editable_area, board_w, board_h,
            max_length=boundary_max_length,
            start_arrow_id=current_arrow_id,
            min_parts=boundary_min_parts
        )

        if boundary_arrows:
            all_generated_arrows.extend(boundary_arrows)
            current_arrow_id = max(a.id for a in boundary_arrows) + 1
            logger.info(f"Lv: {level_name} | Đã tạo {len(boundary_arrows)} boundary arrows.")

    # 3. Vòng lặp chính: giảm length dần, lặp lại ở min_length cho đến hết
    while current_length >= args.min_length:
        occupied_cells = {p for arr in all_generated_arrows for p in arr.points}
        available_cells = editable_area.difference(occupied_cells)
        num_available = len(available_cells)

        # Báo cáo tiến độ
        if progress_callback:
            progress_callback(len(occupied_cells), total_editable_cells,
                              f"Lv: {level_name} | Gen length {current_length}...")

        if num_available == 0:
            logger.debug(f"Lv: {level_name} | Board đã đầy. Dừng.")
            break

        num_to_gen = suggest_arrow_count(num_available, current_length)
        mock_layer = MockLayer(0, mock_color, editable_area)

        # Chọn mode
        if args.generate_mode == "basic":
            newly_found, new_id, status_msg = generator.generate_hybrid_level(
                validator=validator, active_layer=mock_layer,
                all_arrows_on_board=all_generated_arrows,
                start_arrow_id=current_arrow_id,
                num_to_gen=num_to_gen, avg_length=current_length
            )
        elif args.generate_mode == "advance":
            newly_found, new_id, status_msg = generator.generate_hybrid_level_advanced(
                validator=validator, active_layer=mock_layer,
                all_arrows_on_board=all_generated_arrows,
                start_arrow_id=current_arrow_id,
                num_to_gen=num_to_gen, avg_length=current_length,
                turn_probability=args.turn_probability,
                straight_weight=args.straight_weight,
                left_weight=args.left_weight,
                right_weight=args.right_weight,
                max_turns=args.max_turns
            )
        else:
            newly_found = []
            new_id = current_arrow_id
            status_msg = f"Unknown mode: {args.generate_mode}"

        if newly_found:
            all_generated_arrows.extend(newly_found)
            current_arrow_id = new_id
            if current_length > args.min_length:
                current_length -= args.length_step
                if current_length < args.min_length:
                    current_length = args.min_length
            # Nếu đã ở min_length → lặp lại cùng length
        else:
            if current_length == args.min_length:
                break  # Ở min_length mà không tạo được → dừng hẳn
            else:
                current_length -= args.length_step
                if current_length < args.min_length:
                    current_length = args.min_length

    # 4. Hoàn tất
    logger.success(f"Lv: {level_name} | Tổng cộng: {len(all_generated_arrows)} mũi tên.")

    # Fix boundary directions (sau khi tất cả arrows đã đặt)
    if enable_boundary and boundary_arrows:
        all_xs = [p[0] for p in editable_area]
        all_ys = [p[1] for p in editable_area]
        board_w = max(all_xs) - min(all_xs) + 1
        board_h = max(all_ys) - min(all_ys) + 1
        fix_boundary_directions(boundary_arrows, all_generated_arrows, editable_area, board_w, board_h)
        logger.info(f"Lv: {level_name} | Đã fix boundary directions.")

    # Báo cáo cuối
    occupied_cells = {p for arr in all_generated_arrows for p in arr.points}
    if progress_callback:
        progress_callback(len(occupied_cells), total_editable_cells, "Generation complete!")

    fill_pct = (len(occupied_cells) / total_editable_cells) * 100
    logger.success(f"Lv: {level_name} | Fill: {len(occupied_cells)}/{total_editable_cells} ({fill_pct:.1f}%)")

    # 5. Lưu JSON
    if all_generated_arrows:
        save_arrows_to_json(all_generated_arrows, args.output_file, args, level_name)
    else:
        logger.warning(f"Lv: {level_name} | Không có mũi tên nào được tạo.")


# ==============================================================================
# SECTION 3: RENDERING (JSON → PNG)
# ==============================================================================

RENDER_CELL_SIZE = 10
RENDER_LINE_SIZE = 2
RENDER_HEAD_SIZE = 2


def render_level(input_path, output_path):
    """Đọc JSON level, render ra PNG bằng Pillow."""
    if not os.path.exists(input_path):
        logger.trace(f"render | Không tìm thấy '{input_path}'.")
        return

    try:
        with open(input_path, "r", encoding="utf-8") as f:
            level_data = json.load(f)

        x_size = level_data.get("XSize", 20)
        y_size = level_data.get("YSize", 20)
        all_arrows = level_data.get("Arrows", [])

        width_px = x_size * RENDER_CELL_SIZE
        height_px = y_size * RENDER_CELL_SIZE

        img = Image.new("RGB", (width_px, height_px), (255, 255, 255))
        draw = ImageDraw.Draw(img)

        random.seed(42)  # Màu ổn định giữa các lần chạy

        logger.info(f"Đang render: {os.path.basename(output_path)}")

        for arrow in all_arrows:
            color = (random.randint(0, 200), random.randint(0, 200), random.randint(0, 200))
            indices = arrow.get("Indices", [])
            if not indices:
                continue

            points_px = []
            for idx in indices:
                gx = idx % x_size
                gy = idx // x_size
                px = gx * RENDER_CELL_SIZE + RENDER_CELL_SIZE // 2
                py = gy * RENDER_CELL_SIZE + RENDER_CELL_SIZE // 2
                points_px.append((px, py))

            if len(points_px) > 1:
                draw.line(points_px, fill=color, width=RENDER_LINE_SIZE)

            # Vẽ đầu mũi tên (hình tròn)
            hx, hy = points_px[0]
            r = RENDER_HEAD_SIZE
            draw.ellipse((hx - r, hy - r, hx + r, hy + r), fill=color, outline="black")

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        img.save(output_path)
        logger.info(f"Đã lưu render: {output_path}")

    except Exception as e:
        logger.trace(f"Lỗi khi render: {e}")


# ==============================================================================
# SECTION 4: PIPELINE ORCHESTRATION
# ==============================================================================

def setup_loguru(log_path_str, disable_logging=False, enable_stderr=True):
    """Cấu hình loguru (an toàn cho đa xử lý)."""
    logger.remove()

    if disable_logging:
        logger.disable("")
        return

    logger.level("WARNING", color="<yellow>")
    logger.level("ERROR", color="<red>")

    if enable_stderr:
        logger.add(sys.stderr, level="INFO", format="<level>{message}</level>")

    log_path = Path(log_path_str)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logger.add(
        log_path, level="TRACE", rotation="10 MB", enqueue=True,
        format="{time:HH:mm:ss.SSS} | {level:<8} | {message}", colorize=False
    )


def excute_file(args, progress_callback=None):
    """Chạy full pipeline cho 1 file: resize → convert → generate → render."""
    def _report(step, total, msg):
        if progress_callback:
            progress_callback(step, total, msg)

    args.level_set_path = Path(args.level_set_path)
    item_name = getattr(args, 'alter_item_name', args.item_name)

    # Step 1: Resize
    _report(1, 10, f"Lv: {item_name} | Resizing...")
    img_resized = resize_image(
        input_path=args.item_path,
        new_size=args.size,
        output_folder=args.level_set_path / "1_1_icons"
    )

    # Step 2: Convert to board
    _report(2, 10, f"Lv: {item_name} | Converting...")
    board_path = convert_image_to_board(
        input_path=img_resized,
        output_path=args.level_set_path / "1_board_test" / item_name.replace('.png', '.txt')
    )

    # Step 3: Generate arrows
    _report(3, 10, f"Lv: {item_name} | Generating...")
    json_path = args.level_set_path / "2_result_test" / f"{item_name.replace('.png', '')}.json"
    png_path = args.level_set_path / "3_render" / f"{item_name.replace('.png', '')}.png"

    args.input_file = board_path
    args.output_file = json_path

    # Nested callback: generator progress → overall progress (30%→90%)
    def gen_callback(step, total, msg):
        if progress_callback:
            overall = (3 / 10) + (step / total) * 0.60
            progress_callback(overall * 100, 100, msg)

    generate_level(args, progress_callback=gen_callback)

    # Step 4: Render
    _report(10, 10, f"Lv: {item_name} | Rendering...")
    render_level(input_path=json_path, output_path=png_path)


# Flag đảm bảo worker chỉ setup logging 1 lần
_WORKER_LOGGING_INITIALIZED = False


def process_csv_row(row, original_args, styles_dict, log_path_str, progress_queue):
    """Worker function: xử lý 1 dòng CSV trong process pool."""
    global _WORKER_LOGGING_INITIALIZED

    if not _WORKER_LOGGING_INITIALIZED:
        setup_loguru(log_path_str, enable_stderr=False)
        _WORKER_LOGGING_INITIALIZED = True

    try:
        process_name = multiprocessing.current_process().name
        progress_queue.put((process_name, 0.0, f"Bắt đầu {row['level_name']}..."))

        def on_progress(step, total, msg):
            if total > 0:
                pct = step / total
                progress_queue.put((process_name, pct, f"({row['level_name']}) {msg}"))
            elif step == -1:
                progress_queue.put((process_name, -1.0, f"LỖI {row['level_name']}!"))

        _args = original_args.clone()
        _args.generate_mode = "basic"
        icons_folder = Path(f"{_args.level_set_path}/1_0_original_icons")

        _args.item_name = row['template_name']
        _args.template_name = row['template_name']
        _args.level_id = row['level_name']
        _args.alter_item_name = f"{int(row['level_name']):04d}"
        _args.item_path = os.path.join(icons_folder, _args.item_name)

        _args.start_length = row['start_length']
        _args.length_step = row['length_step']
        _args.min_length = row['min_length']
        _args.size = (row['size_x'], row['size_y'])
        _args.border = True

        # Width constraints
        try:
            _args.min_width = row['min_width']
            _args.max_width = row['max_width']
            if row['min_width'] == "" and row['max_width'] == "":
                _args.min_width = 0.0
                _args.max_width = 10000.0
        except:
            _args.min_width = 0.0
            _args.max_width = 10000.0

        # Initial Width
        try:
            _args.initial_width = int(row['initial_width']) if row.get('initial_width', '') != '' else None
        except:
            _args.initial_width = None

        # Boundary params
        try:
            _args.enable_boundary = str(row.get('enable_boundary', '')).strip().lower() in ('true', '1', 'yes')
            _args.boundary_max_length = int(row['boundary_max_length']) if row.get('boundary_max_length', '') != '' else 20
            _args.boundary_min_parts = int(row['boundary_min_parts']) if row.get('boundary_min_parts', '') != '' else 1
        except:
            _args.enable_boundary = False
            _args.boundary_max_length = 20
            _args.boundary_min_parts = 1

        # Style
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
                logger.trace(f"pipeline | Không tìm thấy style '{row['style']}' cho {row['level_name']}")

        # Execute
        logger.info(f"pipeline | [PID {os.getpid()}] Xử lý: {row['level_name']} (Style: {row['style'] or 'basic'})")
        excute_file(_args, progress_callback=on_progress)

        progress_queue.put((process_name, 1.0, f"pipeline | Hoàn thành {row['level_name']}!"))
        return (row['Index'], "Thành công", None)

    except Exception as e:
        logger.trace(f"pipeline | LỖI ở {row['level_name']}: {e}")
        progress_queue.put((process_name, -1.0, f"LỖI {row['level_name']}!"))
        return (row['Index'], "Thất bại", str(e))


# ==============================================================================
# CLI ENTRY POINT (chạy trực tiếp từ terminal)
# ==============================================================================

if __name__ == "__main__":
    MODE = "FOLDER"
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

    timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = Path(__file__).parent / "logs" / f"debug_{timestamp}.log"
    setup_loguru(str(log_path), disable_logging=not ENABLE_LOGS)

    logger.info(f"--- MODE: {MODE} ---")

    try:
        if MODE == "FOLDER":
            args.level_set_path = Path(__file__).parent / "level_set" / "level_set_2"
            icons_folder = args.level_set_path / "1_0_original_icons"
            for item_name in os.listdir(icons_folder):
                if item_name == ".DS_Store":
                    continue
                item_path = os.path.join(icons_folder, item_name)
                if os.path.isfile(item_path):
                    args.item_name = item_name
                    args.item_path = item_path
                    args.generate_mode = "basic"
                    excute_file(args)

    except Exception as e:
        logger.trace(f"--- LỖI MAIN: {e} ---")

    logger.info(f"--- KẾT THÚC ---")
