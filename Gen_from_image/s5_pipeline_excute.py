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

# === GHI LOG RA FILE ===
timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
log_file = open(Path(f"logs/debug_{timestamp}.log"), "w", encoding="utf-8")

# Ghi đồng thời cả ra terminal và file
class Logger(object):
    def __init__(self, file):
        self.terminal = sys.stdout
        self.log = file

    def write(self, message):
        self.terminal.write(message)
        self.log.write(message)

    def flush(self):  # để tránh lỗi buffer
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
        output_folder=Path(f"{args.level_set_path}/1_1_icons")
    )

    _board_test_path = converter.convert_image_to_board(
        input_path=_img_resized_path,
        output_path=Path(
            f"{args.level_set_path}/1_board_test/{item_name.replace('.png', '.txt')}")
    )

    _generated_json_path = Path(
        f"{args.level_set_path}/2_result_test/{item_name.replace('.png', '')}.json")
    _rendered_png_path = Path(
        f"{args.level_set_path}/3_render/{item_name.replace('.png', '')}.png")

    args.input_file = _board_test_path
    args.output_file = _generated_json_path

    client_generator = ClientGenerator(args)
    client_generator.excute()

    renderer.draw_generated_level(
        input_path=_generated_json_path,
        output_path=_rendered_png_path
    )


def excute_folder(args: Args):
    icons_folder_path = Path(f"{args.level_set_path}/1_0_original_icons")

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
    icons_folder_path = Path(f"{args.level_set_path}/1_0_original_icons")
    item_path = os.path.join(icons_folder_path, args.item_name)
    args.item_path = item_path
    excute_file(args)


def excute_sequence_files(args: Args):


    # print(args.csv)
    for row in args.csv.itertuples():
        # print(row.Index, row.template_name, row.size_x)

        _args = args.clone()

        _args.generate_mode = "basic"

        icons_folder_path = Path(f"{_args.level_set_path}/1_0_original_icons")

        _args.item_name = row.template_name

        _args.alter_item_name = f"{int(row.level_name):04d}"
        print(f"alter name ------ {_args.alter_item_name}")
        _args.item_path = os.path.join(icons_folder_path, _args.item_name)

        _args.start_length = row.start_length
        _args.length_step = row.length_step
        _args.min_length = row.min_length
        _args.size = (row.size_x, row.size_y)

        if row.style == "AZ":
            _args.generate_mode = "advance"

            args.turn_probability=0.5
            args.straight_weight=0.75
            args.left_weight=0.25
            args.right_weight=0.5
            args.max_turns=6


        icons_folder_path = Path(f"{_args.level_set_path}/1_0_original_icons")
        item_path = os.path.join(icons_folder_path, _args.alter_item_name)
        args.item_path = item_path
        excute_file(_args)
    pass


if __name__ == "__main__":


    args = Args()
    args.level_set_path = ""
    args.start_length = 15
    args.length_step = 5
    args.min_length = 5
    args.size = (50, 50)

    # Các tham số mới cho advance generator
    args.turn_probability=0.75
    args.straight_weight=2
    args.left_weight=0.5
    args.right_weight=0.5
    args.max_turns=30

    args.generate_mode = "advance" # basic, advance

    # convert 1 file icon theo tên "item_name" trong folder "level_set/level_set_#/1_0_original_icons/" thành level
    # args.level_set_path = Path("level_set/level_set_2")
    # args.item_name = "Daily_328.png"
    # args.size = (30, 30)
    # excute_single_file(args)

    # convert toàn bộ file image trong toàn bộ folder "level_set/level_set_#/1_0_original_icons/" thành level
    # args.level_set_path = Path("level_set/level_set_2")
    # excute_folder(args)


    # convert theo data.csv
    args.level_set_path = Path("level_set/level_set_3_csv")
    args.csv_path = Path("level_set/level_set_3_csv/[Data] levels - test dataframe.csv")
    args.csv = args.load_csv()
    # convert_dict = {'level_name': str}
    # args.csv = args.csv.astype(convert_dict)
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

