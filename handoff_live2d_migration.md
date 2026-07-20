# Handoff: Live2D Migration & Thumbnail Batch Pipeline

This document summarizes the recent work on the Live2D asset ingestion workflow and outlines next steps for batch conversion and rendering.

---

## 1. Summary of Completed Work

### Directory Initialization & Setup
* Created a dedicated model workspace folder at `personal_airi/himouto_umaru` on the macOS host.
* Copied and extracted two Live2D asset packages from the studio volume:
  1. `live2d_3748142873.zip` (Model 873)
  2. `live2d_2173041194.zip` (Model 1194)
* Identified that both packages contained older **`.moc`** (Cubism 2.x) files instead of newer **`.moc3`** (Cubism 3/4) files.

### Quadrism Project Tracking
* A new version of the **Quadrism** toolchain (remote: `https://codeberg.org/Podimium/Quadrism`) has been cloned locally into `personal_airi/Quadrism_July16`.
* Checked out the new July 16 codebase (rewritten/squashed history), which had **147 files changed (+34,231 lines / -12,345 lines)** since the July 15 commit (`4f35df9`).
* Compiled the new code and resolved runtime library loading issues on macOS by executing the dynamically linked binary `./target/debug/quadexec` directly.
* Ran both `.moc` files through the new Quadrism compiler (`conv` command) to produce highly optimized `.cmo3` editor archives (reducing the output size from ~6.8MB to ~2.6MB for model 1194, and from ~4.5MB to ~2.0MB for model 873).
* Re-packaged the finalized `.moc3` exports with all their original motion assets and audio (`.wav`) files back into a clean package zip: [live2d_2173041194_moc3.zip](file:///Users/richardpinedo/Projects.nosync/airi/personal_airi/himouto_umaru/live2d_2173041194_moc3.zip).

### Batch Thumbnail Rendering (Windows Machine)
* Cloned the massive `Eikanya/Live2d-model` repository (approx. **15.5 GB**, containing **1,376 `.moc3`** and **3,552 `.moc`** files) to `E:\Live2d-model` on the Windows host (`10.0.0.91`).
* Created and deployed a parallelized batch script `batch_render.js` under `modules/live2d-renderer/`.
* The script successfully spun up a single Puppeteer instance and executed **4 concurrent rendering workers/tabs** across the database.
* **Result:** Successfully generated **1,156 high-fidelity transparent PNG thumbnails** (1024x1024) at `E:\Live2d-model-thumbnails` alongside a `manifest.json` mapping each thumbnail back to its relative source path.

---

## 2. Outstanding Rendering Challenges

While 1,156 thumbnails were rendered successfully, **232 models failed**. The primary reasons for failure were:
1. **Texture Loading Errors:** Mismatched texture directory names (e.g. model looking for `1024` but folder is named `2048`) or missing texture assets in the source repository.
2. **Path Encoding Failures:** Unicode/UTF-8 character parsing bugs when resolving relative URLs on Windows for directories containing special characters or Asian glyphs.
3. **Puppeteer Execution Drops:** Occasional browser protocol context disconnects during rapid WebGL rendering.

---

## 3. Automated `.moc` to `.moc3` Conversion Pipeline

To convert the remaining **3,552 `.moc`** files to `.moc3` and generate thumbnails for them, we will use a hybrid automated workflow:

### Step 1: Headless `.moc` to `.cmo3` (Using Quadrism)
Run a batch script that loops through all `.moc` files and feeds them into the Quadrism compiler to produce `.cmo3` files:
```sh
quadexec conv <input.moc> <output.cmo3>
```

### Step 2: GUI Automation / Auto-Clicker Workflow
Since Live2D Cubism Editor has no headless CLI exporter for `.moc3` files, we will use an auto-clicker script (VBScript, AutoIt, RobotJS, or PyAutoGUI) to drive the Live2D GUI:

1. **File > Open:** Open the compiled `.cmo3` model file.
2. **Modeling > Convert Model IDs:** Run this function to convert legacy Cubism 2.x parameter IDs into the modern Cubism 3/4 standard.
3. **Motion Export Setup:** Incorporate steps to export/translate the original motions into `.motion3.json` files.
4. **File > Export Runtime > Export as moc3:**
   * Select **SDK3.0/Cubism3.0(3.2)** or **SDK4.0/Cubism4.0(4.2)** or **SDK5.0/Cubism5.0** from the dropdown menu depending on target capabilities.
   * Click **OK** to export the model files.
5. **Re-populate Manifest & Package:** Extract/move the newly exported `.moc3` and `.motion3.json` files, and resolve their paths inside the model's `manifest.json` or `model3.json`.
