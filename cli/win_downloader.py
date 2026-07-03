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
BATCH_SIZE = 50  # Number of workshop downloads in a single steamcmd script session

def get_connection():
    return sqlite3.connect(DB_PATH)

def download_batch(items_to_download):
    """
    Downloads multiple items in a single steamcmd session using +runscript to save login/update overhead.
    """
    if not items_to_download:
        return True, "No items in batch"
        
    os.makedirs(CACHE_DIR, exist_ok=True)
    steamcmd_exe = os.path.join(BASE_DIR, "steamcmd", "steamcmd.exe")
    if not os.path.exists(steamcmd_exe):
        return False, f"Local steamcmd.exe not found at: {steamcmd_exe}"
        
    # Write a steamcmd batch download script
    script_path = os.path.join(BASE_DIR, "steamcmd", "download_script.txt")
    with open(script_path, "w", encoding="utf-8") as f:
        f.write("login anonymous\n")
        for item_id in items_to_download:
            f.write(f"workshop_download_item 616720 {item_id}\n")
        f.write("quit\n")
        
    print(f"Executing batch SteamCMD download script for {len(items_to_download)} items...")
    
    cmd = f'"{steamcmd_exe}" +runscript download_script.txt'
    # Run the script via steamcmd
    process = subprocess.run(cmd, shell=True, capture_output=True, text=True, cwd=os.path.join(BASE_DIR, "steamcmd"))
    
    # Paths where steamcmd might have saved the downloaded workshop contents
    paths_to_check = [
        os.path.join(BASE_DIR, "steamcmd", "steamapps", "workshop", "content", "616720"),
        os.path.expandvars(r"%LOCALAPPDATA%\VirtualStore\Program Files (x86)\Steam\steamapps\workshop\content\616720"),
        r"C:\steamcmd\steamapps\workshop\content\616720",
        r"C:\Program Files (x86)\Steam\steamapps\workshop\content\616720",
    ]
    
    # Process files downloaded by the script
    moved_count = 0
    for item_id in items_to_download:
        item_dir = os.path.join(CACHE_DIR, item_id)
        if os.path.exists(item_dir) and len(os.listdir(item_dir)) > 0:
            continue
            
        source_dir = None
        for p in paths_to_check:
            test_path = os.path.join(p, item_id)
            if os.path.exists(test_path) and len(os.listdir(test_path)) > 0:
                source_dir = test_path
                break
                
        if source_dir:
            os.makedirs(item_dir, exist_ok=True)
            # Move contents to clean E drive cache storage
            for fname in os.listdir(source_dir):
                shutil.move(os.path.join(source_dir, fname), os.path.join(item_dir, fname))
            try:
                shutil.rmtree(source_dir)
            except:
                pass
            moved_count += 1
            
    # Remove the temporary runscript file
    if os.path.exists(script_path):
        try:
            os.remove(script_path)
        except:
            pass
            
    return True, f"Batch complete. Successfully acquired {moved_count}/{len(items_to_download)} new items."

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
    
    # Build list of items that actually need to be downloaded
    pending_ids = []
    skipped_count = 0
    
    for item_id, title, size, m_type in items:
        item_dir = os.path.join(CACHE_DIR, item_id)
        if os.path.exists(item_dir) and len(os.listdir(item_dir)) > 0:
            skipped_count += 1
        else:
            pending_ids.append(item_id)
            
    print(f"Already cached: {skipped_count} | To download: {len(pending_ids)}")
    print("=" * 60)
    
    # Process pending items in chunked batches
    for i in range(0, len(pending_ids), BATCH_SIZE):
        batch = pending_ids[i:i + BATCH_SIZE]
        print(f"Processing Batch {i//BATCH_SIZE + 1} ({len(batch)} items)...")
        try:
            success, msg = download_batch(batch)
            print(f"  {msg}")
        except Exception as e:
            print(f"  ❌ Batch Execution Error: {str(e)}")
            
        # Give SteamCmd a small delay between session scripts to avoid socket throttling
        time.sleep(2)
        
    print("=" * 60)
    print("Download Phase finished!")
    print("=" * 60)

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'download':
        start_download_phase()
    else:
        print("Usage: py cli/win_downloader.py download")
