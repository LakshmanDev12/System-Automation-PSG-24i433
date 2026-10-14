"""Tests for multi-joint decision engine and priority precedence."""

import pytest
from src.config_loader import load_config
from src.decision_engine import DecisionEngine
from src.safety_engine import SafetyCheckResult, SafetyViolation
from src.spoof_detection import SpoofDetectionResult


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def decision_engine(config):
    return DecisionEngine(config)


def _make_dummy_joint_data(arm_id="arm_1", base_status="SAFE"):
    readings = []
    safety_results = []
    spoof_results = []
    predictive_risks = []

    for i in range(1, 7):
        j_id = f"joint_{i}"
        readings.append({"arm_id": arm_id, "joint_id": j_id, "torque": 100.0, "temperature": 45.0, "vibration": 1.2})
        safety_results.append(SafetyCheckResult(
            arm_id=arm_id,
            joint_id=j_id,
            status=base_status,
            emergency_stop=False
        ))
        spoof_results.append(SpoofDetectionResult(
            affected_arm_id=arm_id,
            affected_joint_id=j_id,
            integrity_status="TRUSTED",
            spoofing_suspected=False,
            suspicion_score=0.0
        ))
        predictive_risks.append(0.10)

    return readings, safety_results, spoof_results, predictive_risks


def test_normal_telemetry_produces_safe(decision_engine):
    """Test 1: Normal telemetry with no concerns produces SAFE."""
    readings, safety, spoof, risks = _make_dummy_joint_data("arm_1")
    decision = decision_engine.evaluate_arm(
        arm_id="arm_1",
        joint_readings=readings,
        safety_results=safety,
        spoof_results=spoof,
        predictive_risks=risks
    )
    assert decision.final_decision == "SAFE"
    assert decision.emergency_stop_triggered is False
    assert decision.sensor_integrity_status == "TRUSTED"


def test_emergency_stop_cannot_be_overridden_by_low_risk(decision_engine):
    """Test 5: An emergency stop cannot be overridden by a low model-risk prediction."""
    readings, safety, spoof, risks = _make_dummy_joint_data("arm_6")

    # Joint 2 has a critical safety violation (torque excursion)
    safety[1] = SafetyCheckResult(
        arm_id="arm_6",
        joint_id="joint_2",
        status="EMERGENCY_STOP",
        emergency_stop=True,
        violations=[
            SafetyViolation(
                parameter="torque",
                observed_value=340.0,
                threshold=320.0,
                severity="CRITICAL",
                message="Critical torque threshold exceeded: 340.0 Nm >= 320.0 Nm"
            )
        ],
        reasons=["Critical torque threshold exceeded."]
    )
    # ML model predicts ultra-low failure risk (e.g. 0.02)
    risks = [0.02] * 6

    decision = decision_engine.evaluate_arm(
        arm_id="arm_6",
        joint_readings=readings,
        safety_results=safety,
        spoof_results=spoof,
        predictive_risks=risks
    )
    # MUST BE EMERGENCY_STOP! Low model risk cannot override safety!
    assert decision.final_decision == "EMERGENCY_STOP"
    assert decision.emergency_stop_triggered is True


def test_moderate_predictive_risk_produces_monitor(decision_engine):
    """Test 7: Moderate predictive risk produces MONITOR."""
    readings, safety, spoof, risks = _make_dummy_joint_data("arm_2")
    # Set moderate risk (0.45) on joint 3 (elbow), where monitor threshold is 0.35 and maintenance is 0.70
    risks[2] = 0.45

    decision = decision_engine.evaluate_arm(
        arm_id="arm_2",
        joint_readings=readings,
        safety_results=safety,
        spoof_results=spoof,
        predictive_risks=risks
    )
    assert decision.final_decision == "MONITOR"
    assert decision.highest_risk_joint == "joint_3"
    assert decision.maximum_failure_risk == 0.45


def test_high_predictive_risk_produces_schedule_maintenance(decision_engine):
    """Test 8: High predictive risk produces SCHEDULE_MAINTENANCE."""
    readings, safety, spoof, risks = _make_dummy_joint_data("arm_3")
    # Set high risk (0.82) on joint 2 (shoulder), exceeding maintenance threshold 0.70
    risks[1] = 0.82

    decision = decision_engine.evaluate_arm(
        arm_id="arm_3",
        joint_readings=readings,
        safety_results=safety,
        spoof_results=spoof,
        predictive_risks=risks
    )
    assert decision.final_decision == "SCHEDULE_MAINTENANCE"
    assert decision.highest_risk_joint == "joint_2"
    assert decision.maximum_failure_risk == 0.82


def test_exactly_one_valid_final_decision(decision_engine):
    """Test 15: Every robotic arm receives exactly one valid final decision."""
    valid_decisions = {"SAFE", "MONITOR", "SCHEDULE_MAINTENANCE", "EMERGENCY_STOP"}

    for arm_idx in range(1, 7):
        arm_id = f"arm_{arm_idx}"
        readings, safety, spoof, risks = _make_dummy_joint_data(arm_id)
        decision = decision_engine.evaluate_arm(
            arm_id=arm_id,
            joint_readings=readings,
            safety_results=safety,
            spoof_results=spoof,
            predictive_risks=risks
        )
        assert decision.arm_id == arm_id
        assert decision.final_decision in valid_decisions


def test_multiple_joint_level_alerts_aggregation(decision_engine):
    """Test 16: Multiple joint-level alerts are correctly aggregated to the arm level."""
    readings, safety, spoof, risks = _make_dummy_joint_data("arm_4")

    # Joint 1 has warning status
    safety[0] = SafetyCheckResult(arm_id="arm_4", joint_id="joint_1", status="WARNING", emergency_stop=False)
    # Joint 3 has moderate risk
    risks[2] = 0.42
    # Joint 5 has suspicious integrity
    spoof[4] = SpoofDetectionResult(
        affected_arm_id="arm_4",
        affected_joint_id="joint_5",
        integrity_status="SUSPICIOUS",
        spoofing_suspected=True,
        suspicion_score=0.55
    )

    decision = decision_engine.evaluate_arm(
        arm_id="arm_4",
        joint_readings=readings,
        safety_results=safety,
        spoof_results=spoof,
        predictive_risks=risks
    )
    # Aggregated arm status reflects the elevated joint alerts
    assert decision.final_decision == "MONITOR"
    assert decision.sensor_integrity_status == "SUSPICIOUS"
    assert len(decision.joint_diagnostics) == 6
