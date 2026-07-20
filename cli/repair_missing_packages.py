"""
repair_missing_packages.py
Resets packaged=0 for any model where the DB says packaged=1 but the ZIP is missing on disk.
Then package_models.py can be run to re-fill the gaps.
"""
import sqlite3, os

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH  = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')

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

env_cfg    = load_env_config()
STORAGE    = env_cfg.get("STORAGE_DIR") or env_cfg.get("STORAGE_ROOT") or os.path.join(BASE_DIR, "storage")
LIVE2D_DIR = os.path.join(STORAGE, "live2d_packages")
SPINE_DIR  = os.path.join(STORAGE, "spine_packages")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row
cur  = conn.cursor()

cur.execute("SELECT id, steam_type FROM models WHERE packaged = 1")
rows = cur.fetchall()

ghost_ids = []
for r in rows:
    folder = LIVE2D_DIR if r['steam_type'] == 'Live2D' else SPINE_DIR
    typ    = r['steam_type'].lower()
    path   = os.path.join(folder, typ + '_' + r['id'] + '.zip')
    if not os.path.exists(path):
        ghost_ids.append((r['id'],))

print("Total packaged=1 in DB : " + str(len(rows)))
print("Ghost records (no ZIP) : " + str(len(ghost_ids)))

if ghost_ids:
    cur.executemany("UPDATE models SET packaged = 0 WHERE id = ?", ghost_ids)
    conn.commit()
    print("Reset packaged=0 for " + str(len(ghost_ids)) + " records. Ready for repackaging.")
else:
    print("No ghost records found — everything is in sync.")

conn.close()
