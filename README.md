# Steam LPK Packager

A robust utility pipeline designed to extract `.lpk` files (Live2DViewerEX format) and package them into standardized, clean ZIP files optimized for Spine or Live2D runtimes. 

It handles both local source files and automatic bulk downloading/processing of items directly from the Steam Workshop.

---

## 🚀 Key Entry point: `process_batch2_safe.py`

`process_batch2_safe.py` is the primary orchestrator for batch processing. It automates the entire download-to-package pipeline safely and efficiently.

### Features
- **Automatic Steam CMD Downloads**: If a Steam Workshop item ID is not present in your local Steam Workshop cache folder, the script automatically triggers a download using `steamcmd`.
- **Dry-Run Rollup Reports**: Instantly query Steam Web API for a batch list of workshop items to see file sizes, tags (Live2D vs. Spine), and determine if you have sufficient disk space before starting any download.
- **Smart Deduplication**: Automatically skips items that have already been processed and successfully packaged.
- **Spine Compatibility Enforcement**: Integrates with version checks to ensure incompatible Spine versions (3.x/2.x) are purged from active folders and documented cleanly.
- **Self-Cleaning**: Deletes temporary extraction files and cache copies once processing is successful.

### Usage

#### 1. Running a Batch Processing Job
Specify a text file containing Steam Workshop links or IDs (one per line, with optional annotations like `(vip)` or `(fave)`):
```bash
python process_batch2_safe.py --batch steam-batch-5-may-30.txt
```

#### 2. Performing a Dry Run & Disk Space Pre-check
Use the `--dry-run` flag to fetch metadata from Steam Web API and print a breakdown of files, total size, and disk space diagnostics:
```bash
python process_batch2_safe.py --batch steam-batch-5-may-30.txt --dry-run
```

---

## 🛠️ Pipeline Architecture

The tool is split into three core scripts working in tandem:

### 1. `process_batch2_safe.py`
* **Role**: Pipeline orchestrator, batch parser, download manager, and post-run cleaner.
* **Outputs**: Directs temp copies, coordinates extraction, and handles logging.

### 2. `batch_extract_models.py`
* **Role**: Model extraction and structure standardization.
* **Key Tasks**:
  - Decrypts and extracts `.lpk` archives (via the local `lpk2moc3-spine` submodule).
  - Renames skeleton files to standard conventions (e.g. `skeleton_0.skel`, `model3.json`).
  - Audits and prunes missing expressions/motions references inside the model JSON configuration to prevent runtime crashes.
  - Compresses the clean, packaged result into a `.zip` inside the target output directories.

### 3. `verify_spine_versions.py`
* **Role**: Version verification for Spine animations.
* **Key Tasks**:
  - Scans `spine_packages/` for packaged `.zip` files.
  - Inspects the JSON or binary `.skel` header inside the zip to identify the Spine runtime version.
  - Retains Spine 4.x models (compatible).
  - Purges older Spine 3.x/2.x models (incompatible with the active 4.x runtime) and catalogs them in a markdown list: `spine_packages/incompatible_spine_models.md`.

---

## 📂 Directory Layout

```
steam-lpk-packager/
├── packages/              # Input directory where local LPKs or Workshop folders go
├── live2d_packages/       # Clean, packaged ZIPs for Live2D models
│   └── failing_to_render/ # Subdirectory for Live2D models with renderer issues
├── spine_packages/        # Clean, packaged ZIPs for compatible Spine 4.x models
│   └── incompatible_spine_models.md # Auto-generated catalog of incompatible models
├── lpk2moc3-spine/        # Submodule handling the core LPK format conversion
├── process_batch2_safe.py # Main entry point orchestrating the pipeline
├── batch_extract_models.py# Decryption, texture mapping, and extraction utility
└── verify_spine_versions.py # Post-extraction Spine version validator
```

---

## 📋 Prerequisites & Dependencies

Before running the pipeline, ensure the following are installed and configured:

1. **Python 3.x**
2. **SteamCMD**: Must be installed and available in your environment path for automatic downloads.
3. **FFmpeg**: Required in system PATH for audio conversion.
4. **Pillow**: Python library for texture processing.
   ```bash
   pip install Pillow
   ```

