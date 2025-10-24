import os, json, csv, gzip

SOLVED_FOLDER = "_solved_data"
OUTPUT_CSV = "out_put/analysis.csv"

def load_json(path):
    if path.endswith(".gz"):
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    else:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

def analyze_level(level_data, filename):
    # 🔧 fix lỗi expected str, bytes or os.PathLike
    name = level_data.get("name", os.path.splitext(os.path.basename(filename))[0])
    XSize, YSize = level_data["XSize"], level_data["YSize"]
    total_arrows = level_data["total_arrows"]
    states = level_data["states"]

    # 1️⃣ Solvable per state
    solvable_counts = [len(s.get("solvable", [])) for s in states]
    total_states = len(states)

    # 2️⃣ Arrow lengths
    all_arrows = level_data.get("original_arrows") or []
    if not all_arrows and "remaining_arrows" in states[0]:
        all_arrows = states[0]["remaining_arrows"]

    lengths = [len(a["Indices"]) for a in all_arrows if "Indices" in a]
    max_len = max(lengths) if lengths else 0
    min_len = min(lengths) if lengths else 0
    avg_len = round(sum(lengths) / len(lengths), 2) if lengths else 0

    # 3️⃣ Histogram
    hist = {}
    for L in lengths:
        hist[L] = hist.get(L, 0) + 1

    # 4️⃣ Unused points
    used = {idx for a in all_arrows for idx in a.get("Indices", [])}
    total_points = XSize * YSize
    unused_points = total_points - len(used)

    # 5️⃣ Optional: solvable ratio
    total_solved = sum(solvable_counts)
    solvable_ratio = round(total_solved / total_arrows / total_states, 3) if total_states else 0

    return {
        "name": name,
        "total_arrows": total_arrows,
        "total_states": total_states,
        "solvable_per_state": solvable_counts,
        "max_len": max_len,
        "min_len": min_len,
        "avg_len": avg_len,
        "unused_points": unused_points,
        "length_hist": hist,
        "solvable_ratio": solvable_ratio
    }

def main():
    os.makedirs(os.path.dirname(OUTPUT_CSV), exist_ok=True)
    files = [f for f in os.listdir(SOLVED_FOLDER) if f.endswith(".json") or f.endswith(".json.gz")]
    results = []
    print(f"Analyzing {len(files)} solved levels...")

    for file in files:
        path = os.path.join(SOLVED_FOLDER, file)
        try:
            data = load_json(path)
            info = analyze_level(data, file)
            results.append(info)
            print(f"✅ {info['name']}: {info['total_states']} states, {info['total_arrows']} arrows")
        except Exception as e:
            print(f"❌ Error analyzing {file}: {e}")

    # Write CSV
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            "Level Name",
            "Total Arrows",
            "Total States",
            "Solvable per State",
            "Max Len",
            "Min Len",
            "Avg Len",
            "Unused Points",
            "Length Histogram",
            "Solvable Ratio"
        ])
        for r in results:
            writer.writerow([
                r["name"],
                r["total_arrows"],
                r["total_states"],
                r["solvable_per_state"],
                r["max_len"],
                r["min_len"],
                r["avg_len"],
                r["unused_points"],
                json.dumps(r["length_hist"]),
                r["solvable_ratio"]
            ])

    print(f"\n✅ CSV saved to: {OUTPUT_CSV}")

if __name__ == "__main__":
    main()
