import os
import shutil

STORAGE_DIR = "E:\\lpk-studio-storage"
CACHE_DIR = os.path.join(STORAGE_DIR, "workshop_cache")
STAGING_DIR = os.path.join(CACHE_DIR, "steamapps", "workshop", "content", "616720")

def relocate_downloads():
    print("=" * 60)
    print("LPK STUDIO — DOWNLOAD RELOCATION & CLEANUP")
    print(f"STAGING DIR: {STAGING_DIR}")
    print(f"TARGET DIR:  {CACHE_DIR}")
    print("=" * 60)

    if not os.path.isdir(STAGING_DIR):
        print("No staged downloads found in steamapps folder. System is clean!")
        return

    staged_items = [d for d in os.listdir(STAGING_DIR) if d.isdigit()]
    print(f"Found {len(staged_items)} items staged in steamapps directory.")
    print("Relocating files to workshop_cache root...")

    moved_count = 0
    merged_count = 0

    for idx, item_id in enumerate(staged_items, 1):
        src_path = os.path.join(STAGING_DIR, item_id)
        dst_path = os.path.join(CACHE_DIR, item_id)

        # Skip empty directory structures
        if not os.listdir(src_path):
            try:
                os.rmdir(src_path)
            except:
                pass
            continue

        if not os.path.exists(dst_path):
            # Safe clean move
            try:
                shutil.move(src_path, dst_path)
                moved_count += 1
            except Exception as e:
                print(f"  [{item_id}] Failed to move: {e}")
        else:
            # Destination already exists - merge missing files safely
            try:
                for fname in os.listdir(src_path):
                    src_file = os.path.join(src_path, fname)
                    dst_file = os.path.join(dst_path, fname)
                    if not os.path.exists(dst_file):
                        shutil.move(src_file, dst_file)
                # Clean up empty source directory
                shutil.rmtree(src_path)
                merged_count += 1
            except Exception as e:
                print(f"  [{item_id}] Failed to merge: {e}")

        if idx % 500 == 0:
            print(f"  Processed {idx}/{len(staged_items)} items...")

    # Safely try to clean up empty parent steamapps folder structure
    try:
        shutil.rmtree(os.path.join(CACHE_DIR, "steamapps"))
        print("  Cleaned up empty steamapps staging directory structure.")
    except Exception as e:
        print(f"  Could not remove steamapps directory structure (likely active lock or non-empty downloads): {e}")

    print("\n" + "=" * 60)
    print("RELOCATION SUMMARY")
    print(f"  Total Inspected : {len(staged_items)}")
    print(f"  Moved Folders   : {moved_count}")
    print(f"  Merged Folders  : {merged_count}")
    print("=" * 60)

if __name__ == '__main__':
    relocate_downloads()
