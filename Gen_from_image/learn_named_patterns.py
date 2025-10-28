# learn_named_patterns.py (fixed for your filename format)
import os
import json
import numpy as np
from collections import defaultdict, Counter
import re

SAMPLE_FOLDER = "sample levels"
OUTPUT_FILE = "pattern_profiles.json"

def extract_pattern_from_name(filename: str) -> str:
    """
    Ví dụ: '07-02__25x38___66___Aztec_.json' → 'Aztec'
    """
    base = os.path.splitext(filename)[0]
    # print(base)
    m = base.split("___")[-1]
    print(m)
    # m = re.search(r"___(\w+)_?$", base)
    # if m:
    #     print(m.group(1).replace("_", ""))
    #     return m.group(1)
    # return "Unknown"

    return m.replace("_", "")

def idx_to_xy(idx, XSize):
    return (idx % XSize, idx // XSize)

def extract_features(level):
    XSize, YSize = level["XSize"], level["YSize"]
    arrows = level["Arrows"]
    n = len(arrows)
    if n == 0:
        return None

    lengths = [len(a.get("Indices", [])) for a in arrows]
    mean_len = float(np.mean(lengths))
    std_len = float(np.std(lengths))
    min_len = int(min(lengths))
    max_len = int(max(lengths))

    dir_counter = Counter((a["Dx"], a["Dy"]) for a in arrows)
    directions = [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]
    dir_feats = {f"dir_{dx}_{dy}": dir_counter.get((dx,dy),0)/n for dx,dy in directions}

    xs, ys = [], []
    for a in arrows:
        xs.append(a["X"])
        ys.append(a["Y"])
    mean_x, mean_y = float(np.mean(xs)), float(np.mean(ys))
    var_x, var_y = float(np.var(xs)), float(np.var(ys))

    density = n / (XSize * YSize)
    edge_bias = sum(1 for (x,y) in zip(xs,ys) if x<=1 or x>=XSize-2 or y<=1 or y>=YSize-2)/n

    return {
        "mean_len": mean_len, "std_len": std_len,
        "min_len": min_len, "max_len": max_len,
        "mean_x": mean_x, "mean_y": mean_y,
        "var_x": var_x, "var_y": var_y,
        "density": density, "edge_bias": edge_bias,
        **dir_feats
    }

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
                groups[pattern].append(feats)
        except Exception as e:
            print(f"⚠️ Skip {f}: {e}")

    profiles = {}
    for pattern, lst in groups.items():
        keys = lst[0].keys()
        profiles[pattern] = {k: float(np.mean([f[k] for f in lst])) for k in keys}
        profiles[pattern]["count"] = len(lst)

    json.dump(profiles, open(OUTPUT_FILE, "w"), indent=2)
    print(f"✅ Saved {OUTPUT_FILE} ({len(profiles)} patterns)")

if __name__ == "__main__":
    aggregate_features()

