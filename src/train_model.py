"""Model training and evaluation script for joint predictive maintenance.

Uses chronological time-aware train/test splitting to prevent future data leakage,
evaluates performance metrics addressing class imbalance, and serializes the pipeline.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict
import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score
)

from src.config_loader import load_config
from src.data_generator import generate_historical_dataset
from src.predictive_model import PredictiveModel

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("train_model")


def train_and_evaluate(
    data_path: Path | str | None = None,
    output_dir: Path | str | None = None,
    test_size: float = 0.20
) -> Dict[str, Any]:
    """
    Loads dataset, splits chronologically, trains model, evaluates metrics,
    and saves artifacts.
    """
    project_root = Path(__file__).resolve().parent.parent
    config = load_config()

    if data_path:
        csv_file = Path(data_path)
    else:
        csv_file = project_root / "data" / "historical_joint_readings.csv"

    if not csv_file.exists():
        logger.info("Historical data file not found at %s. Generating synthetic dataset...", csv_file)
        df_hist = generate_historical_dataset(num_samples=2160, random_seed=42)
        csv_file.parent.mkdir(parents=True, exist_ok=True)
        df_hist.to_csv(csv_file, index=False)
        logger.info("Generated and saved %d records to %s", len(df_hist), csv_file)
    else:
        df_hist = pd.read_csv(csv_file)
        logger.info("Loaded %d records from %s", len(df_hist), csv_file)

    # Chronological Time-Aware Splitting to avoid data leakage
    if "timestamp" in df_hist.columns:
        df_hist["timestamp"] = pd.to_datetime(df_hist["timestamp"])
        df_hist = df_hist.sort_values(by="timestamp").reset_index(drop=True)

    split_idx = int(len(df_hist) * (1.0 - test_size))
    train_df = df_hist.iloc[:split_idx].copy()
    test_df = df_hist.iloc[split_idx:].copy()

    feature_cols = config["predictive_maintenance"]["feature_columns"]
    target_col = "failure_within_24h"

    X_train = train_df[feature_cols]
    y_train = train_df[target_col].values
    X_test = test_df[feature_cols]
    y_test = test_df[target_col].values

    # Train model
    model = PredictiveModel(feature_columns=feature_cols)
    logger.info("Training PredictiveModel on %d training samples...", len(X_train))
    model.fit(X_train, y_train)

    # Evaluate predictions
    y_pred_proba = model.predict_risk(X_test)
    y_pred = (y_pred_proba >= 0.50).astype(int)

    acc = float(accuracy_score(y_test, y_pred))
    prec = float(precision_score(y_test, y_pred, zero_division=0))
    rec = float(recall_score(y_test, y_pred, zero_division=0))
    f1 = float(f1_score(y_test, y_pred, zero_division=0))

    try:
        roc_auc = float(roc_auc_score(y_test, y_pred_proba))
    except Exception:
        roc_auc = 0.5

    cm = confusion_matrix(y_test, y_pred)
    tn, fp, fn, tp = [int(v) for v in cm.ravel()]

    class_counts = {
        "total_test_samples": len(y_test),
        "actual_negatives_class_0": int(np.sum(y_test == 0)),
        "actual_positives_class_1": int(np.sum(y_test == 1)),
        "positive_class_ratio": round(float(np.mean(y_test == 1)), 4)
    }

    metrics = {
        "model_architecture": "StandardScaler + RandomForestClassifier(n_estimators=100, max_depth=8, class_weight='balanced')",
        "training_samples": len(X_train),
        "test_samples": len(X_test),
        "split_method": "Chronological Time-Aware Split (80% train / 20% test)",
        "features_used": feature_cols,
        "class_imbalance_analysis": {
            **class_counts,
            "explanation": (
                "In industrial predictive maintenance, failures are rare events (typically 5-15% of samples). "
                "Accuracy is an insufficient metric because a naive model that always predicts healthy (class 0) "
                "could achieve high accuracy while failing to detect critical impending breakdowns. "
                "Recall (identifying actual failures) and Precision (avoiding false alarms) are the primary objectives."
            )
        },
        "evaluation_metrics": {
            "accuracy": round(acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1_score": round(f1, 4),
            "roc_auc": round(roc_auc, 4),
            "confusion_matrix": {
                "true_negatives": tn,
                "false_positives": fp,
                "false_negatives": fn,
                "true_positives": tp
            }
        },
        "disclaimer": "Synthetic demonstration metrics on simulated physics data. Real-world validation required for production."
    }

    # Save model and metrics
    out_dir = Path(output_dir) if output_dir else project_root / "outputs"
    out_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = out_dir / "model_evaluation.json"

    with open(metrics_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Saved evaluation metrics to %s", metrics_path)

    model.save()

    print("\n" + "=" * 65)
    print(" PREDICTIVE MAINTENANCE MODEL TRAINING & EVALUATION REPORT")
    print("=" * 65)
    print(f" Train Samples: {len(X_train)} | Test Samples: {len(X_test)}")
    print(f" Positive Failure Rate in Test: {class_counts['positive_class_ratio']*100:.1f}%")
    print("-" * 65)
    print(f" Accuracy:  {acc:.4f}")
    print(f" Precision: {prec:.4f}")
    print(f" Recall:    {rec:.4f}")
    print(f" F1-Score:  {f1:.4f}")
    print(f" ROC-AUC:   {roc_auc:.4f}")
    print("-" * 65)
    print(f" Confusion Matrix: [TN={tn}, FP={fp}, FN={fn}, TP={tp}]")
    print("=" * 65 + "\n")

    return metrics


if __name__ == "__main__":
    train_and_evaluate()
