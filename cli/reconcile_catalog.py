import os
import glob
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')
STORAGE_DIR = "E:\\lpk-studio-storage"
CACHE_DIR = os.path.join(STORAGE_DIR, "workshop_cache")

def run_reconciliation():
    print("=" * 60)
    print("LPK STUDIO — SYSTEM RECONCILIATION PASS")
    print(f"CACHE DIR: {CACHE_DIR}")
    print(f"DATABASE:  {DB_PATH}")
    print("=" * 60)

    if not os.path.isdir(CACHE_DIR):
        print("[Error] Cache directory does not exist.")
        return

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Step 1: Reset failed flags for things that exist in workshop_cache
    print("\n[Step 1] Resetting failed flags for downloaded items...")
    cache_dirs = [d for d in os.listdir(CACHE_DIR) if d.isdigit()]
    if cache_dirs:
        c.executemany('''
            UPDATE models 
            SET download_failed = 0, download_failed_reason = NULL 
            WHERE id = ? AND download_failed = 1
        ''', [(wid,) for wid in cache_dirs])
        conn.commit()
        print(f"  Reset failed status for matching downloaded items.")

    # Step 2: Scan E: cache and reconcile database flags & cleanup LPKs
    print("\n[Step 2] Reconciling model records & cleaning up redundant LPKs...")
    
    total_lpk_deleted = 0
    total_reconciled = 0

    for idx, wid in enumerate(cache_dirs, 1):
        item_dir = os.path.join(CACHE_DIR, wid)
        decrypted_dir = os.path.join(item_dir, "decrypted")
        
        # Verify decrypted folder is non-empty and contains valid model files
        valid_decrypted = False
        steam_type = "Other"
        cubism_ver = None
        spine_ver = None

        if os.path.isdir(decrypted_dir):
            moc3 = glob.glob(os.path.join(decrypted_dir, "**", "*.moc3"), recursive=True)
            moc = glob.glob(os.path.join(decrypted_dir, "**", "*.moc"), recursive=True)
            skel = glob.glob(os.path.join(decrypted_dir, "**", "*.skel"), recursive=True) or glob.glob(os.path.join(decrypted_dir, "**", "skeleton_0"), recursive=True)
            
            if moc3 or moc:
                valid_decrypted = True
                steam_type = "Live2D"
                cubism_ver = "3.x-4.x"
            elif skel:
                from win_processor import extract_spine_version
                valid_decrypted = True
                steam_type = "Spine"
                spine_ver = extract_spine_version(skel[0])

        # Safe LPK cleanup
        lpk_files = glob.glob(os.path.join(item_dir, "*.lpk"))
        if valid_decrypted and lpk_files:
            try:
                os.remove(lpk_files[0])
                total_lpk_deleted += 1
            except Exception as e:
                print(f"  [{wid}] [WARNING] Failed to remove LPK: {e}")

        # Update database status based on current files on disk
        if valid_decrypted:
            compatible = 1
            compat_reason = None
            if steam_type == "Spine":
                if spine_ver and spine_ver.startswith("4."):
                    compatible = 1
                else:
                    compatible = 0
                    compat_reason = f"Unsupported Spine version: {spine_ver} (requires Spine 4.x)"

            c.execute('''
                UPDATE models SET
                    fingerprinted = 1,
                    packaged = 1,
                    steam_type = ?,
                    cubism_version = ?,
                    spine_version = ?,
                    compatible = ?,
                    compat_reason = ?,
                    download_failed = 0
                WHERE id = ?
            ''', (steam_type, cubism_ver, spine_ver, compatible, compat_reason, wid))
            total_reconciled += 1
        else:
            # If no valid decryption exists, mark it as not processed so the pipeline picks it up
            c.execute('''
                UPDATE models SET
                    fingerprinted = 0,
                    packaged = 0,
                    download_failed = 0
                WHERE id = ?
            ''', (wid,))

    conn.commit()
    conn.close()

    print("\n" + "=" * 60)
    print("RECONCILIATION SUMMARY")
    print(f"  Items Inspected     : {len(cache_dirs)}")
    print(f"  Valid Decrypted     : {total_reconciled}")
    # Estimated space saved (LPK models average 10MB)
    est_saved_mb = total_lpk_deleted * 10
    print(f"  LPK Files Deleted   : {total_lpk_deleted} (~{est_saved_mb} MB saved)")
    print("=" * 60)

if __name__ == '__main__':
    run_reconciliation()
