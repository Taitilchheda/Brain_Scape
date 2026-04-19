import trimesh
import os
from pathlib import Path

source_obj = r"c:\Users\taiti\OneDrive\Desktop\Brain_Scape-taitil\Brain_Scape-taitil\outputs\export\taitil-perfect-20260419\brain_hq_v2_web.obj"
dest_dir = r"c:\Users\taiti\OneDrive\Desktop\Brain_Scape-taitil\Brain_Scape-taitil\outputs\export\demo-scan-taitil"
dest_glb = os.path.join(dest_dir, "brain.glb")

os.makedirs(dest_dir, exist_ok=True)

if os.path.exists(source_obj):
    print(f"Loading {source_obj}...")
    mesh = trimesh.load(source_obj)
    print(f"Exporting to {dest_glb}...")
    mesh.export(dest_glb, file_type="glb")
    print("Export complete.")
else:
    print(f"Source OBJ not found: {source_obj}")
