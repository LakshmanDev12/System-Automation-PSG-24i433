"""CLI executable script to generate synthetic datasets and maintenance logs.

Outputs:
- data/historical_joint_readings.csv
- data/current_telemetry.csv
- data/maintenance_logs.txt
- data/spoofed_sensor_cases.csv
"""

import logging
from pathlib import Path
from src.data_generator import (
    generate_current_telemetry,
    generate_historical_dataset,
    generate_maintenance_logs,
    generate_spoofed_sensor_dataset,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("generate_dataset")


def main() -> None:
    project_root = Path(__file__).resolve().parent.parent
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # 1. Historical Dataset
    logger.info("Generating historical training dataset (2,160 samples)...")
    df_hist = generate_historical_dataset(num_samples=2160, random_seed=42)
    hist_path = data_dir / "historical_joint_readings.csv"
    df_hist.to_csv(hist_path, index=False)
    logger.info("Saved historical dataset to %s (%d rows)", hist_path, len(df_hist))

    # 2. Current Telemetry Snapshot
    logger.info("Generating current telemetry snapshot for 6 arms (36 rows)...")
    df_current = generate_current_telemetry()
    current_path = data_dir / "current_telemetry.csv"
    df_current.to_csv(current_path, index=False)
    logger.info("Saved current telemetry to %s (%d rows)", current_path, len(df_current))

    # 3. Technician Maintenance Logs
    logger.info("Generating free-text technician maintenance logs...")
    logs_content = generate_maintenance_logs()
    logs_path = data_dir / "maintenance_logs.txt"
    with open(logs_path, "w", encoding="utf-8") as f:
        f.write(logs_content)
    logger.info("Saved maintenance logs to %s", logs_path)

    # 4. Spoofed Sensor Test Cases
    logger.info("Generating spoofed sensor test scenario dataset...")
    df_spoof = generate_spoofed_sensor_dataset()
    spoof_path = data_dir / "spoofed_sensor_cases.csv"
    df_spoof.to_csv(spoof_path, index=False)
    logger.info("Saved spoofed sensor dataset to %s (%d rows)", spoof_path, len(df_spoof))

    print("\n" + "=" * 60)
    print(" DATASET GENERATION COMPLETE")
    print("=" * 60)
    print(f" 1. Historical Dataset:    {hist_path} ({len(df_hist)} rows)")
    print(f" 2. Current Telemetry:     {current_path} ({len(df_current)} rows)")
    print(f" 3. Maintenance Logs:      {logs_path} ({len(logs_content.splitlines())} lines)")
    print(f" 4. Spoofed Sensor Cases:  {spoof_path} ({len(df_spoof)} rows)")
    print("=" * 60 + "\n")


if __name__ == "__main__":
    main()
