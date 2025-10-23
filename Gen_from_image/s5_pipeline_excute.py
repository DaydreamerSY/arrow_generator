from s1_img1_rescale_image import Resizer
from s2_img2_image_to_board import ImageConverter
from s3_gen1_cli_generator import ClientGenerator, FakeParser
from s4_gen2_render_generated import Renderer

import os
from pathlib import Path

def excute_folder(level_set_path):
    resizer = Resizer()
    converter = ImageConverter()
    # generator = ClientGenerator()
    renderer = Renderer()

    # level_set_path = "level_set/level_set_2"
    # folder_path = f"{level_set_path}/1_0_original_icons"  # Replace with your target folder
    icons_folder_path = Path(f"{level_set_path}/1_0_original_icons")  # Replace with your target folder

    for item_name in os.listdir(icons_folder_path):
        if item_name == ".DS_Store":
            continue
        item_path = os.path.join(icons_folder_path, item_name)
        if os.path.isfile(item_path):  # Check if it's a file, not a subdirectory
            print(item_path)


            _img_resized_path = resizer.resize_image(
                input_path=item_path, 
                new_size=(50, 50), 
                output_folder=Path(f"{level_set_path}/1_1_icons")
            )

            _board_test_path = converter.convert_image_to_board(
                input_path=_img_resized_path, 
                output_path=Path(f"{level_set_path}/1_board_test/{item_name.replace('.png', '.txt')}")
            )


            _generated_json_path = Path(f"{level_set_path}/2_result_test/{item_name.replace('.png', '')}.json")
            _rendered_png_path = Path(f"{level_set_path}/3_render/{item_name}")
            args = FakeParser({
                "input_file": _board_test_path,
                "output_file": _generated_json_path,
                "start_length": 16,
                "length_step": 2,
                "min_length": 4,
            })
            client_generator = ClientGenerator(args)
            client_generator.excute()

            renderer.draw_generated_level(
                input_path=_generated_json_path, 
                output_path=_rendered_png_path
            )

def excute_single_file(level_set_path, item_name, size):

    resizer = Resizer()
    converter = ImageConverter()
    # generator = ClientGenerator()
    renderer = Renderer()

    # level_set_path = "level_set/level_set_2"
    # folder_path = f"{level_set_path}/1_0_original_icons"  # Replace with your target folder
    icons_folder_path = Path(f"{level_set_path}/1_0_original_icons")  # Replace with your target folder

    item_path = os.path.join(icons_folder_path, item_name)
    _img_resized_path = resizer.resize_image(
        input_path=item_path, 
        new_size=size, 
        output_folder=Path(f"{level_set_path}/1_1_icons")
    )

    _board_test_path = converter.convert_image_to_board(
        input_path=_img_resized_path, 
        output_path=Path(f"{level_set_path}/1_board_test/{item_name.replace('.png', '.txt')}")
    )


    _generated_json_path = Path(f"{level_set_path}/2_result_test/{item_name.replace('.png', '')}.json")
    _rendered_png_path = Path(f"{level_set_path}/3_render/{item_name}")
    args = FakeParser({
        "input_file": _board_test_path,
        "output_file": _generated_json_path,
        "start_length": 10,
        "length_step": 2,
        "min_length": 4,
    })
    client_generator = ClientGenerator(args)
    client_generator.excute()

    renderer.draw_generated_level(
        input_path=_generated_json_path, 
        output_path=_rendered_png_path
    )

def excute_sequence_files(level_set_path, item_name, size):

    resizer = Resizer()
    converter = ImageConverter()
    # generator = ClientGenerator()
    renderer = Renderer()

    # level_set_path = "level_set/level_set_2"
    # folder_path = f"{level_set_path}/1_0_original_icons"  # Replace with your target folder
    icons_folder_path = Path(f"{level_set_path}/1_0_original_icons")  # Replace with your target folder

    item_path = os.path.join(icons_folder_path, item_name)
    _img_resized_path = resizer.resize_image(
        input_path=item_path, 
        new_size=size, 
        output_folder=Path(f"{level_set_path}/1_1_icons")
    )

    _board_test_path = converter.convert_image_to_board(
        input_path=_img_resized_path, 
        output_path=Path(f"{level_set_path}/1_board_test/{item_name.replace('.png', '.txt')}")
    )


    _generated_json_path = Path(f"{level_set_path}/2_result_test/{item_name.replace('.png', '')}.json")
    _rendered_png_path = Path(f"{level_set_path}/3_render/{item_name}")
    args = FakeParser({
        "input_file": _board_test_path,
        "output_file": _generated_json_path,
        "start_length": 10,
        "length_step": 2,
        "min_length": 4,
    })
    client_generator = ClientGenerator(args)
    client_generator.excute()

    renderer.draw_generated_level(
        input_path=_generated_json_path, 
        output_path=_rendered_png_path
    )

if __name__ == "__main__":
    
    level_set_path = Path("level_set/level_set_2")
    # excute_folder(level_set_path)

    excute_single_file(level_set_path, "NIGHT.png", (30, 30))



