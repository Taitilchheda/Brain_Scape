import nibabel as nib
import numpy as np
import trimesh
import os

left_gii = r"C:\Users\taiti\OneDrive\Desktop\Brain_Scape-taitil\Brain_Scape-taitil\.venv\Lib\site-packages\nilearn\datasets\data\fsaverage5\pial_left.gii.gz"
right_gii = r"C:\Users\taiti\OneDrive\Desktop\Brain_Scape-taitil\Brain_Scape-taitil\.venv\Lib\site-packages\nilearn\datasets\data\fsaverage5\pial_right.gii.gz"
export_dir = r"c:\Users\taiti\OneDrive\Desktop\Brain_Scape-taitil\Brain_Scape-taitil\outputs\export\taitil-perfect-20260419"
demo_dir = r"c:\Users\taiti\OneDrive\Desktop\Brain_Scape-taitil\Brain_Scape-taitil\outputs\demo_mesh\taitil-perfect-20260419"

os.makedirs(export_dir, exist_ok=True)
os.makedirs(demo_dir, exist_ok=True)

def load_gii_mesh(path):
    g = nib.load(path)
    coords = g.get_arrays_from_intent('NIFTI_INTENT_POINTSET')[0].data
    faces = g.get_arrays_from_intent('NIFTI_INTENT_TRIANGLE')[0].data
    return coords, faces

print(f"Loading {left_gii}...")
l_coords, l_faces = load_gii_mesh(left_gii)
print(f"Loading {right_gii}...")
r_coords, r_faces = load_gii_mesh(right_gii)

# Merge
all_coords = np.concatenate([l_coords, r_coords], axis=0)
all_faces = np.concatenate([l_faces, r_faces + len(l_coords)], axis=0)

# Normalize/Scale for the web viewer (it expects unit scale)
mins = np.min(all_coords, axis=0)
maxs = np.max(all_coords, axis=0)
center = (mins + maxs) / 2.0
all_coords -= center

# User Feedback: "rotate everything 90 deg on xy plane" (Z-axis rotation)
# x, y, z -> -y, x, z
rotated_coords = np.zeros_like(all_coords)
rotated_coords[:, 0] = -all_coords[:, 1]
rotated_coords[:, 1] = all_coords[:, 0]
rotated_coords[:, 2] = all_coords[:, 2]

# Re-center and scale
extent = np.max(np.max(rotated_coords, axis=0) - np.min(rotated_coords, axis=0))
rotated_coords /= (extent / 2.0)

mesh = trimesh.Trimesh(vertices=rotated_coords, faces=all_faces)

# Export to both locations and both formats
for d in [export_dir, demo_dir]:
    mesh.export(os.path.join(d, "brain.glb"), file_type="glb")
    mesh.export(os.path.join(d, "brain.obj"), file_type="obj")
    mesh.export(os.path.join(d, "brain_web.obj"), file_type="obj")
    mesh.export(os.path.join(d, "brain_hq_v2_web.obj"), file_type="obj")
    mesh.export(os.path.join(d, "brain_xq_v2_web.obj"), file_type="obj")

print("Done exporting with XY plane rotation!")
