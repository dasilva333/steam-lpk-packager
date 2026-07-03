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

def log_download_failure(item_id, reason):
    """
    Marks an item as failed in SQLite database so it gets skipped next time.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute('''
            UPDATE models 
            SET download_failed = 1, download_failed_reason = ? 
            WHERE id = ?
        ''', (reason, item_id))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"  [ERROR] Database logging failure for {item_id}: {str(e)}")

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
    
    # Save the execution logs to trace failures
    log_dir = os.path.join(BASE_DIR, "cli", "logs")
    os.makedirs(log_dir, exist_ok=True)
    with open(os.path.join(log_dir, "steamcmd_last_batch.log"), "w", encoding="utf-8") as lf:
        lf.write(process.stdout)
        if process.stderr:
            lf.write("\n--- STDERR ---\n" + process.stderr)

    # Helper to parse .env file
    env_vars = {}
    env_path = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip()

    # Paths where steamcmd might have saved the downloaded workshop contents
    paths_to_check = []
    if env_vars.get("STEAM_CONTENT_DIR"):
        paths_to_check.append(env_vars.get("STEAM_CONTENT_DIR"))
        
    paths_to_check.extend([
        os.path.join(BASE_DIR, "steamcmd", "steamapps", "workshop", "content", "616720"),
        os.path.expandvars(r"%LOCALAPPDATA%\VirtualStore\Program Files (x86)\Steam\steamapps\workshop\content\616720"),
        r"C:\steamcmd\steamapps\workshop\content\616720",
        r"C:\Program Files (x86)\Steam\steamapps\workshop\content\616720",
    ])
    
    # Process files downloaded by the script
    moved_count = 0
    failures = []
    
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
        else:
            # Analyze steamcmd logs to extract exact error reason
            reason = "Download failed (missing or deprecated from Steam Workshop)"
            for line in process.stdout.split('\n'):
                if f"download item {item_id}" in line.lower() or f"item {item_id}" in line.lower():
                    if "failed" in line.lower() or "error" in line.lower():
                        reason = line.strip()
                        break
            failures.append((item_id, reason))
            log_download_failure(item_id, reason)
            
    # Remove the temporary runscript file
    if os.path.exists(script_path):
        try:
            os.remove(script_path)
        except:
            pass
            
    if failures:
        print(f"  [WARNING] Failed downloads in this batch:")
        for fid, freason in failures:
            print(f"    - ID: {fid} | {freason}")
            
    return True, f"Batch complete. Successfully acquired {moved_count}/{len(items_to_download)} new items."

def start_download_phase():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Fetch all Live2D and Spine models under our 1.5GB size threshold that haven't failed previously
    cursor.execute('''
        SELECT id, title, file_size, steam_type 
        FROM models 
        WHERE steam_type IN ('Live2D', 'Spine') 
          AND file_size <= ?
          AND download_failed = 0
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
            print(f"  [ERROR] Batch Execution Error: {str(e)}")
            
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
