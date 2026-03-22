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
from runner import simulate_level


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
    """Wrapper around shared simulate_level using global profiles/mix."""
    return simulate_level(board, sim_config, n_players, seed, PLAYER_PROFILES, PLAYER_MIX)


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
    parser.add_argument("--auto", action="store_true", help="Auto-calibrate timing_multiplier via binary search")
    parser.add_argument("--auto-iters", type=int, default=8, help="Max iterations for auto-calibration")
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

    # ── Auto-calibration ────────────────────────────────────────────────
    if args.auto and ratios:
        avg_r = statistics.mean(ratios)
        print(f"\n{'='*60}")
        print("  AUTO-CALIBRATION (timing_multiplier)")
        print(f"{'='*60}")
        print(f"  Initial ratio: {avg_r:.3f}")

        # Binary search: target ratio = 1.0
        # timing_multiplier scales output time linearly
        multiplier = 1.0 / avg_r if avg_r > 0 else 1.0
        best_m, best_err = multiplier, abs(1.0 - avg_r)

        for it in range(args.auto_iters):
            sim_config_auto = SimulationConfig(
                cohort_size=args.cohort, random_seed=args.seed,
                timing_multiplier=multiplier,
            )
            # Re-run with new multiplier
            auto_ratios = []
            for lf in level_files:
                board = load_level(str(lf))
                sr = simulate_single_level(board, sim_config_auto, args.cohort, args.seed + board.level_id)
                lvl = board.level_id
                if lvl in feed_pt and feed_pt[lvl]["avg_time"] > 0:
                    auto_ratios.append(sr["avg_time"] / feed_pt[lvl]["avg_time"])

            if not auto_ratios:
                break
            new_avg = statistics.mean(auto_ratios)
            err = abs(1.0 - new_avg)
            print(f"  iter {it+1}: multiplier={multiplier:.4f} ratio={new_avg:.3f} err={err:.4f}")

            if err < best_err:
                best_m, best_err = multiplier, err
            if err < 0.02:  # convergence threshold: within 2%
                break
            # Adjust: new_multiplier = old_multiplier / new_ratio
            multiplier = multiplier / new_avg

        print(f"\n  Best timing_multiplier = {best_m:.4f} (err={best_err:.4f})")
        print(f"  → Set SimulationConfig(timing_multiplier={best_m:.4f})\n")

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
