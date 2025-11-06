# learn_named_patterns.py (Đã sửa đổi để xuất ra TRỌNG SỐ TƯƠNG ĐỐI)
import os
import json
import numpy as np
from collections import defaultdict, Counter
import re

SAMPLE_FOLDER = "sample levels"
OUTPUT_FILE = "pattern_profiles.json"
MIN_WEIGHT_THRESHOLD = 1e-6  # Ngưỡng để coi là "khác không"

# --- Các hàm extract_pattern_from_name, idx_to_xy, get_turn_type ---
# --- (Giữ nguyên, không thay đổi từ câu trả lời trước) ---


def extract_pattern_from_name(filename: str) -> str:
    base = os.path.splitext(filename)[0]
    m = base.split("___")[-1]
    return m.replace("_", "")


def idx_to_xy(idx, XSize):
    return (idx % XSize, idx // XSize)


def get_turn_type(v1, v2):
    if v1 == v2:
        return 'straight'
    cross_product_z = v1[0] * v2[1] - v1[1] * v2[0]
    if cross_product_z > 0:
        return 'left'
    elif cross_product_z < 0:
        return 'right'
    else:
        return 'turn'


def extract_features(level):
    XSize, YSize = level["XSize"], level["YSize"]
    arrows = level["Arrows"]
    n = len(arrows)
    if n == 0:
        return None

    # (Tất cả logic bên trong extract_features giữ nguyên)
    lengths = []
    xs, ys = [], []
    dir_counter = Counter()
    first_turn_types = []
    turn_counts_per_arrow = []
    turn_properties_per_arrow = []

    for a in arrows:
        indices = a.get("Indices", [])
        lengths.append(len(indices))
        xs.append(a["X"])
        ys.append(a["Y"])
        dir_counter[(a["Dx"], a["Dy"])] += 1
        path_len = len(indices)
        if path_len < 3:
            first_turn_types.append('straight')
            turn_counts_per_arrow.append(0)
            continue
        p1 = idx_to_xy(indices[0], XSize)
        p2 = idx_to_xy(indices[1], XSize)
        v_prev = (p2[0] - p1[0], p2[1] - p1[1])
        current_turns = 0
        found_first_turn = False
        for i in range(2, path_len):
            p_curr = idx_to_xy(indices[i-1], XSize)
            p_next = idx_to_xy(indices[i], XSize)
            v_curr = (p_next[0] - p_curr[0], p_next[1] - p_curr[1])
            turn_type = get_turn_type(v_prev, v_curr)
            if not found_first_turn and turn_type != 'straight':
                first_turn_types.append(turn_type)
                found_first_turn = True
            if turn_type == 'left' or turn_type == 'right':
                current_turns += 1
            v_prev = v_curr
        if not found_first_turn:
            first_turn_types.append('straight')
        turn_counts_per_arrow.append(current_turns)
        turn_properties_per_arrow.append(current_turns / path_len)

    # (Phần tổng hợp kết quả cũng giữ nguyên)
    mean_len = float(np.mean(lengths))
    avg_len = float(np.average(lengths))
    std_len = float(np.std(lengths))
    min_len = int(min(lengths))
    max_len = int(max(lengths))
    directions = [(1, 0), (-1, 0), (0, 1), (-1, 0),
                  (1, 1), (-1, 1), (1, -1), (-1, -1)]
    dir_feats = {f"dir_{dx}_{dy}": dir_counter.get(
        (dx, dy), 0)/n for dx, dy in directions}
    mean_x, mean_y = float(np.mean(xs)), float(np.mean(ys))
    var_x, var_y = float(np.var(xs)), float(np.var(ys))
    density = n / (XSize * YSize)
    edge_bias = sum(1 for (x, y) in zip(xs, ys) if x <=
                    1 or x >= XSize-2 or y <= 1 or y >= YSize-2)/n
    turn_counter = Counter(first_turn_types)

    # QUAN TRỌNG: Chúng ta vẫn tính toán XÁC SUẤT ở đây
    left_weight = turn_counter.get('left', 0) / n
    right_weight = turn_counter.get('right', 0) / n
    straight_weight = turn_counter.get('straight', 0) / n
    max_turns = 0
    if turn_counts_per_arrow:
        max_turns = int(max(turn_counts_per_arrow))
    turn_probability = float(np.average(turn_properties_per_arrow))

    return {
        "mean_len": mean_len, "avg_len": avg_len, "std_len": std_len, "min_len": min_len,
        "mean_x": mean_x, "mean_y": mean_y, "var_x": var_x, "var_y": var_y,
        "density": density, "edge_bias": edge_bias, **dir_feats,
        "max_len": max_len, "left_weight": left_weight,
        "right_weight": right_weight, "straight_weight": straight_weight,
        "turn_probability": turn_probability, "max_turns": max_turns
    }

# --- HÀM aggregate_features (ĐÃ THAY ĐỔI) ---


def aggregate_features(folder=SAMPLE_FOLDER):
    groups = defaultdict(list)
    for f in os.listdir(folder):
        if not f.endswith(".json"):
            continue
        pattern = extract_pattern_from_name(f)
        try:
            data = json.load(open(os.path.join(folder, f)))
            feats = extract_features(data)

            if feats:
                # === BẮT ĐẦU THAY ĐỔI: LOGIC "LẬT" (FLIP) ===

                # Kiểm tra xem có phải là level "xoắn phải" (mirrored) không
                if feats['right_weight'] > feats['left_weight']:
                    # Nếu đúng, lật nó lại
                    temp_left = feats['left_weight']
                    feats['left_weight'] = feats['right_weight']
                    feats['right_weight'] = temp_left

                # === KẾT THÚC THAY ĐỔI ===

                groups[pattern].append(feats)

        except Exception as e:
            print(f"⚠️ Skip {f}: {e}")

    profiles = {}
    for pattern, lst in groups.items():
        if not lst:
            continue
        keys = lst[0].keys()

        # Bước 1: Tính toán giá trị trung bình
        profiles[pattern] = {
            k: float(np.mean([f[k] for f in lst])) for k in keys}
        profiles[pattern]["count"] = len(lst)

        # === BƯỚC CHUẨN HÓA (Giữ nguyên như cũ) ===
        l_prob = profiles[pattern]["left_weight"]
        r_prob = profiles[pattern]["right_weight"]
        s_prob = profiles[pattern]["straight_weight"]

        probs = [l_prob, r_prob, s_prob]
        min_positive_prob = 1.0
        positive_probs = [p for p in probs if p > MIN_WEIGHT_THRESHOLD]

        if positive_probs:
            min_positive_prob = min(positive_probs)

        profiles[pattern]["left_weight"] = l_prob / min_positive_prob
        profiles[pattern]["right_weight"] = r_prob / min_positive_prob
        profiles[pattern]["straight_weight"] = s_prob / min_positive_prob
        # === KẾT THÚC BƯỚC CHUẨN HÓA ===

    json.dump(profiles, open(OUTPUT_FILE, "w"), indent=2)
    print(f"✅ Saved {OUTPUT_FILE} ({len(profiles)} patterns)")
    # print(f"ℹ️ Weights have been normalized and mirrored. (e.g., Aztec is now 9.0, 1.0)")


if __name__ == "__main__":
    aggregate_features()
