from s1_img1_rescale_image import Resizer
from s2_img2_image_to_board import ImageConverter
from s3_gen1_cli_generator import ClientGenerator
from s4_gen2_render_generated import Renderer

from helper import Args
import pandas as pd

import os
from pathlib import Path


def excute_file(args: Args):

    resizer = Resizer()
    converter = ImageConverter()
    renderer = Renderer()

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
        f"{args.level_set_path}/3_render/{item_name}")

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
    print(args.csv)
    for row in args.csv.itertuples():
        print(row.Index, row.template_name, row.size_x)

        _args = args.clone()

        icons_folder_path = Path(f"{_args.level_set_path}/1_0_original_icons")

        _args.item_name = row.template_name

        _args.alter_item_name = str(row.level_name)
        _args.item_path = os.path.join(icons_folder_path, _args.item_name)

        _args.start_length = row.start_length
        _args.length_step = row.length_step
        _args.min_length = row.min_length
        _args.size = (row.size_x, row.size_y)

        icons_folder_path = Path(f"{_args.level_set_path}/1_0_original_icons")
        item_path = os.path.join(icons_folder_path, _args.alter_item_name)
        args.item_path = item_path
        excute_file(_args)


    pass



if __name__ == "__main__":

    level_set_path = Path("level_set/level_set_1")

    args = Args()
    args.level_set_path = level_set_path
    args.start_length = 25
    args.length_step = 5
    args.min_length = 4
    args.size = (50, 50)

    # convert toàn bộ file image trong toàn bộ folder "level_set/level_set_#/1_0_original_icons/" thành level
    # excute_folder(args)

    # convert 1 file icon theo tên "item_name" trong folder "level_set/level_set_#/1_0_original_icons/" thành level
    args.item_name = "HEART.png"
    args.size = (30, 30)
    excute_single_file(args)

    # convert theo data.csv
    # args.csv_path = Path("level_set/level_set_3/[Data] levels - test dataframe.csv")
    # args.csv = args.load_csv()
    # excute_sequence_files(args)
