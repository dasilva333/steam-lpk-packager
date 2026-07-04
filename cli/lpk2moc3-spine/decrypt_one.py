"""
One-off decryption script.
Usage:
    py decrypt_one.py <lpk_path> <config_json_path> <output_dir>
"""
import sys
import os

# Make sure Core is importable from this directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from Core.lpk_loader import LpkLoader
from Core.utils import normalize

def main():
    if len(sys.argv) < 4:
        print("Usage: py decrypt_one.py <lpk_path> <config_json_path> <output_dir>")
        sys.exit(1)

    lpk_path    = sys.argv[1]
    config_path = sys.argv[2]
    output_dir  = sys.argv[3]

    os.makedirs(output_dir, exist_ok=True)

    print(f"LPK      : {lpk_path}")
    print(f"Config   : {config_path}")
    print(f"Output   : {output_dir}")
    print("Loading & decrypting...")

    loader = LpkLoader(lpk_path, config_path)
    loader.extract(output_dir)

    print("Done! Files extracted to:", output_dir)

if __name__ == "__main__":
    main()
