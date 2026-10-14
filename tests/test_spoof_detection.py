"""Tests for sensor integrity and anti-spoofing defense module."""

import pytest
from src.config_loader import load_config
from src.spoof_detection import SpoofDetector


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def detector(config):
    return SpoofDetector(config)


def test_repeated_suspicious_readings_trigger_warning(detector):
    """Test 12: Repeated suspicious frozen sensor readings trigger an integrity warning."""
    arm_id = "arm_5"
    joint_id = "joint_2"

    # Feed 6 samples with identical frozen vibration (0.010 mm/s)
    last_res = None
    for i in range(6):
        sample = {
            "timestamp": f"2026-10-14 10:0{i}:00",
            "arm_id": arm_id,
            "joint_id": joint_id,
            "torque": 150.0,
            "temperature": 55.0,
            "vibration": 0.010  # Frozen zero variance
        }
        last_res = detector.analyze_sample(sample)

    assert last_res is not None
    assert last_res.spoofing_suspected is True
    assert last_res.suspicion_score > 0.40
    assert any("Frozen sensor" in r or "frozen" in r.lower() for r in last_res.detection_reasons)


def test_duplicate_replayed_timestamps_detected(detector):
    """Test 13: Duplicate or replayed timestamps are detected."""
    sample1 = {
        "timestamp": "2026-10-14 12:00:00",
        "arm_id": "arm_3",
        "joint_id": "joint_1",
        "torque": 80.0,
        "temperature": 40.0,
        "vibration": 1.2
    }
    detector.analyze_sample(sample1)

    # Replay exact same timestamp
    sample2 = {
        "timestamp": "2026-10-14 12:00:00",
        "arm_id": "arm_3",
        "joint_id": "joint_1",
        "torque": 85.0,
        "temperature": 41.0,
        "vibration": 1.3
    }
    res2 = detector.analyze_sample(sample2)
    assert res2.spoofing_suspected is True
    assert any("Replay detected" in r for r in res2.detection_reasons)


def test_spoofed_low_reading_with_cross_sensor_contradiction(detector):
    """Test 17: Spoofed low sensor readings cannot override independently observed critical evidence."""
    # Joint under massive torque and high thermal load, but vibration reported as 0.01 mm/s
    sample = {
        "timestamp": "2026-10-14 12:05:00",
        "arm_id": "arm_2",
        "joint_id": "joint_2",
        "torque": 220.0,
        "temperature": 78.0,
        "vibration": 0.01  # Artificially low vibration masking mechanical damage
    }
    res = detector.analyze_sample(sample)
    assert res.spoofing_suspected is True
    assert res.suspicion_score >= 0.45
    assert any("Implausible cross-sensor profile" in r for r in res.detection_reasons)


def test_implausible_rate_of_change(detector):
    """Test rate-of-change teleportation jump detection."""
    sample1 = {
        "timestamp": "2026-10-14 12:10:00",
        "arm_id": "arm_1",
        "joint_id": "joint_2",
        "torque": 120.0,
        "temperature": 45.0,
        "vibration": 1.2
    }
    detector.analyze_sample(sample1)

    # Impossible thermal jump of 30°C in a single sample
    sample2 = {
        "timestamp": "2026-10-14 12:10:05",
        "arm_id": "arm_1",
        "joint_id": "joint_2",
        "torque": 120.0,
        "temperature": 75.0,
        "vibration": 1.2
    }
    res2 = detector.analyze_sample(sample2)
    assert res2.spoofing_suspected is True
    assert any("thermal jump" in r.lower() for r in res2.detection_reasons)
