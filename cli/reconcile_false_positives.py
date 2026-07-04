import os
import re
import sqlite3

FALSE_POSITIVES_TXT = r"C:\Users\h4rdc\Documents\Github\coding-agent\VRMs\false-positives.txt"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(PROJECT_ROOT, "db", "catalog.sqlite")

def reconcile():
    print("=" * 60)
    print("LPK STUDIO — RECONCILE FALSE POSITIVES")
    print(f"SOURCE FILE: {FALSE_POSITIVES_TXT}")
    print("=" * 60)

    if not os.path.exists(FALSE_POSITIVES_TXT):
        print(f"[Error] File not found: {FALSE_POSITIVES_TXT}")
        return

    # Parse workshop IDs from the text file
    false_positive_ids = []
    with open(FALSE_POSITIVES_TXT, "r", encoding="utf-16") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(";"):
                continue
            # Extract the numeric filename
            match = re.search(r"(\d+)\.png$", line)
            if match:
                false_positive_ids.append(match.group(1))

    print(f"Parsed {len(false_positive_ids)} false-positive IDs from file.")

    if not false_positive_ids:
        print("No valid IDs found to process.")
        return

    # Clean disk files and collect IDs for database updates
    deleted_bad = 0
    deleted_fixed = 0
    
    for wid in false_positive_ids:
        bad_path = os.path.join(PROJECT_ROOT, "public", "thumbnails", "bad_detected", f"{wid}.png")
        fixed_path = os.path.join(PROJECT_ROOT, "public", "thumbnails", "fixed", f"{wid}.png")
        
        if os.path.isfile(bad_path):
            try:
                os.remove(bad_path)
                deleted_bad += 1
            except Exception as e:
                print(f"  [{wid}] Failed to delete bad_detected image: {e}")

        if os.path.isfile(fixed_path):
            try:
                os.remove(fixed_path)
                deleted_fixed += 1
            except Exception as e:
                print(f"  [{wid}] Failed to delete fixed image: {e}")

    # Mass update database flags in SQLite
    print(f"Updating catalog database records...")
    db_updates = [(wid,) for wid in false_positive_ids]
    
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        
        # Reset flags: checked = 1, regenerated = 0 (since they are good original thumbnails)
        c.executemany("""
            UPDATE models 
            SET thumbnail_checked = 1, thumbnail_regenerated = 0 
            WHERE id = ?
        """, db_updates)
        
        conn.commit()
        affected = c.rowcount
        conn.close()
        print(f"Successfully updated {affected} model records in SQLite database.")
    except Exception as e:
        print(f"[Error] Database update failed: {e}")

    print("\n" + "=" * 60)
    print("RECONCILIATION SUMMARY")
    print(f"  Total Parsed        : {len(false_positive_ids)}")
    print(f"  Deleted Bad Thumbs  : {deleted_bad}")
    print(f"  Deleted Fixed Thumbs: {deleted_fixed}")
    print("=" * 60)

if __name__ == '__main__':
    reconcile()
