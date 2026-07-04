#!/usr/bin/env python3
"""
regenerate_thumbnails.py — Full LPK thumbnail regeneration pipeline.

Steps for each workshop item in the storage directory:
  1. Find <workshop_id>.png thumbnail
  2. Detect if it's a bad auto-generated thumbnail (white + grayscale)
  3. Find or trigger decryption of the model0.json
  4. Invoke render_single.js (Node/Puppeteer) to render a proper thumbnail
  5. Replace the original <workshop_id>.png with the rendered output

Usage:
    # Scan all items, detect + regenerate bad thumbnails
    py regenerate_thumbnails.py

    # Process a single specific workshop ID
    py regenerate_thumbnails.py --workshop-id 3709978268

    # Dry run: only detect, don't render
    py regenerate_thumbnails.py --dry-run

    # Verbose output
    py regenerate_thumbnails.py --verbose

Environment (reads from .env in project root):
    STORAGE_DIR   — base directory of workshop_cache (e.g. E:\lpk-studio-storage)
"""

import argparse
import glob
import json
import os
import subprocess
import sys
import time

# ─── Path resolution ─────────────────────────────────────────────────────────

SCRIPT_DIR   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(SCRIPT_DIR)  # steam-lpk-packager/

RENDERER_JS  = os.path.join(PROJECT_ROOT, "modules", "live2d-renderer", "render_single.js")
DECRYPT_PY   = os.path.join(SCRIPT_DIR, "lpk2moc3-spine", "decrypt_one.py")
DETECT_PY    = os.path.join(SCRIPT_DIR, "detect_thumbnail.py")


def load_env() -> dict:
    """Load key=value pairs from the project's .env file."""
    env = {}
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env[k.strip()] = v.strip()
    return env


ENV = load_env()
STORAGE_DIR   = ENV.get("STORAGE_DIR", r"E:\lpk-studio-storage")
WORKSHOP_CACHE = os.path.join(STORAGE_DIR, "workshop_cache")

def get_connection():
    db_path = os.path.join(PROJECT_ROOT, 'db', 'catalog.sqlite')
    import sqlite3
    conn = sqlite3.connect(db_path)
    return conn


# ─── Detection ───────────────────────────────────────────────────────────────

def is_bad_thumbnail(png_path: str, verbose: bool = False) -> bool:
    """Returns True if the thumbnail is the auto-generated bad one."""
    result = subprocess.run(
         [sys.executable, DETECT_PY, png_path],
         capture_output=True, text=True
    )
    verdict = result.stdout.strip()
    if verbose:
        safe_base = os.path.basename(png_path).encode('ascii', errors='replace').decode('ascii')
        print(f"    [detect] {verdict}  <- {safe_base}")
        if result.stderr.strip():
            safe_err = result.stderr.strip().encode('ascii', errors='replace').decode('ascii')
            print(f"    [detect stderr] {safe_err}")
    return verdict == "BAD"


# ─── Decryption ──────────────────────────────────────────────────────────────

def find_decrypted_model(workshop_dir: str) -> str | None:
    """
    Looks for model0.json in the decrypted/ subfolder.
    Returns the path if found, else None.
    """
    decrypted_base = os.path.join(workshop_dir, "decrypted")
    if not os.path.isdir(decrypted_base):
        return None

    # Model lands in decrypted/<character_name>/model0.json
    for sub in os.listdir(decrypted_base):
        candidate = os.path.join(decrypted_base, sub, "model0.json")
        if os.path.isfile(candidate):
            return candidate
    return None


def decrypt_lpk(workshop_dir: str, verbose: bool = False) -> str | None:
    """
    Finds the .lpk + config.json in workshop_dir and decrypts into decrypted/ subfolder.
    Returns path to model0.json on success, None on failure.
    """
    lpk_files = glob.glob(os.path.join(workshop_dir, "*.lpk"))
    config_path = os.path.join(workshop_dir, "config.json")

    if not lpk_files:
        print(f"    [decrypt] No .lpk file found in {workshop_dir}")
        return None
    if not os.path.isfile(config_path):
        print(f"    [decrypt] No config.json found in {workshop_dir}")
        return None

    lpk_path    = lpk_files[0]
    output_dir  = os.path.join(workshop_dir, "decrypted")

    safe_lpk = os.path.basename(lpk_path).encode('ascii', errors='replace').decode('ascii')
    print(f"    [decrypt] Decrypting {safe_lpk}...")
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"

    result = subprocess.run(
        [sys.executable, DECRYPT_PY, lpk_path, config_path, output_dir],
        capture_output=True, text=True, env=env
    )
    if result.returncode != 0:
        print(f"    [decrypt] FAILED (code {result.returncode})")
        if verbose:
            safe_err = result.stderr.strip().encode('ascii', errors='replace').decode('ascii')
            print(f"    {safe_err}")
        return None

    if verbose:
        safe_out = output_dir.encode('ascii', errors='replace').decode('ascii')
        print(f"    [decrypt] OK -> {safe_out}")

    return find_decrypted_model(workshop_dir)


# ─── Rendering ───────────────────────────────────────────────────────────────

def render_thumbnail(model_json_path: str, output_png_path: str, verbose: bool = False) -> bool:
    """
    Calls render_single.js via Node to render a Live2D thumbnail.
    Returns True on success.
    """
    if not os.path.isfile(RENDERER_JS):
        print(f"    [render] render_single.js not found: {RENDERER_JS}")
        return False

    print(f"    [render] Rendering {os.path.basename(model_json_path)}...")
    start = time.time()

    result = subprocess.run(
        ["node", RENDERER_JS, model_json_path, output_png_path],
        capture_output=not verbose,
        text=True,
        cwd=os.path.dirname(RENDERER_JS),
    )

    elapsed = time.time() - start

    if result.returncode != 0:
        print(f"    [render] FAILED (code {result.returncode}) after {elapsed:.1f}s")
        if not verbose and result.stderr:
            print(f"    [render] stderr: {result.stderr.strip()[-500:]}")
        return False

    if os.path.isfile(output_png_path):
        size_kb = os.path.getsize(output_png_path) / 1024
        print(f"    [render] [OK] Done in {elapsed:.1f}s - {size_kb:.0f} KB -> {output_png_path}")
        return True
    else:
        print(f"    [render] FAILED - output PNG not created after {elapsed:.1f}s")
        return False


# ─── Per-item pipeline ───────────────────────────────────────────────────────

def process_item(workshop_id: str, dry_run: bool = False, verbose: bool = False, progress_prefix: str = "") -> str:
    """
    Processes a single workshop ID by reading the thumbnail from public/thumbnails/<workshop_id>.png.
    Returns: 'ok', 'skipped', 'no_thumbnail', 'no_model', 'render_failed'
    """
    import time
    start_time = time.perf_counter()

    prefix = f"{progress_prefix} " if progress_prefix else ""

    thumbnail_path = os.path.join(PROJECT_ROOT, "public", "thumbnails", f"{workshop_id}.png")
    if not os.path.isfile(thumbnail_path):
        elapsed = (time.perf_counter() - start_time) * 1000.0
        print(f"  {prefix}[?] [{workshop_id}] No PNG thumbnail found in public/thumbnails/ - {elapsed:.0f}ms")
        return "no_thumbnail"

    # Detection
    if not is_bad_thumbnail(thumbnail_path, verbose=verbose):
        elapsed = (time.perf_counter() - start_time) * 1000.0
        print(f"  {prefix}[OK] [{workshop_id}] Thumbnail looks good - {elapsed:.0f}ms")
        return "skipped"

    # Copy the detected "bad" thumbnail to public/thumbnails/bad_detected/ for review
    bad_detected_dir = os.path.join(PROJECT_ROOT, "public", "thumbnails", "bad_detected")
    os.makedirs(bad_detected_dir, exist_ok=True)
    import shutil
    shutil.copy2(thumbnail_path, os.path.join(bad_detected_dir, f"{workshop_id}.png"))

    if dry_run:
        elapsed = (time.perf_counter() - start_time) * 1000.0
        print(f"  {prefix}[X] [{workshop_id}] BAD thumbnail (Dry Run) - {elapsed:.0f}ms")
        return "ok"

    # Find or create decrypted model in workshop_cache
    workshop_dir = os.path.join(WORKSHOP_CACHE, workshop_id)
    if not os.path.isdir(workshop_dir):
        elapsed = (time.perf_counter() - start_time) * 1000.0
        print(f"  {prefix}[!] [{workshop_id}] ERROR: Workshop folder missing in cache - {elapsed:.0f}ms")
        return "no_model"

    model_json = find_decrypted_model(workshop_dir)
    if not model_json:
        model_json = decrypt_lpk(workshop_dir, verbose=verbose)

    if not model_json:
        elapsed = (time.perf_counter() - start_time) * 1000.0
        print(f"  {prefix}[!] [{workshop_id}] ERROR: Could not find/decrypt model - {elapsed:.0f}ms")
        return "no_model"

    # Determine the public review folder target
    fixed_dir = os.path.join(PROJECT_ROOT, "public", "thumbnails", "fixed")
    os.makedirs(fixed_dir, exist_ok=True)
    target_output = os.path.join(fixed_dir, f"{workshop_id}.png")

    # Render directly to public/thumbnails/fixed/<workshop_id>.png
    success = render_thumbnail(model_json, target_output, verbose=verbose)

    if not success:
        if os.path.exists(target_output):
            os.remove(target_output)
        elapsed = (time.perf_counter() - start_time) * 1000.0
        print(f"  {prefix}[!] [{workshop_id}] ERROR: Rendering failed - {elapsed:.0f}ms")
        return "render_failed"

    elapsed_sec = time.perf_counter() - start_time
    print(f"  {prefix}[+] [{workshop_id}] Processed and recovered bad thumbnail - {elapsed_sec:.1f}s")
    return "ok"


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="LPK Studio — Thumbnail Regeneration Pipeline")
    parser.add_argument("--workshop-id", help="Process a single specific workshop ID only")
    parser.add_argument("--dry-run", action="store_true", help="Detect only, do not render or replace")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")
    args = parser.parse_args()

    thumbnails_dir = os.path.join(PROJECT_ROOT, "public", "thumbnails")
    if not os.path.isdir(thumbnails_dir):
        print(f"[Error] public/thumbnails not found: {thumbnails_dir}")
        sys.exit(1)

    # 1. Fetch already-checked items from SQLite
    checked_ids = set()
    if not args.workshop_id:
        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM models WHERE thumbnail_checked = 1")
            checked_ids = {row[0] for row in cursor.fetchall()}
            conn.close()
            print(f"Loaded {len(checked_ids)} already-checked thumbnails from SQLite cache.")
        except Exception as e:
            print(f"[WARNING] Failed to load checked cache from SQLite: {e}")

    # Curate IDs to process
    if args.workshop_id:
        ids = [args.workshop_id]
    else:
        # Find all files directly in public/thumbnails and parse their filenames
        all_ids = sorted([
            os.path.splitext(f)[0] for f in os.listdir(thumbnails_dir)
            if f.endswith(".png") and os.path.isfile(os.path.join(thumbnails_dir, f))
        ])
        # Filter out already checked items
        ids = [wid for wid in all_ids if wid not in checked_ids]

    print("=" * 60)
    print(f"LPK STUDIO — THUMBNAIL REGENERATION PIPELINE (CURATED SET)")
    if args.dry_run:
        print("MODE: DRY RUN (no files will be modified)")
    print(f"THUMBNAILS SOURCE: {thumbnails_dir}")
    print(f"ITEMS TO PROCESS:  {len(ids)}")
    print("=" * 60)

    counts = {"ok": 0, "skipped": 0, "no_thumbnail": 0, "no_model": 0, "render_failed": 0}

    # Batch queues for SQLite commits
    batch_checked = []       # [(id,)]
    batch_regenerated = []   # [(id,)]
    BATCH_LIMIT = 100

    def commit_batches():
        if args.dry_run:
            return
        if not batch_checked and not batch_regenerated:
            return
        try:
            conn = get_connection()
            cursor = conn.cursor()
            if batch_checked:
                cursor.executemany("UPDATE models SET thumbnail_checked = 1 WHERE id = ?", batch_checked)
            if batch_regenerated:
                cursor.executemany("UPDATE models SET thumbnail_checked = 1, thumbnail_regenerated = 1 WHERE id = ?", batch_regenerated)
            conn.commit()
            conn.close()
            batch_checked.clear()
            batch_regenerated.clear()
        except Exception as e:
            print(f"\n  [WARNING] Failed to commit batch update to SQLite database: {e}")

    for i, wid in enumerate(ids, 1):
        progress_prefix = f"[{i}/{len(ids)}]"
        status = process_item(wid, dry_run=args.dry_run, verbose=args.verbose, progress_prefix=progress_prefix)
        counts[status] = counts.get(status, 0) + 1

        # Stage updates based on status
        if status == "skipped":
            batch_checked.append((wid,))
        elif status == "ok":
            batch_regenerated.append((wid,))

        # Commit every 100 items to SQLite
        if i % BATCH_LIMIT == 0:
            commit_batches()

    # Final batch flush
    commit_batches()

    print("\n" + "=" * 60)
    print("PIPELINE COMPLETE — Summary")
    print(f"  [OK] Regenerated    : {counts['ok']}")
    print(f"  [-]  Skipped (good) : {counts['skipped']}")
    print(f"  [?]  No thumbnail   : {counts['no_thumbnail']}")
    print(f"  [!]  No model       : {counts['no_model']}")
    print(f"  [X]  Render failed  : {counts['render_failed']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
