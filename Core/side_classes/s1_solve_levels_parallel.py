from concurrent.futures import ProcessPoolExecutor, as_completed
from solver_core import solve_level
from helper import Args
from pathlib import Path

import os

LEVEL_FOLDER = "input_levels"
CACHE_FOLDER = "_solved_data"
MAX_WORKERS = 16

class LevelSolver:
    def __init__(self):
        pass

    def excute(self, args: Args):
        os.makedirs(args.solver_solved_data, exist_ok=True)
        files = [os.path.join(args.solver_input_folder, f) for f in os.listdir(args.solver_input_folder) if f.endswith(".json")]
        print(f"Analyzing {len(files)} levels with {MAX_WORKERS} workers...")
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(solve_level, f, args.solver_solved_data): f for f in files}
            for fut in as_completed(futures):
                try:
                    name, states, arrows = fut.result()
                    print(f"✅ {name} ({states} states, {arrows} arrows)")
                except Exception as e:
                    print(f"❌ Error in {futures[fut]}: {e}")

    

if __name__ == "__main__":
    level_solver = LevelSolver()

    args = Args()
    args.solver_input_folder = Path("input_levels")
    args.solver_solved_data = Path("_solved_data")

    level_solver.excute(args)
