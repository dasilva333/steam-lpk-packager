import os
import re
import sys
import json
import time
import sqlite3
import urllib.request
import urllib.parse

# Set console output encoding to UTF-8 to support printing CJK characters on Windows
if sys.platform.startswith('win'):
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')

# Unicode ranges for Chinese, Japanese, and Korean characters
CJK_RE = re.compile(r'[\u4e00-\u9fff\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')

def contains_cjk(text):
    if not text:
        return False
    return bool(CJK_RE.search(text))

def translate_text(text, target_lang='en'):
    """
    Translates text to English using Google's free translation web API.
    Can translate blocks containing newlines.
    """
    text_clean = text.strip()
    if not text_clean:
        return text

    url = "https://translate.googleapis.com/translate_a/single"
    params = {
        "client": "gtx",
        "sl": "auto",
        "tl": target_lang,
        "dt": "t",
        "q": text_clean
    }
    
    query_string = urllib.parse.urlencode(params)
    req_url = f"{url}?{query_string}"
    
    try:
        req = urllib.request.Request(
            req_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            translated_pieces = []
            for sentence in data[0]:
                if sentence and sentence[0]:
                    translated_pieces.append(sentence[0])
            translated_text = "".join(translated_pieces)
            return translated_text
    except Exception as e:
        print(f"  [ERROR] Translation request failed: {e}")
        return None

def run_translation():
    print("=" * 60)
    print("LPK STUDIO — ASIAN TITLES BATCH TRANSLATION SERVICE")
    print(f"DATABASE: {DB_PATH}")
    print("=" * 60)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Query all models
    c.execute("SELECT id, title, description FROM models")
    rows = c.fetchall()
    conn.close()

    # Filter targets containing CJK characters
    targets = []
    for item_id, title, desc in rows:
        if contains_cjk(title):
            targets.append((item_id, title, desc))

    if not targets:
        print("No titles with Asian characters found in the database.")
        return

    print(f"Found {len(targets)} models with Asian titles to translate.")

    success_count = 0
    batch_updates = []
    batch_size = 50
    group_size = 5  # Group titles in blocks of 5

    try:
        # Loop through targets in groups of 5
        for i in range(0, len(targets), group_size):
            group = targets[i : i + group_size]
            print(f"[{i + len(group)}/{len(targets)}] Processing batch of {len(group)} items...")

            # Merge titles using newline characters
            merged_titles = "\n".join([item[1] for item in group])
            translated_merged = translate_text(merged_titles)

            if translated_merged:
                # Split translated block back by newline
                translated_lines = [line.strip() for line in translated_merged.split("\n") if line.strip()]
            else:
                translated_lines = []

            # If the output count matches our input count, we can map them directly
            if len(translated_lines) == len(group):
                for idx, (item_id, orig_title, orig_desc) in enumerate(group):
                    eng_title = translated_lines[idx]
                    if eng_title == orig_title:
                        continue

                    desc_clean = orig_desc if orig_desc else ""
                    if "Original Title:" not in desc_clean:
                        updated_desc = f"{desc_clean}\n\nOriginal Title: {orig_title}".strip()
                    else:
                        updated_desc = desc_clean

                    batch_updates.append((eng_title, updated_desc, item_id))
                    success_count += 1
                    print(f"  [OK] Translated {item_id}: {orig_title} --> {eng_title}")
            else:
                # Fallback to single-item translation if the merge splits did not match
                print("  [WARN] Merged splits did not match inputs. Falling back to single translations...")
                for idx, (item_id, orig_title, orig_desc) in enumerate(group):
                    eng_title = translate_text(orig_title)
                    if not eng_title or eng_title == orig_title:
                        continue

                    desc_clean = orig_desc if orig_desc else ""
                    if "Original Title:" not in desc_clean:
                        updated_desc = f"{desc_clean}\n\nOriginal Title: {orig_title}".strip()
                    else:
                        updated_desc = desc_clean

                    batch_updates.append((eng_title, updated_desc, item_id))
                    success_count += 1
                    print(f"  [OK] Translated {item_id} (fallback): {orig_title} --> {eng_title}")

            # Commit batch of 50
            if len(batch_updates) >= batch_size:
                conn = sqlite3.connect(DB_PATH)
                c = conn.cursor()
                c.executemany("UPDATE models SET title = ?, description = ? WHERE id = ?", batch_updates)
                conn.commit()
                conn.close()
                batch_updates = []
                print(f"  [DB COMMIT] Saved batch of {batch_size} translations.")

            # Gentle delay to respect free API rate limits
            time.sleep(0.5)

        # Commit remaining updates
        if batch_updates:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.executemany("UPDATE models SET title = ?, description = ? WHERE id = ?", batch_updates)
            conn.commit()
            conn.close()
            print(f"  [DB COMMIT] Saved final batch of {len(batch_updates)} translations.")

    except KeyboardInterrupt:
        print("\n[WARNING] Process interrupted by user. Saving progress...")
        if batch_updates:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.executemany("UPDATE models SET title = ?, description = ? WHERE id = ?", batch_updates)
            conn.commit()
            conn.close()
        sys.exit(0)

    print("\n" + "=" * 60)
    print("TRANSLATION COMPLETE")
    print(f"  Titles Translated Successfully : {success_count}")
    print("=" * 60)

if __name__ == '__main__':
    run_translation()
