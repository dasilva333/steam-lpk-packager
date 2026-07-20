"""
crossref_packages.py
Cross-references ZIPs in all three package directories against catalog.sqlite.
Outputs:
  - ZIPs that ARE in the catalog (safe to delete if duplicated across dirs)
  - ZIPs that are NOT in the catalog (uniquely sourced, must keep)
  - Duplicates across directories (same ID exists in multiple dirs)
"""
import sqlite3, os, re

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')

STORAGE = 'E:/lpk-studio-storage'
DIRS_TO_SCAN = [
    os.path.join(STORAGE, 'live2d_packages'),
    os.path.join(STORAGE, 'spine_packages'),
    os.path.join(STORAGE, 'packages_live2d'),
]

# Load all catalog IDs into a set for O(1) lookup
conn = sqlite3.connect(DB_PATH)
cur  = conn.cursor()
cur.execute("SELECT id FROM models")
catalog_ids = set(row[0] for row in cur.fetchall())
conn.close()

print("Catalog IDs loaded: " + str(len(catalog_ids)))
print()

# Scan all directories
id_pattern = re.compile(r'(\d{7,12})')  # Steam Workshop IDs are 8-10 digits typically

# Track: {id -> [list of paths it appears in]}
id_to_paths = {}

for scan_dir in DIRS_TO_SCAN:
    if not os.path.isdir(scan_dir):
        print("SKIPPED (not found): " + scan_dir)
        continue
    zips = [f for f in os.listdir(scan_dir) if f.endswith('.zip')]
    print("Scanning " + os.path.basename(scan_dir) + ": " + str(len(zips)) + " ZIPs")
    for z in zips:
        m = id_pattern.search(z)
        if m:
            wid = m.group(1)
            path = os.path.join(scan_dir, z)
            if wid not in id_to_paths:
                id_to_paths[wid] = []
            id_to_paths[wid].append(path)

print()
print("Total unique IDs found across all dirs: " + str(len(id_to_paths)))
print()

# Categorize
in_catalog     = {}  # id -> paths  (safe: already indexed)
not_in_catalog = {}  # id -> paths  (unique: must keep)
duplicates     = []  # ids present in more than one dir

for wid, paths in id_to_paths.items():
    if len(paths) > 1:
        duplicates.append((wid, paths))
    if wid in catalog_ids:
        in_catalog[wid] = paths
    else:
        not_in_catalog[wid] = paths

print("=" * 60)
print("RESULTS")
print("=" * 60)
print("In catalog (indexed):          " + str(len(in_catalog)))
print("NOT in catalog (unique/keep):  " + str(len(not_in_catalog)))
print("Duplicate across dirs:         " + str(len(duplicates)))
print()

# Size calculation
def total_size_gb(id_path_dict):
    total = 0
    for wid, paths in id_path_dict.items():
        for p in paths:
            try:
                total += os.path.getsize(p)
            except:
                pass
    return round(total / (1024**3), 2)

print("Space used by in-catalog ZIPs:    " + str(total_size_gb(in_catalog)) + " GB")
print("Space used by unique ZIPs:        " + str(total_size_gb(not_in_catalog)) + " GB")
print()

# Break down by directory for in_catalog
print("--- In-catalog breakdown by directory ---")
dir_counts = {}
for wid, paths in in_catalog.items():
    for p in paths:
        d = os.path.basename(os.path.dirname(p))
        dir_counts[d] = dir_counts.get(d, 0) + 1
for d, count in sorted(dir_counts.items()):
    print("  " + d + ": " + str(count))

print()
print("--- Unique (not in catalog) breakdown by directory ---")
dir_counts2 = {}
for wid, paths in not_in_catalog.items():
    for p in paths:
        d = os.path.basename(os.path.dirname(p))
        dir_counts2[d] = dir_counts2.get(d, 0) + 1
for d, count in sorted(dir_counts2.items()):
    print("  " + d + ": " + str(count))

print()
print("--- First 20 unique (NOT in catalog) IDs ---")
for wid, paths in list(not_in_catalog.items())[:20]:
    for p in paths:
        size_mb = round(os.path.getsize(p) / (1024**2), 1)
        print("  ID=" + wid + "  " + str(size_mb) + " MB  -> " + p)

# Write a safe-to-delete list for packages_live2d (in-catalog only)
safe_delete_list = []
for wid, paths in in_catalog.items():
    for p in paths:
        if 'packages_live2d' in p:
            safe_delete_list.append(p)

out_path = os.path.join(os.path.dirname(__file__), 'safe_to_delete_packages_live2d.txt')
with open(out_path, 'w', encoding='utf-8') as f:
    for p in safe_delete_list:
        f.write(p + '\n')

print()
print("Safe-to-delete list written to: " + out_path)
print("  " + str(len(safe_delete_list)) + " files in packages_live2d that are already in catalog")
