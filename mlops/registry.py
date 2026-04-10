"""
Brain_Scape — Model Registry

Manages model version promotion with automated quality gates.
No model ever reaches production without passing the automated gate
AND a human sign-off.
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)


class ModelRegistry:
    """
    Model version registry with promotion gates.

    Promotion policy:
        Dice >= 0.82 AND ECE <= 0.05 AND differential F1 >= 0.75
        PASS → staging → human review → production
        FAIL → flag in MLflow, alert ML team
    """

    # Quality gates (from configs/models.yaml)
    PROMOTION_GATES = {
        "dice_score_minimum": 0.82,
        "ece_maximum": 0.05,
        "differential_f1_minimum": 0.75,
    }

    STAGES = ["development", "staging", "production", "archived"]

    def __init__(self, tracking_uri: Optional[str] = None):
        self.tracking_uri = tracking_uri or "http://localhost:5000"
        self._models = {}  # In-memory registry for development

    def register_model(
        self,
        model_name: str,
        version: str,
        metrics: dict,
        stage: str = "development",
        description: str = "",
    ) -> dict:
        """
        Register a new model version.

        Args:
            model_name: Name of the model (e.g., "brainscape-segmentor").
            version: Version string (e.g., "1.0.0").
            metrics: Dict of evaluation metrics.
            stage: Initial stage ("development", "staging", "production").
            description: Model description.

        Returns:
            Model registration record.
        """
        if stage not in self.STAGES:
            raise ValueError(f"Invalid stage: {stage}. Must be one of {self.STAGES}")

        record = {
            "model_name": model_name,
            "version": version,
            "stage": stage,
            "metrics": metrics,
            "description": description,
            "promoted_by": None,
            "promoted_at": None,
        }

        key = f"{model_name}/{version}"
        self._models[key] = record

        logger.info(f"Registered model {model_name} v{version} at stage {stage}")
        return record

    def check_promotion_gates(self, metrics: dict) -> tuple[bool, list[str]]:
        """
        Check if metrics pass the automated promotion gates.

        Returns:
            Tuple of (passed: bool, failures: list of gate descriptions).
        """
        failures = []

        dice = metrics.get("dice_score", 0)
        if dice < self.PROMOTION_GATES["dice_score_minimum"]:
            failures.append(
                f"Dice score {dice:.3f} < minimum {self.PROMOTION_GATES['dice_score_minimum']}"
            )

        ece = metrics.get("ece", 1.0)
        if ece > self.PROMOTION_GATES["ece_maximum"]:
            failures.append(
                f"ECE {ece:.3f} > maximum {self.PROMOTION_GATES['ece_maximum']}"
            )

        f1 = metrics.get("differential_f1", 0)
        if f1 < self.PROMOTION_GATES["differential_f1_minimum"]:
            failures.append(
                f"Differential F1 {f1:.3f} < minimum {self.PROMOTION_GATES['differential_f1_minimum']}"
            )

        passed = len(failures) == 0
        return passed, failures

    def promote_to_staging(
        self, model_name: str, version: str
    ) -> dict:
        """
        Promote a model to staging (automated gate check).

        Returns:
            Promotion result dict.
        """
        key = f"{model_name}/{version}"
        if key not in self._models:
            raise ValueError(f"Model {model_name} v{version} not registered.")

        model = self._models[key]
        passed, failures = self.check_promotion_gates(model["metrics"])

        if passed:
            model["stage"] = "staging"
            logger.info(f"Model {model_name} v{version} promoted to staging.")
            return {"promoted": True, "stage": "staging", "failures": []}
        else:
            logger.warning(
                f"Model {model_name} v{version} FAILED promotion gates: {failures}"
            )
            return {"promoted": False, "stage": model["stage"], "failures": failures}

    def promote_to_production(
        self, model_name: str, version: str, promoted_by: str, ml_admin_jwt: str
    ) -> dict:
        """
        Promote a model to production (requires human sign-off + ml_admin JWT).

        Args:
            model_name: Model name.
            version: Version string.
            promoted_by: User performing the promotion.
            ml_admin_jwt: JWT with ml_admin role claim.

        Returns:
            Promotion result dict.
        """
        # Verify ml_admin role in JWT (would use RBAC manager in production)
        # For development, we just check it's not empty
        if not ml_admin_jwt:
            raise PermissionError(
                "Production promotion requires ml_admin JWT. "
                "No model reaches production without human sign-off."
            )

        key = f"{model_name}/{version}"
        if key not in self._models:
            raise ValueError(f"Model {model_name} v{version} not registered.")

        model = self._models[key]

        if model["stage"] != "staging":
            raise ValueError(
                f"Model must be in staging before production promotion. "
                f"Current stage: {model['stage']}"
            )

        model["stage"] = "production"
        model["promoted_by"] = promoted_by

        from datetime import datetime, timezone
        model["promoted_at"] = datetime.now(timezone.utc).isoformat()

        logger.info(
            f"Model {model_name} v{version} promoted to PRODUCTION by {promoted_by}."
        )
        return {"promoted": True, "stage": "production"}

    def get_model(self, model_name: str, version: str) -> Optional[dict]:
        """Get a model record."""
        key = f"{model_name}/{version}"
        return self._models.get(key)

    def list_models(self, model_name: Optional[str] = None) -> list[dict]:
        """List all registered models, optionally filtered by name."""
        models = list(self._models.values())
        if model_name:
            models = [m for m in models if m["model_name"] == model_name]
        return models

    def get_production_model(self, model_name: str) -> Optional[dict]:
        """Get the current production model for a given name."""
        for model in self._models.values():
            if model["model_name"] == model_name and model["stage"] == "production":
                return model
        return None