import os
import shutil

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
THUMBNAILS_DIR = os.path.join(PROJECT_ROOT, "public", "thumbnails")
FIXED_DIR = os.path.join(THUMBNAILS_DIR, "fixed")

def apply_fixes():
    print("=" * 60)
    print("LPK STUDIO — DEPLOY FIXED THUMBNAILS TO ROOT")
    print(f"SOURCE DIR: {FIXED_DIR}")
    print(f"TARGET DIR: {THUMBNAILS_DIR}")
    print("=" * 60)

    if not os.path.isdir(FIXED_DIR):
        print("No fixed thumbnails directory found. Nothing to deploy!")
        return

    fixed_files = [f for f in os.listdir(FIXED_DIR) if f.endswith(".png")]
    print(f"Found {len(fixed_files)} fixed thumbnails ready to deploy.")

    copied_count = 0
    deleted_count = 0

    for fname in fixed_files:
        src_path = os.path.join(FIXED_DIR, fname)
        dst_path = os.path.join(THUMBNAILS_DIR, fname)

        # Overwrite original with the fixed thumbnail
        try:
            shutil.copy2(src_path, dst_path)
            copied_count += 1
            
            # Safely remove from fixed directory after deployment
            os.remove(src_path)
            deleted_count += 1
        except Exception as e:
            print(f"  [{fname}] Failed to deploy/clean: {e}")

    # Safely try to clean up empty fixed folder
    try:
        if not os.listdir(FIXED_DIR):
            os.rmdir(FIXED_DIR)
            print("  Cleaned up empty fixed/ directory.")
    except Exception as e:
        pass

    print("\n" + "=" * 60)
    print("DEPLOYMENT SUMMARY")
    print(f"  Applied (Overwritten) : {copied_count}")
    print(f"  Cleaned from fixed/   : {deleted_count}")
    print("=" * 60)

if __name__ == '__main__':
    apply_fixes()
