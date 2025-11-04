# Arrow Generator Project

## Description
This project provides a suite of tools for generating, editing, and analyzing "arrow" game levels. The project has three main workflows:
- Generation (Gen_from_image/): An automated pipeline that converts an image (e.g., circle.png) into a "board" (text format), generates a .json level file containing arrows that fill the board, and renders that level into a .png image.
- Editor (Editor_tool/): A visual, GUI-based level editor (using PySide6) to manually create, edit, playtest, and auto-generate arrows within a user-painted area.
- Analysis (Analyze_level/): A separate toolset that takes existing .json level files, runs a solver algorithm, exports statistics (CSV), and renders the solution steps into images.


## Project Structure
```
v2.2/
├── Gen_from_image/           # WORKFLOW 1: GENERATE LEVEL FROM IMAGE
│   ├── s1_img1_rescale_image.py    # Step 1: Resize original image
│   ├── s2_img2_image_to_board.py   # Step 2: Convert resized image to .txt board
│   ├── s3_gen1_cli_generator.py    # Step 3: Generate .json level file from .txt board
│   ├── s4_gen2_render_generated.py # Step 4: Render .json file to .png image
│   ├── s5_pipeline_excute.py       # <<< MAIN EXECUTION FILE FOR WORKFLOW 1
│   ├── generator.py                # Level generation logic (basic & advanced)
│   ├── validator.py                # Level validation logic
│   └── helper.py                   # Args class for configuration management
│
├── Analyze_level/            # WORKFLOW 2: ANALYZE LEVEL
│   ├── 01_solve_levels_parallel.py # Step 1: Solve .json levels
│   ├── 02_render_visuals.py        # Step 2: Render solution visuals
│   ├── 03_analyze_solved_data.py   # Step 3: Analyze and export to CSV
│   └── solver_core.py              # Core solver logic
│
├── Editor_tool/              # WORKFLOW 3: VISUAL LEVEL EDITOR (GUI)
│   └── auto_gen_tool_v1.6_manual.py # <<< MAIN EXECUTION FILE FOR WORKFLOW 3
│
├── template_level/             # Contains template images (circle.png, square.png)
└── ...
```

## Installation
The project requires several Python libraries. You can install them using pip:

```
pip install pandas matplotlib numpy pillow PySide6
```

(Lưu ý: PySide6 là bắt buộc cho Workflow 3: Editor Tool).

## Usage
The project has three main workflows. You can perform any of them.
### Workflow 1: Generate Level from Image (Gen_from_image)
This is the primary automated function. The entire pipeline is controlled by `s5_pipeline_excute.py.`

### Step 1: Prepare Directories and Images:

- Based on the structure in `s5_pipeline_excute.py`, the project expects you to create a "set" directory (e.g., level_set/level_set_1/).

- Inside that directory, create a subdirectory `1_0_original_icons/.`

- Place the (PNG) image files you want to convert into `level_set/level_set_1/1_0_original_icons/` (e.g., HEART.png, square.png).

### Step 2: Configure the Pipeline:
Open the file `Gen_from_image/s5_pipeline_excute.py`.

Find the `if __name__ == "__main__":` block at the end of the file.

Customize the parameters in the args = Args() object:

- `args.level_set_path`: Path to your "set" directory (e.g., Path("level_set/level_set_1")).

- `args.size`: The (width, height) to which the original image will be resized (e.g., (50, 50)).

- `args.start_length`, args.length_step, args.min_length: Configure the arrow generation algorithm.

- `args.generate_mode`: Choose "basic" (simple random walk) or "advance" (controlled random walk).

If using "advance", you can also customize: turn_probability, straight_weight, etc.

### Step 3: Choose Execution Mode:
In the `s5_pipeline_excute.py` file, choose an execution mode by uncommenting the corresponding function (e.g., excute_folder(args)).

### Step 4: Run the Pipeline:
After configuration, run the s5_pipeline_excute.py file:
python Gen_from_image/s5_pipeline_excute.py


### Step 5: Check the Results:
The pipeline will automatically
- create directories and files in `level_set/level_set_1/`:
- Resized Images: `1_1_icons/`
- Board (Text): `1_board_test/`
- Level (JSON): `2_result_test/` (This is the actual level file).
- Image (Render): `3_render/` (Visual representation of the JSON file).

## Workflow 2: Visual Level Editor (Editor_tool)
This tool provides a graphical (GUI) interface for creating and editing levels manually.

### How to Run:

To run the editor, execute the `auto_gen_tool_v1.6_manual.py` script:
```
python Editor_tool/auto_gen_tool_v1.6_manual.py
```

Main Features:

- Paint Area (W): Manually "paint" the shape of your level using a brush, rectangle, or circle tool.
- Draw Arrow (E): Manually draw arrows with the mouse directly on the canvas.
- Generate Hybrid Level (G): Automatically fill the painted area with solvable arrows.
- Save (S) / Load (L): Save or load levels in the standard .json format (compatible with the other workflows).
- Playtest (P): Interactively play and solve the level you are editing directly within the tool.

### **Advance generator (generator with style) NOT included in Visual Level Editor**

## Workflow 3: Analyze Level (Analyze_level)
This workflow is used to analyze `.json` files (either from Workflow 1 or 2).
### Step 1: Prepare Levels
- Create the directory `Analyze_level/input_levels/.`
- Copy all the .json level files you want to analyze into this directory.

### Step 2: Run pipeline excute
- Run the `s5_pipeline_excute.py` script. This will do everything, note that Render file to Image can be skip (optional), disable for faster analyze progress

Results: An `out_put/analysis.csv` file will be created with statistics (total arrows, steps, lengths, etc.).

Update 4 Nov: you can do everything in a single file `s5_pipeline_excute.py`

Video tutorial: https://youtu.be/LYCt4FmL9XY

## Workflow 4: Import Level to Unity
This workflow is used to import created levels into Unity's project

### Step 1: Rename files
### ***Very Important***

Because the lack of features and polish of these tools above, you have to rename all file into this format: `0001.json` to make sure all levels are right order

### Step 2: Open Unity
1. Open `Level Data Converter` by going to `Arrow Escape > Level Data Converter`
2. You can choose convert single file or a folder
3. Set the converted level's ID, in case convert a folder, set the start level's ID to the first level in folder
4. Convert
5. Done


