import pandas as pd
from types import SimpleNamespace
from pathlib import Path
from loguru import logger


class Args(SimpleNamespace):
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
        df = df.fillna("")
        return df

    def clone(self, **overrides):
        """Trả về bản sao của Args với các thuộc tính ghi đè"""
        data = vars(self).copy()
        data.update(overrides)
        return Args(**data)


class Arrow:
    """
    Một cấu trúc dữ liệu đơn giản để chứa thông tin mũi tên.
    Trích xuất từ file gốc.
    """

    def __init__(self, points, direction, layer_id, arrow_id, color):
        self.points = points
        self.direction = direction
        self.layer_id = layer_id
        self.id = arrow_id
        self.color = color


def rename_json_files(folder_path: str):
    folder = Path(folder_path)
    if not folder.is_dir():
        logger.info(f"Error: {folder} is not a valid directory.")
        return

    for file in folder.glob("*.json"):
        try:
            # Extract the number part (e.g. "1" from "1.json")
            stem = file.stem
            if not stem.isdigit():
                logger.info(f"Skipping non-numeric file: {file.name}")
                continue

            new_name = f"{int(stem):04d}.json"  # pad with zeros to 4 digits
            new_path = file.with_name(new_name)

            # Only rename if name changes
            if file.name != new_name:
                file.rename(new_path)
                logger.info(f"Renamed: {file.name} -> {new_name}")
        except Exception as e:
            logger.info(f"Error renaming {file.name}: {e}")


import os
import sys


def list_files(folder_path, exclude=None):
    if exclude is None:
        exclude = {".DS_Store", ".DC"}  # default exclusions

    try:
        items = os.listdir(folder_path)
    except FileNotFoundError:
        print("Error: Folder not found.")
        return
    except NotADirectoryError:
        print("Error: Path is not a folder.")
        return

    # Filter files
    files = [
        f
        for f in items
        if os.path.isfile(os.path.join(folder_path, f)) and f not in exclude
    ]

    return files

def get_random_shiet():
    # ======= Cấu hình =======
    # name_list = ["square", "circle", "pentagon", "triangle", "rhombus", "rectangle"]
    name_list = ["Aztec", "Snake", "Spaghetti"]
    total_items = 625
    min_distance = 1
    step_hard = 7
    step_very_hard = 21
    random.seed(3009199911112025114200001)

    # ======= Sinh list ngẫu nhiên dàn đều =======
    count_per_item = total_items // len(name_list)
    pool = [n for n in name_list for _ in range(count_per_item)]

    while len(pool) < total_items:
        pool.append(random.choice(name_list))

    result = []
    recent = []

    while pool:
        candidates = [x for x in set(pool) if x not in recent]
        if not candidates:
            recent = []
            candidates = list(set(pool))
        choice = random.choice(candidates)
        result.append(choice)
        pool.remove(choice)
        recent.append(choice)
        if len(recent) > min_distance:
            recent.pop(0)

    # ======= Gắn cờ hard / very hard =======
    # for i in range(len(result)):
    #     if i % step_very_hard == 0:
    #         result[i] = "-----very_hard-----"
    #     elif i % step_hard == 0:
    #         result[i] = "-------hard--------"

    # ======= Hàm thống kê lặp lại =======
    def analyze_repeats(seq, group_size=2):
        """Trả về thông tin bộ (group_size) bị lặp lại, vị trí và khoảng cách."""
        seen = defaultdict(list)
        for i in range(len(seq) - group_size + 1):
            key = tuple(seq[i : i + group_size])
            seen[key].append(i)

        report = []
        for key, positions in seen.items():
            if len(positions) > 1:
                distances = [
                    positions[i + 1] - positions[i] for i in range(len(positions) - 1)
                ]
                report.append(
                    {
                        "pattern": key,
                        "count": len(positions),
                        "positions": positions,
                        "min_distance": min(distances) if distances else None,
                    }
                )
        return report

    # ======= Phân tích bộ 2 và bộ 3 =======
    report_2 = analyze_repeats(result, 2)
    report_3 = analyze_repeats(result, 3)

    # ======= In thống kê =======
    def print_report(report, title):
        logger.info(f"\n===== {title} =====")
        if not report:
            logger.info("Không có bộ nào bị lặp lại.")
            return
        for r in sorted(report, key=lambda x: x["min_distance"] or 999):
            logger.info(
                f"{r['pattern']} -> lặp {r['count']} lần, khoảng cách nhỏ nhất {r['min_distance']}, vị trí {r['positions']}"
            )

    print_report(report_2, "BỘ 2 LẶP LẠI")
    print_report(report_3, "BỘ 3 LẶP LẠI")

    # ======= Kiểm tra nhanh output =======
    logger.info("\n--- Một phần sequence ---")
    for i in result:
        logger.info(i)

def get_files_name_in_folder(folder_path: Path):

    # Add more excluded names here if needed
    excluded_names = {".DS_Store", ".DC", "example.txt", "ignore.me"}

    result = list_files(folder_path, excluded_names)

    if result is not None:
        print("Files found:")
        for f in result:
            print(f)

import random
from collections import defaultdict

if __name__ == "__main__":

    folder_path_to_get_files_name = Path(__file__).parent / "level_set" / "level_set_7_daily_challenge" / "1_0_original_icons"

    get_files_name_in_folder(folder_path_to_get_files_name)

    
