import os
import glob
import zipfile
import json
import re
import shutil
from datetime import datetime

# Detect if running in steam-lpk-packager repo or personal_airi
current_dir = os.path.dirname(os.path.abspath(__file__))
if "steam-lpk-packager" in current_dir:
    BASE_DIR = current_dir
    SPINE_DIR = os.path.join(BASE_DIR, "spine_packages")
    LPK_DIR = os.path.join(BASE_DIR, "packages")
else:
    BASE_DIR = "/Users/richardpinedo/Documents/Projects/airi/personal_airi"
    SPINE_DIR = os.path.join(BASE_DIR, "packages_spine")
    LPK_DIR = os.path.join(BASE_DIR, "packages_lpk")

LOG_FILE = os.path.join(SPINE_DIR, "incompatible_spine_models.md")


def get_spine_version(zpath):
    """
    Inspects the zip file to find the skeleton file and extracts the Spine version string.
    Supports both JSON and binary .skel files.
    """
    try:
        with zipfile.ZipFile(zpath, 'r') as zf:
            namelist = zf.namelist()
            
            # 1. Look for skeleton JSON or binary files
            skel_file = None
            for name in namelist:
                name_lower = name.lower()
                # Check for skeleton file endings
                if name_lower.endswith(".json") and "skeleton" in name_lower:
                    skel_file = name
                    break
                elif name_lower.endswith(".skel") or name_lower == "skeleton_0":
                    skel_file = name
                    break
            
            # Fallback to any JSON if no skeleton file found
            if not skel_file:
                for name in namelist:
                    if name.lower().endswith(".json") and name != "model0.json":
                        skel_file = name
                        break
            
            if not skel_file:
                return "Unknown (No skeleton file)"

            content = zf.read(skel_file)
            
            # 2. Extract version based on file type
            if skel_file.lower().endswith(".json"):
                try:
                    data = json.loads(content)
                    version = data.get("skeleton", {}).get("spine")
                    if version:
                        return version
                except Exception:
                    pass
            
            # Try regex on binary or json content (matches 1.2.34 and similar version strings in first 200 bytes)
            match = re.search(rb'([0-9]+\.[0-9]+\.[0-9]+)', content[:200])
            if match:
                return match.group(1).decode("ascii", errors="ignore")
                
    except Exception as e:
        return f"Error reading ({str(e)})"
        
    return "Unknown"

def log_incompatible_model(model_name, version):
    """
    Maintains a persistent markdown catalog of incompatible models.
    """
    now_str = datetime.now().strftime("%Y-%m-%d")
    new_entry = f"| {model_name} | {version} | Purged & Deleted | {now_str} |\n"
    
    header = (
        "# Incompatible Spine Models Catalog\n\n"
        "The following Spine models were detected as incompatible (Spine 3.x or 2.x, "
        "which are unsupported by the current Spine 4.x runtime) and have been purged from the active directories.\n\n"
        "| Model ID / Name | Detected Spine Version | Status | Date Cleaned |\n"
        "| --- | --- | --- | --- |\n"
    )
    
    # Read existing log to avoid duplicate entries
    existing_content = ""
    if os.path.exists(LOG_FILE):
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            existing_content = f.read()
            
    if not existing_content:
        content_to_write = header + new_entry
    elif model_name in existing_content:
        # Already logged
        return
    else:
        # Append to existing table
        content_to_write = existing_content.rstrip("\n") + "\n" + new_entry
        
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write(content_to_write)
    print(f"Logged {model_name} to incompatible catalog.")

def verify_and_purge_spine():
    print("Starting Spine Version Verification Utility...")
    
    zip_files = glob.glob(os.path.join(SPINE_DIR, "*.zip"))
    print(f"Found {len(zip_files)} Spine packages inside packages_spine/.\n")
    
    compatible_count = 0
    purged_count = 0
    
    for zpath in zip_files:
        zname = os.path.basename(zpath)
        model_name = zname.replace(".zip", "")
        
        # Skip verification on standard zip name formats if needed, but verify all
        version = get_spine_version(zpath)
        
        # Determine compatibility
        is_compatible = False
        if version.startswith("4."):
            is_compatible = True
            
        if is_compatible:
            print(f"✅ {model_name}: Spine {version} (Compatible)")
            compatible_count += 1
        else:
            print(f"❌ {model_name}: Spine {version} (INCOMPATIBLE) ➔ PURGING")
            purged_count += 1
            
            # 1. Log the incompatibility
            log_incompatible_model(model_name, version)
            
            # 2. Delete the zipped package from packages_spine
            try:
                os.remove(zpath)
                print(f"  - Deleted Spine ZIP: {zname}")
            except Exception as e:
                print(f"  - Failed to delete ZIP {zname}: {e}")
                
            # 3. Delete raw download folder/zip from packages_lpk
            # Extract workshop ID from name (e.g. spine_3153975148 -> 3153975148)
            workshop_id = model_name.replace("spine_", "")
            
            raw_dir = os.path.join(LPK_DIR, workshop_id)
            raw_zip = os.path.join(LPK_DIR, f"{workshop_id}.zip")
            
            if os.path.isdir(raw_dir):
                try:
                    shutil.rmtree(raw_dir)
                    print(f"  - Deleted raw Workshop Folder: packages_lpk/{workshop_id}/")
                except Exception as e:
                    print(f"  - Failed to delete Folder {workshop_id}: {e}")
            if os.path.isfile(raw_zip):
                try:
                    os.remove(raw_zip)
                    print(f"  - Deleted raw Workshop ZIP: packages_lpk/{workshop_id}.zip")
                except Exception as e:
                    print(f"  - Failed to delete ZIP {workshop_id}.zip: {e}")

    print("\n--- Summary Report ---")
    print(f"Total Spine Packages Checked: {len(zip_files)}")
    print(f"Compatible (Spine 4.x) Retained: {compatible_count}")
    print(f"Incompatible (Spine 3.x / 2.x) Purged: {purged_count}")
    print(f"Catalog updated at: {os.path.relpath(LOG_FILE, BASE_DIR)}")
    print("----------------------")

if __name__ == "__main__":
    verify_and_purge_spine()
