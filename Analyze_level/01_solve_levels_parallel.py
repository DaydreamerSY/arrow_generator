from concurrent.futures import ProcessPoolExecutor, as_completed
from solver_core import solve_level

LEVEL_FOLDER = "input_levels"
CACHE_FOLDER = "_solved_data"
MAX_WORKERS = 12

def main():
    import os
    os.makedirs(CACHE_FOLDER, exist_ok=True)
    files = [os.path.join(LEVEL_FOLDER, f) for f in os.listdir(LEVEL_FOLDER) if f.endswith(".json")]
    print(f"Analyzing {len(files)} levels with {MAX_WORKERS} workers...")
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = {ex.submit(solve_level, f, CACHE_FOLDER): f for f in files}
        for fut in as_completed(futures):
            try:
                name, states, arrows = fut.result()
                print(f"✅ {name} ({states} states, {arrows} arrows)")
            except Exception as e:
                print(f"❌ Error in {futures[fut]}: {e}")

if __name__ == "__main__":
    main()
