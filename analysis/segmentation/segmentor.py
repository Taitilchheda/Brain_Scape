"""
Brain_Scape — nnU-Net Segmentation

Self-configuring medical image segmentation using nnU-Net v2.
Per-voxel damage delineation: lesion boundaries, white matter
hyperintensities, atrophy zones, and mass effect regions.

This is the GPU-bound stage (5-15 min per scan on A10G).
"""

import logging
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class BrainSegmentor:
    """
    Performs per-voxel damage segmentation using nnU-Net.

    nnU-Net is self-configuring — it reads the dataset and automatically
    sets architecture, patch size, and training schedule. This removes
    a large hyperparameter search burden.
    """

    def __init__(
        self,
        model_variant: str = "3d_fullres",
        checkpoint: str = "checkpoint_best.pth",
        use_gpu: bool = True,
        use_mirroring: bool = True,
        overlap: float = 0.5,
        batch_size: int = 1,
    ):
        """
        Args:
            model_variant: nnU-Net variant ("3d_fullres", "3d_lowres", "2d").
            checkpoint: Model checkpoint filename.
            use_gpu: Whether to use GPU for inference.
            use_mirroring: Test-time augmentation by mirroring.
            overlap: Sliding window overlap for large volumes.
            batch_size: Batch size for inference.
        """
        self.model_variant = model_variant
        self.checkpoint = checkpoint
        self.use_gpu = use_gpu
        self.use_mirroring = use_mirroring
        self.overlap = overlap
        self.batch_size = batch_size
        self._predictor = None

    def _get_predictor(self):
        """Lazy-load the nnU-Net predictor."""
        if self._predictor is not None:
            return self._predictor

        try:
            from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

            self._predictor = nnUNetPredictor(
                device="cuda" if self.use_gpu else "cpu",
                task_name="Dataset601_BrainLesion",
                planner_name="nnUNetPlans",
                configuration=self.model_variant,
                fold=0,
                checkpoint_name=self.checkpoint,
            )
            return self._predictor
        except ImportError:
            logger.warning("nnU-Net not available. Using fallback segmentation.")
            return None

    def segment(
        self,
        input_path: str,
        output_path: str,
        atlas_path: Optional[str] = None,
    ) -> dict:
        """
        Perform damage segmentation on a registered brain scan.

        Args:
            input_path: Path to the MNI152-registered NIfTI file.
            output_path: Path to write the segmentation mask.
            atlas_path: Optional atlas labels for region-level segmentation.

        Returns:
            Dictionary with segmentation statistics.
        """
        predictor = self._get_predictor()

        if predictor is not None:
            return self._segment_nnunet(input_path, output_path, predictor)
        else:
            return self._segment_fallback(input_path, output_path, atlas_path)

    def _segment_nnunet(
        self,
        input_path: str,
        output_path: str,
        predictor,
    ) -> dict:
        """Run nnU-Net segmentation."""
        import torch
        import time

        logger.info(f"Running nnU-Net segmentation ({self.model_variant})...")
        start_time = time.time()

        # Run prediction
        segmentation = predictor.predict_from_files(
            list_of_lists=[[input_path]],
            output_files_or_list=output_path,
            save_probabilities=True,
            overwrite=True,
            num_processes=1,
        )

        elapsed = time.time() - start_time

        # Load segmentation result
        seg_img = nib.load(output_path)
        seg_data = seg_img.get_fdata()

        # Compute statistics
        stats = {
            "method": "nnunet",
            "model_variant": self.model_variant,
            "checkpoint": self.checkpoint,
            "inference_time_seconds": round(elapsed, 1),
            "use_gpu": self.use_gpu,
            "use_mirroring": self.use_mirroring,
        }

        # Count lesion voxels per label
        unique_labels = np.unique(seg_data)
        for label in unique_labels:
            if label == 0:
                continue  # Background
            count = np.sum(seg_data == label)
            stats[f"label_{int(label)}_voxels"] = int(count)

        logger.info(
            f"nnU-Net segmentation complete in {elapsed:.1f}s. "
            f"Found {len(unique_labels) - 1} lesion types."
        )
        return stats

    def _segment_fallback(
        self,
        input_path: str,
        output_path: str,
        atlas_path: Optional[str] = None,
    ) -> dict:
        """
        Fallback segmentation using intensity-based thresholding.

        This is a placeholder for development/testing when nnU-Net
        weights are not available. NOT suitable for clinical use.
        """
        logger.warning(
            "Using fallback intensity-based segmentation. "
            "This is NOT suitable for clinical use."
        )

        img = nib.load(input_path)
        data = img.get_fdata()

        # Simple thresholding approach
        brain_mask = data > 0
        brain_data = data[brain_mask]

        # Compute percentile-based thresholds for damage detection
        p25 = np.percentile(brain_data, 25)
        p75 = np.percentile(brain_data, 75)
        median = np.median(brain_data)

        # Hypointense regions (potential damage in T1)
        hypointense_threshold = p25 * 0.7
        # Hyperintense regions (potential damage in FLAIR)
        hyperintense_threshold = p75 * 1.3

        # Create segmentation mask
        # 0 = background, 1 = healthy tissue, 2 = hypointense damage, 3 = hyperintense damage
        seg_mask = np.zeros_like(data, dtype=np.int8)
        seg_mask[brain_mask] = 1  # Healthy tissue baseline
        seg_mask[(data < hypointense_threshold) & brain_mask] = 2  # Hypointense
        seg_mask[(data > hyperintense_threshold) & brain_mask] = 3  # Hyperintense

        # Save segmentation
        seg_img = nib.Nifti1Image(seg_mask, img.affine, img.header)
        nib.save(seg_img, output_path)

        stats = {
            "method": "intensity_threshold_fallback",
            "hypointense_threshold": float(hypointense_threshold),
            "hyperintense_threshold": float(hyperintense_threshold),
            "label_1_voxels": int(np.sum(seg_mask == 1)),  # Healthy
            "label_2_voxels": int(np.sum(seg_mask == 2)),  # Hypointense
            "label_3_voxels": int(np.sum(seg_mask == 3)),  # Hyperintense
            "warning": "FALLBACK_SEGMENTATION_NOT_CLINICAL_GRADE",
        }

        logger.info(
            f"Fallback segmentation complete. "
            f"Healthy: {stats['label_1_voxels']}, "
            f"Damage: {stats['label_2_voxels'] + stats['label_3_voxels']}"
        )
        return stats