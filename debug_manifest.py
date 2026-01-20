
import os
import json

basedir = os.path.abspath(os.path.dirname('app.py'))
manifest_path = os.path.join(basedir, 'frontend', 'dist', '.vite', 'manifest.json')

print(f"Manifest Path: {manifest_path}")

try:
    with open(manifest_path, 'r') as f:
        manifest = json.load(f)
        print("Manifest loaded successfully.")
        print("Keys found:", list(manifest.keys()))

        entry_point_key = 'organograma.html'
        if entry_point_key in manifest:
            print(f"Success: Key '{entry_point_key}' found.")
        else:
            print(f"Error: Key '{entry_point_key}' NOT found.")
except Exception as e:
    print(f"Error loading manifest: {e}")
