import pandas as pd
from types import SimpleNamespace


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

