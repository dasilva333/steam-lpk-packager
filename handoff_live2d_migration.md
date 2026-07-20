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

## 3. Speculative Pipeline: Headless `.moc` to `.moc3` Conversion

To convert the remaining **3,552 `.moc`** files to `.moc3` and generate thumbnails for them, we need a fully automated headless pipeline. 

### Step 1: `.moc` to `.cmo3` (Using Quadrism)
We can run a batch script that loops through all `.moc` files and feeds them into the Quadrism compiler to produce `.cmo3` files:
```sh
quadexec conv <input.moc> <output.cmo3>
```
*Since Quadrism handles this conversion headlessly, this step can be completely automated in a simple Node.js or Python loop.*

### Step 2: `.cmo3` to `.moc3` (The Headless Challenge)
Live2D Cubism Editor is a GUI-based desktop application and does not natively support headless CLI exports of `.moc3` files. To automate this step, we can speculate on two paths:

1. **GUI Automation Scripting (VBScript / AutoIt / RobotJS / PyAutoGUI):**
   * Write a lightweight macro runner on the Windows machine.
   * For each `.cmo3` generated in Step 1:
     1. Open Live2D Cubism Editor with the `.cmo3` file as an argument: `CubismEditor.exe "path/to/model.cmo3"`.
     2. Send keystrokes to trigger the export menu: `Alt + F` (File) -> `E` (Export Embedded) -> `M` (Export as moc3).
     3. Automate clicking "OK" on the export settings and confirmation dialogs.
     4. Close the editor window.
   * *Tradeoff:* Requires a logged-in active Windows GUI session (cannot run in a true ssh-only background environment).

2. **Automated Live2D Editor Plugin (Java/Cubism SDK):**
   * Live2D Cubism Editor is built on Java. It may be possible to write a custom Editor plugin/extension that listens for a folder directory or runs on startup to load, export, and close files sequentially.

Once the `.moc3` files are exported using either method, they can be fed directly into our `batch_render.js` script to generate the final thumbnails.
