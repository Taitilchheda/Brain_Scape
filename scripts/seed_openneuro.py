"""
Brain_Scape — Seed OpenNeuro Sample Datasets

Downloads sample neuroimaging datasets from OpenNeuro for development
and testing. These are public, de-identified datasets.

Usage:
    python scripts/seed_openneuro.py [--output data/samples] [--datasets all]
"""

import argparse
import os
import sys
from pathlib import Path


def download_openneuro_dataset(dataset_id: str, output_dir: Path) -> bool:
    """Download a single OpenNeuro dataset using openneuro-py."""
    try:
        import openneuro
    except ImportError:
        print("[ERROR] openneuro-py not installed. Run: pip install openneuro-py")
        return False

    dataset_dir = output_dir / dataset_id
    if dataset_dir.exists() and any(dataset_dir.iterdir()):
        print(f"[SKIP] Dataset {dataset_id} already exists at {dataset_dir}")
        return True

    dataset_dir.mkdir(parents=True, exist_ok=True)
    print(f"[DOWNLOAD] Fetching dataset {dataset_id}...")

    try:
        openneuro.download(dataset=dataset_id, target_dir=str(dataset_dir))
        print(f"[DONE] Dataset {dataset_id} downloaded to {dataset_dir}")
        return True
    except Exception as e:
        print(f"[ERROR] Failed to download {dataset_id}: {e}")
        return False


# Curated sample datasets for Brain_Scape development
SAMPLE_DATASETS = {
    # Structural MRI (T1w) — brain anatomy
    "ds000105": {
        "description": "Balloon Analog Risk-taking Task",
        "modalities": ["T1w"],
        "subjects": 1,  # Download subset
    },
    "ds000208": {
        "description": "Striatum resting state",
        "modalities": ["T1w", "bold"],
        "subjects": 1,
    },
    # fMRI dataset — for functional connectivity analysis
    "ds000247": {
        "description": "Multi-modal MRI (HNU-1)",
        "modalities": ["T1w", "bold", "dwi"],
        "subjects": 1,
    },
    # EEG dataset — for multimodal fusion
    "ds000103": {
        "description": "EEG Motor Movement/Imagery",
        "modalities": ["eeg"],
        "subjects": 1,
    },
}


def main():
    parser = argparse.ArgumentParser(
        description="Download sample OpenNeuro datasets for Brain_Scape development"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/samples",
        help="Output directory for downloaded datasets",
    )
    parser.add_argument(
        "--datasets",
        type=str,
        default="all",
        help="Comma-separated dataset IDs to download, or 'all'",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.datasets == "all":
        datasets_to_download = list(SAMPLE_DATASETS.keys())
    else:
        datasets_to_download = [d.strip() for d in args.datasets.split(",")]

    print("=" * 50)
    print(" Brain_Scape — OpenNeuro Dataset Seeder")
    print("=" * 50)
    print()

    success_count = 0
    for dataset_id in datasets_to_download:
        if dataset_id in SAMPLE_DATASETS:
            info = SAMPLE_DATASETS[dataset_id]
            print(f"Dataset: {dataset_id}")
            print(f"  Description: {info['description']}")
            print(f"  Modalities: {', '.join(info['modalities'])}")
            print()
        else:
            print(f"[WARN] Unknown dataset {dataset_id}, attempting download anyway...")
            print()

        if download_openneuro_dataset(dataset_id, output_dir):
            success_count += 1
        print()

    print("=" * 50)
    print(f" Downloaded {success_count}/{len(datasets_to_download)} datasets")
    print(f" Output directory: {output_dir.resolve()}")
    print("=" * 50)

    return 0 if success_count == len(datasets_to_download) else 1


if __name__ == "__main__":
    sys.exit(main())