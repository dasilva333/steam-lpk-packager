import sqlite3
import os

# Go up two folders from scratch directory
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')

conn = sqlite3.connect(DB_PATH)
c = conn.cursor()
c.execute("SELECT id, title, description FROM models WHERE description LIKE '%Original Title:%' LIMIT 5")
rows = c.fetchall()
print(f"Total translated found in sample check: {len(rows)}")
for idx, (item_id, title, desc) in enumerate(rows, 1):
    print(f"[{idx}] ID: {item_id}")
    print(f"    Translated Title: {title}")
    # Extract original title from description
    orig_title_line = [line for line in desc.split('\n') if "Original Title:" in line]
    print(f"    {orig_title_line[0] if orig_title_line else 'None'}")
    print("-" * 50)
conn.close()
