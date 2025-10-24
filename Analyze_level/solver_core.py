# solver_core.py
import json, math, os
EPS = 1e-9

def idx_to_xy(idx, XSize): return (idx % XSize, idx // XSize)
def indices_to_path(a, XSize): return [idx_to_xy(i, XSize) for i in a.get("Indices", [])]

def ray_intersect_segment(ray_origin, ray_dir, seg_a, seg_b):
    x0, y0 = ray_origin; r_dx, r_dy = ray_dir
    x1, y1 = seg_a; x2, y2 = seg_b
    s_dx, s_dy = x2 - x1, y2 - y1
    r_cross_s = r_dx * s_dy - r_dy * s_dx
    if abs(r_cross_s) < EPS: return None
    t = ((x1 - x0) * s_dy - (y1 - y0) * s_dx) / r_cross_s
    u = ((x1 - x0) * r_dy - (y1 - y0) * r_dx) / r_cross_s
    if t >= EPS and -EPS <= u <= 1 + EPS:
        return (x0 + t * r_dx, y0 + t * r_dy)
    return None

def point_on_ray_and_in_front(ray_origin, ray_dir, point):
    x0, y0 = ray_origin; r_dx, r_dy = ray_dir; px, py = point
    vx, vy = px - x0, py - y0
    if abs(r_dx * vy - r_dy * vx) > 1e-6: return False
    return vx * r_dx + vy * r_dy >= EPS

def find_solvable(arrows, XSize, YSize):
    solvable, debug_info = [], []
    polylines = [indices_to_path(a, XSize) for a in arrows]
    for i, a in enumerate(arrows):
        x0, y0, dx, dy = a["X"], a["Y"], a["Dx"], a["Dy"]
        nearest_hit, nearest_t = None, float("inf")
        for j, path in enumerate(polylines):
            for k in range(len(path) - 1):
                hit = ray_intersect_segment((x0, y0), (dx, dy), path[k], path[k+1])
                if not hit: continue
                ix, iy = hit
                t_val = (ix - x0) / dx if abs(dx) > abs(dy) else (iy - y0) / dy
                if t_val >= EPS and t_val < nearest_t:
                    nearest_hit, nearest_t = (ix, iy), t_val
        for j, path in enumerate(polylines):
            for v in path:
                if point_on_ray_and_in_front((x0, y0), (dx, dy), v):
                    vx, vy = v[0]-x0, v[1]-y0
                    t_val = vx/dx if abs(dx)>abs(dy) else vy/dy
                    if t_val >= EPS and t_val < nearest_t:
                        nearest_hit, nearest_t = v, t_val
        solvable.append(i if nearest_hit is None else None)
        debug_info.append({"arrow_index": i, "solvable": nearest_hit is None, "hit": nearest_hit})
    solvable = [i for i in solvable if i is not None]
    return solvable, debug_info


def solve_level(level_path, cache_folder="solved_data"):
    level_name = os.path.splitext(os.path.basename(level_path))[0]
    data = json.load(open(level_path))
    XSize, YSize = data["XSize"], data["YSize"]
    original_arrows = data["Arrows"]
    arrows = [a.copy() for a in original_arrows]
    states = []
    state_id = 1

    while arrows:
        solvable, debug_info = find_solvable(arrows, XSize, YSize)
        states.append({
            "state": state_id,
            "solvable": solvable,
            "debug": debug_info,
            # 👇 Thêm danh sách arrow còn lại ở state này
            "remaining_arrows": arrows.copy()
        })
        if not solvable:
            break
        arrows = [a for i, a in enumerate(arrows) if i not in solvable]
        state_id += 1

    info = {
        "name": level_name,
        "XSize": XSize,
        "YSize": YSize,
        "total_arrows": len(original_arrows),
        # 👇 Lưu thêm toàn bộ mũi tên gốc để reference
        "original_arrows": original_arrows,
        "states": states
    }

    os.makedirs(cache_folder, exist_ok=True)
    out_path = os.path.join(cache_folder, f"{level_name}.json")
    json.dump(info, open(out_path, "w"))
    return level_name, len(states), len(original_arrows)