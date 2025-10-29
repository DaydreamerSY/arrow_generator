import os
import shutil
from pathlib import Path 

def collect_state_images(parent_folder, state_name="state_01.png"):
    output_folder = os.path.join("list_of_state_1", f"{parent_folder}_{state_name}_images")
    os.makedirs(output_folder, exist_ok=True)

    for root, dirs, files in os.walk(parent_folder):
        if state_name in files:
            src_path = os.path.join(root, state_name)
            folder_name = os.path.basename(root)
            dst_path = os.path.join(output_folder, f"{folder_name}_{state_name}")
            shutil.copy(src_path, dst_path)
            print(f"Copied: {src_path} → {dst_path}")

    print(f"\n✅ All '{state_name}' images collected in:\n{output_folder}")

# --- Example usage ---
# collect_state_images("/path/to/ANALYZE_LEVEL/_debug_results/visuals")



if __name__ == "__main__":
    # --- Example usage ---
    # parent_folder_path = Path("/Users/locnq/Documents/[Proto] Arrowscape/Level editor tool - experimental/debug_results")
    parent_folder_path = Path("_debug_results")
    collect_state_images(parent_folder_path)
