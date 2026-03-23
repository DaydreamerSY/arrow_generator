# File: helper.py
# Data classes và utilities dùng chung cho toàn bộ pipeline.

import pandas as pd
from types import SimpleNamespace
from pathlib import Path


class Args(SimpleNamespace):
    """Chứa toàn bộ config cho pipeline."""
    input_file: str
    output_file: str
    start_length: str
    length_step: str
    min_length: str
    level_id: str
    template_name: str
    item_path: str
    item_name: str
    level_set_path: str
    size: set = (0, 0)
    progress_callback: callable

    alter_item_name: str

    csv_path: Path
    csv: pd.DataFrame

    generate_mode: str

    # Advance generator params
    turn_probability: float
    straight_weight: float
    left_weight: float
    right_weight: float
    max_turns: int

    # Gameplay Difficulty Constraints
    min_width: int = None
    max_width: int = None
    initial_width: int = None  # Số arrows phải removable ở bước đầu tiên

    # Boundary Arrow Config
    enable_boundary: bool = False       # Bật/tắt boundary generation
    boundary_max_length: int = 20       # Độ dài tối đa mỗi boundary arrow
    boundary_min_parts: int = 1         # Số phần tối thiểu khi split boundary

    def load_csv(self):
        df = pd.read_csv(self.csv_path)
        df = df.fillna("")
        return df

    def clone(self, **overrides):
        """Trả về bản sao của Args với các thuộc tính ghi đè."""
        data = vars(self).copy()
        data.update(overrides)
        return Args(**data)


class Arrow:
    """Cấu trúc dữ liệu chứa thông tin 1 mũi tên."""

    def __init__(self, points, direction, layer_id, arrow_id, color):
        self.points = points
        self.direction = direction
        self.layer_id = layer_id
        self.id = arrow_id
        self.color = color
