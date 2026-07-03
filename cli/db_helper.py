import sys
import os
import json
import sqlite3

# Resolve database path relative to this script
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, 'db', 'catalog.sqlite')

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS models (
            id TEXT PRIMARY KEY,
            title TEXT,
            description TEXT,
            creator TEXT,
            thumbnail_url TEXT,
            thumbnail_local TEXT,
            file_size INTEGER,
            tags TEXT,
            subscriptions INTEGER,
            steam_type TEXT,
            fingerprinted INTEGER DEFAULT 0,
            cubism_version TEXT,
            spine_version TEXT,
            compatible INTEGER,
            compat_reason TEXT,
            packaged INTEGER DEFAULT 0,
            download_failed INTEGER DEFAULT 0,
            download_failed_reason TEXT,
            created_at INTEGER,
            updated_at INTEGER,
            indexed_at INTEGER
        )
    ''')
    
    # Check if download_failed column exists (migration helper)
    cursor.execute("PRAGMA table_info(models)")
    columns = [col[1] for col in cursor.fetchall()]
    if 'download_failed' not in columns:
        cursor.execute("ALTER TABLE models ADD COLUMN download_failed INTEGER DEFAULT 0")
    if 'download_failed_reason' not in columns:
        cursor.execute("ALTER TABLE models ADD COLUMN download_failed_reason TEXT")
        
    conn.commit()
    conn.close()
    return {"success": True, "message": "Database initialized & migrated"}

def query_catalog(params):
    conn = get_connection()
    cursor = conn.cursor()
    
    # Extract query params
    search = params.get('search', '')
    types = params.get('types', [])
    compatibilities = params.get('compatibilities', [])
    limit = int(params.get('limit', 20))
    offset = int(params.get('offset', 0))
    sort = params.get('sort', 'subscriptions')
    
    query = "SELECT * FROM models WHERE 1=1"
    args = []
    
    if search:
        query += " AND (title LIKE ? OR id = ?)"
        args.extend([f"%{search}%", search])
        
    if types:
        query += f" AND steam_type IN ({','.join(['?'] * len(types))})"
        args.extend(types)
        
    if compatibilities:
        compat_conditions = []
        for compat in compatibilities:
            if compat == 'ready':
                compat_conditions.append("compatible = 1")
            elif compat == 'incompatible':
                compat_conditions.append("compatible = 0")
            elif compat == 'unknown':
                compat_conditions.append("compatible IS NULL")
        if compat_conditions:
            query += f" AND ({' OR '.join(compat_conditions)})"
            
    # Count total matching query before pagination
    count_query = query.replace("SELECT *", "SELECT COUNT(*) as count")
    cursor.execute(count_query, args)
    total_count = cursor.fetchone()['count']
    
    # Add sorting
    if sort == 'subscriptions':
        query += " ORDER BY subscriptions DESC"
    elif sort == 'created':
        query += " ORDER BY created_at DESC"
    elif sort == 'size':
        query += " ORDER BY file_size DESC"
    else:
        query += " ORDER BY subscriptions DESC"
        
    query += " LIMIT ? OFFSET ?"
    args.extend([limit, offset])
    
    cursor.execute(query, args)
    rows = cursor.fetchall()
    
    results = []
    for row in rows:
        item = dict(row)
        if item.get('tags'):
            try:
                item['tags'] = json.loads(item['tags'])
            except:
                item['tags'] = []
        results.append(item)
        
    conn.close()
    return {"total": total_count, "items": results}

def get_stats():
    conn = get_connection()
    cursor = conn.cursor()
    
    stats = {}
    
    cursor.execute("SELECT COUNT(*) as count FROM models")
    stats['total'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM models WHERE steam_type = 'Live2D'")
    stats['live2d'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM models WHERE steam_type = 'Spine'")
    stats['spine'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM models WHERE compatible = 1")
    stats['compatible'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM models WHERE compatible = 0")
    stats['incompatible'] = cursor.fetchone()['count']
    
    cursor.execute("SELECT COUNT(*) as count FROM models WHERE compatible IS NULL")
    stats['unknown'] = cursor.fetchone()['count']
    
    conn.close()
    return stats

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "No action provided"}))
        return
        
    action = sys.argv[1]
    params = {}
    if len(sys.argv) > 2:
        try:
            params = json.loads(sys.argv[2])
        except Exception as e:
            print(json.dumps({"error": f"Invalid params JSON: {str(e)}"}))
            return
            
    try:
        if action == 'init':
            print(json.dumps(init_db()))
        elif action == 'query':
            print(json.dumps(query_catalog(params)))
        elif action == 'stats':
            print(json.dumps(get_stats()))
        else:
            print(json.dumps({"error": f"Unknown action: {action}"}))
    except Exception as e:
        print(json.dumps({"error": str(e)}))

if __name__ == '__main__':
    main()
