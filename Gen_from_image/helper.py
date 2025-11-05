import pandas as pd
from types import SimpleNamespace
from pathlib import Path


class Args(SimpleNamespace):
    input_file: str
    output_file: str
    start_length: str
    length_step: str
    min_length: str
    id: int = 0
    item_path: str
    item_name: str
    level_set_path: str
    size: set = (0, 0)

    alter_item_name: str

    csv_path: str
    csv: pd.DataFrame

    generate_mode: str

    # Advance generator param
    turn_probability: float
    straight_weight: float
    left_weight: float
    right_weight: float
    max_turns: int

    def load_csv(self):
        # 1_0_original_icons: chứa template png -> scale lại theo size bỏ vào 1_1_icons 
        # -> convert sang board test -> generate arrow -> render ra img
        df = pd.read_csv(self.csv_path)
        return df
    
    def clone(self, **overrides):
        """Trả về bản sao của Args với các thuộc tính ghi đè"""
        data = vars(self).copy()
        data.update(overrides)
        return Args(**data)


def rename_json_files(folder_path: str):
    folder = Path(folder_path)
    if not folder.is_dir():
        print(f"Error: {folder} is not a valid directory.")
        return

    for file in folder.glob("*.json"):
        try:
            # Extract the number part (e.g. "1" from "1.json")
            stem = file.stem
            if not stem.isdigit():
                print(f"Skipping non-numeric file: {file.name}")
                continue

            new_name = f"{int(stem):04d}.json"  # pad with zeros to 4 digits
            new_path = file.with_name(new_name)

            # Only rename if name changes
            if file.name != new_name:
                file.rename(new_path)
                print(f"Renamed: {file.name} -> {new_name}")
        except Exception as e:
            print(f"Error renaming {file.name}: {e}")


import random

if __name__ == "__main__":

    name_list = [
        "square.png",
        "circle.png",
        "hexagon.png",
        "pentagon.png",
        "star.png",
    ]

    _name_list_loop = name_list * 4
    random.shuffle(_name_list_loop)
    for i in _name_list_loop:
        print(i)

