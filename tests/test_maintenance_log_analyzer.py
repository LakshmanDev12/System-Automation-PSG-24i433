"""Tests for maintenance log natural language analyzer."""

import pytest
from src.config_loader import load_config
from src.maintenance_log_analyzer import MaintenanceLogAnalyzer


@pytest.fixture
def config():
    return load_config()


@pytest.fixture
def analyzer(config):
    return MaintenanceLogAnalyzer(config)


def test_relevant_unresolved_notes_increase_concern(analyzer):
    """Test 9: Relevant unresolved maintenance notes increase maintenance concern."""
    log_text = "2026-10-12 - Arm 3 joint 2 - Abnormal clicking noise and severe gearbox backlash increased during operation."
    analyzer.process_log_file(log_text)

    score, active, expl = analyzer.get_arm_concern("arm_3")
    assert score >= 0.50
    assert len(active) >= 1
    assert "clicking noise" in expl[0].lower() or "backlash" in expl[0].lower()


def test_irrelevant_notes_do_not_trigger_maintenance(analyzer):
    """Test 10: Irrelevant maintenance notes do not independently trigger maintenance."""
    irrelevant_logs = [
        "2026-10-11 - Arm 1 - Production schedule updated for shift 2.",
        "2026-10-12 - Assembly line cleaned and floor swept.",
        "2026-10-13 - Operator shift changed across Line 4.",
        "2026-10-14 - Routine inventory verification completed in sector A."
    ]
    analyzer.process_log_file("\n".join(irrelevant_logs))

    for arm_num in range(1, 7):
        score, active, _ = analyzer.get_arm_concern(f"arm_{arm_num}")
        assert score == 0.0
        assert len(active) == 0


def test_documented_repair_clears_concern(analyzer):
    """Test 11: A documented repair is interpreted differently from an unresolved fault."""
    # First: Log a fault on Arm 2 joint 3 (elbow)
    fault_log = "2026-10-10 - Arm 2 joint 3 - Increasing vibration observed near the elbow joint."
    analyzer.process_log_file(fault_log)

    score_before, active_before, _ = analyzer.get_arm_concern("arm_2")
    assert score_before > 0.0
    assert len(active_before) == 1

    # Second: Log verified repair on Arm 2 joint 3
    repair_log = "2026-10-11 - Arm 2 joint 3 - Bearing replaced and lubrication completed. Restored to nominal."
    analyzer.process_log_file(repair_log)

    score_after, active_after, _ = analyzer.get_arm_concern("arm_2")
    # Concern must be cleared / reduced to zero
    assert score_after == 0.0
    assert len(active_after) == 0

    # Resolved issues list must preserve the historical context
    j3_status = analyzer.statuses[("arm_2", "joint_3")]
    assert len(j3_status.resolved_issues) >= 1
