from types import SimpleNamespace
from pathlib import Path


class Args(SimpleNamespace):
    solver_input_folder: Path
    solver_solved_data: Path
    
