"""Tests for deterministic rule-based safety engine."""

import math
import pytest
from src.config_loader import load_config
from src.safety_engine import SafetyEngine


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def safety_engine(config):
    return SafetyEngine(config)


def test_normal_telemetry_is_safe(safety_engine):
    """Test 1 baseline: Normal telemetry within limits returns SAFE."""
    reading = {
        "arm_id": "arm_1",
        "joint_id": "joint_2",
        "torque": 160.0,
        "temperature": 50.0,
        "vibration": 1.5
    }
    result = safety_engine.evaluate_reading(reading)
    assert result.status == "SAFE"
    assert result.emergency_stop is False
    assert len(result.violations) == 0


def test_critical_torque_triggers_emergency_stop(safety_engine):
    """Test 2: A critical torque reading triggers EMERGENCY_STOP."""
    # Joint 2 critical threshold is 320 Nm
    reading = {
        "arm_id": "arm_1",
        "joint_id": "joint_2",
        "torque": 335.0,
        "temperature": 50.0,
        "vibration": 1.5
    }
    result = safety_engine.evaluate_reading(reading)
    assert result.status == "EMERGENCY_STOP"
    assert result.emergency_stop is True
    assert any("torque" in v.parameter for v in result.violations)


def test_critical_temperature_triggers_emergency_stop(safety_engine):
    """Test 3: A critical temperature reading triggers EMERGENCY_STOP."""
    # Global critical temperature is 85.0 °C
    reading = {
        "arm_id": "arm_2",
        "joint_id": "joint_1",
        "torque": 100.0,
        "temperature": 89.2,
        "vibration": 1.5
    }
    result = safety_engine.evaluate_reading(reading)
    assert result.status == "EMERGENCY_STOP"
    assert result.emergency_stop is True
    assert any("temperature" in v.parameter for v in result.violations)


def test_critical_vibration_triggers_emergency_stop(safety_engine):
    """Test 4: A critical vibration reading triggers EMERGENCY_STOP."""
    # Global critical vibration is 7.0 mm/s
    reading = {
        "arm_id": "arm_3",
        "joint_id": "joint_3",
        "torque": 120.0,
        "temperature": 50.0,
        "vibration": 8.4
    }
    result = safety_engine.evaluate_reading(reading)
    assert result.status == "EMERGENCY_STOP"
    assert result.emergency_stop is True
    assert any("vibration" in v.parameter for v in result.violations)


def test_missing_and_invalid_data_failsafe(safety_engine):
    """Test 14: Missing and invalid critical sensor data follows documented fail-safe policy."""
    # Case A: NaN temperature
    reading_nan = {
        "arm_id": "arm_1",
        "joint_id": "joint_2",
        "torque": 150.0,
        "temperature": float("nan"),
        "vibration": 1.5
    }
    res_nan = safety_engine.evaluate_reading(reading_nan)
    assert res_nan.status == "EMERGENCY_STOP"
    assert res_nan.emergency_stop is True
    assert res_nan.fail_safe_triggered is True

    # Case B: None / Missing torque
    reading_missing = {
        "arm_id": "arm_1",
        "joint_id": "joint_2",
        "torque": None,
        "temperature": 50.0,
        "vibration": 1.5
    }
    res_missing = safety_engine.evaluate_reading(reading_missing)
    assert res_missing.status == "EMERGENCY_STOP"
    assert res_missing.fail_safe_triggered is True

    # Case C: Infinity vibration
    reading_inf = {
        "arm_id": "arm_1",
        "joint_id": "joint_2",
        "torque": 150.0,
        "temperature": 50.0,
        "vibration": float("inf")
    }
    res_inf = safety_engine.evaluate_reading(reading_inf)
    assert res_inf.status == "EMERGENCY_STOP"
    assert res_inf.fail_safe_triggered is True


def test_safety_check_independent_of_model(safety_engine):
    """Test 6: Absence of trained model does not disable immediate safety checks."""
    # Safety engine has no ML model dependency and functions completely standalone
    reading = {
        "arm_id": "arm_4",
        "joint_id": "joint_2",
        "torque": 340.0,
        "temperature": 92.0,
        "vibration": 9.5
    }
    result = safety_engine.evaluate_reading(reading)
    assert result.status == "EMERGENCY_STOP"
    assert result.emergency_stop is True
