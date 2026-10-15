"""Tests for pipeline execution, configuration validation, and dataset reproducibility."""

import json
from pathlib import Path
import pytest
import pandas as pd

from src.config_loader import ConfigurationError, validate_config
from src.data_generator import generate_historical_dataset
from src.main import MonitoringPipeline


def test_invalid_config_rejected_with_error():
    """Test 18: Invalid configuration is rejected with a useful error."""
    # Test case A: warning threshold greater than critical
    invalid_cfg_1 = {
        "global_safety_thresholds": {
            "temperature_celsius": {"warning": 90.0, "critical": 80.0, "physical_min": -20.0, "physical_max": 150.0},
            "vibration_rms_mm_s": {"warning": 4.5, "critical": 7.0, "physical_min": 0.0, "physical_max": 50.0}
        },
        "joint_specific_thresholds": {f"joint_{i}": {"torque_warning_nm": 100.0, "torque_critical_nm": 150.0} for i in range(1, 7)},
        "predictive_maintenance": {"monitor_risk_threshold": 0.35, "maintenance_risk_threshold": 0.70},
        "maintenance_log_analysis": {"monitor_concern_threshold": 0.30, "maintenance_concern_threshold": 0.60},
        "spoof_detection": {"frozen_sensor_window_size": 5, "suspicion_warning_threshold": 0.45, "suspicion_critical_threshold": 0.85},
        "fail_safe_policy": {"fail_safe_on_critical_missing": True}
    }
    with pytest.raises(ConfigurationError) as exc_info:
        validate_config(invalid_cfg_1)
    assert "must be strictly less than critical" in str(exc_info.value)

    # Test case B: Missing required section
    invalid_cfg_2 = {"global_safety_thresholds": {}}
    with pytest.raises(ConfigurationError) as exc_info2:
        validate_config(invalid_cfg_2)
    assert "Missing required configuration section" in str(exc_info2.value)


def test_dataset_generation_reproducibility():
    """Test 19: Dataset generation is reproducible using the configured random seed."""
    df1 = generate_historical_dataset(num_samples=100, random_seed=42)
    df2 = generate_historical_dataset(num_samples=100, random_seed=42)
    pd.testing.assert_frame_equal(df1, df2)

    # Different seeds should yield different datasets
    df3 = generate_historical_dataset(num_samples=100, random_seed=999)
    assert not df1["torque"].equals(df3["torque"])


def test_pipeline_exports_valid_csv_and_json(tmp_path):
    """Test 20: The end-to-end pipeline exports valid CSV and JSON outputs."""
    from src.data_generator import generate_current_telemetry, generate_maintenance_logs

    df_current = generate_current_telemetry()
    log_text = generate_maintenance_logs()
    log_path = tmp_path / "test_logs.txt"
    log_path.write_text(log_text, encoding="utf-8")

    pipeline = MonitoringPipeline()
    decisions = pipeline.run(
        telemetry_df=df_current,
        maintenance_log_path=log_path,
        output_dir=tmp_path
    )

    assert len(decisions) == 6

    # Verify CSV files exist and are valid
    summary_csv = tmp_path / "arm_health_summary.csv"
    assert summary_csv.exists()
    df_sum = pd.read_csv(summary_csv)
    assert len(df_sum) == 6
    assert "final_decision" in df_sum.columns

    diagnostics_csv = tmp_path / "joint_diagnostics.csv"
    assert diagnostics_csv.exists()
    df_diag = pd.read_csv(diagnostics_csv)
    assert len(df_diag) == 36  # 6 arms * 6 joints

    # Verify JSON files exist and are valid JSON
    summary_json = tmp_path / "arm_health_summary.json"
    assert summary_json.exists()
    with open(summary_json, "r", encoding="utf-8") as f:
        loaded_json = json.load(f)
    assert len(loaded_json) == 6

    # Verify Markdown report exists
    report_md = tmp_path / "final_report.md"
    assert report_md.exists()
    report_text = report_md.read_text(encoding="utf-8")
    assert "# Robotic Arm Joint Health & Operational Safety Report" in report_text
