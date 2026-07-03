# lpk-to-moc3

 Based on [LPKUnpacker](https://github.com/ihopenot/LpkUnpacker)

## Features

- **Live2D and Spine Extraction Modes**  
  Select between Live2D and Spine model extraction in the GUI. Spine extraction includes automatic renaming for skeleton, atlas, and texture files according to `model0.json` specifications.
  **Note:** Spine extraction is a work in progress and may not be fully stable.

- **Spine Model Support**
  - Renames `skeleton_0` to `skeleton_0.skel`
  - Renames `atlases_0_atlas_0` to `skeleton_0.atlas.txt`
  - Renames each texture file (e.g., `atlases_0_textures_0_0.png`) to the corresponding name in `tex_names` from `model0.json` (e.g., `c802_00.png`)
  - Supports multiple textures per model

- **Live2D Model Asset Organization**
  - Sets up model assets with *.moc3, *.model3.json, "sounds", and "motions" directories from .lpk file
  - Moves motion .json files to `motions/`, sound files (.wav, .ogg, .mp3) to `sounds/`, and expression files to `expressions/` folder

- **Motion and Hit Area Processing**
  - Converts .ogg audios to single-channeled .wav files using system ffmpeg
  - Recounts values of "CurveCount", "TotalPointCount", and "TotalSegmentCount" in *.motion3.json
  - Links hit areas with motion group names

- **Texture Folder Organization**
  - Moves texture files to a folder named `<character>.<resolution>` and updates texture paths in all .model3.json files

- **Drag & Drop GUI**
  - Modern GUI built with CustomTkinter and tkinterdnd2
  - Drag & drop support for LPK, config.json, and output folder selection

- **Cross-Platform Compilation**
  - Compile to Windows `.exe` or macOS `.app` using the included `compile.py` script and PyInstaller

## Usage

1. **Install requirements:**
   ```sh
   pip install -r requirements.txt

