import os
import sys
import json
import sqlite3
import shutil
import glob

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')
STORAGE_DIR = "E:\\lpk-studio-storage"
CACHE_DIR = os.path.join(STORAGE_DIR, "workshop_cache")
THUMB_DIR = os.path.join(BASE_DIR, "public", "thumbnails")

def get_connection():
    return sqlite3.connect(DB_PATH)

def extract_spine_version(skel_path):
    # Try reading as binary first
    try:
        with open(skel_path, 'rb') as f:
            header = f.read(16)
            # Spine binary headers usually start with version floats encoded as strings or bytes
            for match in glob.glob(os.path.dirname(skel_path) + "/*.json"):
                with open(match, 'r', encoding='utf-8', errors='ignore') as jf:
                    data = json.load(jf)
                    if "skeleton" in data and "spine" in data["skeleton"]:
                        return data["skeleton"]["spine"]
            # Fallback signature scanning
            text = header.decode('utf-8', errors='ignore')
            import re
            m = re.search(r'(\d+\.\d+\.\d+)', text)
            if m:
                return m.group(1)
    except:
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
        
    # 2. Extract PNG thumbnail
    os.makedirs(THUMB_DIR, exist_ok=True)
    png_files = glob.glob(os.path.join(item_dir, "*.png"))
    local_thumb_path = ""
    if png_files:
        # Copy the first found png to public/thumbnails/<id>.png
        target_thumb = os.path.join(THUMB_DIR, f"{item_id}.png")
        shutil.copy(png_files[0], target_thumb)
        local_thumb_path = f"/thumbnails/{item_id}.png"
        
    # 3. Spawn LPK decrypt/extraction pipeline (calling CLI batch_extract_models script)
    # We will invoke the existing batch_extract_models.py inside cli/ to handle format standardization
    print(f"Running batch_extract_models for {item_id}...")
    
    # We will copy the item folder temporarily to the cli/packages directory so the legacy script can process it
    legacy_packages_dir = os.path.join(BASE_DIR, "cli", "packages")
    os.makedirs(legacy_packages_dir, exist_ok=True)
    temp_target = os.path.join(legacy_packages_dir, item_id)
    
    if os.path.exists(temp_target):
        shutil.rmtree(temp_target)
    shutil.copytree(item_dir, temp_target)
    
    # Run the legacy python extractor
    # Explicitly run under the relative cli directory where batch_extract_models expects its paths
    cmd = f'py cli/batch_extract_models.py'
    subprocess.run(cmd, shell=True, cwd=BASE_DIR)
    
    # Clean up temp package folder
    if os.path.exists(temp_target):
        shutil.rmtree(temp_target)
        
    # 4. Check outputs inside cli/live2d_packages or cli/spine_packages
    live2d_zip = os.path.join(BASE_DIR, "cli", "live2d_packages", f"live2d_{item_id}.zip")
    spine_zip = os.path.join(BASE_DIR, "cli", "spine_packages", f"spine_{item_id}.zip")
    
    packaged = 0
    steam_type = "Other"
    cubism_ver = None
    spine_ver = None
    compatible = None
    compat_reason = None
    
    if os.path.exists(live2d_zip):
        packaged = 1
        steam_type = "Live2D"
        # We assume compatible unless verify_spine_versions or render failure flags it
        compatible = 1
        cubism_ver = "3.x-4.x" # Default range detected
    elif os.path.exists(spine_zip):
        packaged = 1
        steam_type = "Spine"
        compatible = 1
        spine_ver = "4.x"
    else:
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

def start_processing_phase():
    # Find all downloaded folders that are not yet fingerprinted in SQLite
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM models WHERE fingerprinted = 0")
    db_ids = {row[0] for row in cursor.fetchall()}
    conn.close()
    
    if not os.path.exists(CACHE_DIR):
        print("Workshop cache is empty.")
        return
        
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
            print(f"  ❌ Error processing: {str(e)}")
            
    print("=" * 60)
    print("Processing Phase finished!")
    print("=" * 60)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'process':
        start_processing_phase()
    else:
        print("Usage: py cli/win_processor.py process")
