# Gameplay Simulation Tool — Design Discussion Summary

## 1. Bối cảnh

### Game hiện tại
- Puzzle dạng **arrow exit**: player tap arrow có đường thoát ra rìa board (không bị block bởi arrow khác).
- Arrow bị xóa → giải phóng ô → mở đường cho arrow khác.
- Đã có tool generate level với validator dùng greedy simulation, constraint `min_width` / `max_width`.

### Arrow structure
- `points[]`: mảng tọa độ grid tạo thành path liên tục.
- `direction (Dx, Dy)`: hướng đầu mũi tên, xác định đường thoát.
- `head = points[0]`, `tail = points[-1]`.
- `BendCount`: số lần đổi hướng trong path.
- Arrow solvable khi: từ head theo direction, không gặp arrow nào khác cho đến khi ra khỏi board.

### Tap mechanic
- Player tap **1 arrow/lần**.
- Tap nhầm → animation penalty **0.3 seconds** cố định.
- Hint system: có nhưng **chưa cần mô phỏng**.

---

## 2. Mục tiêu tool

Mô phỏng hành vi chơi của player trên từng level để:
- **Dự đoán playtime** trước khi đưa lên production.
- **Đánh giá difficulty** dựa trên nhiều metrics.
- **Calibrate model** khi có playtime thực từ game server.

---

## 3. Viewport / Camera Model

Board có thể lớn hơn camera → player chỉ thấy 1 phần board tại mỗi thời điểm. Game có chức năng zoom.

### Giải pháp: Viewport Region

Chia board thành các viewport region dựa trên tỷ lệ `board_size / camera_size`, có overlap zone giữa các region.

```
Board 20×20, Camera 12×12:

┌────────────┬─────────┐
│ Region A   │ Region B│
│ (0,0)      │(10,0)   │
├────────────┼─────────┤
│ Region C   │ Region D│
│ (0,10)     │(10,10)  │
└────────────┴─────────┘

Overlap = 2 cells giữa các region liền kề
```

### Hành vi viewport

- Player bắt đầu ở region mặc định (configurable: top_left hoặc center).
- Scan arrow visible trong viewport hiện tại.
- Tìm được solvable → tap → scan lại viewport hiện tại.
- Không tìm được → pan sang region kế tiếp (tốn `pan_time`).
- Scan order giữa các region: top-down, left-right hoặc reverse.
- Sau xóa arrow, có xác suất quay lại region trước nếu nhớ có arrow gần solvable (`memory_probability`).
- Khi board ≤ camera: toàn bộ viewport logic bị bỏ qua.

### Camera parameters

| Tham số | Ý nghĩa | Đơn vị |
|---|---|---|
| `camera_width` | Chiều rộng camera tính theo cell | cells |
| `camera_height` | Chiều cao camera tính theo cell | cells |
| `viewport_overlap` | Số cell trùng giữa 2 region liền kề | cells |
| `pan_time` | Thời gian pan/scroll sang region kế tiếp | ms |
| `zoom_out_time` | Thời gian zoom out để nhìn tổng thể | ms |
| `zoom_out_probability` | Xác suất player zoom out thay vì pan tuần tự | 0.0–1.0 |
| `initial_position` | Vị trí viewport ban đầu | top_left / center |

---

## 4. Eye Model — Mô phỏng thị giác

### Đặc điểm target demographic (nữ 45–60 tuổi, US) — [Suy luận]

- **Peripheral vision thu hẹp**: vùng nhận diện hiệu quả nhỏ hơn viewport thực tế.
- **Fixation time dài hơn**: mỗi lần mắt dừng xử lý thông tin lâu hơn player trẻ.
- **Systematic scanning**: quét có hệ thống (trái-phải, trên-xuống), ít miss nhưng chậm hơn.
- **Color discrimination giảm nhẹ**: phân biệt arrow gần màu khó hơn.
- **Re-reading tendency**: kiểm tra lại arrow đã đánh giá, đặc biệt khi không tự tin.

### Effective Field of View

FOV nhỏ hơn camera viewport. Player quét FOV trong viewport rồi dịch FOV sang phần còn lại.

```
Viewport 12×16, effective FOV 8×10:

┌──────────────────┐
│  ┌──────────┐    │
│  │ FOV      │    │
│  │ (focus)  │    │
│  └──────────┘    │
│                  │
└──────────────────┘

Số lần dịch FOV = ceil(camera_w / fov_w) × ceil(camera_h / fov_h)
```

### Eye parameters

| Tham số | Ý nghĩa | Đơn vị |
|---|---|---|
| `effective_fov_width` | Vùng nhìn hiệu quả trong viewport | cells |
| `effective_fov_height` | Vùng nhìn hiệu quả chiều cao | cells |
| `fixation_time` | Thời gian mắt dừng tại 1 điểm | ms |
| `saccade_time` | Thời gian mắt di chuyển giữa 2 điểm fixation | ms |
| `recheck_probability` | Xác suất kiểm tra lại arrow đã đánh giá | 0.0–1.0 |
| `color_confusion_penalty` | Thời gian thêm khi 2 arrow gần nhau có màu tương tự | ms |

---

## 5. Arrow Evaluation Process

### Quy trình player đánh giá 1 arrow

```
1. Nhìn thấy arrow trong viewport
2. Tìm đầu mũi tên (head) → tốn thời gian tỷ lệ với arrow length
3. Xác định hướng (direction)
4. Trace đường thoát từ head theo direction:
   a. Đường thoát nằm trong viewport → đánh giá tại chỗ
   b. Đường thoát vượt viewport → pan theo direction để kiểm tra
   c. Gặp arrow khác chặn → kết luận "blocked"
   d. Đường trống đến rìa board → kết luận "solvable"
5. Quyết định tap hoặc bỏ qua
```

### Arrow evaluation parameters

| Tham số | Ý nghĩa | Đơn vị |
|---|---|---|
| `head_find_time_base` | Thời gian cơ bản tìm head | ms |
| `head_find_time_per_cell` | Thời gian thêm theo độ dài arrow | ms/cell |
| `trace_time_per_cell` | Thời gian mắt di chuyển theo đường thoát | ms/cell |
| `trace_pan_time` | Thời gian pan khi đường thoát vượt viewport | ms |
| `block_recognition_time` | Thời gian nhận ra đường thoát bị chặn | ms |
| `miss_probability` | Xác suất bỏ qua arrow solvable | 0.0–1.0 |

---

## 6. Scan Order

Chỉ dùng 2 variant, áp dụng **trong từng viewport region**:

- **`ltr_ttb`**: left-to-right, top-to-bottom (mặc định).
- **`rtl_btt`**: right-to-left, bottom-to-top.

Thứ tự scan dựa trên vị trí **head** của arrow trong viewport hiện tại.

---

## 7. Batch Tap Behavior

Khi tìm được arrow solvable trong viewport, player tiếp tục scan viewport hiện tại thay vì pan ngay:

```
while still_in_current_viewport:
    tap arrow solvable đã tìm được
    board state thay đổi → có thể mở thêm arrow solvable
    quick rescan viewport hiện tại (nhanh hơn full scan)
    tìm thêm solvable → tiếp tục tap
    không tìm thêm → pan sang region khác
```

### Batch tap parameters

| Tham số | Ý nghĩa | Đơn vị |
|---|---|---|
| `rescan_time_ratio` | Tỷ lệ thời gian rescan so với full scan (< 1.0) | ratio |
| `max_batch_before_pan` | Số arrow tối đa tap liên tiếp trước khi pan | count |

---

## 8. Recursive Unblock Behavior

Khi không tìm thấy arrow solvable:

```
frustration tăng
if frustration < threshold:
    chọn 1 arrow "gần solvable" (bị chặn bởi ít arrow nhất)
    trace ngược: tìm arrow đang chặn
    đánh giá arrow chặn có solvable không
    nếu có → tap arrow chặn → quay lại arrow ban đầu
    nếu không → đệ quy thêm 1 tầng (giới hạn max_recursion_depth)
else:
    pan random, scan lại từ đầu
```

### Recursive solve parameters

| Tham số | Ý nghĩa | Đơn vị |
|---|---|---|
| `recursive_solve_probability` | Xác suất player thử unblock thay vì pan random | 0.0–1.0 |
| `max_recursion_depth` | Số tầng đệ quy tối đa player chịu suy nghĩ | count |
| `recursion_think_time` | Thời gian suy nghĩ mỗi tầng đệ quy | ms |
| `frustration_buildup_rate` | Tốc độ tăng frustration mỗi lần scan thất bại | rate |
| `frustration_decay_after_solve` | Frustration giảm sau mỗi tap thành công | amount |

---

## 9. Core Player Parameters

| Tham số | Ý nghĩa | Đơn vị |
|---|---|---|
| `scan_time_per_arrow` | Thời gian quét qua 1 arrow | ms |
| `decision_time_base` | Thời gian suy nghĩ cơ bản trước khi tap | ms |
| `decision_time_per_bend` | Thời gian thêm cho mỗi bend | ms |
| `tap_time` | Thời gian thực hiện tap | ms |
| `mistake_rate` | Xác suất tap nhầm arrow không solvable | 0.0–1.0 |
| `mistake_penalty` | Thời gian mất khi tap nhầm (cố định 300ms) | ms |
| `fatigue_factor` | Hệ số tăng thời gian theo số step | multiplier |
| `board_scan_time` | Thời gian quét tổng thể board khi state thay đổi | ms |
| `hesitation_threshold` | Số arrow solvable ≤ ngưỡng → do dự lâu hơn | count |
| `scan_direction` | Hướng quét | ltr_ttb / rtl_btt |
| `memory_probability` | Xác suất nhớ vị trí arrow ở region đã scan | 0.0–1.0 |

---

## 10. Step Timeline Formula

```
step_time =
  // Phase 1: Tìm arrow (trong viewport + pan nếu cần)
  (num_regions_scanned × pan_time)
  + (num_fov_shifts × saccade_time)
  + (num_arrows_evaluated × (head_find_time_base + arrow_length × head_find_time_per_cell))
  + (trace_distance × trace_time_per_cell)
  + (trace_exceeded_viewport × trace_pan_time)

  // Phase 2: Đánh giá và quyết định
  + decision_time_base
  + (chosen_arrow.bend_count × decision_time_per_bend)

  // Phase 3: Tap
  + tap_time

  // Phase 4: Sai (nếu có)
  + (is_mistake × 300)

  // Phase 5: Fatigue
  × (fatigue_factor ^ step_index)
```

---

## 11. Player Types — 4 Archetype

### A. "The Methodical" — Cẩn thận, có hệ thống

Quét tuần tự, ít miss, chậm. Ít tap nhầm. Bế tắc → kiên nhẫn trace lại.

```
scan_time_per_arrow:     900
head_find_time_base:     500
decision_time_base:      1800
miss_probability:        0.05
mistake_rate:            0.04
recheck_probability:     0.25
recursive_solve_prob:    0.7
max_recursion_depth:     3
frustration_buildup:     0.02
rescan_time_ratio:       0.6
fatigue_factor:          1.015
zoom_out_probability:    0.05
memory_probability:      0.5
```

Ước tính tỷ lệ: [Suy đoán] 30–35% player base.

### B. "The Scanner" — Nhanh, trực giác

Quét nhanh, peripheral vision nhiều, miss nhiều hơn. Tap nhanh, sai nhiều hơn. Bế tắc → pan ngay.

```
scan_time_per_arrow:     450
head_find_time_base:     300
decision_time_base:      900
miss_probability:        0.20
mistake_rate:            0.14
recheck_probability:     0.08
recursive_solve_prob:    0.25
max_recursion_depth:     1
frustration_buildup:     0.06
rescan_time_ratio:       0.4
fatigue_factor:          1.025
zoom_out_probability:    0.25
memory_probability:      0.3
```

Ước tính tỷ lệ: [Suy đoán] 20–25%.

### C. "The Comfortable" — Thong thả, tận hưởng

Chơi không vội, hay zoom out ngắm tổng thể, thích batch tap. Fatigue thấp.

```
scan_time_per_arrow:     700
head_find_time_base:     450
decision_time_base:      1400
miss_probability:        0.12
mistake_rate:            0.08
recheck_probability:     0.15
recursive_solve_prob:    0.4
max_recursion_depth:     2
frustration_buildup:     0.01
rescan_time_ratio:       0.5
fatigue_factor:          1.005
zoom_out_probability:    0.35
memory_probability:      0.4
max_batch_before_pan:    5
```

Ước tính tỷ lệ: [Suy đoán] 30–35%.

### D. "The Struggler" — Mới chơi, chưa quen

Chậm, hay tap nhầm, không hiểu rõ mechanic. Frustration tăng nhanh.

```
scan_time_per_arrow:     1200
head_find_time_base:     700
decision_time_base:      2500
miss_probability:        0.25
mistake_rate:            0.22
recheck_probability:     0.30
recursive_solve_prob:    0.10
max_recursion_depth:     1
frustration_buildup:     0.08
rescan_time_ratio:       0.8
fatigue_factor:          1.035
zoom_out_probability:    0.05
memory_probability:      0.15
max_batch_before_pan:    2
```

Ước tính tỷ lệ: [Suy đoán] 10–15%.

---

## 12. Player Mix

Simulation chạy qua tất cả profile với weight:

```json
{
  "player_mix": {
    "methodical": 0.32,
    "scanner": 0.22,
    "comfortable": 0.33,
    "struggler": 0.13
  }
}
```

Output: weighted percentile cho mỗi level.

---

## 13. Difficulty Scoring

| Metric | Weight |
|---|---|
| `total_arrows` | 0.15 |
| `avg_bend_count` | 0.20 |
| `min_solvable_per_iteration` | 0.25 |
| `max_depth` (số iteration để clear) | 0.20 |
| `board_density` | 0.10 |
| `path_complexity` (trung bình độ dài arrow) | 0.10 |

---

## 14. Simulation Config

```json
{
  "simulation": {
    "runs_per_level": 100,
    "random_seed": 42,
    "output_percentiles": [25, 50, 75, 90]
  }
}
```

---

## 15. Data Collection — Playtest

Các field cần thu thập từ game:

| Field | Kiểu | Mục đích |
|---|---|---|
| `level_id` | string | Định danh level |
| `playtime` | int (ms) | Thời gian chơi thực tế |
| `tap_count` | int | Tổng số tap (đúng + sai) — so sánh với total_arrows |
| `mistake_count` | int | Số lần tap nhầm — calibrate `mistake_rate` |
| `level_completed` | bool | Player có clear được không |
| `arrow_solve_order` | array[int] | Thứ tự arrow_id player tap đúng — calibrate scan pattern |

`tap_count` và `mistake_count` có ROI cao nhất cho calibration: 2 int, chi phí implement thấp, giúp tách biệt `mistake_rate` khỏi các tham số thời gian → model converge tốt hơn.

---

## 16. Calibration Mode

- Input: playtime thực + tap_count + mistake_count từ game server.
- So sánh estimated vs actual.
- Tự động điều chỉnh player model parameters (least squares fit).
- Dùng `arrow_solve_order` để phân loại player thực vào 4 archetype bằng clustering.
- Calibrate từng profile riêng.
- Output: bộ tham số đã calibrate + error report.
