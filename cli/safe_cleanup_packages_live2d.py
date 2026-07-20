"""
safe_cleanup_packages_live2d.py

SAFE RULE: Only flags files that match EXACTLY live2d_{numericId}.zip
AND whose ID exists in the catalog DB.

Everything else in packages_live2d is left completely alone.
Does NOT touch packages_vrm, packages_vrma, packages_mmd, or any other folder.

Runs in DRY-RUN mode by default. Pass --delete to actually remove files.
"""
import sqlite3, os, re, sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')

PACKAGES_LIVE2D = 'E:/lpk-studio-storage/packages_live2d'
LIVE2D_PACKAGES = 'E:/lpk-studio-storage/live2d_packages'  # canonical output dir

DRY_RUN = '--delete' not in sys.argv

# Must match EXACTLY: live2d_<digits>.zip — nothing else
EXACT_PATTERN = re.compile(r'^live2d_(\d+)\.zip$')

# Load catalog IDs
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()
cur.execute("SELECT id FROM models")
catalog_ids = set(row[0] for row in cur.fetchall())
conn.close()

print("Catalog IDs loaded: " + str(len(catalog_ids)))
print("Scanning: " + PACKAGES_LIVE2D)
print()

if not os.path.isdir(PACKAGES_LIVE2D):
    print("ERROR: Directory not found: " + PACKAGES_LIVE2D)
    sys.exit(1)

all_files = os.listdir(PACKAGES_LIVE2D)
print("Total files in packages_live2d: " + str(len(all_files)))
print()

safe_to_delete = []   # exact match live2d_{id}.zip AND in catalog
keep_no_match  = []   # doesn't match exact pattern -> keep, hands off
keep_not_in_db = []   # matches pattern but ID not in catalog -> keep

for fname in all_files:
    fpath = os.path.join(PACKAGES_LIVE2D, fname)
    if os.path.isdir(fpath):
        print("  [DIR - SKIP] " + fname)
        continue

    m = EXACT_PATTERN.match(fname)
    if not m:
        keep_no_match.append(fname)
        continue

    wid = m.group(1)
    if wid in catalog_ids:
        # Also verify the canonical ZIP exists in live2d_packages before marking safe
        canonical = os.path.join(LIVE2D_PACKAGES, fname)
        if os.path.exists(canonical):
            safe_to_delete.append((fpath, fname, wid, 'duplicate of canonical'))
        else:
            safe_to_delete.append((fpath, fname, wid, 'in catalog, no canonical yet'))
    else:
        keep_not_in_db.append((fname, wid))

print("=" * 60)
print("SAFE TO DELETE (exact live2d_ID.zip match + in catalog): " + str(len(safe_to_delete)))
print("KEEP - no ID pattern (named models, unique content):      " + str(len(keep_no_match)))
print("KEEP - ID pattern but not in catalog:                     " + str(len(keep_not_in_db)))
print("=" * 60)
print()

total_bytes = sum(os.path.getsize(p) for p, *_ in safe_to_delete if os.path.exists(p))
print("Reclaimable space: " + str(round(total_bytes / (1024**3), 2)) + " GB")
print()

if safe_to_delete:
    print("Files flagged for deletion:")
    for fpath, fname, wid, reason in safe_to_delete[:20]:
        size_mb = round(os.path.getsize(fpath) / (1024**2), 1)
        print("  " + fname + "  (" + str(size_mb) + " MB) [" + reason + "]")
    if len(safe_to_delete) > 20:
        print("  ... and " + str(len(safe_to_delete) - 20) + " more")

print()
if DRY_RUN:
    print("DRY RUN — no files deleted. Re-run with --delete to actually remove.")
else:
    print("DELETING " + str(len(safe_to_delete)) + " files...")
    deleted = 0
    for fpath, fname, wid, reason in safe_to_delete:
        try:
            os.remove(fpath)
            deleted += 1
        except Exception as e:
            print("  ERROR deleting " + fname + ": " + str(e))
    print("Deleted " + str(deleted) + " files.")
