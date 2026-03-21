# Arrow Escape — User Simulator

A player behavior simulator for Arrow Escape puzzle game. Predicts playtime, fail rate, win rate, and attempt count per level by simulating how real players (female 45-60 demographic) interact with the game.

## Architecture

3-layer design, separating human behavior from game mechanics:

```
Layer 1: UserModel (src/user_model.py) — REUSABLE across games
├── Viewport/Eye scanning model (phone screen, zoom in/out)
├── Cognitive model (scan speed, decision time, fatigue)
├── Emotional model (frustration, engagement curve)
├── Skill progression (improves over levels played)
└── Churn decisions (give up, between-level quit)

Layer 2: GameAdapter (src/game_adapter.py) — GAME-SPECIFIC
├── Board/Arrow state management
├── Arrow evaluation (head finding, path tracing, solvability)
├── Booster system (Hint, Scissors, Magic Wand)
├── Board-state-aware scanning (density clutter, clearing speed bonus)
├── Cascade awareness (newly unlocked arrows → momentum)
└── Level overhead (loading, celebration)

Layer 3: CohortSimulator (src/cohort.py) — ORCHESTRATOR
├── Spawn N players with weighted profiles
├── Run each through level sequence
├── Aggregate → CSV output matching Feed data format
└── Between-level churn (engagement-based)
```

## Quick Start

### CLI

```bash
# Per-level calibration (recommended)
cd "User Simulator"
python tools/calibrate.py --mode level --max-levels 50 --cohort 500

# Full cohort simulation
python tools/run.py --max-levels 100 --cohort 4936

# Output in data/output/
```

### Web UI

```bash
cd "User Simulator"
python tools/server.py --port 8080
# Open http://localhost:8080
```

The UI allows you to adjust player profiles, mix weights, booster config, and level overhead, then run simulation and see results compared against Feed data.

## File Structure

```
User Simulator/
├── ui.html                    # Web UI (standalone HTML)
├── src/                       # Source code
│   ├── config.py              # All configs, profiles, params
│   ├── engine.py              # Board solver, level loader, metrics
│   ├── user_model.py          # Layer 1: human model (reusable)
│   ├── game_adapter.py        # Layer 2: Arrow Escape adapter
│   └── cohort.py              # Layer 3: cohort orchestrator
├── tools/                     # Entry points
│   ├── run.py                 # Cohort simulation runner
│   ├── calibrate.py           # Calibration vs feed data
│   └── server.py              # HTTP server for Web UI
├── data/
│   ├── feed/                  # Real player data (ground truth)
│   ├── levels/                # Level JSON files (1603 levels)
│   └── output/                # Simulation output CSVs + reports
└── docs/
    ├── README.md              # This file
    ├── discuss.md             # Original design discussion
    └── references/            # Game screenshots
```

## Player Profiles

4 archetypes modeling target demographic behavior:

| Profile | Scan Speed | Miss Rate | Frustration | Booster Use | Description |
|---------|-----------|-----------|-------------|-------------|-------------|
| Methodical (32%) | Slow (225ms) | Low (5%) | Low buildup | Reluctant (0.3) | Systematic, patient, accurate |
| Scanner (22%) | Fast (112ms) | High (20%) | Medium buildup | Moderate (0.4) | Quick, impulsive, overview-first |
| Comfortable (33%) | Medium (175ms) | Medium (12%) | Very low buildup | Happy to use (0.6) | Relaxed, enjoys the process |
| Struggler (13%) | Slow (300ms) | High (25%) | High buildup | Relies on (0.8) | New player, learning, frustrated easily |

## Within-Level Model Features

### Board-State-Aware Scanning
Scan cost changes dynamically as board state changes:
- **Density clutter**: more arrows visible → harder to distinguish each → slower scan
- **Clearing speed bonus**: fewer arrows remaining → easier to spot → faster scan

### Cascade Awareness
After each arrow clear, simulator tracks how many NEW arrows become solvable:
- Cascade (≥2 unlocked) → frustration decreases (positive momentum)
- Dead end (0 unlocked) → slight frustration increase

### Reactive Zoom
When player clears all arrows in current viewport:
- Automatically zooms out to survey remaining board
- Probability depends on profile (Scanner: 95%, Struggler: 50%)

### Booster System
3 boosters for Arrow Escape (extensible interface):
- **Hint** (frustration ≥ 0.4): removes 1 solvable arrow, 800ms activation
- **Scissors** (frustration ≥ 0.6): removes 1 blocking arrow, 1200ms activation
- **Magic Wand** (frustration ≥ 0.8): removes up to 3 arrows recursively, 600ms activation
- Inventory: 5 of each per attempt
- Usage probability = config threshold × profile booster_willingness

### Skill Progression
Players improve across levels:
- Scan speed, miss rate, decision time each have separate growth rates
- Different profiles learn at different speeds
- Skill floor prevents infinite improvement
- Mastery gives engagement bonus (skilled players churn less)

## Calibration Results

After 4 rounds of calibration against Feed data (100 levels):

| Metric | Value | Status |
|--------|-------|--------|
| Avg time ratio (sim/feed) | 1.02x | ✓ |
| Win rate diff | -0.001 | ✓ |
| Fail rate diff | -0.011 | ✓ |
| Attempt diff | -0.025 | ✓ |

Early levels (1-5) run faster than feed due to missing tutorial/exploration time that sim doesn't model.

## Extending to Other Games

To support a different puzzle game:
1. Create `new_game_adapter.py` implementing same interface as `ArrowEscapeAdapter`
2. Implement: board state, action evaluation, tap execution
3. Add game-specific boosters via `BoosterModel` subclass
4. Keep `UserModel` and `CohortSimulator` unchanged
5. Combo system ready via `ComboConfig` (set `enabled=True`)

---

## Backlog

### High Priority

- [ ] **Tutorial time model**: Early levels (1-5) sim is 2-5x faster than feed because sim doesn't model first-time player exploration, tutorial reading, or initial confusion. Need a `first_play_overhead` that decays over first 5-10 levels.

- [ ] **Distraction/pause model**: Real players pause mid-level (notification, conversation, put phone down). This adds variance to playtime distribution. Feed data avg/median ratio of 2-3x suggests long tail from paused sessions.

- [ ] **Color confusion penalty**: Arrow colors affect distinguishability. Nearby arrows with similar colors are harder to parse. Needs color data in level JSON files to implement.

- [ ] **Hint system (free hints)**: Game provides free hints after being stuck. Current booster model requires frustration threshold. Free hints would trigger earlier and affect timing differently.

### Medium Priority

- [ ] **Session model**: Between-level churn currently uses per-level probability. Real churn is session-based (player has X minutes budget per sitting). Needs session_start/session_end data from game server.

- [ ] **Adaptive difficulty perception**: Current perceived difficulty blends static score with attempt results. Could be improved by tracking difficulty curve (was previous level easy/hard) — context matters.

- [ ] **Multi-attempt memory model**: On retry, player remembers WHICH arrows they solved and in what order. Current model only reduces miss_prob globally. Should model partial board memory.

- [ ] **Player clustering from real data**: Current 4 archetypes are estimated. With real tap_count + mistake_count + solve_order data, could cluster real players and derive profiles empirically.

### Low Priority

- [ ] **Combo system implementation**: Interface designed in `ComboConfig` but not active. Implement for games with chain-clear mechanics (match-3 style).

- [ ] **Sound/haptic feedback model**: Audio/vibration cues help players identify solvable arrows. Could reduce scan time by X% when feedback is strong.

- [ ] **Ad interruption model**: Interstitial ads between levels affect engagement and session timing. Need ad frequency data to model.

- [ ] **Social features model**: Leaderboards, friend progress, lives system affect motivation and return rate. Complex to model without social data.

- [ ] **Device performance model**: Older phones have slower animations, lower framerate → longer perceived wait times. Target demographic may use older devices.

### Technical Debt

- [ ] **Root file cleanup**: Root directory still has old files that can't be deleted (mount permission). All active code is in `src/`, `tools/`, `data/`.

- [ ] **Calibration automation**: `calibrate.py` suggests changes but doesn't auto-apply. Could implement scipy.optimize loop to auto-tune params.

- [ ] **Performance optimization**: Full cohort run (4936 players × 1100 levels) takes ~100s. Could parallelize with multiprocessing.

- [ ] **Unit tests**: No test suite. Critical logic in engine.py board solver and game_adapter.py should have tests.

- [ ] **Config serialization**: Profile changes in UI are not persisted to `config.py`. Need config export/import to JSON + apply script.
