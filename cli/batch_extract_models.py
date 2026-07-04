import sys
import os
import json
import glob
import zipfile
import shutil

# Add local dependency path
base_dir = os.path.dirname(__file__)
sys.path.append(os.path.join(base_dir, 'lpk2moc3-spine'))

from Core.lpk_loader import LpkLoader
import manager

# Mock the LogArea
class ConsoleLogger:
    def insert(self, index, text, *args):
        pass
    def configure(self, *args, **kwargs):
        pass
    def see(self, *args, **kwargs):
        pass

manager.LogArea = ConsoleLogger()

packages_dir = os.path.join(base_dir, "packages")
output_dir = os.path.join(base_dir, "live2d_packages")
temp_dir = os.path.join(base_dir, "temp_extract")
spine_output_dir = os.path.join(base_dir, "spine_packages")

if not os.path.exists(output_dir):
    os.makedirs(output_dir)
    print(f"Created output dir: {output_dir}")

# Find all items (zips and folders)
items = glob.glob(os.path.join(packages_dir, "*"))
print(f"Found {len(items)} items in packages directory.")

for item in items:
    basename = os.path.basename(item).replace(".zip", "")
    if basename == "README.md":
        continue
        
    print(f"\nProcessing {basename}...")
    
    # Skip if already processed
    zip_output_path_live2d = os.path.join(output_dir, f"live2d_{basename}.zip")
    zip_output_path_spine = os.path.join(spine_output_dir, f"spine_{basename}.zip")
    zip_output_path_failing = os.path.join(output_dir, "failing_to_render", f"live2d_{basename}.zip")
    
    if os.path.exists(zip_output_path_live2d) or os.path.exists(zip_output_path_spine) or os.path.exists(zip_output_path_failing):
        print(f"Output already exists for {basename}. Skipping.")
        continue
        
    # Setup paths for extraction
    lpk_path = None
    config_path = None
    
    if os.path.isfile(item) and item.endswith(".zip"):
        # 1. Extract zip to get LPK
        if os.path.exists(temp_dir):
            shutil.rmtree(temp_dir)
        os.makedirs(temp_dir)
        
        try:
            with zipfile.ZipFile(item, 'r') as zip_ref:
                zip_ref.extractall(temp_dir)
        except Exception as e:
            print(f"Failed to extract zip {item}: {e}")
            continue
            
        # Find .lpk file
        lpk_files = glob.glob(os.path.join(temp_dir, "*.lpk"))
        if not lpk_files:
            print(f"No .lpk file found in {basename}")
            continue
        
        lpk_path = lpk_files[0]
        config_path = os.path.join(temp_dir, "config.json")
        extract_target = os.path.join(temp_dir, "extracted")
        
    elif os.path.isdir(item):
        # It's a folder (from Steam Workshop)
        lpk_files = glob.glob(os.path.join(item, "*.lpk"))
        if not lpk_files:
            print(f"No .lpk file found in folder {basename}")
            continue
        lpk_path = lpk_files[0]
        config_path = os.path.join(item, "config.json")
        extract_target = os.path.join(base_dir, "temp_extract_folder") # Use a separate temp dir for folder processing
        
    else:
        print(f"Skipping {basename} (not a zip or folder).")
        continue
        
    if not os.path.exists(config_path):
        print(f"No config.json found for {basename}")
        continue

    # Ensure config.json has the correct fileId (especially for Steam Workshop items where fileId is empty)
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
        if not config_data.get("fileId"):
            config_data["fileId"] = basename
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=2)
            print(f"[FIX] Set empty fileId in config.json to '{basename}' for decryption compatibility.")
    except Exception as e:
        print(f"[WARNING] Failed to pre-verify config.json fileId: {e}")
        
    # 2. Extract LPK
    if os.path.exists(extract_target):
        shutil.rmtree(extract_target)
    os.makedirs(extract_target)
        
    try:
        loader = LpkLoader(lpk_path, config_path)
        loader.extract(extract_target, basename)
    except Exception as e:
        print(f"Extraction failed for {basename}: {e}")
        continue
        
    model_dir = os.path.join(extract_target, basename)
    
    # 3. Check format
    moc3_files = glob.glob(os.path.join(model_dir, "*.moc3"))
    moc_files = glob.glob(os.path.join(model_dir, "*.moc"))
    skel_files = glob.glob(os.path.join(model_dir, "*.skel")) or glob.glob(os.path.join(model_dir, "skeleton_*"))
    atlas_files = glob.glob(os.path.join(model_dir, "*.atlas")) + glob.glob(os.path.join(model_dir, "*.atlas.txt")) or glob.glob(os.path.join(model_dir, "atlases_*_atlas_*"))
    
    if moc3_files or moc_files:
        print(f"Detected Live2D model for {basename}!")
        try:
            manager.SetupSpineModel(model_dir)
        except Exception as e:
            print(f"SetupSpineModel failed for {basename}: {e} (Continuing anyway)")
            
        # Rename and clean model0.json
        model0_path = os.path.join(model_dir, "model0.json")
        if os.path.exists(model0_path):
            model_json_name = f"{basename}.model3.json" if moc3_files else f"{basename}.model.json"
            model_json_path = os.path.join(model_dir, model_json_name)
            os.rename(model0_path, model_json_path)
            print(f"Renamed model0.json to {model_json_name}")
            
            # Clean up missing expressions/motions references inside model JSON to ensure audit compliance
            try:
                with open(model_json_path, "r", encoding="utf-8") as f:
                    model_data = json.load(f)
                
                # 1. Clean Expressions
                if "FileReferences" in model_data and "Expressions" in model_data["FileReferences"]:
                    orig_expressions = model_data["FileReferences"]["Expressions"]
                    cleaned_expressions = []
                    for exp in orig_expressions:
                        exp_file = exp.get("File") or exp.get("Name")
                        if exp_file and not exp_file.endswith(".json"):
                            exp_file = exp_file + ".exp3.json"
                        
                        if exp_file:
                            if os.path.exists(os.path.join(model_dir, exp_file)):
                                cleaned_expressions.append({
                                    "Name": exp.get("Name") or os.path.splitext(exp_file)[0],
                                    "File": exp_file
                                })
                            else:
                                print(f"🧹 [PRUNE] Removed missing expression reference '{exp_file}' from model JSON.")
                    
                    if cleaned_expressions:
                        model_data["FileReferences"]["Expressions"] = cleaned_expressions
                    else:
                        del model_data["FileReferences"]["Expressions"]
                
                # 2. Clean Motions
                if "FileReferences" in model_data and "Motions" in model_data["FileReferences"]:
                    motions_dict = model_data["FileReferences"]["Motions"]
                    cleaned_motions = {}
                    for group_name, motion_list in list(motions_dict.items()):
                        cleaned_list = []
                        for motion in motion_list:
                            motion_file = motion.get("File")
                            if motion_file:
                                if os.path.exists(os.path.join(model_dir, motion_file)):
                                    cleaned_list.append(motion)
                                else:
                                    print(f"[PRUNE] Removed missing motion reference '{motion_file}' from group '{group_name}'.")
                        if cleaned_list:
                            cleaned_motions[group_name] = cleaned_list
                    if cleaned_motions:
                        model_data["FileReferences"]["Motions"] = cleaned_motions
                    else:
                        del model_data["FileReferences"]["Motions"]
                
                # Write back cleaned JSON
                with open(model_json_path, "w", encoding="utf-8") as f:
                    json.dump(model_data, f, ensure_ascii=False, indent=2)
                print(f"[CLEANUP] Successfully sanitized model references in {model_json_name}")
            except Exception as e:
                print(f"[WARNING] Failed to clean up model JSON references: {e}")
            
        # Zip the contents
        try:
            with zipfile.ZipFile(zip_output_path_live2d, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(model_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, model_dir)
                        zipf.write(file_path, arcname)
            print(f"Successfully packaged {basename} to {zip_output_path_live2d}")
        except Exception as e:
            print(f"Failed to create zip for {basename}: {e}")
            
    elif skel_files or atlas_files:
        print(f"Detected Spine model for {basename}!")
        try:
            manager.SetupSpineModel(model_dir)
        except Exception as e:
            print(f"SetupSpineModel failed for {basename}: {e} (Continuing anyway)")
            
        if not os.path.exists(spine_output_dir):
            os.makedirs(spine_output_dir)
            
        # Zip the contents
        try:
            with zipfile.ZipFile(zip_output_path_spine, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(model_dir):
                    for file in files:
                        file_path = os.path.join(root, file)
                        arcname = os.path.relpath(file_path, model_dir)
                        zipf.write(file_path, arcname)
            print(f"Successfully packaged {basename} to {zip_output_path_spine}")
        except Exception as e:
            print(f"Failed to create zip for {basename}: {e}")
    else:
        print(f"{basename} is not Live2D or Spine. Skipping.")

# Clean up temp dirs
if os.path.exists(temp_dir):
    shutil.rmtree(temp_dir)
if os.path.exists(os.path.join(base_dir, "temp_extract_folder")):
    shutil.rmtree(os.path.join(base_dir, "temp_extract_folder"))

print("\nBatch processing complete!")
