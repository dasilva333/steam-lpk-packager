import argparse
import json
import os
import re
import shutil
import subprocess
import time
import urllib.parse
import urllib.request

# Detect if running in steam-lpk-packager repo or personal_airi
current_dir = os.path.dirname(os.path.abspath(__file__))
if "steam-lpk-packager" in current_dir:
    BASE_DIR = current_dir
    LPK_DIR = os.path.join(BASE_DIR, "packages")
    LIVE2D_DIR = os.path.join(BASE_DIR, "live2d_packages")
    SPINE_DIR = os.path.join(BASE_DIR, "spine_packages")
else:
    BASE_DIR = "/Users/richardpinedo/Documents/Projects/airi/personal_airi"
    LPK_DIR = os.path.join(BASE_DIR, "packages_lpk")
    LIVE2D_DIR = os.path.join(BASE_DIR, "packages_live2d")
    SPINE_DIR = os.path.join(BASE_DIR, "packages_spine")

# Resolve Steam content directory dynamically (cross-platform relative folder fallback)
if os.name == 'nt':
    STEAM_CONTENT_DIR = r"C:\Program Files (x86)\Steam\steamapps\workshop\content\616720"
else:
    home = os.path.expanduser("~")
    STEAM_CONTENT_DIR = os.path.join(home, "Library/Application Support/Steam/steamapps/workshop/content/616720")
INCOMPATIBLE_LOG = os.path.join(SPINE_DIR, "incompatible_spine_models.md")


def load_batch_ids(batch_file_path):
    """Parses Workshop IDs and annotations from a batch text file."""
    if not os.path.exists(batch_file_path):
        print(f"❌ Batch file not found: {batch_file_path}")
        return []
    
    items = []
    seen = set()
    with open(batch_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            
            # Match any 9-11 digit numbers in the details links
            match = re.search(r'\?id=(\d+)', line)
            item_id = None
            if match:
                item_id = match.group(1)
            elif line.isdigit():
                item_id = line
                
            if item_id:
                if item_id not in seen:
                    seen.add(item_id)
                    # Detect annotations like (vip) or (fave) in the same line
                    annotation = ""
                    if "(vip)" in line.lower():
                        annotation = "VIP"
                    elif "(fave)" in line.lower():
                        annotation = "FAVORITE"
                    items.append({
                        "id": item_id,
                        "annotation": annotation
                    })
    return items


def is_processed(item_id):
    """Determines if the workshop item has already been successfully processed or verified."""
    # 1. Check if Live2D package exists
    if os.path.exists(os.path.join(LIVE2D_DIR, f"live2d_{item_id}.zip")):
        return True, "Live2D ZIP exists"
        
    # 2. Check if Live2D failing to render exists
    if os.path.exists(os.path.join(LIVE2D_DIR, "failing_to_render", f"live2d_{item_id}.zip")):
        return True, "Live2D Failing ZIP exists"
        
    # 3. Check if Spine package exists
    if os.path.exists(os.path.join(SPINE_DIR, f"spine_{item_id}.zip")):
        return True, "Spine ZIP exists"
        
    # 4. Check if cataloged as incompatible
    if os.path.exists(INCOMPATIBLE_LOG):
        with open(INCOMPATIBLE_LOG, 'r', encoding='utf-8') as f:
            log_content = f.read()
            if f"spine_{item_id}" in log_content:
                return True, "Incompatible Spine (Cataloged)"
                
    return False, "Not processed"

def run_command(cmd, cwd=BASE_DIR):
    """Helper to run a shell command and return stdout/stderr."""
    print(f"  🏃 Running: {cmd} inside {os.path.basename(cwd)}")
    result = subprocess.run(cmd, shell=True, cwd=cwd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr

def process_item(item_id):
    """Processes a single item: copy, extract, check, cleanup."""
    src_dir = os.path.join(STEAM_CONTENT_DIR, item_id)
    dest_dir = os.path.join(LPK_DIR, item_id)
    
    if not os.path.exists(src_dir):
        print(f"📡 [DOWNLOAD] Source folder not found in Steam cache: {src_dir}")
        print(f"   Initiating automatic download of Workshop Item {item_id} via SteamCMD...")
        code, stdout, stderr = run_command(f"steamcmd +login anonymous +workshop_download_item 616720 {item_id} +quit")
        if code == 0 and os.path.exists(src_dir):
            print(f"   ✅ [DOWNLOAD SUCCESS] Successfully downloaded {item_id} via SteamCMD!")
        else:
            print(f"   ❌ [DOWNLOAD ERROR] Failed to download {item_id}. Exit code: {code}")
            return False
        
    # Make sure packages_lpk exists
    os.makedirs(LPK_DIR, exist_ok=True)
    
    # 1. Clean up any existing temp lpk folder
    if os.path.exists(dest_dir):
        print(f"  🧹 Cleaning up pre-existing directory: {dest_dir}")
        shutil.rmtree(dest_dir)
        
    # 2. Copy the item to packages_lpk
    print(f"  📂 Copying {item_id} from Steam cache to packages_lpk...")
    start_time = time.time()
    try:
        shutil.copytree(src_dir, dest_dir)
        elapsed = time.time() - start_time
        print(f"  ✅ Copy completed in {elapsed:.2f}s.")
    except Exception as e:
        print(f"  ❌ Failed to copy folder: {e}")
        return False
        
    # 3. Run the extractor script
    print("  ⚙️ Extracting model via batch_extract_models.py...")
    code, stdout, stderr = run_command("python3 batch_extract_models.py")
    if code != 0:
        print(f"  ⚠️ Warning: batch_extract_models returned code {code}")
        print(f"  STDOUT: {stdout}")
        print(f"  STDERR: {stderr}")
        
    # 4. Run the Spine version verification script
    print("  🛡️ Verifying Spine versions and cataloging/pruning if incompatible...")
    code, stdout, stderr = run_command("python3 verify_spine_versions.py")
    if code != 0:
        print(f"  ⚠️ Warning: verify_spine_versions returned code {code}")
        print(f"  STDOUT: {stdout}")
        
    # 5. Manual cleanup of packages_lpk folder (since verify_spine_versions only cleans Spine folders)
    if os.path.exists(dest_dir):
        print(f"  🧹 Cleaning up temporary packages_lpk folder for {item_id}...")
        try:
            shutil.rmtree(dest_dir)
            print("  ✅ Temp folder deleted.")
        except Exception as e:
            print(f"  ❌ Failed to delete temp folder: {e}")
            
    # 6. Verify result
    processed, reason = is_processed(item_id)
    if processed:
        print(f"🎉 [SUCCESS] Finished processing {item_id}. Outcome: {reason}.")
        return True
    else:
        print(f"⚠️ [WARNING] Completed run for {item_id} but could not find a clear output package.")
        return False

def query_steam_metadata(ids):
    """Queries Steam Web API for the metadata of a list of published file IDs."""
    if not ids:
        return []
    
    url = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
    data = {
        "itemcount": len(ids),
    }
    for i, item_id in enumerate(ids):
        data[f"publishedfileids[{i}]"] = item_id
        
    encoded_data = urllib.parse.urlencode(data).encode('utf-8')
    req = urllib.request.Request(url, data=encoded_data, method='POST')
    
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
            return res.get("response", {}).get("publishedfiledetails", [])
    except Exception as e:
        print(f"❌ Error querying Steam API: {e}")
        return []

def run_dry_run(batch_file_path):
    """Performs a dry run: loads batch details, queries Steam API, and outputs a rollup report."""
    print("=" * 66)
    print("🔍 PERFORMING DRY RUN PEEK & ROLLUP REPORT 🔍")
    print("=" * 66)
    
    items = load_batch_ids(batch_file_path)
    if not items:
        print("❌ No items found to query.")
        return
    
    ids = [item["id"] for item in items]
    annotations = {item["id"]: item["annotation"] for item in items}
    
    print(f"📡 Querying Steam Web API for {len(ids)} items...")
    details = query_steam_metadata(ids)
    if not details:
        print("❌ Failed to retrieve metadata from Steam.")
        return
    
    # Analyze and group
    total_bytes = 0
    live2d_count = 0
    spine_count = 0
    other_count = 0
    
    processed_items = []
    largest_item = None
    
    for item in details:
        item_id = item.get("publishedfileid", "")
        title = item.get("title", f"ID: {item_id}")
        size = int(item.get("file_size", 0))
        total_bytes += size
        
        tags = [t.get("tag", "") for t in item.get("tags", [])]
        
        # Classification
        classification = "Other"
        if "Live2D" in tags:
            classification = "Live2D"
            live2d_count += 1
        elif "Spine" in tags:
            classification = "Spine"
            spine_count += 1
        else:
            other_count += 1
            
        anno = annotations.get(item_id, "")
        
        processed_items.append({
            "id": item_id,
            "title": title,
            "size": size,
            "type": classification,
            "annotation": anno
        })
        
        if largest_item is None or size > largest_item["size"]:
            largest_item = {
                "title": title,
                "size": size,
                "id": item_id
            }
            
    # Sort items by size (descending) for the report list
    processed_items.sort(key=lambda x: x["size"], reverse=True)
    
    print("\n" + "=" * 70)
    print(f"📊  STEAM WORKSHOP BATCH SUMMARY: {os.path.basename(batch_file_path)}")
    print("=" * 70)
    
    # General stats
    total_mb = total_bytes / (1024 * 1024)
    total_gb = total_bytes / (1024 * 1024 * 1024)
    
    print(f"📂  Total Workshop Items : {len(processed_items)}")
    if total_gb >= 1.0:
        print(f"💾  Total Download Size  : {total_gb:.2f} GB ({total_mb:,.1f} MB)")
    else:
        print(f"💾  Total Download Size  : {total_mb:.2f} MB")
        
    print(f"🎭  Live2D Models        : {live2d_count}")
    print(f"💀  Spine Models         : {spine_count}")
    print(f"❓  Other / Unclassified : {other_count}")
    
    # Disk space checking
    try:
        total_disk, used_disk, free_disk = shutil.disk_usage("/")
        free_gb = free_disk / (1024 * 1024 * 1024)
        print(f"🖥️   Available Disk Space : {free_gb:.2f} GB")
        if free_disk < total_bytes:
            print("❌  [CRITICAL WARNING] You do NOT have enough free disk space to download this batch!")
        elif free_disk < (total_bytes * 2):
            print("⚠️   [WARNING] Disk space is tight! Download will fit, but buffer is less than 2x total size.")
        else:
            print("✅  [STATUS] Safe to Download! You have plenty of free storage space.")
    except Exception:
        pass
        
    if largest_item:
        l_mb = largest_item["size"] / (1024 * 1024)
        print(f"🐘  Largest Model        : '{largest_item['title']}' ({l_mb:.1f} MB) [ID: {largest_item['id']}]")
        
    print("-" * 70)
    print(f"{'TYPE':<8} | {'SIZE':<10} | {'WORKSHOP ID':<12} | {'ITEM TITLE':<25}")
    print("-" * 70)
    for idx, item in enumerate(processed_items, 1):
        sz_mb = item["size"] / (1024 * 1024)
        size_str = f"{sz_mb:.2f} MB"
        
        # Format title to keep report clean
        title_disp = item["title"]
        if len(title_disp) > 28:
            title_disp = title_disp[:25] + "..."
            
        type_str = item["type"]
        if item["annotation"]:
            type_str = f"{type_str} ({item['annotation']})"
            
        print(f"{type_str:<8} | {size_str:<10} | {item['id']:<12} | {title_disp:<25}")
        
    print("=" * 70)

def main():
    parser = argparse.ArgumentParser(description="AIRI Safe Batch Processing Pipeline")
    parser.add_argument("--batch", type=str, default="steam-batch-2-may-17.txt", 
                        help="The batch text file to parse IDs from.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Query the Steam Web API for file metadata and output a rollup report without downloading/extracting.")
    args = parser.parse_args()
    
    batch_file = args.batch
    if not os.path.isabs(batch_file):
        batch_file = os.path.join(BASE_DIR, batch_file)
        
    if args.dry_run:
        run_dry_run(batch_file)
        return
        
    print("=" * 60)
    print(f"🌟 AIRI SAFE BATCH PROCESSING PIPELINE: {os.path.basename(batch_file)} 🌟")
    print("=" * 60)
    
    items = load_batch_ids(batch_file)
    ids = [item["id"] for item in items]
    print(f"Found {len(ids)} unique Workshop IDs in batch file.")
    
    to_process = []
    for fid in ids:
        processed, reason = is_processed(fid)
        if processed:
            print(f"⏭️  Skipping {fid:12} | Reason: {reason}")
        else:
            to_process.append(fid)
            
    print("-" * 60)
    print(f"Total models to process in this run: {len(to_process)}")
    print("-" * 60)
    
    if not to_process:
        print(f"🎉 All models in {os.path.basename(batch_file)} are already fully processed!")
        return
        
    for index, fid in enumerate(to_process, 1):
        print(f"\n[{index}/{len(to_process)}] 🚀 STARTING ITEM {fid}")
        print("-" * 40)
        success = process_item(fid)
        print("-" * 40)
        if not success:
            print(f"⚠️ Item {fid} encountered issues, continuing with next...")
            
    print("\n" + "=" * 60)
    print(f"✨ ALL {os.path.basename(batch_file)} MODELS PROCESSED AND CLEANED! ✨")
    print("=" * 60)

if __name__ == "__main__":
    main()
