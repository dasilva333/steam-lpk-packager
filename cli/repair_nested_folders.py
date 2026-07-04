import os
import shutil

STORAGE_DIR = "E:\\lpk-studio-storage"
CACHE_DIR = os.path.join(STORAGE_DIR, "workshop_cache")

def repair_nesting():
    print("=" * 60)
    print("LPK STUDIO — REPAIR NESTED FOLDERS")
    print(f"CACHE DIR: {CACHE_DIR}")
    print("=" * 60)

    if not os.path.isdir(CACHE_DIR):
        print("Cache directory not found.")
        return

    items = [d for d in os.listdir(CACHE_DIR) if d.isdigit()]
    repaired_count = 0

    for item_id in items:
        parent_dir = os.path.join(CACHE_DIR, item_id)
        nested_dir = os.path.join(parent_dir, item_id)

        # Check if the double nested directory exists
        if os.path.isdir(nested_dir):
            print(f"Repairing double nested folder: {item_id}")
            
            # Move all contents of the nested folder up to the parent folder
            for fname in os.listdir(nested_dir):
                src_file = os.path.join(nested_dir, fname)
                dst_file = os.path.join(parent_dir, fname)
                
                # Relocate to parent
                try:
                    if os.path.exists(dst_file):
                        # Merge or resolve collision safely
                        if os.path.isdir(src_file):
                            shutil.copytree(src_file, dst_file, dirs_exist_ok=True)
                            shutil.rmtree(src_file)
                        else:
                            os.remove(dst_file)
                            shutil.move(src_file, dst_file)
                    else:
                        shutil.move(src_file, dst_file)
                except Exception as e:
                    print(f"  Failed to move {fname}: {e}")

            # Safely remove the now empty nested folder
            try:
                shutil.rmtree(nested_dir)
                repaired_count += 1
            except Exception as e:
                print(f"  Failed to delete nested folder {nested_dir}: {e}")

    print("\n" + "=" * 60)
    print(f"REPAIR SUMMARY")
    print(f"  Repaired Nested Folders: {repaired_count}")
    print("=" * 60)

if __name__ == '__main__':
    repair_nesting()
