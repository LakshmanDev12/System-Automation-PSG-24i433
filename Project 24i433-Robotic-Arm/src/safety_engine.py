"""Deterministic rule-based safety engine for robotic arm joint monitoring.

IMPORTANT DISCLAIMER:
This module is a software simulation and demonstration. It is NOT a certified industrial
safety controller (e.g., ISO 13849 PL-e, IEC 61508 SIL-3, IEC 62061). Real-world industrial
machinery requires independently validated hardware interlocks, dual-channel fail-safe safety
relays, and certified hardware emergency-stop circuits.
"""

from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional
import pandas as pd


@dataclass
class SafetyViolation:
    parameter: str
    observed_value: Any
    threshold: float
    severity: str  # "WARNING" or "CRITICAL"
    message: str


@dataclass
class SafetyCheckResult:
    arm_id: str
    joint_id: str
    status: str  # "SAFE", "WARNING", "EMERGENCY_STOP"
    emergency_stop: bool
    violations: List[SafetyViolation] = field(default_factory=list)
    fail_safe_triggered: bool = False
    reasons: List[str] = field(default_factory=list)
    disclaimer: str = (
        "Simulation only: Hardware safety controller required in actual industrial operations."
    )


class SafetyEngine:
    """
    Deterministic rule-based safety engine.
    Operates strictly prior to and independently of any machine learning models,
    anomaly detectors, or historical analysis.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.global_thresholds = config.get("global_safety_thresholds", {})
        self.joint_thresholds = config.get("joint_specific_thresholds", {})
        self.fail_safe_policy = config.get("fail_safe_policy", {})

    def evaluate_reading(self, reading: Dict[str, Any]) -> SafetyCheckResult:
        """
        Inspects an individual joint reading and immediately evaluates deterministic safety rules.

        Args:
            reading: Dictionary containing arm_id, joint_id, torque, temperature, vibration, etc.

        Returns:
            SafetyCheckResult indicating SAFE, WARNING, or EMERGENCY_STOP.
        """
        arm_id = str(reading.get("arm_id", "unknown")).strip()
        joint_id = str(reading.get("joint_id", "unknown")).strip()

        violations: List[SafetyViolation] = []
        fail_safe_active = self.fail_safe_policy.get("fail_safe_on_critical_missing", True)

        # 1. Check for Missing or Non-numeric Telemetry (Fail-Safe Policy)
        for param in ["torque", "temperature", "vibration"]:
            raw_val = reading.get(param)
            if raw_val is None or pd.isna(raw_val):
                if fail_safe_active:
                    v = SafetyViolation(
                        parameter=param,
                        observed_value=raw_val,
                        threshold=0.0,
                        severity="CRITICAL",
                        message=f"Critical sensor telemetry missing or NaN for {param} on {arm_id}/{joint_id}."
                    )
                    violations.append(v)
                continue

            try:
                num_val = float(raw_val)
            except (ValueError, TypeError):
                if fail_safe_active:
                    v = SafetyViolation(
                        parameter=param,
                        observed_value=raw_val,
                        threshold=0.0,
                        severity="CRITICAL",
                        message=f"Malformed non-numeric sensor reading '{raw_val}' for {param} on {arm_id}/{joint_id}."
                    )
                    violations.append(v)
                continue

            if math.isnan(num_val) or math.isinf(num_val):
                if fail_safe_active:
                    v = SafetyViolation(
                        parameter=param,
                        observed_value=num_val,
                        threshold=0.0,
                        severity="CRITICAL",
                        message=f"Sensor telemetry is NaN or Infinite for {param} on {arm_id}/{joint_id}."
                    )
                    violations.append(v)
                continue

        # If any fail-safe violation occurred above, trigger immediate EMERGENCY_STOP
        if any(v.severity == "CRITICAL" for v in violations):
            return SafetyCheckResult(
                arm_id=arm_id,
                joint_id=joint_id,
                status="EMERGENCY_STOP",
                emergency_stop=True,
                violations=violations,
                fail_safe_triggered=True,
                reasons=[v.message for v in violations]
            )

        # 2. Check Temperature Thresholds
        temp = float(reading["temperature"])
        t_cfg = self.global_thresholds.get("temperature_celsius", {})
        t_warn = t_cfg.get("warning", 75.0)
        t_crit = t_cfg.get("critical", 85.0)
        t_pmin = t_cfg.get("physical_min", -20.0)
        t_pmax = t_cfg.get("physical_max", 150.0)

        if temp < t_pmin or temp > t_pmax:
            # Physical impossibility triggers fail-safe stop
            violations.append(
                SafetyViolation(
                    parameter="temperature",
                    observed_value=temp,
                    threshold=t_crit,
                    severity="CRITICAL",
                    message=f"Temperature {temp:.1f}°C is outside physical boundaries [{t_pmin}, {t_pmax}]."
                )
            )
        elif temp >= t_crit:
            violations.append(
                SafetyViolation(
                    parameter="temperature",
                    observed_value=temp,
                    threshold=t_crit,
                    severity="CRITICAL",
                    message=f"Critical temperature threshold crossed: {temp:.1f}°C >= {t_crit:.1f}°C."
                )
            )
        elif temp >= t_warn:
            violations.append(
                SafetyViolation(
                    parameter="temperature",
                    observed_value=temp,
                    threshold=t_warn,
                    severity="WARNING",
                    message=f"Temperature warning limit exceeded: {temp:.1f}°C >= {t_warn:.1f}°C."
                )
            )

        # 3. Check Vibration Thresholds
        vib = float(reading["vibration"])
        v_cfg = self.global_thresholds.get("vibration_rms_mm_s", {})
        v_warn = v_cfg.get("warning", 4.5)
        v_crit = v_cfg.get("critical", 7.0)
        v_pmin = v_cfg.get("physical_min", 0.0)
        v_pmax = v_cfg.get("physical_max", 50.0)

        if vib < v_pmin or vib > v_pmax:
            violations.append(
                SafetyViolation(
                    parameter="vibration",
                    observed_value=vib,
                    threshold=v_crit,
                    severity="CRITICAL",
                    message=f"Vibration {vib:.2f} mm/s is outside physical boundaries [{v_pmin}, {v_pmax}]."
                )
            )
        elif vib >= v_crit:
            violations.append(
                SafetyViolation(
                    parameter="vibration",
                    observed_value=vib,
                    threshold=v_crit,
                    severity="CRITICAL",
                    message=f"Critical vibration threshold crossed: {vib:.2f} mm/s >= {v_crit:.2f} mm/s."
                )
            )
        elif vib >= v_warn:
            violations.append(
                SafetyViolation(
                    parameter="vibration",
                    observed_value=vib,
                    threshold=v_warn,
                    severity="WARNING",
                    message=f"Vibration warning limit exceeded: {vib:.2f} mm/s >= {v_warn:.2f} mm/s."
                )
            )

        # 4. Check Torque Thresholds (Joint-Specific)
        torque = float(reading["torque"])
        j_cfg = self.joint_thresholds.get(joint_id, {})
        def_tq = self.global_thresholds.get("torque_nm_default", {})

        torque_warn = j_cfg.get("torque_warning_nm", def_tq.get("warning", 180.0))
        torque_crit = j_cfg.get("torque_critical_nm", def_tq.get("critical", 220.0))
        torque_mag = abs(torque)

        if torque_mag >= torque_crit:
            violations.append(
                SafetyViolation(
                    parameter="torque",
                    observed_value=torque,
                    threshold=torque_crit,
                    severity="CRITICAL",
                    message=f"Critical torque threshold crossed on {joint_id}: |{torque:.1f}| Nm >= {torque_crit:.1f} Nm."
                )
            )
        elif torque_mag >= torque_warn:
            violations.append(
                SafetyViolation(
                    parameter="torque",
                    observed_value=torque,
                    threshold=torque_warn,
                    severity="WARNING",
                    message=f"Torque warning limit exceeded on {joint_id}: |{torque:.1f}| Nm >= {torque_warn:.1f} Nm."
                )
            )

        # 5. Determine Overall Safety Status
        has_critical = any(v.severity == "CRITICAL" for v in violations)
        has_warning = any(v.severity == "WARNING" for v in violations)

        if has_critical:
            status = "EMERGENCY_STOP"
            is_e_stop = True
        elif has_warning:
            status = "WARNING"
            is_e_stop = False
        else:
            status = "SAFE"
            is_e_stop = False

        return SafetyCheckResult(
            arm_id=arm_id,
            joint_id=joint_id,
            status=status,
            emergency_stop=is_e_stop,
            violations=violations,
            fail_safe_triggered=False,
            reasons=[v.message for v in violations]
        )

    def evaluate_batch(self, df: pd.DataFrame) -> List[SafetyCheckResult]:
        """Evaluates deterministic safety on a pandas DataFrame of telemetry."""
        results = []
        for _, row in df.iterrows():
            record = row.to_dict()
            results.append(self.evaluate_reading(record))
        return results
