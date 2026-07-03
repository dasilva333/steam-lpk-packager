import subprocess
import sys
import os

def main():
    script = "main.py"
    # Ensure requirements are installed
    subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
    # Run PyInstaller
    pyinstaller_args = [
        "pyinstaller",
        "--onefile",
        "--windowed",
        "--add-data", "Core;Core",
        "--add-data", "requirements.txt;.",
        "--add-data", "motion_spec.py;.",
        "--add-data", "manager.py;.",
        "--add-data", "README.md;.",
        script
    ]
    # On Windows, use ';' as separator for --add-data, on Linux/Mac use ':'
    if os.name != "nt":
        pyinstaller_args = [arg.replace(";", ":") if "--add-data" in arg else arg for arg in pyinstaller_args]
    subprocess.run(pyinstaller_args)

if __name__ == "__main__":
    main()