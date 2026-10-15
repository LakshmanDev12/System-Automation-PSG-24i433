"""Reporting and artifact generation module.

Exports CSV summaries, structured JSON documents, and comprehensive Markdown reports
for robotic arm joint health and safety decisions.
"""

from dataclasses import asdict
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
import pandas as pd

from src.decision_engine import ArmHealthDecision, JointDiagnostic
from src.spoof_detection import SpoofDetectionResult


def export_arm_health_summary_csv(
    decisions: List[ArmHealthDecision],
    output_path: Path | str
) -> pd.DataFrame:
    """Exports high-level arm decision summaries to CSV."""
    rows = []
    for d in decisions:
        rows.append({
            "arm_id": d.arm_id,
            "final_decision": d.final_decision,
            "highest_risk_joint": d.highest_risk_joint,
            "maximum_failure_risk": d.maximum_failure_risk,
            "emergency_stop_triggered": d.emergency_stop_triggered,
            "sensor_integrity_status": d.sensor_integrity_status,
            "maintenance_concern_score": d.maintenance_concern_score,
            "reasons": " | ".join(d.reasons),
            "recommended_action": d.recommended_action,
            "timestamp": d.timestamp
        })
    df = pd.DataFrame(rows)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


def export_arm_health_summary_json(
    decisions: List[ArmHealthDecision],
    output_path: Path | str
) -> None:
    """Exports complete structured arm decision hierarchy to JSON."""
    data = [d.to_dict() for d in decisions]
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def export_joint_diagnostics_csv(
    decisions: List[ArmHealthDecision],
    output_path: Path | str
) -> pd.DataFrame:
    """Exports joint-level telemetry and status breakdowns across all arms to CSV."""
    rows = []
    for d in decisions:
        for j in d.joint_diagnostics:
            rows.append({
                "arm_id": j.arm_id,
                "joint_id": j.joint_id,
                "torque_nm": j.torque,
                "temperature_c": j.temperature,
                "vibration_rms": j.vibration,
                "safety_status": j.safety_status,
                "safety_emergency_stop": j.safety_emergency_stop,
                "predictive_risk": j.predictive_risk,
                "integrity_status": j.integrity_status,
                "suspicion_score": j.suspicion_score,
                "maintenance_concern": j.maintenance_concern,
                "diagnostic_reasons": " | ".join(j.reasons)
            })
    df = pd.DataFrame(rows)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


def export_spoof_detection_report_csv(
    spoof_results: List[SpoofDetectionResult],
    output_path: Path | str
) -> pd.DataFrame:
    """Exports sensor integrity analysis results to CSV."""
    rows = []
    for r in spoof_results:
        rows.append({
            "arm_id": r.affected_arm_id,
            "joint_id": r.affected_joint_id,
            "integrity_status": r.integrity_status,
            "spoofing_suspected": r.spoofing_suspected,
            "suspicion_score": r.suspicion_score,
            "reasons": " | ".join(r.detection_reasons)
        })
    df = pd.DataFrame(rows)
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False)
    return df


def generate_final_markdown_report(
    decisions: List[ArmHealthDecision],
    maintenance_summary: Dict[str, Any],
    model_eval_metrics: Optional[Dict[str, Any]],
    output_path: Path | str
) -> str:
    """Generates comprehensive human-readable Markdown report."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    report_lines: List[str] = [
        "# Robotic Arm Joint Health & Operational Safety Report",
        "",
        "> [!IMPORTANT]",
        "> **INDUSTRIAL SAFETY DISCLAIMER**: This software system is a simulation and diagnostic decision support tool. It is **NOT** a certified industrial safety controller (e.g., ISO 13849 PL-e, IEC 61508 SIL-3). Actual industrial robotics must rely on certified hardware interlocks and dedicated safety relays.",
        "",
        "## Executive Summary",
        "",
        f"This report details the health evaluation for the six 6-axis robotic arms on assembly line production. Exactly one mutually exclusive decision has been synthesized per arm based on the deterministic safety engine, sensor integrity validation, technician maintenance notes, and predictive wear estimation.",
        "",
        "| Arm ID | Final Decision | Highest Risk Joint | Max Failure Risk | E-Stop Triggered | Sensor Integrity | Maintenance Concern |",
        "|:-------|:--------------:|:------------------:|:----------------:|:----------------:|:----------------:|:-------------------:|"
    ]

    for d in decisions:
        risk_pct = f"{d.maximum_failure_risk * 100:.1f}%"
        e_stop_str = "YES" if d.emergency_stop_triggered else "NO"
        report_lines.append(
            f"| **{d.arm_id}** | `{d.final_decision}` | {d.highest_risk_joint} | {risk_pct} | {e_stop_str} | {d.sensor_integrity_status} | {d.maintenance_concern_score:.2f} |"
        )

    report_lines.extend([
        "",
        "---",
        "",
        "## Detailed Arm Analysis & Recommended Actions",
        ""
    ])

    for d in decisions:
        report_lines.extend([
            f"### Robotic Arm: `{d.arm_id}`",
            f"- **Final Operational Decision**: `{d.final_decision}`",
            f"- **Emergency Stop Engaged**: `{d.emergency_stop_triggered}`",
            f"- **Most Vulnerable Joint**: `{d.highest_risk_joint}`",
            f"- **Peak 24h Predictive Failure Risk**: `{d.maximum_failure_risk * 100:.1f}%`",
            f"- **Telemetry Integrity Status**: `{d.sensor_integrity_status}`",
            f"- **Maintenance Concern Level**: `{d.maintenance_concern_score:.2f}`",
            f"- **Recommended Operator Action**: {d.recommended_action}",
            "- **Decision Justification / Diagnostic Findings**:"
        ])
        for r in d.reasons:
            report_lines.append(f"  - {r}")

        # Add joint breakdown table
        report_lines.extend([
            "",
            "#### Joint Diagnostic Telemetry Breakdown:",
            "| Joint | Torque (Nm) | Temp (°C) | Vib (mm/s) | Safety Status | Pred Risk | Integrity | Notes |",
            "|:---|:---:|:---:|:---:|:---:|:---:|:---:|:---|"
        ])
        for j in d.joint_diagnostics:
            reasons_summary = "; ".join(j.reasons) if j.reasons else "Nominal"
            report_lines.append(
                f"| {j.joint_id} | {j.torque:.1f} | {j.temperature:.1f} | {j.vibration:.2f} | `{j.safety_status}` | {j.predictive_risk*100:.1f}% | `{j.integrity_status}` | {reasons_summary} |"
            )
        report_lines.append("")

    # Technician Maintenance Log Synthesis
    report_lines.extend([
        "---",
        "",
        "## Technician Maintenance Log Findings",
        "",
        "The automated natural language analyzer parsed free-text technician notes without reliance on external commercial APIs. It distinguished mechanical faults (bearing wear, backlash, chatter) from verified repairs and discarded irrelevant shift chatter.",
        ""
    ])
    for arm_id, summary in maintenance_summary.items():
        active = summary.get("active_issues", [])
        if active:
            report_lines.append(f"- **{arm_id}**: Active unresolved observations ({len(active)} notes):")
            for note in active:
                report_lines.append(f"  - \"{note}\"")
        else:
            report_lines.append(f"- **{arm_id}**: No unresolved mechanical maintenance notes.")

    # Predictive Model Evaluation Metrics
    if model_eval_metrics:
        eval_data = model_eval_metrics.get("evaluation_metrics", {})
        cm = eval_data.get("confusion_matrix", {})
        report_lines.extend([
            "",
            "---",
            "",
            "## Predictive Model Evaluation (24-Hour Failure Risk)",
            "",
            f"- **Architecture**: {model_eval_metrics.get('model_architecture', 'Random Forest')}",
            f"- **Evaluation Dataset Split**: {model_eval_metrics.get('split_method', 'Time-Aware')}",
            f"- **Accuracy**: `{eval_data.get('accuracy', 0.0):.4f}`",
            f"- **Precision**: `{eval_data.get('precision', 0.0):.4f}`",
            f"- **Recall**: `{eval_data.get('recall', 0.0):.4f}`",
            f"- **F1-Score**: `{eval_data.get('f1_score', 0.0):.4f}`",
            f"- **ROC-AUC**: `{eval_data.get('roc_auc', 0.0):.4f}`",
            f"- **Confusion Matrix**: True Negatives={cm.get('true_negatives')}, False Positives={cm.get('false_positives')}, False Negatives={cm.get('false_negatives')}, True Positives={cm.get('true_positives')}",
            "",
            "> [!NOTE]",
            "> **Class Imbalance Note**: In industrial failure telemetry, positive failure cases comprise a small minority (<15%). Precision and Recall are prioritized over naive Accuracy to prevent catastrophic false-negative machine crashes while avoiding excessive false alarms."
        ])

    # System Limitations
    report_lines.extend([
        "",
        "---",
        "",
        "## Assumptions and Limitations",
        "",
        "1. **Synthetic Data**: Training labels and telemetry are generated from empirical degradation models. Real-world physical variations require transfer calibration.",
        "2. **Sensory Spoofing Scope**: The detector reliably catches frozen telemetry, step-jump discontinuities, duplicate timestamps, and single-channel physical decoupling. Highly sophisticated, multi-sensor coordinated replay attacks synchronized with realistic thermal physics could still evade detection.",
        "3. **Log Processing**: Keyword and regex extraction handles common industrial terminology; non-standard slang or novel abbreviations may require dictionary updates.",
        "4. **Fail-Safe Hierarchy**: Safety threshold evaluations strictly precede ML inference. Under zero circumstances will a low model risk override a physical safety violation or confirmed telemetry integrity breach."
    ])

    report_content = "\n".join(report_lines) + "\n"
    with open(path, "w", encoding="utf-8") as f:
        f.write(report_content)
    return report_content
