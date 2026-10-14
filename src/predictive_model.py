"""Predictive maintenance model module for estimating 24-hour joint failure risk.

Trains and evaluates scikit-learn classifiers on synthetic telemetry features.
Returns continuous probability scores [0.0, 1.0].
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger("predictive_model")

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent.parent / "models" / "predictive_model.joblib"


class PredictiveModel:
    """
    Predictive maintenance machine learning wrapper.
    Utilizes an ensemble Random Forest pipeline with feature scaling to estimate
    the probability of a joint failure within the subsequent 24 operating hours.
    """

    def __init__(
        self,
        feature_columns: Optional[List[str]] = None,
        model_path: Optional[Union[str, Path]] = None,
        random_state: int = 42
    ):
        self.feature_columns = feature_columns or [
            "torque",
            "temperature",
            "vibration",
            "operating_hours",
            "maintenance_age_hours",
            "previous_failure_count",
            "sensor_quality"
        ]
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL_PATH
        self.random_state = random_state
        self.pipeline: Optional[Pipeline] = None
        self.is_trained: bool = False

    def build_pipeline(self) -> Pipeline:
        """Constructs an end-to-end preprocessing and classification pipeline."""
        return Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", RandomForestClassifier(
                n_estimators=100,
                max_depth=8,
                min_samples_split=4,
                class_weight="balanced",  # Address industrial class imbalance
                random_state=self.random_state,
                n_jobs=1
            ))
        ])

    def fit(self, X: pd.DataFrame, y: Union[pd.Series, np.ndarray]) -> "PredictiveModel":
        """
        Fits the predictive pipeline onto feature matrix X and target labels y.
        """
        missing_features = [col for col in self.feature_columns if col not in X.columns]
        if missing_features:
            raise ValueError(f"Feature matrix is missing required columns: {missing_features}")

        X_subset = X[self.feature_columns]
        self.pipeline = self.build_pipeline()
        self.pipeline.fit(X_subset, y)
        self.is_trained = True
        return self

    def predict_risk(
        self,
        data: Union[Dict[str, Any], pd.DataFrame]
    ) -> Union[float, np.ndarray]:
        """
        Estimates joint failure risk as a calibrated probability score [0.0, 1.0].

        If the model is unavailable, logs a warning and returns safe fallback (0.0),
        ensuring deterministic safety rules are never impeded.
        """
        if not self.is_trained and not self.load():
            logger.warning("Predictive model unavailable; returning fallback risk score 0.0.")
            if isinstance(data, dict):
                return 0.0
            return np.zeros(len(data))

        if isinstance(data, dict):
            # Single sample evaluation
            row = {}
            for col in self.feature_columns:
                val = data.get(col, 0.0)
                try:
                    row[col] = float(val) if val is not None else 0.0
                except (ValueError, TypeError):
                    row[col] = 0.0
            df_single = pd.DataFrame([row])
            proba = self.pipeline.predict_proba(df_single[self.feature_columns])[0, 1]
            return float(np.clip(proba, 0.0, 1.0))

        elif isinstance(data, pd.DataFrame):
            # Batch evaluation
            missing_cols = [col for col in self.feature_columns if col not in data.columns]
            df_proc = data.copy()
            for col in missing_cols:
                df_proc[col] = 0.0
            probas = self.pipeline.predict_proba(df_proc[self.feature_columns])[:, 1]
            return np.clip(probas, 0.0, 1.0)

        else:
            raise TypeError(f"Unsupported data type for risk prediction: {type(data)}")

    def save(self, path: Optional[Union[str, Path]] = None) -> Path:
        """Serializes trained model pipeline to disk."""
        if not self.is_trained or self.pipeline is None:
            raise RuntimeError("Cannot save untrained predictive model.")
        save_path = Path(path) if path else self.model_path
        save_path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump({
            "pipeline": self.pipeline,
            "feature_columns": self.feature_columns,
            "random_state": self.random_state
        }, save_path)
        logger.info("Saved predictive model pipeline to %s", save_path)
        return save_path

    def load(self, path: Optional[Union[str, Path]] = None) -> bool:
        """Loads serialized model pipeline from disk."""
        load_path = Path(path) if path else self.model_path
        if not load_path.exists():
            return False
        try:
            artifact = joblib.load(load_path)
            self.pipeline = artifact["pipeline"]
            self.feature_columns = artifact.get("feature_columns", self.feature_columns)
            self.random_state = artifact.get("random_state", self.random_state)
            self.is_trained = True
            logger.info("Loaded predictive model pipeline from %s", load_path)
            return True
        except Exception as exc:
            logger.error("Failed to load model from %s: %s", load_path, exc)
            return False
