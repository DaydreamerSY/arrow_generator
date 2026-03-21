"""
Calibration script — compare simulator vs Feed data.

Usage (from project root):
    python tools/calibrate.py --mode level --max-levels 50 --cohort 500
    python tools/calibrate.py --mode cohort --max-levels 50 --cohort 1000
"""

import argparse
import csv
import random
import statistics
import sys
import time
from pathlib import Path
from typing import Dict, List

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import PLAYER_MIX, PLAYER_PROFILES, SimulationConfig
from engine import load_level, compute_level_metrics
from game_adapter import ArrowEscapeAdapter
from user_model import AttemptResult, UserModel


def load_feed_playtime(filepath: str) -> Dict[int, Dict]:
    rows = {}
    with open(filepath, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lvl = int(row["level"])
            rows[lvl] = {
                "avg_time": float(row["Avg time spent (minutes)"]),
                "med_time": float(row["Median time spent (minutes)"]),
                "avg_attempts": float(row["avg attempts"]),
                "pct_multi_attempt": float(row["%User having more than one attempt"]),
            }
    return rows


def load_feed_engagement(filepath: str) -> Dict[int, Dict]:
    rows = {}
    with open(filepath, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            lvl = int(row["level"])
            rows[lvl] = {
                "start": int(row["start"]),
                "win_rate": float(row["Win Rate %"]),
                "fail_rate": float(row["fail rate %"]),
            }
    return rows


def simulate_single_level(board, sim_config, n_players, seed):
    rng = random.Random(seed)
    acfg = sim_config.attempt
    all_times_ms, all_attempts = [], []
    wins, total_matches, total_wins = 0, 0, 0
    profiles = list(PLAYER_PROFILES.keys())
    weights = [PLAYER_MIX[p] for p in profiles]

    for ui in range(n_players):
        chosen = rng.choices(profiles, weights=weights, k=1)[0]
        user = UserModel(ui + seed, PLAYER_PROFILES[chosen], sim_config)
        adapter = ArrowEscapeAdapter(board, user, sim_config)
        total_time, won = 0.0, False

        for att in range(acfg.max_attempts):
            result = adapter.simulate_attempt(att)
            total_time += result.time_ms
            total_matches += 1
            if result.won:
                won = True
                total_wins += 1
                break
            if user.should_give_up(att + 1):
                break

        if won: wins += 1
        all_times_ms.append(total_time)
        all_attempts.append(att + 1 if not won else att + 1)

    times_min = [t / 60_000.0 for t in all_times_ms]
    return {
        "avg_time": statistics.mean(times_min),
        "med_time": statistics.median(times_min),
        "avg_attempts": statistics.mean(all_attempts),
        "win_rate": wins / n_players if n_players > 0 else 0,
        "fail_rate": 1 - (total_wins / total_matches) if total_matches > 0 else 0,
    }


def main():
    project_root = Path(__file__).parent.parent
    parser = argparse.ArgumentParser(description="Calibrate simulator vs Feed data")
    parser.add_argument("--levels", type=str, default=str(project_root / "data" / "levels"))
    parser.add_argument("--feed-dir", type=str, default=str(project_root / "data" / "feed"))
    parser.add_argument("--cohort", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-levels", type=int, default=50)
    parser.add_argument("--min-feed-start", type=int, default=30)
    parser.add_argument("--mode", type=str, default="level", choices=["level", "cohort"])
    args = parser.parse_args()

    feed_pt = load_feed_playtime(str(Path(args.feed_dir) / "Level playtime.csv"))
    feed_eng = load_feed_engagement(str(Path(args.feed_dir) / "Level engagement.csv"))
    sim_config = SimulationConfig(cohort_size=args.cohort, random_seed=args.seed)

    level_files = list(Path(args.levels).glob("*.json"))
    def eid(p):
        try: return int(p.stem.split("_")[1])
        except: return 0
    level_files.sort(key=eid)
    level_files = [f for f in level_files if eid(f) in feed_pt]
    if args.max_levels > 0:
        level_files = level_files[:args.max_levels]

    print(f"Mode: per-level | {len(level_files)} levels × {args.cohort} players\n")
    t0 = time.time()
    sim_results = {}

    for i, lf in enumerate(level_files):
        board = load_level(str(lf))
        sim_results[board.level_id] = simulate_single_level(
            board, sim_config, args.cohort, args.seed + board.level_id)
        if (i + 1) % 10 == 0:
            print(f"  {i+1}/{len(level_files)} levels ({time.time()-t0:.1f}s)")

    print(f"Done: {time.time()-t0:.1f}s\n")

    # Compute errors
    time_ratios, wr_diffs, fr_diffs, att_diffs = [], [], [], []
    for lvl in sorted(sim_results):
        if lvl not in feed_pt or lvl not in feed_eng: continue
        if feed_eng[lvl]["start"] < args.min_feed_start: continue
        sr, fp, fe = sim_results[lvl], feed_pt[lvl], feed_eng[lvl]
        if fp["avg_time"] > 0:
            time_ratios.append((lvl, sr["avg_time"] / fp["avg_time"]))
        wr_diffs.append(sr["win_rate"] - fe["win_rate"])
        fr_diffs.append(sr["fail_rate"] - fe["fail_rate"])
        att_diffs.append(sr["avg_attempts"] - fp["avg_attempts"])

    def s(vals):
        if not vals: return "N/A"
        return f"mean={statistics.mean(vals):.3f} med={statistics.median(vals):.3f}"

    ratios = [r for _, r in time_ratios]
    print("=" * 60)
    print("  CALIBRATION REPORT")
    print("=" * 60)
    print(f"\n  Levels: {len(time_ratios)}")
    print(f"  Avg time ratio:  {s(ratios)}")
    print(f"  Win rate diff:   {s(wr_diffs)}")
    print(f"  Fail rate diff:  {s(fr_diffs)}")
    print(f"  Attempt diff:    {s(att_diffs)}")

    print(f"\n  Sample (first 15 levels):")
    for lvl, ratio in time_ratios[:15]:
        sa = sim_results[lvl]["avg_time"]
        fa = feed_pt[lvl]["avg_time"]
        swr = sim_results[lvl]["win_rate"]
        fwr = feed_eng[lvl]["win_rate"]
        print(f"    L{lvl:>4}: sim={sa:.2f}m feed={fa:.2f}m ratio={ratio:.2f} | WR {swr:.3f} vs {fwr:.3f}")

    # Suggestions
    avg_r = statistics.mean(ratios) if ratios else 1.0
    print(f"\n{'='*60}")
    print("  SUGGESTIONS")
    print(f"{'='*60}")
    if avg_r > 1.3:
        print(f"  TIMING: {avg_r:.1f}x slow → multiply timing params by {1/avg_r:.2f}")
    elif avg_r < 0.7:
        print(f"  TIMING: {1/avg_r:.1f}x fast → multiply timing params by {1/avg_r:.2f}")
    else:
        print(f"  TIMING: ✓ ratio = {avg_r:.2f}")

    att_m = statistics.mean(att_diffs) if att_diffs else 0
    print(f"  ATTEMPTS: {'✓' if abs(att_m)<0.05 else '✗'} diff = {att_m:+.4f}")
    wr_m = statistics.mean(wr_diffs) if wr_diffs else 0
    print(f"  WIN RATE: {'✓' if abs(wr_m)<0.02 else '✗'} diff = {wr_m:+.4f}")
    fr_m = statistics.mean(fr_diffs) if fr_diffs else 0
    print(f"  FAIL RATE: {'✓' if abs(fr_m)<0.02 else '✗'} diff = {fr_m:+.4f}")
    print()


if __name__ == "__main__":
    main()
