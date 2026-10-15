"""Input schema and sensor data validation module."""

import math
from typing import Any, Dict, List, Tuple
import pandas as pd


class ValidationError(ValueError):
    """Raised when critical schema requirements are not met."""
    pass


REQUIRED_TELEMETRY_COLUMNS = [
    "timestamp",
    "arm_id",
    "joint_id",
    "torque",
    "temperature",
    "vibration"
]

OPTIONAL_FEATURE_COLUMNS = [
    "operating_hours",
    "maintenance_age_hours",
    "previous_failure_count",
    "sensor_quality"
]

VALID_ARM_IDS = {f"arm_{i}" for i in range(1, 7)}
VALID_JOINT_IDS = {f"joint_{i}" for i in range(1, 7)}


def validate_telemetry_schema(df: pd.DataFrame) -> Tuple[bool, List[str]]:
    """
    Validates DataFrame schema against required columns and types.

    Returns:
        (is_valid, list of error messages)
    """
    errors: List[str] = []

    if not isinstance(df, pd.DataFrame):
        return False, ["Input is not a valid pandas DataFrame."]

    if df.empty:
        return False, ["Telemetry dataset is completely empty."]

    # Check required columns
    missing_cols = [col for col in REQUIRED_TELEMETRY_COLUMNS if col not in df.columns]
    if missing_cols:
        errors.append(f"Missing mandatory telemetry columns: {missing_cols}")

    return len(errors) == 0, errors


def validate_sensor_reading(record: Dict[str, Any], config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """
    Validates an individual telemetry record for physical plausibility, NaN, and Inf.

    Returns:
        (is_plausible, list_of_reasons)
    """
    reasons: List[str] = []
    gst = config.get("global_safety_thresholds", {})

    arm_id = str(record.get("arm_id", "")).strip().lower()
    joint_id = str(record.get("joint_id", "")).strip().lower()

    if arm_id not in VALID_ARM_IDS:
        reasons.append(f"Invalid arm_id: '{arm_id}'. Expected one of {sorted(VALID_ARM_IDS)}")
    if joint_id not in VALID_JOINT_IDS:
        reasons.append(f"Invalid joint_id: '{joint_id}'. Expected one of {sorted(VALID_JOINT_IDS)}")

    # Check numeric sensor fields
    for field in ["torque", "temperature", "vibration"]:
        val = record.get(field)
        if val is None or pd.isna(val):
            reasons.append(f"Sensor field '{field}' is missing or NaN.")
            continue
        try:
            val_float = float(val)
        except (ValueError, TypeError):
            reasons.append(f"Sensor field '{field}' has non-numeric value: '{val}'.")
            continue

        if math.isinf(val_float):
            reasons.append(f"Sensor field '{field}' contains infinity.")
            continue

        # Physical limit checks
        if field == "temperature":
            t_cfg = gst.get("temperature_celsius", {})
            p_min = t_cfg.get("physical_min", -20.0)
            p_max = t_cfg.get("physical_max", 150.0)
            if val_float < p_min or val_float > p_max:
                reasons.append(f"Temperature {val_float}°C violates physical limits [{p_min}, {p_max}].")

        elif field == "vibration":
            v_cfg = gst.get("vibration_rms_mm_s", {})
            p_min = v_cfg.get("physical_min", 0.0)
            p_max = v_cfg.get("physical_max", 50.0)
            if val_float < p_min or val_float > p_max:
                reasons.append(f"Vibration {val_float} mm/s violates physical limits [{p_min}, {p_max}].")

        elif field == "torque":
            tq_cfg = gst.get("torque_nm_default", {})
            p_min = tq_cfg.get("physical_min", -400.0)
            p_max = tq_cfg.get("physical_max", 400.0)
            if val_float < p_min or val_float > p_max:
                reasons.append(f"Torque {val_float} Nm violates physical limits [{p_min}, {p_max}].")

    return len(reasons) == 0, reasons
