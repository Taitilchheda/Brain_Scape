# Perfect Brain Showcase

This folder provides a polished publication-facing visualization set using an actual human cortical surface template (fsaverage) plus MRI-derived DICOM panels.

## Inputs
- MRI source volume: data/raw/uploads/brainscape_sample_fmri.nii.gz
- Clinical metadata source: outputs/analysis/4b11d116-1e3e-4bef-a077-01f06d462523/analysis.json
- Surface template left: c:\Users\taiti\OneDrive\Desktop\Brain_Scape-taitil\Brain_Scape-taitil\.venv\lib\site-packages\nilearn\datasets\data\fsaverage5\pial_left.gii.gz
- Surface template right: c:\Users\taiti\OneDrive\Desktop\Brain_Scape-taitil\Brain_Scape-taitil\.venv\lib\site-packages\nilearn\datasets\data\fsaverage5\pial_right.gii.gz

## Generated Visuals
- perfect_brain_surface.png / .svg: fsaverage human cortical surface (multi-view)
- perfect_brain_hotspots.png / .svg: fsaverage surface with highlighted hotspots
- dicom_mri_series.png / .svg: radiology-style MRI orthogonal panel series
- dicom_mri_hotspots.png / .svg: MRI panels with hotspot overlays

## Notes
- This is a dedicated visual-quality showcase folder requested for publication-ready appearance using true human cortical anatomy.
- The MRI views are generated from the source NIfTI using robust windowing and radiology-style panel formatting.
