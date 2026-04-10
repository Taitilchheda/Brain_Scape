"""
Brain_Scape — Atlas Registrar

The most critical and most expensive preprocessing step. Registers each
scan to MNI152 standard brain space using ANTs SyN (non-linear diffeomorphic
registration) or FSL FNIRT as fallback.

After this step, a voxel at coordinate (x, y, z) means the same anatomical
location in every patient's scan — making comparisons, statistics, and atlas
labeling possible.

Takes 5-20 minutes per scan on CPU. Must be the LAST preprocessing step.
"""

import logging
import subprocess
from pathlib import Path
from typing import Optional

import nibabel as nib
import numpy as np

logger = logging.getLogger(__name__)


class AtlasRegistrar:
    """
    Registers brain scans to MNI152 standard space.

    Uses ANTs SyN as the primary method (most accurate) with
    FSL FNIRT as a fallback if ANTs fails or is unavailable.
    """

    def __init__(
        self,
        method: str = "ants_syn",
        template_path: str = "data/atlases/MNI152_T1_1mm_brain.nii.gz",
        max_iterations: Optional[list[int]] = None,
        fallback_method: str = "fsl_fnirt",
    ):
        """
        Args:
            method: "ants_syn" or "fsl_fnirt".
            template_path: Path to the MNI152 template file.
            max_iterations: ANTs SyN iteration schedule [coarse, medium, fine, finest].
            fallback_method: Method to use if primary fails.
        """
        self.method = method
        self.template_path = template_path
        self.max_iterations = max_iterations or [100, 70, 50, 20]
        self.fallback_method = fallback_method

    def register(
        self,
        input_path: str,
        output_path: str,
        output_transform_dir: Optional[str] = None,
    ) -> dict:
        """
        Register a brain scan to MNI152 standard space.

        Args:
            input_path: Path to the preprocessed, skull-stripped NIfTI file.
            output_path: Path to write the registered NIfTI file.
            output_transform_dir: Directory to save transformation matrices.

        Returns:
            Dictionary with registration statistics.
        """
        # Validate template exists
        if not Path(self.template_path).exists():
            raise FileNotFoundError(
                f"MNI152 template not found at {self.template_path}. "
                f"Run scripts/download_atlases.sh first."
            )

        # Try primary method
        try:
            if self.method == "ants_syn":
                stats = self._register_ants(input_path, output_path, output_transform_dir)
            elif self.method == "fsl_fnirt":
                stats = self._register_fnirt(input_path, output_path)
            else:
                raise ValueError(f"Unknown registration method: {self.method}")

            stats["method"] = self.method
            return stats

        except (FileNotFoundError, subprocess.TimeoutExpired, RuntimeError) as e:
            logger.warning(
                f"Primary registration ({self.method}) failed: {e}. "
                f"Trying fallback ({self.fallback_method})."
            )
            return self._try_fallback(input_path, output_path, output_transform_dir)

    def _register_ants(
        self,
        input_path: str,
        output_path: str,
        transform_dir: Optional[str] = None,
    ) -> dict:
        """
        Run ANTs SyN non-linear registration.

        ANTs SyN produces the most accurate registrations but is slow
        (5-20 minutes per scan on CPU).
        """
        try:
            import ants
        except ImportError:
            logger.warning("ANTsPy not available. Falling back to command-line ANTs.")
            return self._register_ants_cli(input_path, output_path, transform_dir)

        logger.info(f"Running ANTs SyN registration (Python API)...")

        # Load images
        moving = ants.image_read(input_path)
        fixed = ants.image_read(self.template_path)

        # Run SyN registration
        iteration_str = "x".join(str(i) for i in self.max_iterations)

        result = ants.registration(
            fixed=fixed,
            moving=moving,
            type_of_transform="SyN",
            reg_iterations=self.max_iterations,
            verbose=True,
        )

        # Get registered image
        registered = result["warpedmovout"]
        ants.image_write(registered, output_path)

        # Save transforms if requested
        if transform_dir:
            Path(transform_dir).mkdir(parents=True, exist_ok=True)
            for key, transform in result.items():
                if key.startswith("fwdtransforms") or key.startswith("invtransforms"):
                    for i, t in enumerate(transform):
                        ants.image_write(t, str(Path(transform_dir) / f"{key}_{i}.nii.gz"))

        # Compute registration quality metrics
        stats = {
            "method": "ants_syn_python",
            "iterations": self.max_iterations,
        }

        # Dice overlap with template (rough measure of registration quality)
        try:
            registered_arr = registered.numpy()
            fixed_arr = fixed.numpy()
            moving_mask = registered_arr > 0
            fixed_mask = fixed_arr > 0
            if moving_mask.sum() > 0 and fixed_mask.sum() > 0:
                dice = 2 * np.sum(moving_mask & fixed_mask) / (
                    np.sum(moving_mask) + np.sum(fixed_mask)
                )
                stats["dice_overlap_with_template"] = round(float(dice), 4)
        except Exception:
            pass

        logger.info(
            f"ANTs SyN registration complete. "
            f"Dice overlap: {stats.get('dice_overlap_with_template', 'N/A')}"
        )
        return stats

    def _register_ants_cli(
        self,
        input_path: str,
        output_path: str,
        transform_dir: Optional[str] = None,
    ) -> dict:
        """Run ANTs via command line (fallback if ANTsPy not installed)."""
        prefix = output_path.replace(".nii.gz", "")

        iteration_str = "x".join(str(i) for i in self.max_iterations)

        cmd = [
            "antsRegistrationSyN.sh",
            "-d", "3",
            "-f", self.template_path,
            "-m", input_path,
            "-o", prefix,
            "-n", iteration_str,
        ]

        logger.info(f"Running ANTs SyN (CLI): {' '.join(cmd)}")
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minute timeout
        )

        if result.returncode != 0:
            raise RuntimeError(f"ANTs registration failed: {result.stderr}")

        return {"method": "ants_syn_cli", "iterations": self.max_iterations}

    def _register_fnirt(self, input_path: str, output_path: str) -> dict:
        """
        Run FSL FNIRT for affine + non-linear registration.

        Faster than ANTs SyN but less accurate. Used as a fallback.
        """
        # Step 1: FLIRT (affine registration)
        affine_mat = output_path.replace(".nii.gz", "_affine.mat")
        flirt_output = output_path.replace(".nii.gz", "_affine.nii.gz")

        cmd_flirt = [
            "flirt",
            "-in", input_path,
            "-ref", self.template_path,
            "-out", flirt_output,
            "-omat", affine_mat,
            "-cost", "corratio",
            "-dof", "12",
        ]

        logger.info(f"Running FLIRT (affine): {' '.join(cmd_flirt)}")
        subprocess.run(cmd_flirt, capture_output=True, text=True, check=True, timeout=300)

        # Step 2: FNIRT (non-linear refinement)
        cmd_fnirt = [
            "fnirt",
            "--in=" + input_path,
            "--ref=" + self.template_path,
            "--aff=" + affine_mat,
            "--cout=" + output_path.replace(".nii.gz", "_warp"),
            "--iout=" + output_path,
        ]

        logger.info(f"Running FNIRT (non-linear): {' '.join(cmd_fnirt)}")
        subprocess.run(cmd_fnirt, capture_output=True, text=True, check=True, timeout=600)

        return {"method": "fsl_fnirt"}

    def _try_fallback(
        self,
        input_path: str,
        output_path: str,
        transform_dir: Optional[str] = None,
    ) -> dict:
        """Try the fallback registration method."""
        if self.fallback_method == "fsl_fnirt":
            try:
                stats = self._register_fnirt(input_path, output_path)
                stats["was_fallback"] = True
                return stats
            except Exception as e:
                logger.error(f"Fallback registration also failed: {e}")
                raise RuntimeError(
                    "Both primary and fallback registration methods failed."
                ) from e
        else:
            raise RuntimeError(f"Unknown fallback method: {self.fallback_method}")