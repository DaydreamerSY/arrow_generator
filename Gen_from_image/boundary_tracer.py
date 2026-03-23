# File: boundary_tracer.py
# Port từ BoundaryTracer.cs (C#) sang Python.
# Trace viền ngoài của editable area bằng Moore boundary tracing,
# tạo boundary arrows hướng ra ngoài, đảm bảo initial removable.

import math
from helper import Arrow

# 4 hướng: phải, xuống, trái, lên
DIRS_4 = [(1, 0), (0, 1), (-1, 0), (0, -1)]

# 8 hướng theo chiều kim đồng hồ: E, SE, S, SW, W, NW, N, NE
DIRS_8 = [
    (1, 0),    # 0: E
    (1, 1),    # 1: SE
    (0, 1),    # 2: S
    (-1, 1),   # 3: SW
    (-1, 0),   # 4: W
    (-1, -1),  # 5: NW
    (0, -1),   # 6: N
    (1, -1)    # 7: NE
]


def _find_dir8_index(dx, dy):
    """Tìm index của direction trong DIRS_8."""
    for i, (ddx, ddy) in enumerate(DIRS_8):
        if ddx == dx and ddy == dy:
            return i
    return -1


def _make_path_4connected(path8, editable_area):
    """
    Chuyển path 8-connected thành 4-connected bằng cách chèn
    cell trung gian cho mỗi bước chéo (diagonal).
    """
    if len(path8) <= 1:
        return list(path8)

    result = []
    in_path = set()

    for i in range(len(path8)):
        if path8[i] not in in_path:
            result.append(path8[i])
            in_path.add(path8[i])

        next_idx = i + 1
        if next_idx >= len(path8):
            break

        dx = path8[next_idx][0] - path8[i][0]
        dy = path8[next_idx][1] - path8[i][1]

        # Nếu Manhattan distance <= 1 → đã 4-connected, skip
        if abs(dx) + abs(dy) <= 1:
            continue

        # Chèn cell trung gian: thử horizontal-first, rồi vertical-first
        opt_h = (path8[i][0] + dx, path8[i][1])
        opt_v = (path8[i][0], path8[i][1] + dy)

        if opt_h in editable_area and opt_h not in in_path:
            intermediate = opt_h
        elif opt_v in editable_area and opt_v not in in_path:
            intermediate = opt_v
        elif opt_h in editable_area:
            intermediate = opt_h
        elif opt_v in editable_area:
            intermediate = opt_v
        else:
            continue  # Không resolve được diagonal → skip

        if intermediate not in in_path:
            result.append(intermediate)
            in_path.add(intermediate)

    return result


def trace_boundary(editable_area, board_w, board_h):
    """
    Trace viền ngoài của editable area bằng Moore boundary tracing.
    Scan 8-connected, rồi convert sang 4-connected path.
    """
    if not editable_area:
        return []

    # Tìm cell bắt đầu: topmost (min y), leftmost (min x)
    start = min(editable_area, key=lambda c: (c[1], c[0]))

    # Backtrack position: cell phía trên start (đảm bảo ngoài area cho topmost cell)
    backtrack_pos = (start[0], start[1] - 1)
    trace = [start]
    current = start
    max_iter = len(editable_area) * 4

    for _ in range(max_iter):
        bt_dx = backtrack_pos[0] - current[0]
        bt_dy = backtrack_pos[1] - current[1]
        bt_idx = _find_dir8_index(bt_dx, bt_dy)
        if bt_idx < 0:
            break

        moved = False
        last_outside = backtrack_pos

        for i in range(1, 9):
            scan_idx = (bt_idx + i) % 8
            ddx, ddy = DIRS_8[scan_idx]
            neighbor = (current[0] + ddx, current[1] + ddy)

            if neighbor in editable_area:
                backtrack_pos = last_outside
                current = neighbor

                if current == start and len(trace) > 2:
                    # Đã quay về start → xong
                    return _make_path_4connected(trace, editable_area)

                trace.append(current)
                moved = True
                break

            last_outside = neighbor

        if not moved:
            break

    return _make_path_4connected(trace, editable_area)


def _split_at_connectivity_gaps(path):
    """
    Tách path tại các chỗ không 4-connected (Manhattan distance > 1).
    Trả về list các segment đều 4-connected.
    """
    result = []
    if not path:
        return result

    current_seg = [path[0]]
    for i in range(1, len(path)):
        dx = path[i][0] - path[i - 1][0]
        dy = path[i][1] - path[i - 1][1]
        if abs(dx) + abs(dy) == 1:
            current_seg.append(path[i])
        else:
            if len(current_seg) >= 2:
                result.append(current_seg)
            current_seg = [path[i]]

    if len(current_seg) >= 2:
        result.append(current_seg)

    return result


def _has_outward_neighbor(cell, editable_area):
    """Kiểm tra cell có ít nhất 1 neighbor 4-connected nằm ngoài editable area."""
    for dx, dy in DIRS_4:
        if (cell[0] + dx, cell[1] + dy) not in editable_area:
            return True
    return False


def split_path(path, max_length, min_parts=1):
    """
    Tách path thành sub-paths.
    Đảm bảo mỗi phần <= max_length và có ít nhất min_parts phần.
    """
    result = []
    if not path:
        return result

    parts_for_length = math.ceil(len(path) / max_length) if max_length > 0 else 1
    num_parts = max(parts_for_length, min_parts, 1)
    num_parts = min(num_parts, len(path))

    if num_parts <= 1:
        result.append(list(path))
        return result

    part_len = len(path) // num_parts

    for i in range(num_parts):
        start_idx = i * part_len
        end_idx = len(path) if i == num_parts - 1 else (i + 1) * part_len
        result.append(path[start_idx:end_idx])

    return result


def split_path_at_outward_cells(path, max_length, min_parts, editable_area, board_w, board_h):
    """
    Smart split: chọn điểm cắt sao cho direction tự nhiên (path[i] - path[i+1])
    hướng ra NGOÀI editable area VÀ exit ray không bị chặn bởi boundary cells khác.
    """
    result = []
    if not path:
        return result

    parts_for_length = math.ceil(len(path) / max_length) if max_length > 0 else 1
    num_parts = max(parts_for_length, min_parts, 1)
    num_parts = min(num_parts, len(path))

    if num_parts <= 1:
        result.append(list(path))
        return result

    # Build set tất cả boundary cells để ray-check
    boundary_set = set(path)

    # Tìm indices có direction outward + exit ray clear
    outward_dir_indices = []
    for i in range(len(path) - 1):
        dx = path[i][0] - path[i + 1][0]
        dy = path[i][1] - path[i + 1][1]
        # Skip diagonal pairs
        if abs(dx) + abs(dy) != 1:
            continue
        move_target = (path[i][0] + dx, path[i][1] + dy)
        if move_target in editable_area:
            continue

        # Trace full ray từ head đến board edge
        clear = True
        px, py = move_target
        while 0 <= px < board_w and 0 <= py < board_h:
            if (px, py) in boundary_set:
                clear = False
                break
            px += dx
            py += dy

        if clear:
            outward_dir_indices.append(i)

    # Fallback 1: chỉ outward cardinal, không check ray
    if len(outward_dir_indices) < num_parts:
        outward_dir_indices.clear()
        for i in range(len(path) - 1):
            dx = path[i][0] - path[i + 1][0]
            dy = path[i][1] - path[i + 1][1]
            if abs(dx) + abs(dy) != 1:
                continue
            move_target = (path[i][0] + dx, path[i][1] + dy)
            if move_target not in editable_area:
                outward_dir_indices.append(i)

    # Fallback 2: bất kỳ cell nào có outward neighbor
    if len(outward_dir_indices) < num_parts:
        outward_dir_indices.clear()
        for i in range(len(path)):
            if _has_outward_neighbor(path[i], editable_area):
                outward_dir_indices.append(i)

    # Fallback cuối: dùng split_path đơn giản
    if len(outward_dir_indices) < num_parts:
        return split_path(path, max_length, min_parts)

    # Chọn num_parts split points, cách đều nhau nhất có thể
    split_starts = []
    for p in range(num_parts):
        ideal_idx = int(p * len(path) / num_parts)

        best_candidate = -1
        best_dist = float('inf')
        for ci in outward_dir_indices:
            last_end = (split_starts[-1] + 2) if split_starts else 0
            if ci < last_end:
                continue
            dist = abs(ci - ideal_idx)
            if dist < best_dist:
                best_dist = dist
                best_candidate = ci

        if best_candidate >= 0:
            split_starts.append(best_candidate)

    # Build sub-paths
    for i in range(len(split_starts)):
        start_idx = split_starts[i]
        end_idx = split_starts[i + 1] if i + 1 < len(split_starts) else len(path)
        if end_idx <= start_idx:
            continue
        result.append(path[start_idx:end_idx])

    return result


def _split_at_self_overlaps(sub_paths):
    """
    Tách sub-path nào visit cùng 1 cell hai lần (self-overlap tại U-turn).
    """
    result = []
    for path in sub_paths:
        seen = set()
        split_idx = -1
        for i, cell in enumerate(path):
            if cell in seen:
                split_idx = i
                break
            seen.add(cell)

        if split_idx < 0:
            result.append(path)
        else:
            part1 = path[:split_idx]
            part2 = path[split_idx:]
            if len(part1) >= 2:
                result.append(part1)
            if len(part2) >= 2:
                sub = _split_at_self_overlaps([part2])
                result.extend(sub)

    return result


def _dist_to_edge(pos, direction, board_w, board_h):
    """Số cell từ pos đến board edge theo direction."""
    dx, dy = direction
    if dx == 1:  return board_w - 1 - pos[0]
    if dx == -1: return pos[0]
    if dy == 1:  return board_h - 1 - pos[1]
    if dy == -1: return pos[1]
    return float('inf')


def _can_exit_cleanly(arrow, other_arrows, grid_w, grid_h):
    """
    Kiểm tra arrow có thể exit grid theo direction mà không bị chặn
    bởi obstacle cells (từ other_arrows + own body trừ head).
    """
    obstacles = set()
    for other in other_arrows:
        for p in other.points:
            obstacles.add(p)

    # Own body (tất cả trừ head)
    for i in range(1, len(arrow.points)):
        obstacles.add(arrow.points[i])

    head = arrow.points[0]
    dx, dy = arrow.direction
    if dx == 0 and dy == 0:
        return False

    px, py = head[0] + dx, head[1] + dy

    while 0 <= px < grid_w and 0 <= py < grid_h:
        if (px, py) in obstacles:
            return False
        px += dx
        py += dy

    return True


def compute_outward_direction(arrow_points, editable_area, board_w=0, board_h=0):
    """
    Tính direction hướng ra ngoài cho head của boundary arrow.
    Ưu tiên hướng gần board edge nhất (exit nhanh nhất).
    """
    if not arrow_points:
        return (0, -1)

    head = arrow_points[0]

    # Thu thập tất cả outward directions
    outward_dirs = []
    for dx, dy in DIRS_4:
        if (head[0] + dx, head[1] + dy) not in editable_area:
            outward_dirs.append((dx, dy))

    if not outward_dirs:
        return (0, -1)

    if len(outward_dirs) == 1:
        return outward_dirs[0]

    # Chọn direction có khoảng cách đến board edge ngắn nhất
    if board_w > 0 and board_h > 0:
        best_dir = outward_dirs[0]
        best_dist = float('inf')
        for d in outward_dirs:
            dist = _dist_to_edge(head, d, board_w, board_h)
            if dist < best_dist:
                best_dist = dist
                best_dir = d
        return best_dir

    # Fallback: ưu tiên perpendicular to path, rồi forward
    if len(arrow_points) >= 2:
        pdx = arrow_points[1][0] - arrow_points[0][0]
        pdy = arrow_points[1][1] - arrow_points[0][1]
        left_normal = (-pdy, pdx)
        right_normal = (pdy, -pdx)
        forward = (-pdx, -pdy)

        if left_normal in outward_dirs:  return left_normal
        if right_normal in outward_dirs: return right_normal
        if forward in outward_dirs:      return forward

    return outward_dirs[0]


def generate_boundary_arrows(editable_area, board_w, board_h, max_length, start_arrow_id, min_parts=1):
    """
    Tạo boundary arrows từ editable area.
    1. Trace boundary (Moore 8-connected → 4-connected)
    2. Split tại connectivity gaps
    3. Smart split mỗi segment tại outward cells
    4. Loại bỏ self-overlaps
    5. Tạo Arrow objects với direction hướng ra ngoài
    6. Trim overlap giữa arrows kề nhau
    7. Verify exit cleanly, reverse nếu cần
    """
    boundary_path = trace_boundary(editable_area, board_w, board_h)

    if len(boundary_path) < 3:
        return []

    # Tách tại connectivity gaps
    segments = _split_at_connectivity_gaps(boundary_path)

    all_sub_paths = []
    for segment in segments:
        if len(segment) < 2:
            continue
        # Phân bổ min_parts tỷ lệ theo segment length
        seg_min_parts = max(1, round(min_parts * len(segment) / len(boundary_path)))
        seg_subs = split_path_at_outward_cells(
            segment, max_length, seg_min_parts, editable_area, board_w, board_h
        )
        all_sub_paths.extend(seg_subs)

    # Tách self-overlaps
    all_sub_paths = _split_at_self_overlaps(all_sub_paths)

    arrows = []
    arrow_id = start_arrow_id

    for sub_path in all_sub_paths:
        if len(sub_path) < 2:
            continue

        # Direction = Points[0] - Points[1] (game convention)
        direction = (sub_path[0][0] - sub_path[1][0], sub_path[0][1] - sub_path[1][1])
        arrow = Arrow(sub_path, direction, 0, arrow_id, (128, 128, 128))  # gray
        arrows.append(arrow)
        arrow_id += 1

    # Loại bỏ overlap cells giữa boundary arrows kề nhau
    for i in range(len(arrows)):
        used_by_others = set()
        for j in range(len(arrows)):
            if j == i:
                continue
            for p in arrows[j].points:
                used_by_others.add(p)

        # Trim từ tail
        while len(arrows[i].points) > 2 and arrows[i].points[-1] in used_by_others:
            arrows[i].points.pop()

        # Trim từ head (ít gặp hơn)
        while len(arrows[i].points) > 2 and arrows[i].points[0] in used_by_others:
            arrows[i].points.pop(0)

        # Tính lại direction sau trim
        if len(arrows[i].points) >= 2:
            arrows[i].direction = (
                arrows[i].points[0][0] - arrows[i].points[1][0],
                arrows[i].points[0][1] - arrows[i].points[1][1]
            )

    # Verify exit cleanly, reverse nếu cần (chỉ khi reversed cũng outward)
    for i in range(len(arrows)):
        arrow = arrows[i]
        others = [a for j, a in enumerate(arrows) if j != i]

        arrow.direction = (arrow.points[0][0] - arrow.points[1][0],
                           arrow.points[0][1] - arrow.points[1][1])

        if _can_exit_cleanly(arrow, others, board_w, board_h):
            continue

        # Blocked → thử reversed
        orig_points = list(arrow.points)
        rev = list(reversed(orig_points))
        dir_rev = (rev[0][0] - rev[1][0], rev[0][1] - rev[1][1])
        rev_move_target = (rev[0][0] + dir_rev[0], rev[0][1] + dir_rev[1])
        rev_is_outward = rev_move_target not in editable_area

        if rev_is_outward:
            arrow.points = rev
            arrow.direction = dir_rev
            if _can_exit_cleanly(arrow, others, board_w, board_h):
                continue

            # Reversed cũng blocked → chọn hướng gần edge hơn
            dir_orig = (orig_points[0][0] - orig_points[1][0],
                        orig_points[0][1] - orig_points[1][1])
            d_orig = _dist_to_edge(orig_points[0], dir_orig, board_w, board_h)
            d_rev = _dist_to_edge(rev[0], dir_rev, board_w, board_h)
            if d_orig <= d_rev:
                arrow.points = orig_points
                arrow.direction = dir_orig

    return arrows


def fix_boundary_directions(boundary_arrows, all_arrows, editable_area, board_w, board_h):
    """
    Fix lại direction của boundary arrows SAU KHI tất cả arrows (interior + boundary)
    đã được đặt. Đảm bảo exit cleanly, reverse nếu cần.
    """
    for b_arrow in boundary_arrows:
        others = [a for a in all_arrows if a.id != b_arrow.id]

        # Enforce direction = head - body[1]
        b_arrow.direction = (b_arrow.points[0][0] - b_arrow.points[1][0],
                             b_arrow.points[0][1] - b_arrow.points[1][1])

        if _can_exit_cleanly(b_arrow, others, board_w, board_h):
            continue

        # Blocked → thử reversed (chỉ khi reversed cũng outward)
        orig_points = list(b_arrow.points)
        rev = list(reversed(orig_points))
        dir_rev = (rev[0][0] - rev[1][0], rev[0][1] - rev[1][1])
        rev_move_target = (rev[0][0] + dir_rev[0], rev[0][1] + dir_rev[1])
        rev_is_outward = rev_move_target not in editable_area

        if rev_is_outward:
            b_arrow.points = rev
            b_arrow.direction = dir_rev
            if _can_exit_cleanly(b_arrow, others, board_w, board_h):
                continue

            dir_orig = (orig_points[0][0] - orig_points[1][0],
                        orig_points[0][1] - orig_points[1][1])
            d_orig = _dist_to_edge(orig_points[0], dir_orig, board_w, board_h)
            d_rev = _dist_to_edge(rev[0], dir_rev, board_w, board_h)
            if d_orig <= d_rev:
                b_arrow.points = orig_points
                b_arrow.direction = dir_orig
