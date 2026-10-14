# Comprehensive Engineering Report: Robotic Arm Joint Health Monitoring System

## 1. Executive Summary & Problem Statement

In automated discrete manufacturing, articulated 6-axis robotic arms perform continuous high-cycle operations such as spot welding, high-precision assembly, and material handling. Joint failures—predominantly in cycloidal drives, harmonic reducers, and servo motor bearings—are among the costliest sources of unplanned downtime, running in excess of $20,000 per hour in automotive and semiconductor assembly plants.

The core engineering challenge is synthesizing disparate, noisy data streams into a single reliable operational decision:
1. High-frequency physical telemetry (joint torque, bearing temperature, vibration velocity).
2. Historical wear and component failure datasets.
3. Unstructured free-text technician maintenance logs.
4. Adversarial cybersecurity threats targeting sensor integrity.

This project delivers a complete, modular, and verified software monitoring pipeline for six 6-axis robotic arms on an assembly line. The system guarantees deterministic safety precedence, incorporates robust sensor spoofing defense, utilizes explainable NLP for maintenance logs, trains an imbalanced-aware predictive wear classifier, and outputs exactly one mutually exclusive decision per arm:
1. `SAFE`
2. `MONITOR`
3. `SCHEDULE_MAINTENANCE`
4. `EMERGENCY_STOP`

> [!IMPORTANT]
> **SAFETY SYSTEM DISCLAIMER**: This software system is a simulation and diagnostic decision support tool. It is **NOT** a certified industrial safety controller (e.g., ISO 13849 PL-e, IEC 61508 SIL-3, IEC 62061). Real-world machinery requires independently validated hardware interlocks, safety relays, and certified dual-channel hardware emergency-stop circuits.

---

## 2. Project Objectives & Engineering Methodology

### Key Objectives:
- **Immediate Deterministic Safety Engine**: Evaluate hard safety limits on raw telemetry before any ML model, log analysis, or anomaly detection is triggered.
- **Explainable Predictive Wear Modeling**: Train a supervised learning classifier estimating the probability of a joint failure within 24 hours, addressing severe industrial class imbalance.
- **Autonomous Maintenance Log Analysis**: Parse free-text technician logs without external LLM dependencies, distinguish faults from verified repairs, and credit repairs only to verified joints.
- **Cyber-Physical Sensor Defense**: Detect adversarial spoofing (frozen low values, replay attacks, impossible rate-of-change jumps, cross-sensor contradictions) and enforce a fail-safe policy.
- **Multi-Joint Synthesis**: Synthesize conditions across all six joints per arm to generate exactly one mutually exclusive decision per arm.

---

## 3. Verified System Execution Results

### A. Machine Learning Model Training & Evaluation
The predictive model was trained on 2,160 synthetic historical records using a chronological 80/20 train/test split (1,728 train samples, 432 test samples) to prevent time-series lookahead leakage:

- **Model Architecture**: `StandardScaler` + `RandomForestClassifier(n_estimators=100, max_depth=8, class_weight='balanced')`
- **Class Imbalance in Test Set**: Positive failure rate = 2.8% (12 actual failures out of 432 samples)
- **Observed Metrics**:
  - **Accuracy**: `0.9884` (98.84%)
  - **Precision**: `0.7333` (73.33%)
  - **Recall**: `0.9167` (91.67% — detected 11 out of 12 impending failures)
  - **F1-Score**: `0.8148` (81.48%)
  - **ROC-AUC**: `0.9970` (99.70%)
  - **Confusion Matrix**:
    - True Negatives (TN): `416`
    - False Positives (FP): `4`
    - False Negatives (FN): `1`
    - True Positives (TP): `11`

*Engineering Rationale on Metrics*: In industrial predictive maintenance, accuracy is a misleading metric because a naive baseline model predicting zero failures achieves 97.2% accuracy while allowing 100% of catastrophic failures. High Recall (91.67%) ensures impending catastrophic breakdowns are caught early, while strong Precision (73.33%) avoids false alarms and unwarranted line stoppages.

### B. End-to-End Simulation Demonstration
The complete end-to-end pipeline was executed across the six robotic arms, successfully demonstrating all four permitted operational decisions:

| Arm ID | Final Decision | Critical Joint | Peak 24h Risk | E-Stop Triggered | Sensor Integrity | Maintenance Concern | Primary Triggering Reason |
|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|
| **arm_1** | `SAFE` | `joint_1` | 0.0% | NO | `TRUSTED` | 0.00 | All 6 joints operating nominally; past repair verified. |
| **arm_2** | `MONITOR` | `joint_3` | 45.1% | NO | `TRUSTED` | 0.45 | Moderate vibration wear (3.50 mm/s) & active technician note. |
| **arm_3** | `SCHEDULE_MAINTENANCE` | `joint_2` | 99.0% | NO | `TRUSTED` | 0.55 | Severe mechanical degradation (5.20 mm/s) & clicking gearbox note. |
| **arm_4** | `EMERGENCY_STOP` | `joint_2` | 1.0% | **YES** | `TRUSTED` | 0.00 | Critical thermal threshold exceeded: 88.5°C >= 85.0°C. |
| **arm_5** | `EMERGENCY_STOP` | `joint_2` | 1.0% | **YES** | `CRITICAL_INTEGRITY_FAILURE` | 0.00 | Frozen sensor attack detected ($\sigma=0.000000$) with cross-sensor contradiction. |
| **arm_6** | `EMERGENCY_STOP` | `joint_2` | 1.9% | **YES** | `TRUSTED` | 0.00 | Critical torque limit crossed (338.0 Nm >= 320.0 Nm); **overrode low 1.9% ML risk**. |

### C. Automated Test Suite Verification
The complete test suite was executed via `pytest -v`:
- **Total Tests Collected**: 22
- **Passed**: 22
- **Failed**: 0
- **Execution Time**: 2.25 seconds
- **Requirements Coverage**: 100% of the 20 mandatory scenarios in Section 8 verified.

---

## 4. Key Engineering Insights

1. **Separation of Safety and AI**: Modern AI models are probabilistic approximations. By establishing a deterministic rule engine as the primary gatekeeper, the system guarantees that high-torque mechanical crashes or thermal runaways trigger an immediate emergency stop without waiting for model inference.
2. **Cyber-Physical Defense in Depth**: Adversaries attacking industrial IoT often attempt to disguise failures by spoofing flatline nominal values. The sensor integrity module successfully detects such attacks through micro-variance noise floor checks and cross-sensor thermodynamic correlation.
3. **Closing the Loop with Field Notes**: Maintenance logs often contain the earliest warnings of mechanical anomalies (e.g., clicking noises, backlash). The stateful NLP analyzer tracks unresolved issues and credits repairs strictly to matching components.

---

## 5. Generated Artifacts & File Locations

All generated artifacts are persisted in the workspace:
- Decision Summaries: `outputs/arm_health_summary.csv` and `outputs/arm_health_summary.json`
- Joint Diagnostics: `outputs/joint_diagnostics.csv`
- Sensor Integrity Reports: `outputs/spoof_detection_report.csv`
- Maintenance NLP Analysis: `outputs/maintenance_analysis.json`
- ML Model Evaluation: `outputs/model_evaluation.json`
- Human-Readable Report: `outputs/final_report.md`
- Diagnostic Execution Logs: `logs/monitoring.log`
