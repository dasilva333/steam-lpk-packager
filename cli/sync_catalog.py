import sys
import os
import json
import time
import urllib.parse
import urllib.request
import sqlite3

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')

# Load API key from .env file
def get_api_key():
    env_path = os.path.join(BASE_DIR, '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                if line.startswith('STEAM_API_KEY='):
                    return line.strip().split('=', 1)[1]
    return None

def fetch_page(api_key, cursor="*"):
    url = "https://api.steampowered.com/IPublishedFileService/QueryFiles/v1/"
    params = {
        "key": api_key,
        "appid": "616720",
        "query_type": "0", # Most Recent (ranked by publication date)
        "numperpage": "100",
        "cursor": cursor,
        "return_details": "1",
        "return_tags": "1",
        "return_vote_data": "1",
        "return_previews": "1"
    }
    encoded = urllib.parse.urlencode(params)
    full_url = f"{url}?{encoded}"
    req = urllib.request.Request(full_url, method='GET')
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
            return data.get("response", {})
    except Exception as e:
        print(f"Error querying Steam API: {str(e)}", file=sys.stderr)
        return None

def sync():
    api_key = get_api_key()
    if not api_key:
        print(json.dumps({"error": "No STEAM_API_KEY found in .env"}))
        return

    print("Starting sync with Steam Workshop...")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM models")
    existing_ids = {row[0] for row in cursor.fetchall()}

    next_cursor = "*"
    page_count = 0
    added_count = 0
    updated_count = 0

    caught_up = False
    while next_cursor and not caught_up:
        print(f"Fetching page {page_count + 1}...")
        response = fetch_page(api_key, next_cursor)
        if not response:
            break

        published_files = response.get("publishedfiledetails", [])
        if not published_files:
            break

        for item in published_files:
            item_id = item.get("publishedfileid")
            if not item_id:
                continue

            # Parse tags
            tags = [t.get("tag", "") for t in item.get("tags", [])]
            steam_type = "Other"
            if "Live2D" in tags:
                steam_type = "Live2D"
            elif "Spine" in tags:
                steam_type = "Spine"

            # Parse statistics
            votes = item.get("vote_data", {})
            subscriptions = votes.get("votes_up", 0) # Fallback to votes_up as relative subscription rating indicator

            title = item.get("title", f"ID: {item_id}")
            description = item.get("description", "")
            creator = item.get("owner", "")
            thumbnail_url = item.get("preview_url", "")
            file_size = int(item.get("file_size", 0))
            created_at = int(item.get("time_created", 0))
            updated_at = int(item.get("time_updated", 0))
            indexed_at = int(time.time())

            tags_json = json.dumps(tags)

            if item_id in existing_ids:
                print(f"Reached existing item {item_id} (title: '{title}'). Database is up to date!")
                caught_up = True
                break
            else:
                # Insert new records
                cursor.execute('''
                    INSERT INTO models (
                        id, title, description, creator, thumbnail_url, file_size,
                        tags, subscriptions, steam_type, created_at, updated_at, indexed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (item_id, title, description, creator, thumbnail_url, file_size,
                      tags_json, subscriptions, steam_type, created_at, updated_at, indexed_at))
                added_count += 1
                existing_ids.add(item_id)

        conn.commit()
        page_count += 1
        
        # Steam API provides next_cursor for pagination. If it is empty or matches previous, we are done
        prev_cursor = next_cursor
        next_cursor = response.get("next_cursor", "")
        if next_cursor == prev_cursor or not next_cursor:
            break

        # Yield control to prevent rate limit
        time.sleep(0.5)

    conn.close()
    print(f"Sync complete! Pages fetched: {page_count}. Added: {added_count}. Updated: {updated_count}.")

if __name__ == '__main__':
    sync()
