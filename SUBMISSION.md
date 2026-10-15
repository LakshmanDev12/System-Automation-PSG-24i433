# Project Submission: Robotic Arm Joint Health Monitoring System

## Deliverables Checklist & Verification

| # | Required Deliverable | Status | Location / Artifact | Verification Details |
|:---:|:---|:---:|:---|:---|
| **1** | Complete, Executable Python Source Code | **COMPLETED** | [`src/`](file:///e:/Occ/src) | 12 modular Python files with strict type hints, error handling, and zero commercial API dependencies. |
| **2** | $\ge 50$ Labeled Historical Sensor Readings | **COMPLETED** | [`data/historical_joint_readings.csv`](file:///e:/Occ/data/historical_joint_readings.csv) | **2,160 rows** with physical features (`torque`, `temperature`, `vibration`, `operating_hours`, `maintenance_age_hours`, `previous_failure_count`, `sensor_quality`) and `failure_within_24h` binary target. |
| **3** | Maintenance Log with $\ge 8$ Entries (Relevant & Irrelevant) | **COMPLETED** | [`data/maintenance_logs.txt`](file:///e:/Occ/data/maintenance_logs.txt) | **12 entries** with bearing wear, gear backlash, clicking noise, verified repairs, and irrelevant operational chatter. |
| **4** | Half-Page Architectural Explanation | **COMPLETED** | *See Section Below &* [`docs/report.md`](file:///e:/Occ/docs/report.md) | In-depth coverage of deterministic safety, ML/log fusion, and spoof defense. |
| **5** | README with Installation & Execution Instructions | **COMPLETED** | [`README.md`](file:///e:/Occ/README.md) | Windows PowerShell & Linux instructions, dependencies, and command documentation. |
| **6** | Automated Tests & Generated Reports | **COMPLETED** | [`tests/`](file:///e:/Occ/tests) & [`outputs/`](file:///e:/Occ/outputs) | **22 automated tests passing (100%)**; all 7 required CSV, JSON, and Markdown output artifacts generated. |
| **7** | Personal GitHub Repository Readiness | **PREPARED** | Local Branch: `main` | Git initialized, 35 files committed to `main`. Remote push instructions detailed below. |

---

## Half-Page Architectural Explanation

### 1. Safety Thresholds & Immediate Deterministic Gating
The first line of defense in the cyber-physical monitoring pipeline is an independent, deterministic rule-based safety engine ([`src/safety_engine.py`](file:///e:/Occ/src/safety_engine.py)). In high-speed industrial robotics, safety cannot be subordinated to stochastic or probabilistic machine learning models. Raw sensor telemetry is inspected immediately upon ingestion against hard physical limits: bearing temperature (warning: 75°C, critical: 85°C), vibration velocity (warning: 4.5 mm/s, critical: 7.0 mm/s RMS per ISO 10816), and joint-specific torque boundaries tailored to mechanical loading (e.g., Joint 2 Shoulder: 320 Nm critical limit; Joint 6 Wrist: 45 Nm critical limit). Crucially, the engine implements a strict fail-safe policy: any missing telemetry, `NaN`, infinite, or malformed data immediately triggers an `EMERGENCY_STOP`. Under zero circumstances can a low-risk machine learning prediction override or suppress an immediate physical safety violation.

### 2. Predictive Modeling and Maintenance Log Combination
Long-term degradation manifests gradually through thermodynamic dissipation, friction accumulation, and acoustic anomalies before crossing catastrophic safety thresholds. The system pairs a supervised Random Forest classifier ([`src/predictive_model.py`](file:///e:/Occ/src/predictive_model.py)) with an autonomous, zero-API natural language maintenance log analyzer ([`src/maintenance_log_analyzer.py`](file:///e:/Occ/src/maintenance_log_analyzer.py)). The ML model is trained with balanced class weighting to handle real-world failure rarity (2.8% positive rate) using chronological time-aware splitting to prevent future data leakage, yielding **98.84% accuracy, 91.67% recall, and 0.9970 ROC-AUC**. Concurrently, the log analyzer maps domain-specific fault phrases ("gearbox backlash", "clicking noise", "bearing wear") to specific joints, computes an explainable concern score, ignores operational chatter, and credits verified repairs only when documented for the matching arm and joint. The decision engine ([`src/decision_engine.py`](file:///e:/Occ/src/decision_engine.py)) synthesizes these streams under strict priority precedence: high predictive risk ($\ge 70\%$) or severe maintenance concern ($\ge 0.60$) triggers `SCHEDULE_MAINTENANCE`, while moderate risk ($\ge 35\%$) or active notes ($\ge 0.30$) triggers `MONITOR`.

### 3. Spoofed-Sensor Cyber Defense & Fail-Safe Policy
Articulated robotic arms connected to industrial networks face man-in-the-middle packet tampering and sensor bypass attacks designed to conceal mechanical faults by spoofing artificially low nominal readings. The spoofing defense module ([`src/spoof_detection.py`](file:///e:/Occ/src/spoof_detection.py)) combats this using four algorithmic layers: (1) **noise floor verification** that flags frozen telemetry when rolling-window standard deviation drops below sensor physical noise ($\sigma < 0.0001\text{ mm/s}$); (2) **kinematic slew rate checks** that detect impossible step-jumps violating thermal or mechanical inertia; (3) **cross-sensor physical coupling checks** that detect thermodynamic contradictions (e.g., high motor torque and rising thermal load paired with near-zero vibration); and (4) **temporal replay detection** caching timestamp monotonicity. If a telemetry stream is critically compromised (suspicion score $\ge 0.85$), the system loses observability over the plant and enforces a fail-safe `EMERGENCY_STOP`.

---

## Requirement Satisfaction Summary

### Requirement 1: Immediate Safety-Stop Mechanism
- **Implemented in**: [`src/safety_engine.py`](file:///e:/Occ/src/safety_engine.py)
- **Features**: Joint-specific torque thresholds (configured in [`config/thresholds.json`](file:///e:/Occ/config/thresholds.json)); fail-safe on `NaN`, `Inf`, and missing values; independent of ML model presence; cannot be overridden by low model risk.
- **Verification**: Verified by automated tests `test_critical_torque_triggers_emergency_stop`, `test_critical_temperature_triggers_emergency_stop`, `test_critical_vibration_triggers_emergency_stop`, `test_missing_and_invalid_data_failsafe`, and `test_safety_check_independent_of_model`.

### Requirement 2: Predictive Wear Detection
- **Implemented in**: [`src/predictive_model.py`](file:///e:/Occ/src/predictive_model.py), [`src/train_model.py`](file:///e:/Occ/src/train_model.py), and [`src/data_generator.py`](file:///e:/Occ/src/data_generator.py)
- **Features**: 2,160 historical records generated with fixed seed (`RANDOM_SEED = 42`); chronological train/test split (80/20); addresses class imbalance with balanced weighting; calibrated probabilities [0.0, 1.0]; serialized pipeline saved to [`models/predictive_model.joblib`](file:///e:/Occ/models/predictive_model.joblib); evaluation metrics saved to [`outputs/model_evaluation.json`](file:///e:/Occ/outputs/model_evaluation.json).
- **Verification**: Model achieved Recall = 0.9167, ROC-AUC = 0.9970, Accuracy = 0.9884. Verified by tests `test_moderate_predictive_risk_produces_monitor` and `test_high_predictive_risk_produces_schedule_maintenance`.

### Requirement 3: Maintenance Log Analysis
- **Implemented in**: [`src/maintenance_log_analyzer.py`](file:///e:/Occ/src/maintenance_log_analyzer.py)
- **Features**: Zero commercial API dependencies; regex entity extraction for arms (`arm_1`..`arm_6`) and joints (`shoulder`, `elbow`, `wrist pitch`, etc.); categorized fault dictionary; repair resolution tracking; operational chatter filtering.
- **Verification**: Verified by tests `test_relevant_unresolved_notes_increase_concern`, `test_irrelevant_notes_do_not_trigger_maintenance`, and `test_documented_repair_clears_concern`.

### Requirement 4: Spoofed-Sensor Defense
- **Implemented in**: [`src/spoof_detection.py`](file:///e:/Occ/src/spoof_detection.py)
- **Features**: Rolling window variance check against noise floor ($\sigma < 0.0001$); rate-of-change boundaries for torque ($120\text{ Nm}$), temperature ($12^\circ\text{C}$), and vibration ($4.5\text{ mm/s}$); cross-sensor thermodynamic decoupling detection; duplicate timestamp caching; fail-safe `EMERGENCY_STOP` on critical suspicion ($\ge 0.85$).
- **Verification**: Verified by tests `test_repeated_suspicious_readings_trigger_warning`, `test_duplicate_replayed_timestamps_detected`, `test_spoofed_low_reading_with_cross_sensor_contradiction`, and `test_implausible_rate_of_change`.

### Requirement 5: One Final Decision Per Arm
- **Implemented in**: [`src/decision_engine.py`](file:///e:/Occ/src/decision_engine.py)
- **Features**: Aggregates all 6 joints per arm; strictly enforces priority precedence (`EMERGENCY_STOP` > `SCHEDULE_MAINTENANCE` > `MONITOR` > `SAFE`); produces structured decision dataclass with joint diagnostic breakdowns.
- **Verification**: Verified by tests `test_normal_telemetry_produces_safe`, `test_emergency_stop_cannot_be_overridden_by_low_risk`, `test_exactly_one_valid_final_decision`, and `test_multiple_joint_level_alerts_aggregation`.

---

## Executed Demonstration Results

Running `python -m src.main --mode simulate` generates the verified operational outcomes:

```
==========================================================================================
 ROBOTIC ARM JOINT HEALTH MONITORING SYSTEM - OPERATIONAL SUMMARY
==========================================================================================
ARM ID   | FINAL DECISION         | CRITICAL JOINT  | MAX RISK   | INTEGRITY      
------------------------------------------------------------------------------------------
arm_1    | SAFE                   | joint_1         | 0.0%       | TRUSTED        
arm_2    | MONITOR                | joint_3         | 45.1%      | TRUSTED        
arm_3    | SCHEDULE_MAINTENANCE   | joint_2         | 99.0%      | TRUSTED        
arm_4    | EMERGENCY_STOP         | joint_2         | 1.0%       | TRUSTED        
arm_5    | EMERGENCY_STOP         | joint_2         | 1.0%       | CRITICAL_INTEGRITY_FAILURE
arm_6    | EMERGENCY_STOP         | joint_2         | 1.9%       | TRUSTED        
==========================================================================================
Precedence: EMERGENCY_STOP > SCHEDULE_MAINTENANCE > MONITOR > SAFE
==========================================================================================
```

All 4 operational decisions are clearly demonstrated across the 6 robotic arms. In particular, `arm_6` demonstrates that a critical torque spike (338.0 Nm > 320.0 Nm limit) immediately triggers an `EMERGENCY_STOP`, completely overriding an otherwise low model predicted failure risk of 1.9%.

---

## Test Execution Evidence

Running `pytest -v`:
```
============================= test session starts =============================
platform win32 -- Python 3.13.14, pytest-8.3.3, pluggy-1.6.0
configfile: pytest.ini
testpaths: tests
collected 22 items

tests/test_decision_engine.py::test_normal_telemetry_produces_safe PASSED        [  4%]
tests/test_decision_engine.py::test_emergency_stop_cannot_be_overridden_by_low_risk PASSED [  9%]
tests/test_decision_engine.py::test_moderate_predictive_risk_produces_monitor PASSED [ 13%]
tests/test_decision_engine.py::test_high_predictive_risk_produces_schedule_maintenance PASSED [ 18%]
tests/test_decision_engine.py::test_exactly_one_valid_final_decision PASSED     [ 22%]
tests/test_decision_engine.py::test_multiple_joint_level_alerts_aggregation PASSED [ 27%]
tests/test_maintenance_log_analyzer.py::test_relevant_unresolved_notes_increase_concern PASSED [ 31%]
tests/test_maintenance_log_analyzer.py::test_irrelevant_notes_do_not_trigger_maintenance PASSED [ 36%]
tests/test_maintenance_log_analyzer.py::test_documented_repair_clears_concern PASSED [ 40%]
tests/test_pipeline.py::test_invalid_config_rejected_with_error PASSED           [ 45%]
tests/test_pipeline.py::test_dataset_generation_reproducibility PASSED           [ 50%]
tests/test_pipeline.py::test_pipeline_exports_valid_csv_and_json PASSED          [ 54%]
tests/test_safety_engine.py::test_normal_telemetry_is_safe PASSED                [ 59%]
tests/test_safety_engine.py::test_critical_torque_triggers_emergency_stop PASSED [ 63%]
tests/test_safety_engine.py::test_critical_temperature_triggers_emergency_stop PASSED [ 68%]
tests/test_safety_engine.py::test_critical_vibration_triggers_emergency_stop PASSED [ 72%]
tests/test_safety_engine.py::test_missing_and_invalid_data_failsafe PASSED       [ 77%]
tests/test_safety_engine.py::test_safety_check_independent_of_model PASSED     [ 81%]
tests/test_spoof_detection.py::test_repeated_suspicious_readings_trigger_warning PASSED [ 86%]
tests/test_spoof_detection.py::test_duplicate_replayed_timestamps_detected PASSED [ 90%]
tests/test_spoof_detection.py::test_spoofed_low_reading_with_cross_sensor_contradiction PASSED [ 95%]
tests/test_spoof_detection.py::test_implausible_rate_of_change PASSED            [100%]

============================== 22 passed in 2.25s ==============================
```

---

## Instructions for Pushing to Personal GitHub Repository

The local Git repository is initialized, on branch `main`, with all deliverables staged and committed.

To push to your personal GitHub repository:

1. **Create an empty repository on GitHub**:
   - Go to [GitHub - New Repository](https://github.com/new).
   - Enter a repository name (e.g., `robotic-arm-joint-health-monitoring`).
   - Do **not** initialize with a README, `.gitignore`, or license (the local project already contains them).

2. **Add your remote repository URL and push**:
   Open PowerShell in `e:\Occ` and run:
   ```powershell
   git remote add origin https://github.com/LakshmanDev12/<YOUR-REPOSITORY-NAME>.git
   git push -u origin main
   ```
   *(Replace `<YOUR-REPOSITORY-NAME>` with the name you chose on GitHub)*

> **Status Notice**: The local repository has been verified, cleanly committed, and prepared on branch `main`. Push to GitHub is ready to be triggered as soon as the remote repository URL is linked.
