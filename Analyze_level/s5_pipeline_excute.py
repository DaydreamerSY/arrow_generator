from s1_solve_levels_parallel import LevelSolver
from s2_render_visuals import Renderer
from s3_analyze_solved_data import Analyzer
# from s import Renderer
from helper import Args
from pathlib import Path

if __name__ == "__main__":
    args = Args()

    solver = LevelSolver()
    args.solver_input_folder = Path("input_levels")
    args.solver_solved_data = Path("_solved_data")


    renderer = Renderer()
    args.render_debug_results = "_debug_results"
    args.render_debug_mode = "solve_only" # "solve_only", "unsolve_only", "both"


    analyer = Analyzer()
    args.analyze_output_csv_path = "out_put/analysis.csv"

    solver.excute(args)
    renderer.excute(args) # can skip render for faster analyze stat
    analyer.excute(args)





