"""Main entry point and orchestrator for the Robotic Arm Joint Health Monitoring System.

Supports:
- Simulation Mode: Demonstrates SAFE, MONITOR, SCHEDULE_MAINTENANCE, and EMERGENCY_STOP across 6 arms.
- Batch Mode: Ingests an external telemetry CSV and maintenance log text file.
"""

import argparse
import json
import logging
from pathlib import Path
import sys
from typing import Any, Dict, List, Optional
import pandas as pd

from src.config_loader import ConfigurationError, load_config
from src.data_generator import (
    generate_current_telemetry,
    generate_historical_dataset,
    generate_maintenance_logs,
    generate_spoofed_sensor_dataset,
)
from src.data_validator import ValidationError, validate_sensor_reading, validate_telemetry_schema
from src.decision_engine import ArmHealthDecision, DecisionEngine
from src.maintenance_log_analyzer import MaintenanceLogAnalyzer
from src.predictive_model import PredictiveModel
from src.reporting import (
    export_arm_health_summary_csv,
    export_arm_health_summary_json,
    export_joint_diagnostics_csv,
    export_spoof_detection_report_csv,
    generate_final_markdown_report,
)
from src.safety_engine import SafetyCheckResult, SafetyEngine
from src.spoof_detection import SpoofDetectionResult, SpoofDetector

# Configure file and stream logging
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"
LOGS_DIR.mkdir(parents=True, exist_ok=True)
log_file = LOGS_DIR / "monitoring.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_file, encoding="utf-8"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("main_pipeline")


class MonitoringPipeline:
    """End-to-end monitoring pipeline coordinating safety, integrity, NLP, and ML."""

    def __init__(self, config_path: Optional[str | Path] = None):
        self.project_root = Path(__file__).resolve().parent.parent
        self.config = load_config(config_path)
        self.safety_engine = SafetyEngine(self.config)
        self.spoof_detector = SpoofDetector(self.config)
        self.maint_analyzer = MaintenanceLogAnalyzer(self.config)
        self.decision_engine = DecisionEngine(self.config)
        self.predictive_model = PredictiveModel(
            feature_columns=self.config["predictive_maintenance"]["feature_columns"],
            model_path=self.project_root / "models" / "predictive_model.joblib"
        )
        # Attempt to load trained model; if unavailable, model operates in fallback mode
        if not self.predictive_model.load():
            logger.warning("Trained model not found at startup. Fallback mode will be active until trained.")

    def run(
        self,
        telemetry_df: pd.DataFrame,
        maintenance_log_path: Optional[Path | str] = None,
        warmup_df: Optional[pd.DataFrame] = None,
        output_dir: Optional[Path | str] = None
    ) -> List[ArmHealthDecision]:
        """
        Executes the 12-step monitoring pipeline.
        Deterministic safety checks are evaluated immediately and cannot be delayed or overridden.
        """
        out_dir = Path(output_dir) if output_dir else self.project_root / "outputs"
        out_dir.mkdir(parents=True, exist_ok=True)

        logger.info("Step 1: Validating telemetry dataset schema...")
        is_schema_valid, schema_errors = validate_telemetry_schema(telemetry_df)
        if not is_schema_valid:
            logger.error("Schema validation failed: %s", schema_errors)
            raise ValidationError(f"Schema errors: {schema_errors}")

        # Optional warmup history for spoof detector (e.g. frozen sensor attack scenario)
        if warmup_df is not None and not warmup_df.empty:
            logger.info("Initializing sensor integrity buffer with %d warmup samples...", len(warmup_df))
            for _, w_row in warmup_df.iterrows():
                self.spoof_detector.analyze_sample(w_row.to_dict())

        # Step 2: IMMEDIATE DETERMINISTIC SAFETY CHECKS (Must not be delayed)
        logger.info("Step 2: Executing immediate deterministic safety engine...")
        safety_results_map: Dict[str, List[SafetyCheckResult]] = {}
        for _, row in telemetry_df.iterrows():
            rec = row.to_dict()
            arm_id = str(rec.get("arm_id", "unknown")).strip()
            res = self.safety_engine.evaluate_reading(rec)
            if arm_id not in safety_results_map:
                safety_results_map[arm_id] = []
            safety_results_map[arm_id].append(res)
            if res.emergency_stop:
                logger.critical(
                    "IMMEDIATE EMERGENCY STOP DETECTED on %s/%s: %s",
                    res.arm_id, res.joint_id, res.reasons
                )

        # Step 3: Sensor Integrity & Anti-Spoofing Defense
        logger.info("Step 3: Evaluating sensor telemetry integrity and spoofing defense...")
        spoof_results_map: Dict[str, List[SpoofDetectionResult]] = {}
        all_spoof_results: List[SpoofDetectionResult] = []
        for _, row in telemetry_df.iterrows():
            rec = row.to_dict()
            arm_id = str(rec.get("arm_id", "unknown")).strip()
            sp_res = self.spoof_detector.analyze_sample(rec)
            if arm_id not in spoof_results_map:
                spoof_results_map[arm_id] = []
            spoof_results_map[arm_id].append(sp_res)
            all_spoof_results.append(sp_res)
            if sp_res.integrity_status == "CRITICAL_INTEGRITY_FAILURE":
                logger.error(
                    "CRITICAL SENSOR INTEGRITY FAILURE on %s/%s: %s",
                    sp_res.affected_arm_id, sp_res.affected_joint_id, sp_res.detection_reasons
                )

        # Step 4: Maintenance Log NLP Analysis
        if maintenance_log_path and Path(maintenance_log_path).exists():
            logger.info("Step 4: Analyzing technician maintenance logs from %s...", maintenance_log_path)
            self.maint_analyzer.process_log_file(str(maintenance_log_path))
        else:
            logger.info("Step 4: No external maintenance log specified or file not found; skipping log updates.")

        # Step 5: Predictive Model Inference
        logger.info("Step 5: Estimating 24-hour joint failure risk via predictive model...")
        pred_risks = self.predictive_model.predict_risk(telemetry_df)
        telemetry_df["predictive_risk"] = pred_risks

        # Step 6: Multi-Joint Aggregation per Robotic Arm
        logger.info("Step 6: Aggregating joint diagnostic data for 6 robotic arms...")
        arm_decisions: List[ArmHealthDecision] = []
        all_arms = sorted(list(telemetry_df["arm_id"].unique()))

        for arm_id in all_arms:
            arm_df = telemetry_df[telemetry_df["arm_id"] == arm_id].reset_index(drop=True)
            joint_readings = [r.to_dict() for _, r in arm_df.iterrows()]
            s_results = safety_results_map.get(arm_id, [])
            sp_results = spoof_results_map.get(arm_id, [])
            p_risks = arm_df["predictive_risk"].tolist()
            ts = str(arm_df["timestamp"].iloc[0]) if "timestamp" in arm_df.columns else None

            decision = self.decision_engine.evaluate_arm(
                arm_id=arm_id,
                joint_readings=joint_readings,
                safety_results=s_results,
                spoof_results=sp_results,
                predictive_risks=p_risks,
                maint_analyzer=self.maint_analyzer,
                timestamp=ts
            )
            arm_decisions.append(decision)
            logger.info(
                "ARM %s DECISION: [%s] (Max Risk: %.1f%%, E-Stop: %s, Integrity: %s)",
                arm_id, decision.final_decision, decision.maximum_failure_risk * 100,
                decision.emergency_stop_triggered, decision.sensor_integrity_status
            )

        # Step 7: Export Structured Results to CSV and JSON
        logger.info("Step 7: Exporting diagnostic results to %s...", out_dir)
        export_arm_health_summary_csv(arm_decisions, out_dir / "arm_health_summary.csv")
        export_arm_health_summary_json(arm_decisions, out_dir / "arm_health_summary.json")
        export_joint_diagnostics_csv(arm_decisions, out_dir / "joint_diagnostics.csv")
        export_spoof_detection_report_csv(all_spoof_results, out_dir / "spoof_detection_report.csv")

        # Export maintenance analysis JSON
        maint_summary = self.maint_analyzer.get_summary_dict()
        with open(out_dir / "maintenance_analysis.json", "w", encoding="utf-8") as f:
            json.dump(maint_summary, f, indent=2)

        # Step 8: Generate Final Markdown Report
        model_eval_path = out_dir / "model_evaluation.json"
        eval_metrics = None
        if model_eval_path.exists():
            try:
                with open(model_eval_path, "r", encoding="utf-8") as f:
                    eval_metrics = json.load(f)
            except Exception:
                pass

        logger.info("Step 8: Generating comprehensive human-readable final report...")
        generate_final_markdown_report(
            decisions=arm_decisions,
            maintenance_summary=maint_summary,
            model_eval_metrics=eval_metrics,
            output_path=out_dir / "final_report.md"
        )
        logger.info("Pipeline execution complete. All outputs successfully saved.")
        return arm_decisions


def print_console_summary(decisions: List[ArmHealthDecision]) -> None:
    """Prints a polished ASCII table summary to the console."""
    print("\n" + "=" * 90)
    print(" ROBOTIC ARM JOINT HEALTH MONITORING SYSTEM - OPERATIONAL SUMMARY")
    print("=" * 90)
    print(f"{'ARM ID':<8} | {'FINAL DECISION':<22} | {'CRITICAL JOINT':<15} | {'MAX RISK':<10} | {'INTEGRITY':<15}")
    print("-" * 90)
    for d in decisions:
        risk_str = f"{d.maximum_failure_risk * 100:.1f}%"
        print(f"{d.arm_id:<8} | {d.final_decision:<22} | {d.highest_risk_joint:<15} | {risk_str:<10} | {d.sensor_integrity_status:<15}")
    print("=" * 90)
    print("Precedence: EMERGENCY_STOP > SCHEDULE_MAINTENANCE > MONITOR > SAFE")
    print("=" * 90 + "\n")


def run_simulation() -> None:
    """Executes the simulation demonstrating all four final decisions."""
    logger.info("Starting simulation mode...")
    project_root = Path(__file__).resolve().parent.parent

    # 1. Ensure historical data exists and model is trained
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    hist_file = data_dir / "historical_joint_readings.csv"
    if not hist_file.exists():
        logger.info("Generating historical dataset for simulation...")
        df_hist = generate_historical_dataset(num_samples=2160)
        df_hist.to_csv(hist_file, index=False)

    model_file = project_root / "models" / "predictive_model.joblib"
    if not model_file.exists():
        logger.info("Training predictive model pipeline for simulation...")
        from src.train_model import train_and_evaluate
        train_and_evaluate(data_path=hist_file)

    # 2. Ensure current telemetry exists
    telemetry_file = data_dir / "current_telemetry.csv"
    if not telemetry_file.exists():
        df_curr = generate_current_telemetry()
        df_curr.to_csv(telemetry_file, index=False)
    else:
        df_curr = pd.read_csv(telemetry_file)

    # 3. Ensure maintenance logs exist
    maint_file = data_dir / "maintenance_logs.txt"
    if not maint_file.exists():
        with open(maint_file, "w", encoding="utf-8") as f:
            f.write(generate_maintenance_logs())

    # 4. Prepare spoofed sensor cases warmup for Arm 5
    spoof_file = data_dir / "spoofed_sensor_cases.csv"
    df_warmup = None
    if not spoof_file.exists():
        df_warmup = generate_spoofed_sensor_dataset()
        df_warmup.to_csv(spoof_file, index=False)
    else:
        df_warmup = pd.read_csv(spoof_file)

    # 5. Execute Pipeline
    pipeline = MonitoringPipeline()
    decisions = pipeline.run(
        telemetry_df=df_curr,
        maintenance_log_path=maint_file,
        warmup_df=df_warmup
    )
    print_console_summary(decisions)


def run_batch(input_csv: str, log_txt: Optional[str] = None) -> None:
    """Executes the batch analysis mode for a specified CSV file."""
    logger.info("Starting batch mode for input: %s", input_csv)
    df_input = pd.read_csv(input_csv)
    pipeline = MonitoringPipeline()
    decisions = pipeline.run(
        telemetry_df=df_input,
        maintenance_log_path=log_txt
    )
    print_console_summary(decisions)


def main() -> None:
    parser = argparse.ArgumentParser(description="Robotic Arm Joint Health Monitoring System")
    parser.add_argument(
        "--mode",
        choices=["simulate", "batch"],
        default="simulate",
        help="Execution mode: 'simulate' runs demonstration across 6 arms; 'batch' analyzes CSV file."
    )
    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="Path to input telemetry CSV file (for batch mode)."
    )
    parser.add_argument(
        "--logs",
        type=str,
        default=None,
        help="Path to maintenance log text file (optional for batch mode)."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=None,
        help="Path to custom thresholds JSON configuration file."
    )

    args = parser.parse_args()

    try:
        if args.mode == "simulate":
            run_simulation()
        elif args.mode == "batch":
            if not args.input:
                print("Error: --input argument is required in batch mode. Example: --input data/current_telemetry.csv")
                sys.exit(1)
            run_batch(input_csv=args.input, log_txt=args.logs)
    except ConfigurationError as ce:
        logger.error("Configuration Error: %s", ce)
        sys.exit(2)
    except ValidationError as ve:
        logger.error("Validation Error: %s", ve)
        sys.exit(3)
    except Exception as exc:
        logger.exception("Fatal error executing monitoring pipeline: %s", exc)
        sys.exit(4)


if __name__ == "__main__":
    main()
