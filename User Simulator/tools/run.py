"""
Entry point: Cohort simulation for Arrow Escape.

Usage (from project root):
    python tools/run.py [--levels data/levels] [--output-dir data/output] [--cohort N]
"""

import argparse
import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import SimulationConfig
from cohort import CohortSimulator, write_csv


def main():
    project_root = Path(__file__).parent.parent

    parser = argparse.ArgumentParser(description="Arrow Escape — Cohort Simulator")
    parser.add_argument("--levels", type=str, default=str(project_root / "data" / "levels"))
    parser.add_argument("--output-dir", type=str, default=str(project_root / "data" / "output"))
    parser.add_argument("--cohort", type=int, default=4936)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--max-levels", type=int, default=0)
    args = parser.parse_args()

    sim_config = SimulationConfig(cohort_size=args.cohort, random_seed=args.seed)

    levels_dir = Path(args.levels)
    if not levels_dir.exists():
        print(f"ERROR: Levels directory not found: {levels_dir}")
        sys.exit(1)

    level_files = list(levels_dir.glob("*.json"))
    if not level_files:
        print(f"ERROR: No JSON files found in {levels_dir}")
        sys.exit(1)

    def extract_id(p):
        try: return int(p.stem.split("_")[1])
        except: return 0
    level_files.sort(key=extract_id)

    if args.max_levels > 0:
        level_files = level_files[:args.max_levels]

    print(f"Levels: {len(level_files)} | Cohort: {args.cohort} | Seed: {args.seed}\n")

    simulator = CohortSimulator([str(f) for f in level_files], sim_config)
    pt_rows, eng_rows = simulator.run()

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    write_csv(pt_rows, str(output_dir / "Sim_Level_playtime.csv"))
    write_csv(eng_rows, str(output_dir / "Sim_Level_engagement.csv"))

    print(f"\nOutput: {output_dir / 'Sim_Level_playtime.csv'}")
    print(f"Output: {output_dir / 'Sim_Level_engagement.csv'}")


if __name__ == "__main__":
    main()
