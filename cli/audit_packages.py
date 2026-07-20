import sqlite3, os

db = sqlite3.connect('../db/catalog.sqlite')
db.row_factory = sqlite3.Row
cur = db.cursor()

# 1. Check the specific model
cur.execute('SELECT id, title, steam_type, packaged, download_failed FROM models WHERE id = ?', ('2173041194',))
row = cur.fetchone()
if row:
    print('--- SPECIFIC MODEL ---')
    print('ID:              ' + str(row['id']))
    print('Title:           ' + str(row['title']))
    print('Type:            ' + str(row['steam_type']))
    print('packaged flag:   ' + str(row['packaged']))
    print('download_failed: ' + str(row['download_failed']))
else:
    print('ID 2173041194 NOT FOUND in DB')

# 2. Broad audit: models flagged packaged=1 but ZIP missing on disk
storage = 'E:/lpk-studio-storage'
cur.execute("SELECT id, steam_type, packaged, download_failed FROM models WHERE packaged = 1")
rows = cur.fetchall()

missing = []
for r in rows:
    folder = 'live2d_packages' if r['steam_type'] == 'Live2D' else 'spine_packages'
    typ = r['steam_type'].lower()
    path = os.path.join(storage, folder, typ + '_' + str(r['id']) + '.zip')
    if not os.path.exists(path):
        missing.append((r['id'], r['steam_type'], r['download_failed']))

print('\n--- AUDIT RESULTS ---')
print('Total packaged=1 in DB:       ' + str(len(rows)))
print('Missing ZIPs on disk:         ' + str(len(missing)))

live2d_missing = [m for m in missing if m[1] == 'Live2D']
spine_missing  = [m for m in missing if m[1] == 'Spine']
print('  Live2D missing: ' + str(len(live2d_missing)))
print('  Spine  missing: ' + str(len(spine_missing)))

if missing:
    print('\nFirst 30 missing:')
    for m in missing[:30]:
        print('  [' + m[1] + '] id=' + str(m[0]) + '  download_failed=' + str(m[2]))

# 3. Inverse: ZIPs on disk but packaged=0 in DB
print('\n--- INVERSE CHECK (ZIP on disk but packaged=0 or not in DB) ---')
for folder, typ in [('live2d_packages', 'Live2D'), ('spine_packages', 'Spine')]:
    folder_path = os.path.join(storage, folder)
    if not os.path.isdir(folder_path):
        print('Folder not found: ' + folder_path)
        continue
    zips = [f for f in os.listdir(folder_path) if f.endswith('.zip')]
    print('ZIPs on disk in ' + folder + ': ' + str(len(zips)))
    untracked = 0
    for z in zips:
        stem = z.replace('.zip', '')
        prefix = typ.lower() + '_'
        if stem.startswith(prefix):
            stem = stem[len(prefix):]
        cur.execute('SELECT packaged FROM models WHERE id = ?', (stem,))
        r2 = cur.fetchone()
        if r2 is None or r2['packaged'] == 0:
            untracked += 1
    print('  -> ' + str(untracked) + ' ZIPs present but packaged=0 or not in DB')

db.close()
