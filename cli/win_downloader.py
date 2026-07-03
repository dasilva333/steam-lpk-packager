import os
import sys
import json
import sqlite3
import subprocess
import time
import shutil

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')
STORAGE_DIR = "E:\\lpk-studio-storage"
CACHE_DIR = os.path.join(STORAGE_DIR, "workshop_cache")
MAX_SIZE = 1.5 * 1024 * 1024 * 1024  # 1.5 GB

def get_connection():
    return sqlite3.connect(DB_PATH)

def download_item(item_id):
    os.makedirs(CACHE_DIR, exist_ok=True)
    item_dir = os.path.join(CACHE_DIR, item_id)
    
    if os.path.exists(item_dir) and len(os.listdir(item_dir)) > 0:
        return True, "Already downloaded"
        
    print(f"Downloading {item_id} via steamcmd...")
    # Target steamcmd workshop download path
    cmd = f'steamcmd +login anonymous +workshop_download_item 616720 {item_id} +quit'
    
    # Run steamcmd and track output
    process = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    
    # Check if download actually populated Steam's default workshop cache folder
    # On Windows, steamcmd downloads to its installation directory under steamapps\workshop\content\616720\<id>
    # We will locate it and move it to our custom E:\lpk-studio-storage\workshop_cache directory
    # Default steamcmd paths are typically resolved relatively. Let's look for the downloaded content.
    steamcmd_workshop_dir = None
    
    # Check common locations where steamcmd stores workshop items on Windows
    paths_to_check = [
        os.path.expandvars(r"%LOCALAPPDATA%\VirtualStore\Program Files (x86)\Steam\steamapps\workshop\content\616720"),
        r"C:\steamcmd\steamapps\workshop\content\616720",
        r"C:\Program Files (x86)\Steam\steamapps\workshop\content\616720",
    ]
    
    # Also check relative to where steamcmd might be installed on path
    try:
        steamcmd_path = shutil.which("steamcmd")
        if steamcmd_path:
            steamcmd_root = os.path.dirname(steamcmd_path)
            paths_to_check.append(os.path.join(steamcmd_root, "steamapps", "workshop", "content", "616720"))
    except:
        pass

    source_dir = None
    for p in paths_to_check:
        test_path = os.path.join(p, item_id)
        if os.path.exists(test_path) and len(os.listdir(test_path)) > 0:
            source_dir = test_path
            break
            
    if source_dir:
        # Move it to our clean E drive cache storage
        shutil.move(source_dir, item_dir)
        return True, "Download successful"
    else:
        # Check process output for error logs
        if "failed" in process.stdout.lower() or "error" in process.stdout.lower():
            return False, f"SteamCMD Error: {process.stdout.strip()[-200:]}"
        return False, "Download folder not found"

def start_download_phase():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch all Live2D and Spine models under our 1.5GB size threshold
    cursor.execute('''
        SELECT id, title, file_size, steam_type 
        FROM models 
        WHERE steam_type IN ('Live2D', 'Spine') 
          AND file_size <= ?
    ''', (MAX_SIZE,))
    
    items = cursor.fetchall()
    conn.close()
    
    total = len(items)
    print(f"Loaded {total} targets for download phase (Live2D & Spine <= 1.5GB)")
    print("=" * 60)
    
    success_count = 0
    failed_count = 0
    skipped_count = 0
    
    for idx, (item_id, title, size, m_type) in enumerate(items, 1):
        size_mb = size / (1024 * 1024)
        print(f"[{idx}/{total}] Processing {item_id} ({m_type} | {size_mb:.2f} MB) - '{title[:30]}'")
        
        try:
            success, message = download_item(item_id)
            if success:
                if message == "Already downloaded":
                    skipped_count += 1
                else:
                    success_count += 1
                print(f"  ✅ {message}")
            else:
                failed_count += 1
                print(f"  ❌ {message}")
        except Exception as e:
            failed_count += 1
            print(f"  ❌ Error: {str(e)}")
            
        # Give Steam connection a minor breathing delay
        time.sleep(1)
        
    print("=" * 60)
    print(f"Download Phase finished! Success: {success_count} | Skipped: {skipped_count} | Failed: {failed_count}")
    print("=" * 60)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'download':
        start_download_phase()
    else:
        print("Usage: py cli/win_downloader.py download")
