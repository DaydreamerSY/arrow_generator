from types import SimpleNamespace
from pathlib import Path


class Args(SimpleNamespace):
    solver_input_folder: Path
    solver_solved_data: Path
    
    # render_solved_data: Path # render_solved_data == solver_solved_data
    render_debug_results: Path
    render_debug_mode: str # "solve_only", "unsolve_only", "both"
    state: dict
    data: dict

    # analyze_solved_data: Path # analyze_solved_data = solver_solved_data
    analyze_output_csv_path: Path

    
