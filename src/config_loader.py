"""Configuration loader and schema validator for robotic arm joint health monitoring."""

import json
from pathlib import Path
from typing import Any, Dict


class ConfigurationError(ValueError):
    """Raised when configuration file is missing, malformed, or violates safety bounds."""
    pass


def get_default_config_path() -> Path:
    """Returns the default configuration file path relative to project root."""
    return Path(__file__).resolve().parent.parent / "config" / "thresholds.json"


def load_config(config_path: Path | str | None = None) -> Dict[str, Any]:
    """
    Loads and validates the configuration file.

    Args:
        config_path: Optional path to JSON configuration. If None, uses default.

    Returns:
        Validated configuration dictionary.

    Raises:
        ConfigurationError: If the file does not exist, contains invalid JSON,
                            or contains invalid/unsafe parameter values.
    """
    path = Path(config_path) if config_path else get_default_config_path()

    if not path.exists():
        raise ConfigurationError(f"Configuration file not found at: {path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Configuration file contains invalid JSON: {exc}") from exc
    except Exception as exc:
        raise ConfigurationError(f"Failed to read configuration file: {exc}") from exc

    validate_config(config)
    return config


def validate_config(config: Dict[str, Any]) -> None:
    """
    Strictly validates the configuration parameters.
    Ensures warning thresholds are strictly less than critical thresholds,
    values are within physical limits, and mandatory keys exist.
    """
    required_top_level = [
        "global_safety_thresholds",
        "joint_specific_thresholds",
        "predictive_maintenance",
        "maintenance_log_analysis",
        "spoof_detection",
        "fail_safe_policy"
    ]
    for key in required_top_level:
        if key not in config:
            raise ConfigurationError(f"Missing required configuration section: '{key}'")

    # 1. Global Safety Thresholds
    gst = config["global_safety_thresholds"]
    for param in ["temperature_celsius", "vibration_rms_mm_s"]:
        if param not in gst:
            raise ConfigurationError(f"Missing global safety threshold parameter: '{param}'")
        item = gst[param]
        for field in ["warning", "critical", "physical_min", "physical_max"]:
            if field not in item or not isinstance(item[field], (int, float)):
                raise ConfigurationError(f"Field '{field}' in '{param}' must be a valid number.")
        if item["warning"] >= item["critical"]:
            raise ConfigurationError(
                f"Safety warning threshold ({item['warning']}) must be strictly less than critical threshold ({item['critical']}) for '{param}'."
            )
        if item["physical_min"] >= item["physical_max"]:
            raise ConfigurationError(f"physical_min must be less than physical_max for '{param}'.")
        if not (item["physical_min"] <= item["warning"] <= item["physical_max"]) or not (
            item["physical_min"] <= item["critical"] <= item["physical_max"]
        ):
            raise ConfigurationError(f"Thresholds for '{param}' must fall within physical boundaries.")

    # 2. Joint Specific Thresholds
    jst = config["joint_specific_thresholds"]
    if not isinstance(jst, dict) or len(jst) < 6:
        raise ConfigurationError("joint_specific_thresholds must define configurations for all 6 joints.")

    for j_id, j_conf in jst.items():
        if "torque_warning_nm" not in j_conf or "torque_critical_nm" not in j_conf:
            raise ConfigurationError(f"Joint '{j_id}' missing torque_warning_nm or torque_critical_nm.")
        warn = j_conf["torque_warning_nm"]
        crit = j_conf["torque_critical_nm"]
        if not isinstance(warn, (int, float)) or not isinstance(crit, (int, float)):
            raise ConfigurationError(f"Torque thresholds for '{j_id}' must be numeric.")
        if warn <= 0 or crit <= 0:
            raise ConfigurationError(f"Torque thresholds for '{j_id}' must be positive numbers.")
        if warn >= crit:
            raise ConfigurationError(
                f"Torque warning ({warn}) must be strictly less than critical ({crit}) for '{j_id}'."
            )

    # 3. Predictive Maintenance
    pm = config["predictive_maintenance"]
    for field in ["monitor_risk_threshold", "maintenance_risk_threshold"]:
        if field not in pm or not isinstance(pm[field], (int, float)):
            raise ConfigurationError(f"Missing or invalid predictive field: '{field}'")
        if not (0.0 <= pm[field] <= 1.0):
            raise ConfigurationError(f"Predictive risk threshold '{field}' must be between 0.0 and 1.0.")
    if pm["monitor_risk_threshold"] >= pm["maintenance_risk_threshold"]:
        raise ConfigurationError(
            f"Predictive monitor_risk_threshold ({pm['monitor_risk_threshold']}) must be strictly less than maintenance_risk_threshold ({pm['maintenance_risk_threshold']})."
        )

    # 4. Maintenance Log Analysis
    mla = config["maintenance_log_analysis"]
    for field in ["monitor_concern_threshold", "maintenance_concern_threshold"]:
        if field not in mla or not isinstance(mla[field], (int, float)):
            raise ConfigurationError(f"Missing or invalid maintenance log field: '{field}'")
        if not (0.0 <= mla[field] <= 1.0):
            raise ConfigurationError(f"Maintenance concern threshold '{field}' must be between 0.0 and 1.0.")
    if mla["monitor_concern_threshold"] >= mla["maintenance_concern_threshold"]:
        raise ConfigurationError(
            f"Maintenance monitor_concern_threshold ({mla['monitor_concern_threshold']}) must be strictly less than maintenance_concern_threshold ({mla['maintenance_concern_threshold']})."
        )

    # 5. Spoof Detection
    sd = config["spoof_detection"]
    if sd.get("frozen_sensor_window_size", 0) < 2:
        raise ConfigurationError("frozen_sensor_window_size must be at least 2 samples.")
    if sd.get("suspicion_warning_threshold", 0) >= sd.get("suspicion_critical_threshold", 1):
        raise ConfigurationError("suspicion_warning_threshold must be strictly less than suspicion_critical_threshold.")

    # 6. Fail-Safe Policy
    fsp = config["fail_safe_policy"]
    if not isinstance(fsp.get("fail_safe_on_critical_missing"), bool):
        raise ConfigurationError("fail_safe_on_critical_missing must be a boolean.")
