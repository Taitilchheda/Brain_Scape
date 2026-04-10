#!/bin/bash
# Brain_Scape — One-Command Full Pipeline Launcher
# Usage: bash scripts/run_pipeline.sh <scan_path> [--modalities MRI_T1 fMRI]
#
# This script runs the complete Brain_Scape pipeline from ingestion to export.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

cd "$PROJECT_DIR"

# Default values
SCAN_PATH="${1:?Usage: run_pipeline.sh <scan_path> [modalities...]}"
shift
MODALITIES="${*:-MRI_T1}"
JOB_ID=$(python -c "import uuid; print(uuid.uuid4())")

echo "========================================="
echo " Brain_Scape — Full Pipeline"
echo "========================================="
echo "Job ID:     $JOB_ID"
echo "Scan path:  $SCAN_PATH"
echo "Modalities: $MODALITIES"
echo ""

# Step 1: Ingest
echo "[1/7] Ingesting scan..."
python scripts/ingest.py "$SCAN_PATH" --job-id "$JOB_ID" --modalities $MODALITIES
echo ""

# Step 2: Preprocess
echo "[2/7] Preprocessing..."
python -c "
from preprocessing.skull_stripper import SkullStripper
from preprocessing.intensity_normalizer import IntensityNormalizer
from preprocessing.denoiser import Denoiser
from preprocessing.atlas_registrar import AtlasRegistrar
import logging
logging.basicConfig(level=logging.INFO)

job_id = '$JOB_ID'
input_path = f'data/raw/{job_id}/scan.nii.gz'
processed_dir = f'data/processed/{job_id}'

print('  Skull stripping...')
stripper = SkullStripper()
stripper.strip(input_path, f'{processed_dir}/stripped.nii.gz')

print('  Intensity normalization...')
normalizer = IntensityNormalizer()
normalizer.normalize(f'{processed_dir}/stripped.nii.gz', f'{processed_dir}/normalized.nii.gz')

print('  Denoising...')
denoiser = Denoiser()
denoiser.denoise(f'{processed_dir}/normalized.nii.gz', f'{processed_dir}/denoised.nii.gz')

print('  Atlas registration...')
registrar = AtlasRegistrar()
registrar.register(f'{processed_dir}/denoised.nii.gz', f'data/registered/{job_id}/registered.nii.gz')
"
echo ""

# Steps 3-7: Run via Prefect pipeline
echo "[3/7] Running analysis, reconstruction, and report generation..."
echo "Starting Prefect pipeline..."
python -m mlops.pipeline "$JOB_ID" "$SCAN_PATH" $MODALITIES
echo ""

echo "========================================="
echo " Pipeline Complete!"
echo " Job ID: $JOB_ID"
echo " Results in: outputs/{JOB_ID}/"
echo "========================================="