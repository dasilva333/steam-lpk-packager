import os
import sys
import json
import sqlite3
import shutil
import glob
import subprocess

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')

# Helper to read basic key=values from .env if present
def load_env_config():
    env_vars = {}
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

env_cfg = load_env_config()

default_storage = os.path.join(BASE_DIR, "storage")
STORAGE_DIR = env_cfg.get("STORAGE_DIR", default_storage)
CACHE_DIR = os.path.join(STORAGE_DIR, "workshop_cache")
THUMB_DIR = os.path.join(BASE_DIR, "public", "thumbnails")

def get_connection():
    return sqlite3.connect(DB_PATH)

def extract_spine_version(skel_path):
    try:
        # Check if JSON format
        if skel_path.lower().endswith(".json"):
            with open(skel_path, 'r', encoding='utf-8', errors='ignore') as f:
                data = json.load(f)
                version = data.get("skeleton", {}).get("spine")
                if version:
                    return version
        
        # Read 200 bytes for binary/fallback signature scanning
        with open(skel_path, 'rb') as f:
            content = f.read(200)
            import re
            match = re.search(rb'([0-9]+\.[0-9]+\.[0-9]+)', content)
            if match:
                return match.group(1).decode("ascii", errors="ignore")
            match_short = re.search(rb'([0-9]+\.[0-9]+)', content)
            if match_short:
                return match_short.group(1).decode("ascii", errors="ignore")
    except Exception as e:
        pass
    return "Unknown"

def extract_cubism_version(moc3_path):
    try:
        with open(moc3_path, 'rb') as f:
            header = f.read(64)
            # Cubism 3.x+ headers start with 'MOC3' and have version signatures around byte 4
            if header.startswith(b'MOC3'):
                version_byte = header[4]
                if version_byte == 3:
                    return "3.x"
                elif version_byte == 4:
                    return "4.x"
                elif version_byte == 5:
                    return "5.0-5.2" # Target range
                return "Cubism 3+"
    except:
        pass
    return "Unknown"

def process_item(item_id):
    item_dir = os.path.join(CACHE_DIR, item_id)
    if not os.path.exists(item_dir):
        return False, "Not downloaded yet"
        
    config_path = os.path.join(item_dir, "config.json")
    if not os.path.exists(config_path):
        return False, "config.json missing"
        
    # 1. Parse config.json
    config_data_str = ""
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config_data = json.load(f)
            config_data_str = json.dumps(config_data)
    except Exception as e:
        return False, f"Failed to parse config.json: {str(e)}"
        
    # 2. Extract PNG thumbnail and convert to JPG
    os.makedirs(THUMB_DIR, exist_ok=True)
    png_files = glob.glob(os.path.join(item_dir, "*.png"))
    local_thumb_path = ""
    if png_files:
        try:
            from PIL import Image
            # Load and convert PNG to JPG with size limit
            img = Image.open(png_files[0])
            if img.width > 512 or img.height > 512:
                img.thumbnail((512, 512), Image.Resampling.LANCZOS)
            target_thumb = os.path.join(THUMB_DIR, f"{item_id}.jpg")
            rgb_img = img.convert("RGB")
            rgb_img.save(target_thumb, "JPEG", quality=75)
            img.close()
            rgb_img.close()
            local_thumb_path = f"/thumbnails/{item_id}.jpg"
        except Exception as e:
            print(f"  [WARNING] Failed to optimize thumbnail for {item_id}: {e}")
            # Fallback copy
            target_thumb = os.path.join(THUMB_DIR, f"{item_id}.png")
            shutil.copy(png_files[0], target_thumb)
            local_thumb_path = f"/thumbnails/{item_id}.png"
        
    # 3. Spawn LPK decrypt/extraction pipeline (calling CLI batch_extract_models script)
    # We will invoke the existing batch_extract_models.py inside cli/ to handle format standardization
    print(f"Running batch_extract_models for {item_id}...")
    
    # We create a Directory Junction from E: to C: instead of copying files.
    # This prevents any C: disk space usage during the run.
    legacy_packages_dir = os.path.join(BASE_DIR, "cli", "packages")
    os.makedirs(legacy_packages_dir, exist_ok=True)
    temp_target = os.path.join(legacy_packages_dir, item_id)
    
    if os.path.exists(temp_target):
        # Remove existing symlink/junction
        if os.path.isdir(temp_target):
            subprocess.run(f'rmdir "{temp_target}"', shell=True)
        else:
            os.remove(temp_target)

    # Create Windows directory junction (mklink /J)
    # mklink requires paths with backslashes
    src_dir = item_dir.replace("/", "\\")
    dst_dir = temp_target.replace("/", "\\")
    subprocess.run(f'mklink /J "{dst_dir}" "{src_dir}"', shell=True, capture_output=True)
    
    # Run the legacy python extractor
    # Explicitly run under the relative cli directory where batch_extract_models expects its paths
    cmd = f'py batch_extract_models.py'
    subprocess.run(cmd, shell=True, cwd=os.path.join(BASE_DIR, "cli"))
    
    # Clean up temp package junction link safely
    if os.path.exists(temp_target):
        for _ in range(5):
            try:
                subprocess.run(f'rmdir "{temp_target.replace("/", "\\")}"', shell=True)
                break
            except Exception:
                time.sleep(0.5)

    # Delete the source LPK file to save disk space if successfully decrypted
    decrypted_dir = os.path.join(CACHE_DIR, item_id, "decrypted")
    if os.path.isdir(decrypted_dir) and len(os.listdir(decrypted_dir)) > 0:
        lpk_files = glob.glob(os.path.join(item_dir, "*.lpk"))
        if lpk_files:
            try:
                os.remove(lpk_files[0])
                print(f"  [{item_id}] [DELETE] Removed source LPK file: {os.path.basename(lpk_files[0])}")
            except Exception as e:
                print(f"  [{item_id}] [WARNING] Failed to remove source LPK file: {e}")
        
    # 4. Check outputs inside workshop_cache/<item_id>/decrypted/
    decrypted_dir = os.path.join(CACHE_DIR, item_id, "decrypted")
    
    packaged = 0
    steam_type = "Other"
    cubism_ver = None
    spine_ver = None
    compatible = None
    compat_reason = None
    
    if os.path.isdir(decrypted_dir):
        # Scan for format indicators inside the decrypted folders
        moc3_files = glob.glob(os.path.join(decrypted_dir, "**", "*.moc3"), recursive=True)
        moc_files = glob.glob(os.path.join(decrypted_dir, "**", "*.moc"), recursive=True)
        skel_files = glob.glob(os.path.join(decrypted_dir, "**", "*.skel"), recursive=True) or glob.glob(os.path.join(decrypted_dir, "**", "skeleton_0"), recursive=True)
        
        if moc3_files or moc_files:
            packaged = 1
            steam_type = "Live2D"
            compatible = 1
            cubism_ver = "3.x-4.x"
        elif skel_files:
            packaged = 1
            steam_type = "Spine"
            # Extract actual Spine version to determine compatibility
            detected_ver = extract_spine_version(skel_files[0])
            spine_ver = detected_ver
            if detected_ver.startswith("4."):
                compatible = 1
            else:
                compatible = 0
                compat_reason = f"Unsupported Spine version: {detected_ver} (requires Spine 4.x)"
            
    if not packaged:
        # Check if it was flagged as incompatible Spine model
        incompatible_log = os.path.join(BASE_DIR, "cli", "spine_packages", "incompatible_spine_models.md")
        if os.path.exists(incompatible_log):
            with open(incompatible_log, 'r', encoding='utf-8') as f:
                content = f.read()
                if f"spine_{item_id}" in content:
                    steam_type = "Spine"
                    compatible = 0
                    compat_reason = "Incompatible Spine runtime version (requires Spine 4.x)"
                    spine_ver = "3.x"
            
    if not packaged:
        # Check if it was flagged as incompatible Spine model
        incompatible_log = os.path.join(BASE_DIR, "cli", "spine_packages", "incompatible_spine_models.md")
        if os.path.exists(incompatible_log):
            with open(incompatible_log, 'r', encoding='utf-8') as f:
                content = f.read()
                if f"spine_{item_id}" in content:
                    steam_type = "Spine"
                    compatible = 0
                    compat_reason = "Incompatible Spine runtime version (requires Spine 4.x)"
                    spine_ver = "3.x"
                    
    # Update SQLite database
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        UPDATE models SET
            fingerprinted = 1,
            steam_type = ?,
            compatible = ?,
            compat_reason = ?,
            cubism_version = ?,
            spine_version = ?,
            config_data = ?,
            thumbnail_local = ?,
            packaged = ?
        WHERE id = ?
    ''', (steam_type, compatible, compat_reason, cubism_ver, spine_ver, 
          config_data_str, local_thumb_path, packaged, item_id))
    conn.commit()
    conn.close()
    
    return True, f"Processed {steam_type} | Compat: {compatible} | Packaged: {packaged}"

def start_processing_phase(specific_id=None):
    # Find all downloaded folders that are not yet fingerprinted in SQLite
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM models WHERE fingerprinted = 0")
    db_ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    if not os.path.exists(CACHE_DIR):
        print("Workshop cache is empty.")
        return
        
    if specific_id:
        targets = [specific_id]
    else:
        downloaded_ids = os.listdir(CACHE_DIR)
        targets = [fid for fid in downloaded_ids if fid in db_ids]
    
    print(f"Found {len(targets)} downloaded items ready for extraction processing")
    print("=" * 60)
    
    for idx, fid in enumerate(targets, 1):
        print(f"[{idx}/{len(targets)}] Extracting & Inspecting {fid}...")
        try:
            success, msg = process_item(fid)
            print(f"  {msg}")
        except Exception as e:
            print(f"  [ERROR] processing: {str(e)}")
            
    print("=" * 60)
    print("Processing Phase finished!")
    print("=" * 60)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'process':
        specific = sys.argv[2] if len(sys.argv) > 2 else None
        start_processing_phase(specific)
    else:
        print("Usage: py cli/win_processor.py process [optional_workshop_id]")
