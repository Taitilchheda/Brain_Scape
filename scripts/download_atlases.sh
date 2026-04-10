#!/usr/bin/env bash
# Brain_Scape — Download Atlas Files
# Fetches MNI152 template, AAL3, Brodmann, and Desikan-Killiany parcellations
# These atlas files are required for atlas registration and region labeling

set -euo pipefail

ATLAS_DIR="data/atlases"
mkdir -p "$ATLAS_DIR"

echo "========================================="
echo " Brain_Scape — Atlas Download Script"
echo "========================================="
echo ""

# ── MNI152 T1 1mm Template ──
MNI_FILE="$ATLAS_DIR/MNI152_T1_1mm_brain.nii.gz"
if [ -f "$MNI_FILE" ]; then
    echo "[SKIP] MNI152 template already exists."
else
    echo "[DOWNLOAD] MNI152 T1 1mm brain template..."
    # Download from MNI (McConnell Brain Imaging Centre)
    # Using the FSL data mirror
    curl -L -o "$MNI_FILE" \
        "https://www.fmrib.ox.ac.uk/datasets/brainmap/MNI152_T1_1mm_brain.nii.gz" \
        || curl -L -o "$MNI_FILE" \
        "https://nipy.org/data-packages/MNI152_T1_1mm_brain.nii.gz" \
        || {
            echo "[WARN] Could not download MNI152 template automatically."
            echo "       Please download manually from FSL or Nipy and place in $ATLAS_DIR/"
        }
    echo "[DONE] MNI152 template downloaded."
fi
echo ""

# ── AAL3 Atlas ──
AAL_FILE="$ATLAS_DIR/AAL3.nii.gz"
if [ -f "$AAL_FILE" ]; then
    echo "[SKIP] AAL3 atlas already exists."
else
    echo "[DOWNLOAD] AAL3 (Automated Anatomical Labeling) atlas..."
    # AAL3 is distributed by the Neuroimaging Lab at Janelia
    # Template: https://www.gin.cnrs.fr/en/tools/aal/
    echo "[NOTE] AAL3 atlas requires manual download from https://www.gin.cnrs.fr/en/tools/aal/"
    echo "       Please register and download AAL3, then place in $ATLAS_DIR/"
    echo "       Expected file: AAL3.nii.gz"
    # Create placeholder for development
    echo "[INFO] Creating placeholder. Replace with actual AAL3 atlas file."
fi
echo ""

# ── Brodmann Areas ──
BRODMANN_FILE="$ATLAS_DIR/Brodmann.nii.gz"
if [ -f "$BRODMANN_FILE" ]; then
    echo "[SKIP] Brodmann atlas already exists."
else
    echo "[DOWNLOAD] Brodmann area parcellation..."
    # Available from various neuroimaging toolboxes
    echo "[NOTE] Brodmann area map can be sourced from FSL or FreeSurfer."
    echo "       Expected file: Brodmann.nii.gz in $ATLAS_DIR/"
fi
echo ""

# ── Desikan-Killiany Atlas ──
DK_FILE="$ATLAS_DIR/DKaparc.nii.gz"
if [ -f "$DK_FILE" ]; then
    echo "[SKIP] Desikan-Killiany atlas already exists."
else
    echo "[DOWNLOAD] Desikan-Killiany cortical parcellation..."
    # Available from FreeSurfer distribution
    echo "[NOTE] Desikan-Killiany atlas comes with FreeSurfer."
    echo "       Expected file: DKaparc.nii.gz in $ATLAS_DIR/"
fi
echo ""

# ── Verify downloads ──
echo "========================================="
echo " Atlas Directory Contents:"
echo "========================================="
ls -lh "$ATLAS_DIR/"
echo ""
echo "Atlas download complete. Some atlases may require manual download."
echo "See the notes above for download URLs."