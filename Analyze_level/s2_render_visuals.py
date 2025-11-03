import os
import json
import matplotlib.pyplot as plt
import random

# ================= CONFIG =================
CACHE_FOLDER = "_solved_data"
OUTPUT_ROOT = "_debug_results"

# Mode hiển thị ray cast: "solve_only", "unsolve_only", "both"
DEBUG_MODE_RAY = "solve_only"

# ================= DRAW FUNCTION =================
def draw_state(level_data, state):
    XSize, YSize = level_data["XSize"], level_data["YSize"]
    name = level_data["name"]
    out_dir = os.path.join(OUTPUT_ROOT, "visuals", name)
    os.makedirs(out_dir, exist_ok=True)

    plt.figure(figsize=(XSize / 2.5, YSize / 2.5))
    ax = plt.gca()
    ax.set_xlim(-0.5, XSize - 0.5)
    ax.set_ylim(-0.5, YSize - 0.5)
    ax.set_aspect("equal")
    ax.invert_yaxis()
    plt.axis("off")
    plt.title(f"{name} — State {state['state']}", fontsize=9)

    random.seed(42)
    remaining_arrows = state.get("remaining_arrows", [])
    colors = [(random.random(), random.random(), random.random()) for _ in remaining_arrows]

    # --- Vẽ tất cả arrow (polyline + đầu mũi tên)
    for i, a in enumerate(remaining_arrows):
        pts = [(idx % XSize, idx // XSize) for idx in a.get("Indices", [])]
        if not pts:
            continue
        xs, ys = zip(*pts)
        ax.plot(xs, ys, color=colors[i], linewidth=3)

        # vẽ đầu mũi tên
        ax.arrow(
            a["X"], a["Y"], a["Dx"] * 0.001, a["Dy"] * 0.001,
            head_width=0.35, head_length=0.35,
            fc="black", ec="none", zorder=3
        )

    # --- Vẽ ray cast (theo mode)
    for dbg in state["debug"]:
        arrow_idx = dbg["arrow_index"]
        if arrow_idx >= len(remaining_arrows):
            continue
        a = remaining_arrows[arrow_idx]
        x0, y0, dx, dy = a["X"], a["Y"], a["Dx"], a["Dy"]
        is_solvable = dbg["solvable"]

        # Lọc theo DEBUG_MODE_RAY
        if DEBUG_MODE_RAY == "solve_only" and not is_solvable:
            continue
        if DEBUG_MODE_RAY == "unsolve_only" and is_solvable:
            continue

        color = "green" if is_solvable else "red"
        # Ray chỉ để minh họa, kẻ dài ra tới biên bản đồ
        ray_length = max(XSize, YSize)
        xs = [x0, x0 + dx * ray_length]
        ys = [y0, y0 + dy * ray_length]
        ax.plot(xs, ys, color=color, linestyle="--", alpha=0.5)

        # Đánh dấu điểm va chạm (nếu có)
        if dbg.get("hit"):
            hx, hy = dbg["hit"]
            ax.scatter([hx], [hy], marker="x", c=color, s=40, zorder=4)

    # --- Save figure
    save_path = os.path.join(out_dir, f"state_{state['state']:02d}.png")
    plt.savefig(save_path, dpi=200, bbox_inches="tight", pad_inches=0.05)
    plt.close()

# ================= MAIN =================
def main():
    for file in os.listdir(CACHE_FOLDER):
        if not file.endswith(".json"):
            continue
        path = os.path.join(CACHE_FOLDER, file)
        data = json.load(open(path, "r", encoding="utf-8"))

        for state in data["states"]:
            draw_state(data, state)

        print(f"✅ Rendered {data['name']} ({len(data['states'])} states)")

if __name__ == "__main__":
    main()
