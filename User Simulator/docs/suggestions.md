# Simulator — Đề Xuất Thay Đổi

> **Tác giả**: Suggester
> **Ngày tạo**: 2026-03-21
> **Phiên bản phân tích**: Toàn bộ codebase (config.py, engine.py, user_model.py, game_adapter.py, cohort.py, ui.html, tools/server.py, tools/calibrate.py, tools/run.py, docs/discuss.md)
> **Mục đích tool**: Mô phỏng hành vi player trên Arrow Escape để dự đoán playtime, đánh giá difficulty, calibrate với data thực.
> **Vai trò Human**: Game Designer — cần tool chính xác để ra quyết định balance, không phải engineer nên code cần đơn giản, dễ bảo trì.

---

## MỨC ĐỘ ƯU TIÊN

- 🔴 **Critical** — Bug hoặc logic sai ảnh hưởng kết quả simulation
- 🟡 **Important** — Cải thiện đáng kể chất lượng/maintainability
- 🟢 **Nice-to-have** — Tối ưu, UX, mở rộng

---

## 🔴 S-01: engine.py chứa dead code — PlayerSimulator cũ sẽ crash nếu gọi

**Vấn đề**: `engine.py` chứa class `PlayerSimulator` và hàm `run_simulation_batch` là phiên bản CŨ, trước khi refactor sang kiến trúc 3 lớp (user_model + game_adapter). Code này:

- Tham chiếu `sim_config.camera` → thuộc tính không tồn tại (thực tế là `sim_config.viewport`)
- Tham chiếu `sim_config.arrow_eval` → không tồn tại (các tham số nằm trực tiếp trên `SimulationConfig`)
- `run_simulation_batch()` gọi `sim_config.runs_per_level` → field không có trong `SimulationConfig`
- → **Crash ngay nếu ai gọi đến** (import vẫn thành công, chỉ crash ở runtime)

**Đề xuất**: Xóa `PlayerSimulator`, `run_simulation_batch`, `compute_percentiles` khỏi `engine.py`. Chỉ giữ lại: data models (Arrow, Board, StepEvent, SimulationResult, LevelMetrics), level loader, BoardState, viewport functions, `compute_level_metrics`. Nếu muốn giữ backward compat, đánh dấu `@deprecated` và raise `NotImplementedError`.

**Tác động**: Giảm confusion cho AI và Human khi đọc code. Hiện tại có 2 cách simulate (engine.py cũ vs game_adapter.py mới), dễ dùng nhầm.

---

## 🔴 S-02: Scissors booster chọn SAI mục tiêu

**Vấn đề**: `game_adapter.py` dòng 130–139, `apply_scissors()` chọn arrow có `count_blockers(a)` CAO NHẤT. Nhưng `count_blockers(a)` đếm số arrow CHẶN arrow `a` — tức arrow `a` bị blocked nhiều nhất.

Logic đúng cho player dùng Scissors: chọn arrow đang CHẶN nhiều arrow khác nhất (blocker lớn nhất), không phải arrow bị block nhiều nhất.

```python
# Hiện tại (SAI): chọn arrow bị block nhiều nhất
for a in self.board_state.remaining.values():
    score = self.board_state.count_blockers(a)  # đếm ai chặn a
    if score > best_score: ...

# Cần (ĐÚNG): chọn arrow đang chặn nhiều arrow khác nhất
for candidate in self.board_state.remaining.values():
    blocking_count = 0
    for other in self.board_state.remaining.values():
        if other.arrow_id == candidate.arrow_id:
            continue
        blocker = self.board_state.find_blocker(other)
        if blocker and blocker.arrow_id == candidate.arrow_id:
            blocking_count += 1
    if blocking_count > best_score: ...
```

**Tác động**: Ảnh hưởng trực tiếp đến hiệu quả booster Scissors trong simulation → sai lệch playtime khi player dùng scissors.

---

## 🔴 S-03: Cohort CSV metric "During Level %" tính sai

**Vấn đề**: `cohort.py` dòng 127:
```python
during_pct = complete_pct - start_pct
```
`complete_pct` luôn ≤ `start_pct` (không thể có nhiều người complete hơn người start) → **during_pct luôn ≤ 0**. Metric này không có ý nghĩa.

Trong feed data, "During Level %" thường biểu thị tỷ lệ churn/mất mát TRONG level. Nên tính:
```python
during_pct = (agg.started - agg.completed) / agg.started  # % player bỏ cuộc trong level
```
hoặc nếu muốn giữ dạng %cohort:
```python
during_pct = agg.churned_during / cohort_size
```

**Tác động**: Report CSV sai → Human so sánh nhầm với feed data.

---

## 🔴 S-04: BoosterInventory default không khớp BoosterConfig

**Vấn đề**: `game_adapter.py` dòng 41–44:
```python
class BoosterInventory:
    hints_remaining: int = 3       # default 3
    scissors_remaining: int = 2    # default 2
    wands_remaining: int = 1       # default 1
```
Trong khi `BoosterConfig` default:
```python
hint_per_attempt: int = 5
scissors_per_attempt: int = 5
wand_per_attempt: int = 5
```

`reset()` được gọi trong `ArrowEscapeAdapter.reset()` và overwrite default bằng config → **không gây bug trực tiếp**. Nhưng nếu ai dùng `BoosterInventory` mà quên gọi `reset()`, sẽ có số inventory sai.

**Đề xuất**: Đồng bộ default, hoặc bỏ default trên `BoosterInventory` (force gọi `reset()`).

---

## 🟡 S-05: File .py root trùng lặp với src/ — confusing imports

**Vấn đề**: Thư mục root có `config.py`, `engine.py`, `user_model.py`, `game_adapter.py`, `cohort.py` — giống hệt các file trong `src/`. Tools (`server.py`, `calibrate.py`, `run.py`) đều import từ `src/` qua `sys.path.insert`. File root không được dùng.

**Đề xuất**: Xóa các file .py ở root. Chỉ giữ `src/` làm source of truth. Nếu cần chạy từ root, dùng `__init__.py` hoặc setup proper package.

**Tác động**: Human hoặc AI sửa file root → thay đổi không có hiệu lực → debug khó. Đã từng có risk này khi diff cho thấy 2 bản giống nhau nhưng có thể diverge bất cứ lúc nào.

---

## 🟡 S-06: calibrate.py và server.py duplicate logic simulate

**Vấn đề**:
- `server.py::simulate_level()` (dòng 128–167)
- `calibrate.py::simulate_single_level()` (dòng 54–90)

Gần như giống nhau, chỉ khác cách truyền profiles/mix. Vi phạm DRY → fix bug ở 1 nơi, quên nơi kia.

**Đề xuất**: Extract shared function vào `src/`, cả `server.py` và `calibrate.py` cùng import. Có thể đặt trong file mới `src/runner.py` hoặc mở rộng `cohort.py`.

---

## 🟡 S-07: Tham số config không được sử dụng

**Vấn đề**: Các tham số được define nhưng KHÔNG dùng ở bất kỳ đâu trong simulation:

| Tham số | File | Lý do |
|---------|------|-------|
| `color_confusion_penalty` | EyeConfig | Không có logic phân biệt màu arrow trong simulation |
| `hesitation_threshold` | PlayerProfile | Không có code nào check số solvable vs threshold |
| `ComboConfig` (toàn bộ) | config.py | `enabled=False`, không có code xử lý combo |

**Đề xuất**:
- `color_confusion_penalty`: Implement hoặc xóa. Nếu implement: thêm extra scan time khi 2 arrow cùng region có visual similarity.
- `hesitation_threshold`: Implement logic: khi `len(solvable_here) <= threshold`, nhân decision_time với hệ số (vd: 1.3). Hoặc xóa.
- `ComboConfig`: Giữ nếu có kế hoạch dùng cho game khác. Thêm comment rõ "placeholder for future games".

---

## 🟡 S-08: Performance — _rebuild_occupied() gọi O(N) mỗi lần xóa arrow

**Vấn đề**: `BoardState.remove_arrow()` gọi `_rebuild_occupied()` rebuild toàn bộ occupied set từ scratch. Với board 50 arrow, mỗi lần xóa đều iterate lại tất cả remaining arrows.

**Đề xuất**: Thay bằng incremental update:
```python
def remove_arrow(self, arrow_id: int):
    if arrow_id in self.remaining:
        arrow = self.remaining.pop(arrow_id)
        # Chỉ xóa cells của arrow này, nhưng giữ cells shared với arrow khác
        for cell in arrow.cells:
            still_occupied = any(
                cell in a.cells for a in self.remaining.values()
            )
            if not still_occupied:
                self.occupied.discard(cell)
```

**Tác động**: Cải thiện speed cho board lớn (50+ arrows). Với cohort 5000 × 100 levels, tiết kiệm đáng kể.

---

## 🟡 S-09: Auto-calibration chưa implement (discuss.md Section 16)

**Vấn đề**: `discuss.md` mô tả:
- Auto-adjust parameters bằng least squares fit
- Clustering player thực vào 4 archetype
- Calibrate từng profile riêng

Hiện tại `calibrate.py` chỉ SO SÁNH và in ra gợi ý text. Không tự động điều chỉnh.

**Đề xuất**: Implement calibration loop cơ bản:
1. Chạy sim với params hiện tại
2. Tính error vector (sim - feed) cho mỗi metric
3. Điều chỉnh params theo hướng giảm error (gradient-free optimizer như scipy.optimize.minimize hoặc đơn giản hơn: binary search trên timing multiplier)
4. Lặp cho đến convergence

Bắt đầu đơn giản: chỉ tự động điều chỉnh `timing_multiplier` (nhân tất cả timing params). Sau đó mở rộng.

---

## 🟢 S-10: UI — Profile Editor chỉ expose 8/20+ tham số

**Vấn đề**: UI cho phép chỉnh 8 tham số (scan, decision, tap, miss, mistake, fatigue, frustration, booster), nhưng mỗi profile có 20+ tham số ảnh hưởng simulation (recursive_solve_probability, max_recursion_depth, memory_probability, zoom behavior...).

**Đề xuất**: Thêm "Advanced" toggle trong Profile Editor. Nhóm tham số theo category:
- Basic (hiện tại): timing, errors, behavior
- Advanced: zoom, recursion, memory, skill progression, scan behavior

---

## 🟢 S-11: UI — Không hỗ trợ so sánh nhiều run

**Vấn đề**: Mỗi lần chạy sim mới, kết quả cũ bị overwrite. Human thường cần so sánh: "tôi thay đổi param X, kết quả thay đổi thế nào?"

**Đề xuất**: Thêm "snapshot" feature:
- Button "Save Run" lưu kết quả + config vào array
- Tab "Compare" hiển thị overlay chart giữa 2+ runs
- Mỗi run có label do Human đặt (vd: "baseline", "faster scanner", "more boosters")

---

## 🟢 S-12: Thiếu validation cho cohort mode vs per-level mode

**Vấn đề**: UI có dropdown Mode (Per-Level / Cohort), nhưng server.py chỉ implement per-level logic. `mode` field gửi lên server nhưng không được xử lý — luôn chạy per-level.

Cohort mode (có churn, engagement, skill progression) chỉ available qua `tools/run.py` CLI.

**Đề xuất**: Kết nối cohort mode vào server API. Khi `mode=cohort`:
- Sử dụng `CohortSimulator` thay vì loop `simulate_level`
- Trả về thêm metrics: retention funnel, churn rate per level, engagement curve
- UI hiển thị thêm chart: Retention funnel, Cumulative playtime

---

## 🟢 S-13: churn_rate trong engagement CSV khác ý nghĩa thực

**Vấn đề**: `cohort.py` dòng 129:
```python
churn_rate = 1.0 - win_rate
```
Đây là "tỷ lệ không win" = fail rate, KHÔNG phải churn rate. Churn là player bỏ game hoàn toàn. Player fail level nhưng retry không phải churn.

**Đề xuất**: Phân biệt rõ:
- `fail_rate` = 1 - (total_wins / total_matches) ← đã có đúng
- `churn_during_rate` = churned_during / started
- `churn_between_rate` = churned_between / completed

---

## 🟢 S-14: Không có unit test

**Vấn đề**: Không có file test nào. Với hệ thống phức tạp nhiều tham số, regression rất dễ xảy ra khi calibrate hoặc refactor.

**Đề xuất**: Tạo `tests/` folder với:
- `test_board_state.py`: test is_solvable, remove_arrow, get_solvable trên board nhỏ (3-5 arrows)
- `test_user_model.py`: test engagement curve, churn probability, skill progression
- `test_game_adapter.py`: test simulate_attempt trên 1 level cố định → kết quả deterministic với seed
- `test_booster.py`: test logic chọn và apply booster

---

## 🔴 S-15: `churned_during` đánh đồng "fail hết attempts" với "bỏ cuộc" — và thiếu cơ chế mô phỏng "muốn bỏ game trong khi chơi"

> **Tác giả**: Suggester | **Ngày**: 2026-03-22 (cập nhật 2026-03-22)

### 15A — Metric sai: `churned_during = not won`

**Vấn đề**: `cohort.py` dòng 240 — bất kỳ player nào KHÔNG win đều bị đánh dấu `churned_during=True`. Nhưng theo feed data, "During Level %" là tỷ lệ user **muốn bỏ game** trong quá trình chơi — tức là họ CHỦ ĐỘNG dừng, không phải bị fail hết attempts.

Hai nhóm hiện bị đánh đồng:
- **Churn thật**: `should_give_up()` trả về True → player CỦ ĐỘNG không chơi tiếp
- **Exhausted**: dùng hết 5/5 attempts, fail, nhưng **vẫn chơi tiếp từ level select** (không phải churn)

**Fix**: Chỉ đánh dấu `churned_during=True` khi `should_give_up()` trả về True:
```python
gave_up = False
for att in range(acfg.max_attempts):
    result = adapter.simulate_attempt(att)
    if result.won: break
    if user.should_give_up(att + 1):
        gave_up = True
        break
return LevelResult(..., churned_during=gave_up)
```

### 15B — Thiếu cơ chế: player muốn bỏ trong khi đang chơi, không phải sau khi fail

**Vấn đề sâu hơn**: `should_give_up()` chỉ được gọi GIỮA hai attempts (sau khi fail xong). Nhưng trong thực tế, player có thể muốn dừng TRONG KHI đang chơi attempt — ví dụ khi frustration tăng cao nhưng chưa đạt `frustration_cap` (1.0).

Hiện tại, con đường duy nhất để abandon một attempt là:
1. `frustration >= 1.0` → fail với reason "frustration"
2. `total_time >= 900,000ms` → fail với reason "timeout"

Không có cơ chế player thấy khó, mệt mỏi, rồi tự tắt app mà không cần "fail hẳn".

**Đề xuất — 2 hướng**:

**Hướng 1 (đơn giản)**: Sau khi attempt fail với reason `"frustration"`, tăng xác suất give_up đáng kể:
```python
# Trong should_give_up(), thêm fail_reason param
def should_give_up(self, failed_attempts: int, fail_reason: Optional[str] = None) -> bool:
    prob = acfg.give_up_base_prob + (failed_attempts - 1) * acfg.give_up_increment
    if fail_reason == "frustration":
        prob *= acfg.frustration_quit_multiplier  # mới, vd: 3.0
    return self.rng.random() < min(0.95, prob)
```
Thêm `frustration_quit_multiplier: float = 3.0` vào `AttemptConfig`.

**Hướng 2 (chính xác hơn)**: Thêm in-attempt quit check định kỳ. Ví dụ: mỗi 30 giây game-time, check xác suất abandon dựa trên frustration hiện tại:
```python
# Trong simulate_attempt(), khi frustration > ngưỡng nhất định (vd: 0.6)
if self.user.frustration > 0.6:
    abandon_prob = (self.user.frustration - 0.6) / 0.4 * 0.05  # tối đa 5% mỗi lần check
    if self.rng.random() < abandon_prob:
        return AttemptResult(won=False, fail_reason="abandoned", ...)
```
Sau đó `should_give_up()` với reason "abandoned" có xác suất gần 1.0.

**Recommendation**: Hướng 1 đủ cho giai đoạn hiện tại — ít thay đổi, dễ calibrate. Hướng 2 sau khi có test để verify behavior.

**Tác động**: Ảnh hưởng trực tiếp `churn_during_rate` trong engagement CSV → Human dùng metric này để evaluate level nào gây mất player.

---

## ~~🔴 S-16: Level load overhead tính cho MỌI attempt — nên chỉ tính lần đầu~~ ✖ WITHDRAWN

> **Tác giả**: Suggester | **Ngày**: 2026-03-22 | **Withdrawn**: 2026-03-22

**Lý do rút**: Trong game thật, mỗi lần retry cũng chạy lại animation load đầy đủ → `level_load_time_ms` áp dụng cho mọi attempt là ĐÚNG. Không cần thay đổi.

---

## 🔴 S-17: `timing_multiplier` không ảnh hưởng internal decisions — chỉ scale output

> **Tác giả**: Suggester | **Ngày**: 2026-03-22

**Vấn đề**: `runner.py` dòng 58:
```python
all_times_ms.append(total_time * sim_config.timing_multiplier)
```
`timing_multiplier` nhân VÀO KẾT QUẢ SAU KHI simulation chạy xong. Nghĩa là:

- Internal decisions (`should_fail_attempt` check `total_time >= max_attempt_time_ms`) **KHÔNG bị ảnh hưởng**
- Frustration buildup, fatigue curve **KHÔNG thay đổi**
- Player behavior giữ nguyên, chỉ output time bị scale

→ Nếu sim chạy nhanh hơn thực tế (multiplier > 1), player behavior vẫn như "thời gian nhanh" (ít fatigue, ít frustration timeout) nhưng output lại nói "thời gian lâu". **Inconsistency giữa behavior và reported time.**

**Đề xuất**: Có 2 hướng:
1. **Giữ hiện tại** nhưng document rõ: multiplier chỉ scale output, không ảnh hưởng dynamics. OK cho rough calibration.
2. **Apply multiplier vào timing params trước khi simulate**: nhân tất cả timing fields (scan_time, decision_time, tap_time, head_find_time...) bằng multiplier. Behavior và output sẽ consistent. Phức tạp hơn nhưng chính xác hơn.

**Recommendation**: Hướng 1 OK cho giai đoạn hiện tại. Ghi chú rõ trong code + doc.

---

## 🟡 S-18: engine.py còn dead code — viewport functions và ViewportRegion trùng lặp

> **Tác giả**: Suggester | **Ngày**: 2026-03-22 (xác minh kỹ 2026-03-22)

**Xác minh**: Simulator CÓ mô phỏng zoom in/out và di chuyển viewport. Toàn bộ logic này sống ở `user_model.py` + `game_adapter.py`:

- `user_model.py` có `ViewportModel` (dòng 118–190): quản lý `zoom_in_regions`, `zoom_out_regions`, `switch_zoom()`, `current_region()`, zoom multipliers
- `user_model.py` có `compute_regions()` (dòng 85–115): tính regions cho cả hai zoom level
- `game_adapter.py` import `ViewportModel, ViewportRegion` từ `user_model` (dòng 34)
- `game_adapter.py` dùng `ViewportModel` để simulate toàn bộ hành vi zoom, pan, scan từng region
- `game_adapter.py` có `_arrows_in_region()` và `_sort_arrows()` riêng

**Vậy code trong `engine.py` là 100% dead — không ai import:**

| Code trong engine.py | Dòng | Thực tế dùng ở đâu |
|----------------------|------|--------------------|
| `ViewportRegion` class | 55–62 | Trùng với `user_model.py` dòng 74–82. Không ai import từ engine.py |
| `compute_zoom_in_regions()` | 250–284 | Không ai import. user_model.py có `compute_regions()` riêng |
| `compute_zoom_out_regions()` | 287–321 | Không ai import |
| `arrows_in_region()` | 324–332 | Không ai import. game_adapter có `_arrows_in_region()` |
| `sort_arrows_by_scan()` | 335–340 | Không ai import. game_adapter có `_sort_arrows()` |
| `CameraConfig` alias | dòng 14 | `ViewportConfig as CameraConfig` — không dùng ở bất kỳ đâu trong file |

**Đề xuất**: Xóa tất cả code trên. `engine.py` chỉ nên giữ: data models (Arrow, Board, BoardState, LevelMetrics, StepEvent, SimulationResult), `load_level`, `compute_level_metrics`.

> **Lưu ý**: StepEvent và SimulationResult cũng đang là dead code (xem S-22). Sau khi S-22 done, `engine.py` sẽ gọn hơn nhiều.

**Tác động**: Giảm ~100 dòng dead code. Nguy cơ hiện tại: AI đọc engine.py thấy "có hàm viewport" rồi import nhầm → sim chạy sai silently.

---

## 🟡 S-19: `apply_scissors()` fix đúng logic nhưng O(N³) — cần tối ưu

> **Tác giả**: Suggester | **Ngày**: 2026-03-22

**Vấn đề**: S-02 fix sửa đúng semantics, nhưng implementation hiện tại:
```python
for candidate in remaining:           # O(N)
    for other in remaining:           # O(N)
        blocker = find_blocker(other) # O(board_width) tracing
```
= **O(N² × W)** cho mỗi lần dùng Scissors. Với board 50 arrows, mỗi Scissors call = ~50 × 50 × 30 = 75,000 operations.

**Đề xuất**: Precompute `blocking_map` một lần rồi lookup:
```python
# Build reverse index: arrow_id → set of arrows it blocks
blocking_map = {}
for other in self.board_state.remaining.values():
    blocker = self.board_state.find_blocker(other)
    if blocker:
        blocking_map.setdefault(blocker.arrow_id, set()).add(other.arrow_id)

# Chọn candidate có len(blocking_map[id]) lớn nhất
best = max(remaining, key=lambda a: len(blocking_map.get(a.arrow_id, set())))
```
Giảm từ O(N² × W) xuống O(N × W) — cùng logic, nhanh hơn N lần.

---

## 🟡 S-20: S-08 incremental occupied update — thực tế không nhanh hơn rebuild

> **Tác giả**: Suggester | **Ngày**: 2026-03-22

**Vấn đề**: `engine.py` dòng 214–219 (fix S-08):
```python
for cell in arrow.cells:          # O(K) cells per arrow
    still_occupied = any(
        cell in a.cells           # O(1) set lookup
        for a in self.remaining.values()  # O(N) remaining arrows
    )
```
= **O(K × N)** cho mỗi `remove_arrow()`.

So sánh với full rebuild (cũ): iterate N arrows × K_avg cells = **O(N × K_avg)**.

Hai cách có cùng complexity. Incremental chỉ thắng khi arrow bị xóa có ÍT cells. Với arrow dài (10+ cells), incremental có thể CHẬM hơn vì mỗi cell phải iterate all remaining.

**Đề xuất tốt hơn**: Dùng **reverse index** `cell → count`:
```python
# Trong __init__:
self.cell_count = {}  # (x,y) → int (bao nhiêu arrow dùng cell này)
for a in board.arrows:
    for cell in a.cells:
        self.cell_count[cell] = self.cell_count.get(cell, 0) + 1

# Trong remove_arrow:
for cell in arrow.cells:
    self.cell_count[cell] -= 1
    if self.cell_count[cell] == 0:
        self.occupied.discard(cell)
        del self.cell_count[cell]
```
= **O(K) per removal** — không phụ thuộc N. Thật sự incremental.

---

## 🟡 S-21: Booster activation time không nhân fatigue — inconsistent

> **Tác giả**: Suggester | **Ngày**: 2026-03-22

**Vấn đề**: `game_adapter.py` dòng 397–417, khi dùng booster:
```python
self.user.total_time += self.cfg.booster.hint_activation_ms    # raw, không fatigue
self.user.total_time += self.cfg.booster.scissors_activation_ms
self.user.total_time += self.cfg.booster.wand_activation_ms
```
Mọi thao tác khác trong sim đều nhân `self.user.fatigue()`: scan, eval, tap, pan, zoom. Riêng booster activation không nhân → inconsistent.

Booster activation bao gồm "thinking + UI interaction" — cũng bị fatigue ảnh hưởng.

**Đề xuất**: Nhân fatigue:
```python
self.user.total_time += self.cfg.booster.hint_activation_ms * self.user.fatigue()
```

**Tác động**: Nhỏ (booster ít dùng), nhưng cải thiện consistency cho calibration.

---

## 🟡 S-22: `StepEvent` và `SimulationResult` trong engine.py không còn ai dùng

> **Tác giả**: Suggester | **Ngày**: 2026-03-22

**Vấn đề**: Sau khi xóa `PlayerSimulator` (S-01), hai dataclass này chỉ được DEFINE nhưng không ai import hoặc instantiate:

- `StepEvent` — output của PlayerSimulator cũ
- `SimulationResult` — output của `run_simulation_batch` cũ

Kiến trúc mới dùng `AttemptResult` (user_model.py) và `LevelResult` (user_model.py).

**Đề xuất**: Xóa cả hai. Giảm thêm dead code trong engine.py.

---

# UI POLISH — ĐỀ XUẤT TOÀN DIỆN

> **Tác giả**: Suggester | **Ngày**: 2026-03-22
>
> **Bối cảnh**: Backend đã ổn định (S-01→S-22 xong). Giờ là lúc UI phải phục vụ đúng workflow của Game Designer: **chạy sim → so sánh feed → phát hiện vấn đề → điều chỉnh → re-run**. Mỗi đề xuất UI kèm backend API cần thiết.

---

## PHÂN TÍCH UI HIỆN TẠI

### Có gì:
- Left panel 340px: Version selector, Sim settings, Player mix sliders, Profile editor (8 params), Booster config, Level overhead, Run button
- Right panel: Status bar, 4 summary cards (Levels, Avg Time Ratio, Win Rate Diff, Attempt Diff), 3 tabs (Chart / Table / Config JSON)
- Charts: Avg Time bar (sim vs feed + range slider), Time Ratio bar (color-coded), Win Rate line
- API: `GET /api/datasets`, `POST /api/simulate`

### Thiếu gì (theo workflow Game Designer):

| Workflow step | Hiện tại | Thiếu |
|---------------|----------|-------|
| "Level nào có vấn đề?" | Bảng + chart — phải tự đọc từng dòng | Không sort/filter được. Không highlight outlier tự động |
| "Profile nào gây mismatch?" | Không có | Per-profile breakdown hoàn toàn thiếu |
| "Thay param X thì sao?" | Chạy lại, kết quả cũ mất | Không so sánh 2 runs. Không biết thay đổi gì |
| "Level 15 cụ thể bị gì?" | Chỉ thấy avg time + WR | Không có detail: attempt distribution, fail reasons, booster usage |
| "Cohort churn ở đâu?" | Mode dropdown có nhưng không hoạt động | Không có retention funnel, churn chart |
| "Export cho team review" | Copy JSON config — không export results | Không xuất CSV/Excel từ UI |
| "Nhanh calibrate thử" | CLI only (calibrate.py --auto) | Không có auto-calibrate button |

---

## UI-01: Level Drill-Down — Click level để xem chi tiết

> 🔴 **Critical cho workflow** | **Effort**: Trung bình

### UI:
- Table row clickable → mở panel/modal **Level Detail**
- Nội dung:
  - **Board info**: size, arrows, difficulty score, min_solvable_per_iteration, max_depth
  - **Per-profile breakdown**: bảng 4 dòng (Methodical/Scanner/Comfortable/Struggler) × cột (avg_time, win_rate, avg_attempts, fail_rate)
  - **Attempt distribution**: histogram (1 att, 2 att, 3 att...) — sim vs feed nếu có
  - **Fail reasons pie**: % frustration / % timeout / % exhausted
  - **Booster usage**: avg hint/scissors/wand used per player

### Backend:
```
POST /api/simulate-detail
Body: { level_id, version, cohort, seed, profiles, mix, booster, overhead }
Response: {
  board: { width, height, arrows, difficulty, min_solvable, max_depth },
  per_profile: {
    methodical: { avg_time, win_rate, avg_attempts, fail_rate, n_players },
    scanner: {...}, comfortable: {...}, struggler: {...}
  },
  attempt_distribution: { "1": 340, "2": 98, "3": 42, "4": 15, "5": 5 },
  fail_reasons: { frustration: 38, timeout: 12, exhausted: 10 },
  booster_usage: { hints_avg: 1.2, scissors_avg: 0.4, wand_avg: 0.1 }
}
```
**Thay đổi backend**: `runner.py::simulate_level()` cần trả thêm per-profile stats + attempt detail. Tách logic chung ra thành `simulate_level_detailed()`.

---

## UI-02: Run Comparison — So sánh 2+ lần chạy

> 🔴 **Critical cho workflow** | **Effort**: Trung bình

### UI:
- Button **"Save Run"** sau mỗi simulation → lưu `{ label, config, results, timestamp }` vào `localStorage` / JS array
- **Saved Runs** panel dưới summary: danh sách runs với label editable + delete button
- Tab **"Compare"** mới (cạnh Chart/Table/Config):
  - Dropdown chọn 2 runs
  - Overlay chart: 2 đường sim trên cùng chart, feed data làm baseline
  - Diff table: mỗi dòng = 1 level, cột = Run A time / Run B time / delta / Run A WR / Run B WR / delta
  - Summary diff: "Run B trung bình nhanh hơn 12% so với Run A"

### Backend:
Không cần API mới — comparison xử lý hoàn toàn client-side. Kết quả đã lưu trong JS memory.

---

## UI-03: Outlier Highlighting + Sort/Filter

> 🟡 **Important** | **Effort**: Thấp

### UI:
- Table header clickable → sort bất kỳ cột nào (ascending/descending)
- Filter row phía trên table:
  - **Ratio filter**: dropdown "All / Off-track (>1.3x or <0.7x) / Way off (>2x or <0.5x)"
  - **Level range**: quick filter text input "15-25"
- Auto-highlight hàng: nền đỏ nhạt cho ratio >2x hoặc <0.5x, vàng nhạt cho >1.3x hoặc <0.7x
- Summary card **"Outliers"**: số level off-track, clickable → filter table

### Backend: Không cần — client-side JS.

---

## UI-04: Cohort Mode Integration

> 🟡 **Important** | **Effort**: Cao (= S-12 mở rộng)

### UI:
Khi chọn Mode = "Cohort":
- **Retention Funnel chart**: bar chart giảm dần — mỗi bar = % cohort còn lại ở level N
- **Churn Breakdown chart**: stacked bar — mỗi level có 3 phần: during_churn + between_churn + active
- **Playtime Curve**: cumulative avg time — dùng để estimate "total session length trung bình"
- **Engagement Heatmap**: level × perceived_difficulty → color = engagement score
- Summary cards thay đổi: thêm "Retention L10", "Avg Quit Level", "Median Session Time"

### Backend:
```
POST /api/simulate-cohort
Body: { version, cohort, seed, profiles, mix, booster, overhead, levelFrom, levelTo }
Response: {
  levels: [...],  // giống per-level nhưng thêm retention metrics
  funnel: [
    { level: 1, started: 4936, completed: 4820, churned_during: 40, churned_between: 76 },
    { level: 2, started: 4744, ... },
    ...
  ],
  summary: {
    retention_l10: 0.82,
    avg_quit_level: 28.5,
    median_session_minutes: 45.2
  }
}
```
**Thay đổi backend**: Kết nối `CohortSimulator` vào `server.py`. Cần endpoint mới hoặc branch logic trong `/api/simulate` dựa trên `mode`.

---

## UI-05: Advanced Profile Editor

> 🟡 **Important** | **Effort**: Trung bình (= S-10 chi tiết hóa)

### UI:
- Giữ 8 basic params như hiện tại
- Thêm toggle **"Show Advanced"** → mở section ẩn với các param nhóm:

**Zoom & Viewport:**
| Param | Field ID | Default range |
|-------|----------|---------------|
| Initial zoom | `p_initial_zoom` | "in" / "out" |
| Preferred zoom | `p_preferred_zoom` | "in" / "out" / "adaptive" |
| Zoom-in-to-tap prob | `p_zoom_in_tap` | 0–1 |
| Zoom-out survey prob | `p_zoom_out_survey` | 0–1 |
| Viewport cleared zoom-out prob | `p_viewport_cleared` | 0–1 |

**Cognition:**
| Param | Field ID | Default range |
|-------|----------|---------------|
| Recursive solve prob | `p_recursive_solve` | 0–1 |
| Max recursion depth | `p_max_recursion` | 0–5 |
| Memory probability | `p_memory` | 0–1 |
| Recheck probability | `p_recheck` | 0–1 |

**Effort & Quit:**
| Param | Field ID | Default range |
|-------|----------|---------------|
| Board scan time | `p_board_scan` | ms |
| Max batch before pan | `p_max_batch` | 1–10 |
| Frustration decay after solve | `p_frust_decay` | 0–0.1 |

### Backend:
`server.py::handle_simulate()` cần map thêm advanced params từ request body vào `PlayerProfile` fields. Hiện tại chỉ map 8 fields (dòng 157–164).

---

## UI-06: Auto-Calibrate từ UI

> 🟡 **Important** | **Effort**: Trung bình

### UI:
- Button **"Auto-Calibrate"** cạnh "Run Simulation"
- Click → chạy binary search trên `timing_multiplier` (logic từ calibrate.py)
- Progress bar: "Iteration 3/10 — ratio 1.08x — adjusting..."
- Kết quả: hiển thị `timing_multiplier` tìm được + auto-fill vào config
- Optional: checkbox "Also calibrate win_rate" → adjust `frustration_buildup_rate`

### Backend:
```
POST /api/auto-calibrate
Body: { version, cohort, seed, profiles, mix, target_metrics: ["avg_time", "win_rate"], max_iters: 10 }
Response: {
  timing_multiplier: 0.87,
  iterations: 5,
  final_ratio: 1.02,
  adjustments: { timing_multiplier: "1.0 → 0.87" }
}
```
**Thay đổi backend**: Extract auto-calibration loop từ `calibrate.py` vào `src/runner.py` hoặc `src/calibrator.py`, expose qua server.

---

## UI-07: Export Results

> 🟢 **Nice-to-have** | **Effort**: Thấp

### UI:
- Button **"Export CSV"** ở góc phải tab Table
- Button **"Export All Charts"** → download PNG/SVG của tất cả charts (Plotly built-in)
- Auto-save đã có (server ghi CSV vào `report/`), nhưng UI nên show link download trực tiếp

### Backend:
- Server đã auto-save CSV. Thêm endpoint:
```
GET /api/report/{version}/{filename}
```
- UI tạo download link sau mỗi run: `<a href="/api/report/v1.8.0/Sim_Level_playtime.csv">Download Playtime CSV</a>`

---

## UI-08: Real-time Progress Streaming

> 🟢 **Nice-to-have** | **Effort**: Trung bình

### UI:
- Thay status bar "check terminal" bằng progress bar thực
- Hiển thị: `Level 15/30 — L142 — 12.3s elapsed — ETA 8s`
- Mini-chart cập nhật live: mỗi level xong → thêm 1 bar vào chart

### Backend:
2 phương án:

**A. Server-Sent Events (SSE)** — đơn giản hơn:
```
POST /api/simulate → trả về stream
data: {"type":"progress", "level":15, "total":30, "level_id":142, "elapsed":12.3}
data: {"type":"result", "level":142, "sim_avg":0.45, "feed_avg":0.52}
...
data: {"type":"done", "summary":{...}}
```

**B. Polling** — dễ implement hơn:
```
POST /api/simulate → trả về job_id ngay
GET /api/simulate-status/{job_id} → { progress: 15, total: 30, partial_results: [...] }
```

**Recommendation**: SSE (phương án A) — `http.server` hỗ trợ sẵn, client dùng `EventSource`.

---

## UI-09: Config Presets — Save/Load cấu hình

> 🟢 **Nice-to-have** | **Effort**: Thấp

### UI:
- Dropdown **"Presets"** bên cạnh "Run Simulation"
- Options: "Default", "Fast Scanner Heavy", "Struggler Focus", "Custom 1", "Custom 2"
- Buttons: "Save as Preset" (nhập tên) / "Load Preset"
- Presets lưu toàn bộ config (profiles + mix + booster + overhead + level range)

### Backend: Không cần — lưu client-side trong JS. Hoặc nếu muốn persist:
```
GET  /api/presets → [{ name, config }]
POST /api/presets → save preset
```
File-based storage: `data/presets/*.json`

---

## UI-10: Difficulty Score Visualization

> 🟢 **Nice-to-have** | **Effort**: Thấp

### UI:
- Chart mới trong tab Chart: **"Difficulty Curve"**
- X = level, Y = difficulty_score (từ `compute_level_metrics`)
- Overlay: sim_avg_time trend line — để thấy correlation difficulty ↔ playtime
- Color-code points: xanh = ratio OK, đỏ = sim deviates from feed
- Tooltip: board size, arrow count, min_solvable, max_depth

### Backend:
`/api/simulate` response đã có `difficulty` field per level. Chỉ cần thêm chart client-side.

---

## THỨ TỰ TRIỂN KHAI ĐỀ XUẤT

Dựa trên impact cho workflow Game Designer × effort:

### Phase 1 — Quick wins (client-side only, không cần backend mới)
1. **UI-03** Outlier highlight + sort/filter table *(Thấp effort, dùng ngay)*
2. **UI-02** Run comparison *(Trung bình effort, giải quyết pain point lớn nhất)*
3. **UI-10** Difficulty curve chart *(Thấp effort, data đã có)*
4. **UI-09** Config presets *(Thấp effort, tiện dụng)*

### Phase 2 — Backend additions
5. **UI-05** Advanced profile editor *(Mở rộng server mapping)*
6. **UI-07** Export CSV + download links *(Thêm 1 endpoint đơn giản)*
7. **UI-06** Auto-calibrate button *(Extract logic từ calibrate.py)*

### Phase 3 — Major features
8. **UI-01** Level drill-down *(Endpoint mới + refactor runner.py)*
9. **UI-04** Cohort mode integration *(Kết nối CohortSimulator + UI charts mới)*
10. **UI-08** Real-time progress *(SSE hoặc polling — thay đổi request flow)*

---

## TỔNG KẾT HÀNH ĐỘNG

| # | Mức độ | Mô tả ngắn | Effort | Trạng thái |
|---|--------|-------------|--------|------------|
| S-01 | 🔴 | Xóa dead code engine.py | Thấp | ✅ Done |
| S-02 | 🔴 | Fix Scissors target logic | Thấp | ✅ Done |
| S-03 | 🔴 | Fix During Level % calculation | Thấp | ✅ Done |
| S-04 | 🔴 | Sync BoosterInventory defaults | Thấp | ✅ Done |
| S-05 | 🟡 | Xóa duplicate root .py files | Thấp | ✅ Done |
| S-06 | 🟡 | Extract shared simulate function | Trung bình | ✅ Done |
| S-07 | 🟡 | Implement/xóa unused params | Trung bình | ✅ Done |
| S-08 | 🟡 | Optimize _rebuild_occupied | Trung bình | ✅ Done |
| S-09 | 🟡 | Implement auto-calibration | Cao | ✅ Done |
| S-10 | 🟢 | UI advanced profile editor | Trung bình | ✅ Done (→ UI-05) |
| S-11 | 🟢 | UI run comparison | Cao | ✅ Done (→ UI-02) |
| S-12 | 🟢 | Kết nối cohort mode vào UI | Trung bình | ⬚ Pending |
| S-13 | 🟢 | Phân biệt churn_rate vs fail_rate | Thấp | ✅ Done |
| S-14 | 🟢 | Thêm unit tests | Cao | ⬚ Pending |
| S-15 | 🔴 | churned_during đánh đồng fail vs bỏ cuộc | Thấp | ✅ Done |
| S-16 | ~~🔴~~ | ~~Level load overhead tính cho mọi attempt~~ | — | ✖ Withdrawn |
| S-17 | 🔴 | timing_multiplier chỉ scale output, không ảnh hưởng behavior | Thấp | ✅ Done |
| S-18 | 🟡 | engine.py còn dead viewport code + trùng ViewportRegion | Thấp | ✅ Done |
| S-19 | 🟡 | apply_scissors O(N³) cần tối ưu | Trung bình | ✅ Done |
| S-20 | 🟡 | S-08 incremental occupied chưa thật sự nhanh hơn, cần reverse index | Trung bình | ✅ Done |
| S-21 | 🟡 | Booster activation không nhân fatigue | Thấp | ✅ Done |
| S-22 | 🟡 | StepEvent + SimulationResult dead dataclass | Thấp | ✅ Done |
| UI-01 | 🔴 | Level drill-down (click level → detail) | Trung bình | ⬚ Phase 3 |
| UI-02 | 🔴 | Run comparison (save + overlay 2 runs) | Trung bình | ✅ Done |
| UI-03 | 🟡 | Outlier highlight + sort/filter table | Thấp | ✅ Done |
| UI-04 | 🟡 | Cohort mode integration (funnel, churn chart) | Cao | ⬚ Phase 3 |
| UI-05 | 🟡 | Advanced profile editor (20+ params) | Trung bình | ✅ Done |
| UI-06 | 🟡 | Auto-calibrate button từ UI | Trung bình | ✅ Done |
| UI-07 | 🟢 | Export CSV + download links | Thấp | ✅ Done |
| UI-08 | 🟢 | Real-time progress streaming (SSE) | Trung bình | ✅ Done |
| UI-09 | 🟢 | Config presets save/load | Thấp | ✅ Done |
| UI-10 | 🟢 | Difficulty score curve chart | Thấp | ✅ Done |

---

## CHANGELOG

### 2026-03-22 — Dev

**10 items hoàn thành (S-01 → S-09, S-13). Chi tiết thay đổi:**

**S-01** `src/engine.py` — Xóa ~460 dòng dead code: class `PlayerSimulator`, hàm `run_simulation_batch`, `compute_percentiles`. Đây là code cũ trước refactor 3 lớp, tham chiếu field không tồn tại (`sim_config.camera`, `sim_config.arrow_eval`, `sim_config.runs_per_level`). Thay bằng comment giải thích lý do xóa.

**S-02** `src/game_adapter.py` dòng 129–141 — `apply_scissors()` đã sửa logic: thay vì chọn arrow bị block nhiều nhất (`count_blockers(a)` = đếm ai chặn `a`), giờ iterate tất cả candidate và đếm xem mỗi candidate đang chặn bao nhiêu arrow khác (`find_blocker(other) == candidate`). Chọn candidate có `blocking_count` cao nhất.

**S-03** `src/cohort.py` dòng 127–128 — `during_pct` đã sửa từ `complete_pct - start_pct` (luôn ≤ 0, vô nghĩa) thành `(agg.started - agg.completed) / agg.started` = tỷ lệ player bỏ cuộc trong level.

**S-04** `src/game_adapter.py` dòng 41–44 — `BoosterInventory` defaults đổi từ `(3, 2, 1)` thành `(0, 0, 0)`. Bắt buộc gọi `reset(bcfg)` trước khi dùng. Tránh bug nếu ai quên gọi `reset()`.

**S-05** Root directory — Xóa 5 file `.py` trùng lặp ở root (`config.py`, `engine.py`, `user_model.py`, `game_adapter.py`, `cohort.py`). `src/` là source of truth duy nhất. Tools import từ `src/` qua `sys.path.insert`.

**S-06** Tạo `src/runner.py` — Extract hàm `simulate_level()` dùng chung. `tools/server.py` và `tools/calibrate.py` đều import từ `runner.py` thay vì duplicate logic. `calibrate.py::simulate_single_level()` giờ chỉ là wrapper truyền `PLAYER_PROFILES` + `PLAYER_MIX`.

**S-07** `src/config.py` — Annotate 3 tham số chưa implement:
- `EyeConfig.color_confusion_penalty`: thêm comment `NOT YET IMPLEMENTED`
- `PlayerProfile.hesitation_threshold`: thêm comment `NOT YET IMPLEMENTED`
- `ComboConfig`: cập nhật docstring ghi rõ "Placeholder for future games. Do not remove."

**S-08** `src/engine.py` — `BoardState.remove_arrow()` đổi từ `_rebuild_occupied()` (rebuild toàn bộ O(N)) sang incremental update: chỉ xóa cells không còn ai dùng. Cải thiện performance cho board 50+ arrows × cohort lớn.

**S-09** Thêm auto-calibration:
- `src/config.py`: thêm `SimulationConfig.timing_multiplier` (default 1.0) — hệ số nhân global cho timing.
- `src/runner.py`: apply `timing_multiplier` vào output time (`total_time * sim_config.timing_multiplier`).
- `tools/calibrate.py`: thêm flag `--auto` + `--auto-iters`. Chạy binary search trên `timing_multiplier` cho đến khi `avg_time_ratio ≈ 1.0` (threshold 2%).

**S-13** `src/cohort.py` dòng 129–148 — Đổi `churn_rate = 1.0 - win_rate` (thực chất là fail rate) thành `churn_during_rate = agg.churned_during / agg.started` (churn thật: player bỏ game hoàn toàn trong level).

**Còn lại (4 items pending):**
- S-10, S-11, S-12: cần thiết kế UI/UX trước khi code — recommend bàn riêng.
- S-14: unit tests nên tạo riêng session, sau khi code ổn định.

### 2026-03-22 — Dev (batch 2)

**7 items hoàn thành (S-15, S-17, S-18, S-19, S-20, S-21, S-22). Chi tiết thay đổi:**

**S-15** `src/cohort.py` dòng 220–241 — `_simulate_player_on_level()`: thêm biến `gave_up = False`, chỉ set `True` khi `should_give_up()` trả về True. `churned_during=gave_up` thay vì `churned_during=not won`. Player fail hết attempts nhưng không chủ động bỏ cuộc sẽ KHÔNG bị tính churn.

**S-17** `src/config.py` + `src/runner.py` — Thêm comment chi tiết ghi rõ: `timing_multiplier` chỉ post-multiply output time, KHÔNG ảnh hưởng internal decisions (fatigue, frustration, timeout, should_give_up). OK cho rough calibration.

**S-18 + S-22** `src/engine.py` — Xóa ~150 dòng dead code:
- `ViewportRegion` dataclass (trùng với `user_model.py`)
- `StepEvent` + `SimulationResult` dataclass (legacy, không ai import)
- `compute_zoom_in_regions()`, `compute_zoom_out_regions()` (trùng với `user_model.compute_regions()`)
- `arrows_in_region()`, `sort_arrows_by_scan()` (trùng với `game_adapter._arrows_in_region()`)
- `CameraConfig` alias (không ai dùng)
- Xóa import `random`, `ViewportConfig as CameraConfig`, `EyeConfig`, `PlayerProfile`, `SimulationConfig` (không còn cần)
- Cập nhật docstring module cho đúng vai trò hiện tại

**S-19** `src/game_adapter.py` dòng 129–144 — `apply_scissors()` tối ưu từ O(N²×W) xuống O(N×W): precompute `blocking_count` dict bằng 1 pass `find_blocker()` cho mỗi arrow, rồi pick max. Cùng kết quả, nhanh hơn N lần.

**S-20** `src/engine.py` — `BoardState.__init__()` + `remove_arrow()`: thay thế incremental check (O(K×N) per removal) bằng `_cell_count` reverse index (cell → int). `remove_arrow()` giờ thật sự O(K): giảm count, xóa khỏi occupied khi count = 0.

**S-21** `src/game_adapter.py` dòng 396, 404, 412 — Booster activation time giờ nhân `self.user.fatigue()`, consistent với mọi thao tác timing khác trong sim.

**Còn lại (2 items pending — tất cả 🟢 Nice-to-have):**
- ~~S-10: UI advanced profile editor~~ → ✅ Done (batch 3: UI-05)
- ~~S-11: UI run comparison/snapshot~~ → ✅ Done (batch 3: UI-02)
- S-12: Kết nối cohort mode vào server API — cần thêm endpoint + UI chart
- S-14: Unit tests — nên làm khi code ổn định

### 2026-03-22 — Dev (batch 3: UI Polish)

**7 UI items hoàn thành (UI-02, UI-03, UI-05, UI-06, UI-07, UI-09, UI-10). Cũng hoàn thành S-10 (→ UI-05) và S-11 (→ UI-02). Chi tiết thay đổi:**

**Phase 1 — Client-side only:**

**UI-03** `ui.html` — Sort/filter table + outlier highlighting:
- Table header clickable → sort ascending/descending bất kỳ cột nào
- Filter dropdown: "All / Off-track (>1.3x or <0.7x) / Way off (>2x or <0.5x)"
- Level range filter input (format "15-25")
- Auto-highlight: hàng đỏ nhạt cho ratio >2x hoặc <0.5x, vàng nhạt cho >1.3x hoặc <0.7x (CSS class `row-danger`, `row-warn`)
- Summary card "Outliers" hiển thị số level off-track

**UI-02** `ui.html` — Run comparison:
- Button "Save Run" lưu `{ label, config, results, timestamp }` vào JS array `savedRuns`
- Tab "Compare" mới: dropdown chọn 2 runs, overlay chart (2 đường sim trên cùng chart + feed baseline), diff table mỗi dòng = 1 level × delta time/WR
- Summary diff text tự động: "Run B trung bình nhanh/chậm hơn X% so với Run A"

**UI-10** `ui.html` — Difficulty curve chart:
- Chart mới "Difficulty Curve" trong tab Chart
- Bar chart difficulty score + line overlay sim_avg_time trend
- Color-coded points: xanh = ratio OK, đỏ = outlier
- Tooltip hiển thị board size, arrow count

**UI-09** `ui.html` — Config presets save/load:
- Dropdown "Presets" với "Save Preset" / "Load Preset" buttons
- Lưu toàn bộ config (profiles + mix + booster + overhead + level range) vào JS memory
- Preset name editable khi save

**Phase 2 — Backend additions:**

**UI-05** `ui.html` + `tools/server.py` — Advanced profile editor (= S-10):
- Toggle "Show Advanced" mở section ẩn với 12 params bổ sung, nhóm:
  - **Zoom & Viewport**: initial_zoom, preferred_zoom, zoom_in_to_tap_prob, zoom_out_survey_prob, viewport_cleared_zoom_out_prob
  - **Cognition**: recursive_solve_probability, max_recursion_depth, memory_probability, recheck_probability
  - **Effort & Quit**: board_scan_time, max_batch_before_pan, frustration_decay_after_solve
- `tools/server.py::handle_simulate()` dòng 168–179: thêm mapping cho 12 advanced params từ request body vào `PlayerProfile` fields

**UI-07** `ui.html` — Export CSV:
- Button "Export CSV" ở góc phải tab Table
- Client-side CSV generation từ results array, trigger download trực tiếp
- Server đã auto-save CSV vào `report/` folder (có sẵn từ trước)

**UI-06** `ui.html` + `tools/server.py` — Auto-calibrate từ UI:
- Button "Auto-Calibrate" cạnh "Run Simulation"
- Client-side iterative binary search trên `timing_multiplier`: chạy N iterations, mỗi lần gửi `/api/simulate` với multiplier mới, so ratio, adjust
- Progress hiển thị: "Iteration X/N — ratio Xx — adjusting..."
- Kết quả auto-fill `timing_multiplier` vào config panel
- `tools/server.py` dòng 138: thêm `sim_config.timing_multiplier = config.get("timing_multiplier", 1.0)`

**Còn lại (2 UI items + 2 S items pending):**
- UI-01 🔴: Level drill-down — cần endpoint `/api/simulate-detail` + refactor runner.py
- UI-04 🟡: Cohort mode integration — cần endpoint `/api/simulate-cohort` + UI charts
- ~~UI-08 🟢: Real-time progress streaming (SSE)~~ → ✅ Done (batch 4)
- S-12 🟢: Kết nối cohort mode vào UI (= UI-04)
- S-14 🟢: Unit tests — nên làm khi code ổn định

### 2026-03-22 — Dev (batch 4: SSE + UI fixes)

**3 items hoàn thành: UI-08 + 2 UI improvements theo yêu cầu Game Designer.**

**UI-08** `tools/server.py` + `ui.html` — Real-time progress streaming (SSE):
- Server: thêm endpoint `POST /api/simulate-stream` trả SSE events thay vì JSON response
- SSE events: `start` (total levels, config), `progress` (per-level: index, level_id, elapsed, ETA, result), `done` (full results + elapsed)
- UI: `runSimulation()` chuyển từ `fetch('/api/simulate')` sang `fetch('/api/simulate-stream')` + ReadableStream reader
- Progress bar thực với phần trăm, elapsed time, ETA — thay thế "check terminal" message cũ
- Endpoint cũ `/api/simulate` vẫn giữ nguyên để auto-calibrate + backward compatibility

**Level set context info** `ui.html` — Hiển thị dataset đang dùng:
- Thêm banner `#runContext` phía trên status bar: hiển thị version, level range, cohort size, seed, timing_multiplier
- Mỗi chart card header thêm subtitle context (version + level range) để biết chart thuộc dataset nào
- `lastRunConfig` variable lưu config hiện tại, render qua `updateRunContext()` sau mỗi simulation

**Avg Time chart → Line chart** `ui.html` — Đổi chart type:
- Chart "Avg Time: Sim vs Feed" đổi từ `type: 'bar'` sang `type: 'scatter', mode: 'lines+markers'`
- Sim line: solid #4a6fa5, Feed line: dotted #f39c12
- Giữ range slider, responsive layout, hover template

**Còn lại (2 UI items + 2 S items pending):**
- UI-01 🔴: Level drill-down — cần endpoint `/api/simulate-detail` + refactor runner.py
- UI-04 🟡: Cohort mode integration — cần endpoint `/api/simulate-cohort` + UI charts
- S-12 🟢: Kết nối cohort mode vào UI (= UI-04)
- S-14 🟢: Unit tests — nên làm khi code ổn định

---

*File này dùng chung giữa các AI. Khi cập nhật, ghi rõ tác giả + ngày ở mỗi thay đổi, không quên cập nhật vào changelog.*
