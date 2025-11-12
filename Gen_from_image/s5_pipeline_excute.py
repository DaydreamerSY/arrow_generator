from s1_img1_rescale_image import Resizer
from s2_img2_image_to_board import ImageConverter
from s3_gen1_cli_generator import ClientGenerator
from s4_gen2_render_generated import Renderer
from helper import Args

from pathlib import Path
from itertools import product

import os
import pandas as pd
import numpy as np

import sys
import datetime
import inspect

# === GHI LOG RA FILE ===
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_path = Path(f"logs/debug_{timestamp}.log")
log_path.parent.mkdir(parents=True, exist_ok=True)
log_file = open(log_path, "a", encoding="utf-8")

# Ghi đồng thời cả ra terminal và file


class Logger(object):
    def __init__(self, file):
        self.terminal = sys.stdout
        self.log = file
        self.at_start_of_line = True
        
        try:
            self.logger_filename = os.path.abspath(__file__)
        except NameError:
            self.logger_filename = os.path.abspath(inspect.currentframe().f_code.co_filename)
        
        try:
            self.cwd = os.getcwd()
        except OSError:
            self.cwd = None

    def _get_caller_info(self):
        """
        Hàm trợ giúp: Đi ngược call stack để tìm file đã gọi print.
        Trả về: (full_path, line_number)
        """
        try:
            stack = inspect.stack()
            
            for frame_info in stack[2:]:
                filename = os.path.abspath(frame_info.filename)
                
                # if filename == self.logger_filename:
                #     continue
                
                basename = os.path.basename(filename)
                if basename in ['io.py', 'code.py', 'runpy.py']:
                    continue
                
                return (filename, frame_info.lineno)
                
        except Exception:
            pass 
        
        return (None, 0) # Fallback

    def write(self, message):
        if not message:
            return

        if self.at_start_of_line and message.strip():
            full_path, line_no = self._get_caller_info()
            
            if full_path:
                # --- BẮT ĐẦU THAY ĐỔI ---
                
                # 1. Tạo đường dẫn cho Log (Tuyệt đối)
                log_prefix = f"[{full_path}:{line_no}] " 
                
                # 2. Tạo đường dẫn cho Terminal (Tương đối)
                display_path = full_path
                if self.cwd:
                    try:
                        rel_path = os.path.relpath(full_path, self.cwd)
                        display_path = rel_path
                    except ValueError:
                        pass # Giữ full_path nếu ở ổ đĩa khác
                
                terminal_prefix = f"[{display_path}:{line_no}] "
                
                # 3. Viết prefix riêng cho từng nơi
                self.terminal.write(terminal_prefix)
                self.log.write(log_prefix)
                
                # --- KẾT THÚC THAY ĐỔI ---
            else:
                prefix = f"[unknown:0] "
                self.terminal.write(prefix)
                self.log.write(prefix)
            
            self.at_start_of_line = False

        # Viết message gốc cho cả hai
        self.terminal.write(message)
        self.log.write(message)

        if message.endswith('\n'):
            self.at_start_of_line = True

    def flush(self):
        self.terminal.flush()
        self.log.flush()
# Gán lại stdout
sys.stdout = Logger(log_file)
sys.stderr = Logger(log_file)

print(f"[LOGGING] Bắt đầu ghi log vào {log_file.name}\n")


def excute_file(args: Args):

    resizer = Resizer()
    converter = ImageConverter()
    renderer = Renderer()

    print(f"args: {args}")

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

    _generated_json_path = args.level_set_path / "2_result_test" / f"{item_name.replace('.png', '')}"
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
            print(item_path)
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



    # print(args.csv)
    for row in args.csv.itertuples():
        # print(row.Index, row.template_name, row.size_x)

        _args = args.clone()

        _args.generate_mode = "basic"

        icons_folder_path = Path(f"{_args.level_set_path}/1_0_original_icons")

        _args.item_name = row.template_name
        _args.template_name = row.template_name
        _args.level_id = row.level_name

        _args.alter_item_name = f"{int(row.level_name):04d}"
        print(f"alter name ------ {_args.alter_item_name}")
        _args.item_path = os.path.join(icons_folder_path, _args.item_name)

        _args.start_length = row.start_length
        _args.length_step = row.length_step
        _args.min_length = row.min_length
        _args.size = (row.size_x, row.size_y)


        print(f"row style {row.style}")
        print(f"row style != '' ? {row.style != ''}")

        if row.style != "":
            _args.generate_mode = "advance"

            _args.left_weight = styles[row.style]["left_weight"]
            _args.right_weight = styles[row.style]["right_weight"]
            _args.straight_weight = styles[row.style]["straight_weight"]
            _args.turn_probability = styles[row.style]["turn_probability"]
            _args.max_turns = styles[row.style]["max_turns"]

            print(_args)

        icons_folder_path = Path(f"{_args.level_set_path}/1_0_original_icons")
        item_path = os.path.join(icons_folder_path, _args.alter_item_name)
        args.item_path = item_path
        excute_file(_args)
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
    args.level_set_path = Path(__file__).parent / "level_set" / "level_set_4_csv_pictures"
    args.csv_path = Path(__file__).parent / "level_set" / "level_set_4_csv_pictures" / "[Data] levels - test dataframe.csv"
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
