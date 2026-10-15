"""Synthetic dataset generator for robotic arm joint health monitoring.

Generates realistic historical training data, current telemetry for 6 arms,
technician maintenance logs, and sensor spoofing test cases.
Reproducible using a fixed random seed.
"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple
import numpy as np
import pandas as pd

RANDOM_SEED = 42

# Joint definitions and nominal base parameters
JOINT_CONFIGS = {
    "joint_1": {"name": "Base", "base_torque": 90.0, "torque_sigma": 15.0, "base_temp": 42.0, "base_vib": 1.2},
    "joint_2": {"name": "Shoulder", "base_torque": 160.0, "torque_sigma": 30.0, "base_temp": 48.0, "base_vib": 1.5},
    "joint_3": {"name": "Elbow", "base_torque": 110.0, "torque_sigma": 20.0, "base_temp": 46.0, "base_vib": 1.4},
    "joint_4": {"name": "Wrist 1", "base_torque": 25.0, "torque_sigma": 6.0, "base_temp": 38.0, "base_vib": 0.9},
    "joint_5": {"name": "Wrist 2", "base_torque": 20.0, "torque_sigma": 5.0, "base_temp": 37.0, "base_vib": 0.8},
    "joint_6": {"name": "Wrist 3", "base_torque": 15.0, "torque_sigma": 4.0, "base_temp": 36.0, "base_vib": 0.8},
}


def generate_historical_dataset(
    num_samples: int = 1800,
    random_seed: int = RANDOM_SEED
) -> pd.DataFrame:
    """
    Generates synthetic historical training data with realistic degradation correlations,
    wear dynamics, and binary failure_within_24h labels.

    DISCLAIMER: The failure labels are generated via a synthetic mathematical risk function
    and must not be construed as real-world field failure data.
    """
    rng = np.random.default_rng(random_seed)

    records: List[Dict[str, Any]] = []
    base_time = datetime(2026, 1, 1, 8, 0, 0)

    arms = [f"arm_{i}" for i in range(1, 7)]
    joints = [f"joint_{j}" for j in range(1, 7)]

    # Generate sequential chronological telemetry across arms and joints
    step_minutes = 15
    current_time = base_time

    samples_per_joint = max(1, num_samples // (len(arms) * len(joints)))

    for step in range(samples_per_joint):
        current_time += timedelta(minutes=step_minutes)
        for arm_id in arms:
            for joint_id in joints:
                j_info = JOINT_CONFIGS[joint_id]

                # Component age and baseline usage
                operating_hours = float(rng.uniform(100.0, 8000.0) + step * 0.25)
                maintenance_age_hours = float(rng.uniform(10.0, 2500.0) + step * 0.25)
                previous_failure_count = int(rng.choice([0, 1, 2, 3], p=[0.70, 0.20, 0.08, 0.02]))
                sensor_quality = float(rng.uniform(0.92, 1.0))

                # Degradation progression state
                # Most components are healthy, but some experience wear acceleration
                wear_factor = (maintenance_age_hours / 2500.0) ** 1.8
                is_degrading = rng.random() < 0.12  # ~12% in degrading state

                if is_degrading:
                    vib_boost = rng.uniform(2.0, 4.8) * wear_factor
                    temp_boost = rng.uniform(10.0, 28.0) * wear_factor
                    torque_boost = rng.uniform(1.1, 1.45)
                else:
                    vib_boost = rng.uniform(-0.2, 0.5)
                    temp_boost = rng.uniform(-3.0, 6.0)
                    torque_boost = rng.uniform(0.92, 1.08)

                torque = round(float(j_info["base_torque"] * torque_boost + rng.normal(0, j_info["torque_sigma"] * 0.3)), 2)
                temperature = round(float(j_info["base_temp"] + temp_boost + rng.normal(0, 1.5)), 2)
                vibration = round(float(max(0.2, j_info["base_vib"] + vib_boost + rng.normal(0, 0.15))), 3)

                # Physics-informed synthetic failure probability within 24h
                # Function of vibration, temperature, maintenance age, and torque
                norm_vib = max(0.0, (vibration - 1.5) / 3.0)
                norm_temp = max(0.0, (temperature - 55.0) / 25.0)
                norm_age = min(1.0, maintenance_age_hours / 2500.0)
                norm_prev_fail = previous_failure_count / 3.0

                # Logistic-like synthetic risk score
                logit = (
                    -3.2
                    + 2.8 * norm_vib
                    + 2.1 * norm_temp
                    + 1.5 * norm_age
                    + 1.0 * norm_prev_fail
                    + rng.normal(0, 0.4)
                )
                fail_prob = 1.0 / (1.0 + np.exp(-logit))
                failure_within_24h = int(fail_prob >= 0.50)

                records.append({
                    "timestamp": current_time.isoformat(),
                    "arm_id": arm_id,
                    "joint_id": joint_id,
                    "torque": torque,
                    "temperature": temperature,
                    "vibration": vibration,
                    "operating_hours": round(operating_hours, 1),
                    "maintenance_age_hours": round(maintenance_age_hours, 1),
                    "previous_failure_count": previous_failure_count,
                    "sensor_quality": round(sensor_quality, 3),
                    "failure_within_24h": failure_within_24h,
                })

    df = pd.DataFrame(records)
    # Sort chronologically
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df = df.sort_values(by="timestamp").reset_index(drop=True)
    df["timestamp"] = df["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
    return df


def generate_current_telemetry() -> pd.DataFrame:
    """
    Generates current snapshot telemetry for all 6 arms and all 6 joints (36 total rows).
    Configured so different arms clearly exercise all four final decisions:
      - arm_1: SAFE (nominal operation)
      - arm_2: MONITOR (moderate vibration wear & moderate ML risk)
      - arm_3: SCHEDULE_MAINTENANCE (high wear, severe gearbox vibration)
      - arm_4: EMERGENCY_STOP (critical temperature spike crossing safety limit)
      - arm_5: EMERGENCY_STOP (compromised sensor integrity / frozen attack)
      - arm_6: EMERGENCY_STOP (critical torque excursion despite low ML risk)
    """
    timestamp_str = "2026-10-14 14:00:00"
    records: List[Dict[str, Any]] = []

    for arm_num in range(1, 7):
        arm_id = f"arm_{arm_num}"
        for joint_num in range(1, 7):
            joint_id = f"joint_{joint_num}"
            j_info = JOINT_CONFIGS[joint_id]

            torque = float(j_info["base_torque"])
            temp = float(j_info["base_temp"])
            vib = float(j_info["base_vib"])
            op_hours = 2500.0 + joint_num * 100.0
            maint_age = 400.0 + joint_num * 50.0
            prev_fails = 0
            quality = 0.98

            if arm_id == "arm_1":
                # Healthy SAFE arm
                torque += 2.0
                temp += 1.0
                vib += 0.1

            elif arm_id == "arm_2":
                # MONITOR arm: moderate wear & moderate predictive risk on elbow (joint_3)
                if joint_id == "joint_3":
                    vib = 3.5   # Yields calibrated moderate risk ~0.46 in [0.35, 0.70)
                    temp = 58.0
                    maint_age = 1200.0

            elif arm_id == "arm_3":
                # SCHEDULE_MAINTENANCE arm: high wear, high predictive risk on shoulder (joint_2)
                if joint_id == "joint_2":
                    vib = 5.2   # Elevated, triggers warning (4.5) but below critical (7.0)
                    temp = 72.0  # Near warning (75.0)
                    torque = 240.0 # High torque
                    maint_age = 2450.0
                    op_hours = 7500.0
                    prev_fails = 2

            elif arm_id == "arm_4":
                # EMERGENCY_STOP arm: critical temperature limit crossed on shoulder (joint_2)
                if joint_id == "joint_2":
                    temp = 88.5  # Exceeds critical threshold 85.0 °C!
                    vib = 2.5
                    torque = 210.0

            elif arm_id == "arm_5":
                # Spoofed sensor arm: frozen low values / cross-sensor inconsistency
                # Shoulder under extreme load but vibration frozen at 0.001 mm/s
                if joint_id == "joint_2":
                    torque = 200.0
                    temp = 76.0
                    vib = 0.01  # Artificially low vibration under high load/temperature

            elif arm_id == "arm_6":
                # EMERGENCY_STOP arm: critical torque excursion (335 Nm > 320 Nm)
                # But operating_hours low and maint_age low so ML model predicts LOW risk!
                if joint_id == "joint_2":
                    torque = 338.0  # Exceeds critical threshold 320.0 Nm!
                    temp = 45.0     # Low temp
                    vib = 1.4       # Low vibration
                    maint_age = 50.0 # Fresh component -> ML predicts low risk!
                    op_hours = 120.0

            records.append({
                "timestamp": timestamp_str,
                "arm_id": arm_id,
                "joint_id": joint_id,
                "torque": round(torque, 2),
                "temperature": round(temp, 2),
                "vibration": round(vib, 3),
                "operating_hours": op_hours,
                "maintenance_age_hours": maint_age,
                "previous_failure_count": prev_fails,
                "sensor_quality": quality
            })

    return pd.DataFrame(records)


def generate_maintenance_logs() -> str:
    """
    Generates a realistic maintenance log with relevant findings, resolved repairs,
    and irrelevant operational notes.
    """
    entries = [
        # Arm 1: Normal maintenance and operations
        "2026-10-10 09:15:00 - Arm 1 - Routine inventory verification completed in sector A.",
        "2026-10-11 14:00:00 - Arm 1 - Production schedule updated for upcoming shift.",
        "2026-10-12 11:30:00 - Arm 1 joint 2 - Minor vibration observed during high speed pick and place.",
        "2026-10-13 16:45:00 - Arm 1 joint 2 - Bearing replaced and lubrication completed. Restored to nominal.",

        # Arm 2: Unresolved moderate wear note
        "2026-10-12 08:30:00 - Arm 2 joint 3 - Increasing vibration observed near the elbow joint.",
        "2026-10-13 10:00:00 - Operator shift changed across Line 4.",

        # Arm 3: Severe mechanical wear notes
        "2026-10-11 15:20:00 - Arm 3 joint 2 - Gearbox backlash increased during inspection on shoulder.",
        "2026-10-13 13:10:00 - Arm 3 joint 2 - Abnormal clicking noise detected at shoulder under heavy load. Grinding suspected.",

        # Arm 4: Thermal note
        "2026-10-14 11:00:00 - Arm 4 joint 2 - Motor temperature rising rapidly during prolonged operation.",

        # Arm 5 & 6 and Irrelevant notes
        "2026-10-14 07:00:00 - Assembly line cleaned and floor swept.",
        "2026-10-14 08:45:00 - Arm 5 - Routine visual check completed; no exterior leaks noted.",
        "2026-10-14 12:30:00 - Arm 6 joint 2 - Scheduled preventative overhaul completed last week."
    ]
    return "\n".join(entries) + "\n"


def generate_spoofed_sensor_dataset() -> pd.DataFrame:
    """
    Generates a sequential multi-sample dataset for Arm 5 joint 2 demonstrating
    a frozen sensor attack and cross-sensor contradiction over time.
    """
    records = []
    base_ts = datetime(2026, 10, 14, 13, 50, 0)
    for i in range(8):
        ts = base_ts + timedelta(minutes=i)
        # Constant frozen vibration of 0.010 mm/s and constant torque of 200.0 Nm
        # while motor temperature steadily escalates from 65 to 79 °C
        records.append({
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "arm_id": "arm_5",
            "joint_id": "joint_2",
            "torque": 200.00,
            "temperature": round(65.0 + i * 2.0, 2),
            "vibration": 0.010,  # Frozen identical value
            "operating_hours": 3200.0,
            "maintenance_age_hours": 1200.0,
            "previous_failure_count": 1,
            "sensor_quality": 1.0
        })
    return pd.DataFrame(records)
