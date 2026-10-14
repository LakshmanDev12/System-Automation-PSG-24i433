"""Sensor integrity and anti-spoofing defense module for robotic arm telemetry.

Detects telemetry manipulation, frozen sensor attacks, replay attacks,
implausible rate-of-change, and cross-sensor inconsistencies.
"""

from collections import defaultdict, deque
from dataclasses import dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class SpoofDetectionResult:
    affected_arm_id: str
    affected_joint_id: str
    integrity_status: str  # "TRUSTED", "SUSPICIOUS", "CRITICAL_INTEGRITY_FAILURE"
    spoofing_suspected: bool
    suspicion_score: float  # [0.0, 1.0]
    detection_reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


class SpoofDetector:
    """
    Stateful and statistical sensor integrity analyzer.
    Maintains a rolling historical window per (arm_id, joint_id) to verify
    signal consistency, sensor dynamics, rate-of-change, and timestamp integrity.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        cfg = config.get("spoof_detection", {})
        self.window_size = int(cfg.get("frozen_sensor_window_size", 5))
        self.frozen_std_threshold = float(cfg.get("frozen_sensor_std_threshold", 0.0001))
        self.max_torque_roc = float(cfg.get("max_torque_rate_of_change_nm_per_sample", 120.0))
        self.max_temp_roc = float(cfg.get("max_temperature_rate_of_change_c_per_sample", 12.0))
        self.max_vib_roc = float(cfg.get("max_vibration_rate_of_change_mm_s_per_sample", 4.5))
        self.cross_sensor_z_thresh = float(cfg.get("cross_sensor_inconsistency_threshold", 3.0))
        self.warning_threshold = float(cfg.get("suspicion_warning_threshold", 0.45))
        self.critical_threshold = float(cfg.get("suspicion_critical_threshold", 0.85))

        # Rolling history buffer per (arm_id, joint_id): stores recent dicts of readings
        self._history: Dict[Tuple[str, str], deque] = defaultdict(lambda: deque(maxlen=self.window_size))
        # Known timestamps seen per arm/joint to detect replay/duplicates
        self._seen_timestamps: Dict[Tuple[str, str], set] = defaultdict(set)
        self._last_timestamp: Dict[Tuple[str, str], Optional[pd.Timestamp]] = defaultdict(lambda: None)

    def reset(self) -> None:
        """Clears all historical buffers."""
        self._history.clear()
        self._seen_timestamps.clear()
        self._last_timestamp.clear()

    def analyze_sample(self, sample: Dict[str, Any]) -> SpoofDetectionResult:
        """
        Analyzes a single sensor reading in sequence against rolling history and physical rules.
        """
        arm_id = str(sample.get("arm_id", "unknown")).strip()
        joint_id = str(sample.get("joint_id", "unknown")).strip()
        key = (arm_id, joint_id)

        reasons: List[str] = []
        metrics: Dict[str, Any] = {}
        suspicion_penalty = 0.0

        # Extract values
        try:
            curr_torque = float(sample.get("torque", 0.0))
            curr_temp = float(sample.get("temperature", 0.0))
            curr_vib = float(sample.get("vibration", 0.0))
        except (ValueError, TypeError):
            # Non-numeric readings are handled primarily by validator/safety engine,
            # but indicate untrusted input
            return SpoofDetectionResult(
                affected_arm_id=arm_id,
                affected_joint_id=joint_id,
                integrity_status="CRITICAL_INTEGRITY_FAILURE",
                spoofing_suspected=True,
                suspicion_score=1.0,
                detection_reasons=["Malformed non-numeric sensor reading in telemetry stream."],
                metrics={"malformed": True}
            )

        # 1. Timestamp Integrity: Replay and Out-of-Order Check
        raw_ts = sample.get("timestamp")
        if raw_ts is not None:
            try:
                curr_ts = pd.to_datetime(raw_ts)
                if curr_ts in self._seen_timestamps[key]:
                    reasons.append(f"Replay detected: duplicate timestamp '{raw_ts}' received for {arm_id}/{joint_id}.")
                    suspicion_penalty += 0.50
                else:
                    self._seen_timestamps[key].add(curr_ts)

                last_ts = self._last_timestamp[key]
                if last_ts is not None and curr_ts < last_ts:
                    reasons.append(f"Out-of-order telemetry: timestamp {curr_ts} is older than previous {last_ts}.")
                    suspicion_penalty += 0.40

                self._last_timestamp[key] = curr_ts
            except Exception:
                pass

        # 2. Cross-Sensor Physical Disagreement (Single-sample check)
        # Threat: Attacker fakes low vibration/torque while joint is under heavy thermal stress,
        # or reports heavy torque with absolute zero vibration and room temperature.
        if curr_torque > 150.0 and curr_temp > 70.0 and curr_vib < 0.05:
            reasons.append(
                f"Implausible cross-sensor profile: high torque ({curr_torque:.1f} Nm) and high temp "
                f"({curr_temp:.1f}°C) with near-zero vibration ({curr_vib:.3f} mm/s) suggests masked signal."
            )
            suspicion_penalty += 0.55

        if curr_vib > 6.0 and abs(curr_torque) < 1.0:
            reasons.append(
                f"Implausible cross-sensor profile: severe vibration ({curr_vib:.2f} mm/s) with near-zero torque "
                f"({curr_torque:.2f} Nm) on active arm."
            )
            suspicion_penalty += 0.40

        # Check against previous sample if available (Rate-of-Change / Teleportation)
        history = list(self._history[key])
        if len(history) >= 1:
            prev_sample = history[-1]
            prev_torque = float(prev_sample["torque"])
            prev_temp = float(prev_sample["temperature"])
            prev_vib = float(prev_sample["vibration"])

            delta_torque = abs(curr_torque - prev_torque)
            delta_temp = abs(curr_temp - prev_temp)
            delta_vib = abs(curr_vib - prev_vib)

            metrics["delta_torque"] = delta_torque
            metrics["delta_temp"] = delta_temp
            metrics["delta_vib"] = delta_vib

            if delta_torque > self.max_torque_roc:
                reasons.append(
                    f"Implausible torque step jump: {delta_torque:.1f} Nm exceeded max allowed rate "
                    f"({self.max_torque_roc:.1f} Nm/sample)."
                )
                suspicion_penalty += 0.45

            if delta_temp > self.max_temp_roc:
                reasons.append(
                    f"Physically impossible thermal jump: {delta_temp:.1f}°C exceeded thermal dissipation rate "
                    f"({self.max_temp_roc:.1f}°C/sample)."
                )
                suspicion_penalty += 0.50

            if delta_vib > self.max_vib_roc:
                reasons.append(
                    f"Implausible vibration impulse jump: {delta_vib:.2f} mm/s exceeded rate limit "
                    f"({self.max_vib_roc:.2f} mm/s/sample)."
                )
                suspicion_penalty += 0.40

        # 3. Rolling Window Statistical Checks: Frozen Sensor / Stuck Low Attack
        # Attacker injects exactly constant low readings to hide ongoing wear
        if len(history) >= (self.window_size - 1):
            window_torques = [float(h["torque"]) for h in history] + [curr_torque]
            window_temps = [float(h["temperature"]) for h in history] + [curr_temp]
            window_vibs = [float(h["vibration"]) for h in history] + [curr_vib]

            std_torque = float(np.std(window_torques))
            std_vib = float(np.std(window_vibs))
            metrics["std_torque_window"] = std_torque
            metrics["std_vib_window"] = std_vib

            # Check if vibration is artificially frozen with zero noise
            if std_vib < self.frozen_std_threshold:
                reasons.append(
                    f"Frozen sensor attack detected: vibration reading standard deviation ({std_vib:.6f}) "
                    f"is below physical sensor noise floor ({self.frozen_std_threshold}) across {len(window_vibs)} samples."
                )
                suspicion_penalty += 0.55

            # Check if all sensor values are completely identical across samples
            all_torques_identical = all(abs(t - curr_torque) < 1e-9 for t in window_torques)
            all_vibs_identical = all(abs(v - curr_vib) < 1e-9 for v in window_vibs)
            if all_torques_identical and all_vibs_identical:
                reasons.append(
                    f"Static frozen telemetry: identical torque and vibration reported consecutively for {len(window_torques)} samples."
                )
                suspicion_penalty += 0.40

            # 4. Robust Outlier / MAD Check against history
            if len(history) >= 4:
                med_vib = float(np.median(window_vibs[:-1]))
                mad_vib = float(np.median([abs(v - med_vib) for v in window_vibs[:-1]]))
                if mad_vib > 0.05:
                    mod_z = 0.6745 * abs(curr_vib - med_vib) / mad_vib
                    if mod_z > 5.0:
                        reasons.append(
                            f"Statistical anomaly: robust modified z-score ({mod_z:.2f}) indicates extreme divergence from baseline."
                        )
                        suspicion_penalty += 0.30

        # Record this sample in history
        self._history[key].append(sample)

        # Cap suspicion score between 0.0 and 1.0
        final_suspicion_score = min(1.0, max(0.0, suspicion_penalty))

        # Determine integrity status
        if final_suspicion_score >= self.critical_threshold:
            status = "CRITICAL_INTEGRITY_FAILURE"
            spoofing = True
        elif final_suspicion_score >= self.warning_threshold:
            status = "SUSPICIOUS"
            spoofing = True
        else:
            status = "TRUSTED"
            spoofing = False

        return SpoofDetectionResult(
            affected_arm_id=arm_id,
            affected_joint_id=joint_id,
            integrity_status=status,
            spoofing_suspected=spoofing,
            suspicion_score=round(final_suspicion_score, 4),
            detection_reasons=reasons,
            metrics=metrics
        )

    def analyze_batch(self, df: pd.DataFrame) -> List[SpoofDetectionResult]:
        """
        Analyzes a chronological DataFrame of sensor readings.
        """
        results: List[SpoofDetectionResult] = []
        for _, row in df.iterrows():
            record = row.to_dict()
            results.append(self.analyze_sample(record))
        return results
