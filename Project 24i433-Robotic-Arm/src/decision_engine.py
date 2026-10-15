"""Decision engine aggregating multi-joint telemetry, safety, spoofing, and predictive health.

Enforces strict priority precedence to produce exactly one definitive decision per robotic arm:
1. EMERGENCY_STOP
2. SCHEDULE_MAINTENANCE
3. MONITOR
4. SAFE
"""

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
import pandas as pd

from src.maintenance_log_analyzer import MaintenanceLogAnalyzer
from src.predictive_model import PredictiveModel
from src.safety_engine import SafetyCheckResult, SafetyEngine
from src.spoof_detection import SpoofDetectionResult, SpoofDetector


@dataclass
class JointDiagnostic:
    arm_id: str
    joint_id: str
    torque: float
    temperature: float
    vibration: float
    safety_status: str
    safety_emergency_stop: bool
    predictive_risk: float
    integrity_status: str
    suspicion_score: float
    maintenance_concern: float
    reasons: List[str] = field(default_factory=list)


@dataclass
class ArmHealthDecision:
    arm_id: str
    final_decision: str  # "SAFE", "MONITOR", "SCHEDULE_MAINTENANCE", "EMERGENCY_STOP"
    highest_risk_joint: str
    maximum_failure_risk: float
    emergency_stop_triggered: bool
    sensor_integrity_status: str  # "TRUSTED", "SUSPICIOUS", "CRITICAL_INTEGRITY_FAILURE"
    maintenance_concern_score: float
    reasons: List[str]
    recommended_action: str
    timestamp: str
    joint_diagnostics: List[JointDiagnostic] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        return d


class DecisionEngine:
    """
    Evaluates multi-source diagnostic evidence across all joints of each robotic arm.
    Guarantees deterministic safety precedence over machine learning predictions.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        pm_cfg = config.get("predictive_maintenance", {})
        mla_cfg = config.get("maintenance_log_analysis", {})
        sd_cfg = config.get("spoof_detection", {})

        self.pm_monitor_risk = float(pm_cfg.get("monitor_risk_threshold", 0.35))
        self.pm_maint_risk = float(pm_cfg.get("maintenance_risk_threshold", 0.70))

        self.mla_monitor_concern = float(mla_cfg.get("monitor_concern_threshold", 0.30))
        self.mla_maint_concern = float(mla_cfg.get("maintenance_concern_threshold", 0.60))

        self.sd_crit_suspicion = float(sd_cfg.get("suspicion_critical_threshold", 0.85))

    def evaluate_arm(
        self,
        arm_id: str,
        joint_readings: List[Dict[str, Any]],
        safety_results: List[SafetyCheckResult],
        spoof_results: List[SpoofDetectionResult],
        predictive_risks: List[float],
        maint_analyzer: Optional[MaintenanceLogAnalyzer] = None,
        timestamp: Optional[str] = None
    ) -> ArmHealthDecision:
        """
        Aggregates evidence across all joints for an arm and produces exactly one decision.
        """
        now_ts = timestamp or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

        # Combine results into JointDiagnostic list
        diagnostics: List[JointDiagnostic] = []
        max_pred_risk = 0.0
        highest_risk_j = "joint_1"
        any_e_stop = False
        e_stop_reasons: List[str] = []

        overall_integrity = "TRUSTED"
        integrity_priority = {"TRUSTED": 0, "SUSPICIOUS": 1, "CRITICAL_INTEGRITY_FAILURE": 2}
        highest_suspicion_score = 0.0

        for idx, reading in enumerate(joint_readings):
            j_id = str(reading.get("joint_id", f"joint_{idx+1}")).strip()
            s_res = safety_results[idx]
            sp_res = spoof_results[idx]
            p_risk = round(float(predictive_risks[idx]), 4) if idx < len(predictive_risks) else 0.0

            # Get maintenance status for this joint if available
            j_maint_concern = 0.0
            if maint_analyzer:
                status_obj = maint_analyzer.statuses.get((arm_id, j_id))
                if status_obj:
                    j_maint_concern = status_obj.concern_score

            reasons_j = []
            if s_res.reasons:
                reasons_j.extend(s_res.reasons)
            if sp_res.detection_reasons:
                reasons_j.extend(sp_res.detection_reasons)

            diag = JointDiagnostic(
                arm_id=arm_id,
                joint_id=j_id,
                torque=float(reading.get("torque", 0.0)),
                temperature=float(reading.get("temperature", 0.0)),
                vibration=float(reading.get("vibration", 0.0)),
                safety_status=s_res.status,
                safety_emergency_stop=s_res.emergency_stop,
                predictive_risk=p_risk,
                integrity_status=sp_res.integrity_status,
                suspicion_score=sp_res.suspicion_score,
                maintenance_concern=j_maint_concern,
                reasons=reasons_j
            )
            diagnostics.append(diag)

            if s_res.emergency_stop:
                any_e_stop = True
                e_stop_reasons.extend([f"[{j_id}] {r}" for r in s_res.reasons])

            if sp_res.integrity_status == "CRITICAL_INTEGRITY_FAILURE":
                any_e_stop = True
                e_stop_reasons.extend([f"[{j_id} Telemetry Integrity Compromised] {r}" for r in sp_res.detection_reasons])

            if integrity_priority.get(sp_res.integrity_status, 0) > integrity_priority.get(overall_integrity, 0):
                overall_integrity = sp_res.integrity_status

            if sp_res.suspicion_score > highest_suspicion_score:
                highest_suspicion_score = sp_res.suspicion_score

            if p_risk > max_pred_risk:
                max_pred_risk = p_risk
                highest_risk_j = j_id

        # Maintenance concern at arm level
        arm_maint_concern = 0.0
        maint_active_notes: List[str] = []
        if maint_analyzer:
            score, active, _ = maint_analyzer.get_arm_concern(arm_id)
            arm_maint_concern = score
            maint_active_notes = active

        # PRECEDENCE EVALUATION
        final_decision: str
        recommended_action: str
        arm_reasons: List[str] = []

        # 1. EMERGENCY_STOP
        if any_e_stop:
            final_decision = "EMERGENCY_STOP"
            recommended_action = (
                "IMMEDIATE SAFETY SHUTDOWN: Cut motor power, engage mechanical brakes, "
                "lock out and tag out (LOTO) robotic arm. Inspect affected joints before restart."
            )
            arm_reasons = e_stop_reasons or ["Critical deterministic threshold or telemetry integrity failure."]

        # 2. SCHEDULE_MAINTENANCE
        elif (max_pred_risk >= self.pm_maint_risk) or (arm_maint_concern >= self.mla_maint_concern):
            final_decision = "SCHEDULE_MAINTENANCE"
            trigger_reasons = []
            if max_pred_risk >= self.pm_maint_risk:
                trigger_reasons.append(
                    f"High predictive failure risk ({max_pred_risk:.2%}) on {highest_risk_j} within 24 hours."
                )
            if arm_maint_concern >= self.mla_maint_concern:
                trigger_reasons.append(
                    f"High maintenance concern score ({arm_maint_concern:.2f}) from unresolved technician logs: {maint_active_notes[:2]}"
                )
            arm_reasons = trigger_reasons
            recommended_action = (
                f"Schedule mechanical maintenance window within 12-24 hours for {highest_risk_j}. "
                "Prepare replacement bearings/gearbox components and review log history."
            )

        # 3. MONITOR
        elif (
            (max_pred_risk >= self.pm_monitor_risk)
            or (arm_maint_concern >= self.mla_monitor_concern)
            or (overall_integrity == "SUSPICIOUS")
            or any(d.safety_status == "WARNING" for d in diagnostics)
        ):
            final_decision = "MONITOR"
            trigger_reasons = []
            if max_pred_risk >= self.pm_monitor_risk:
                trigger_reasons.append(
                    f"Elevated predictive wear risk ({max_pred_risk:.2%}) on {highest_risk_j}."
                )
            if arm_maint_concern >= self.mla_monitor_concern:
                trigger_reasons.append(
                    f"Active maintenance observation recorded (concern score: {arm_maint_concern:.2f})."
                )
            if overall_integrity == "SUSPICIOUS":
                trigger_reasons.append(
                    f"Sensor telemetry integrity flagged as SUSPICIOUS (suspicion score: {highest_suspicion_score:.2f})."
                )
            for d in diagnostics:
                if d.safety_status == "WARNING":
                    trigger_reasons.append(f"Safety warning on {d.joint_id}: {d.reasons}")

            arm_reasons = trigger_reasons
            recommended_action = (
                f"Increase telemetry polling rate, perform visual and acoustic inspection during next shift, "
                f"and monitor {highest_risk_j} vibration and thermal trends."
            )

        # 4. SAFE
        else:
            final_decision = "SAFE"
            arm_reasons = [
                "All 6 joints operating within normal safety limits. Telemetry integrity verified and predictive risk nominal."
            ]
            recommended_action = "Continue standard automated production operations."

        return ArmHealthDecision(
            arm_id=arm_id,
            final_decision=final_decision,
            highest_risk_joint=highest_risk_j,
            maximum_failure_risk=round(max_pred_risk, 4),
            emergency_stop_triggered=(final_decision == "EMERGENCY_STOP"),
            sensor_integrity_status=overall_integrity,
            maintenance_concern_score=round(arm_maint_concern, 4),
            reasons=arm_reasons,
            recommended_action=recommended_action,
            timestamp=now_ts,
            joint_diagnostics=diagnostics
        )
