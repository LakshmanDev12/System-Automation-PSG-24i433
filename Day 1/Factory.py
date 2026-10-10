import random
import time
LOG_FILE = "day1_log_Factory.txt"
MACHINES = ["M1", "M2", "M3", "M4", "M5"]

RULES = [
    {
        "name": "CRITICAL_OVERLOAD",
        "priority": 1,
        "condition": lambda r: r["temperature"] > 93.0 and r["current"] > 15.0,
        "action": "EMERGENCY_POWER_CUT"
    },
    {
        "name": "HIGH_TEMP",
        "priority": 2,
        "condition": lambda r: r["temperature"] > 85.0,
        "action": "STOP_MACHINE"
    },
    {
        "name": "HIGH_PRESSURE",
        "priority": 3,
        "condition": lambda r: r["pressure"] > 4.0,
        "action": "VENT_VALVE"
    },
    {
        "name": "EXCESSIVE_VIBRATION",
        "priority": 4,
        "condition": lambda r: r["vibration"] > 40.0,
        "action": "TRIGGER_MAINTENANCE_ALERT"
    }
]
ACTION_PRIORITY = {
    "EMERGENCY_POWER_CUT": 1,
    "STOP_MACHINE": 2,
    "LOG_ERROR_AND_HOLD": 3,
    "VENT_VALVE": 4,
    "TRIGGER_MAINTENANCE_ALERT": 5,
    "CONTINUE_NORMAL": 6
}
def generate_sensor_data():
    if random.random() < 0.05:
        return {
            "temperature": None,
            "pressure": None,
            "vibration": None,
            "current": None
        }
    if random.random() < 0.05:
        return {
            "temperature": round(random.uniform(110, 150), 1),
            "pressure": round(random.uniform(8, 12), 2),
            "vibration": round(random.uniform(90, 150), 1),
            "current": round(random.uniform(40, 60), 1)
        }
    return {
        "temperature": round(random.uniform(50, 95), 1),
        "pressure": round(random.uniform(1.5, 4.5), 2),
        "vibration": round(random.uniform(10, 45), 1),
        "current": round(random.uniform(5, 18), 1)
    }
def evaluate_rules(reading):
    if reading["temperature"] is None:
        return "SENSOR_DROPOUT_DETECTED", "LOG_ERROR_AND_HOLD"

    for rule in sorted(RULES, key=lambda r: r["priority"]):
        if rule["condition"](reading):
            return rule["name"], rule["action"]

    return "NO_RULE_FIRED", "CONTINUE_NORMAL"
def take_action(action):
    messages = {
        "EMERGENCY_POWER_CUT":
            "EMERGENCY: Critical overload detected. Power cut required.",
        "STOP_MACHINE":
            "CRITICAL: High temperature detected. Stop the machine.",
        "VENT_VALVE":
            "WARNING: High pressure detected. Open the relief valve.",
        "TRIGGER_MAINTENANCE_ALERT":
            "WARNING: Excessive vibration. Maintenance is required.",
        "LOG_ERROR_AND_HOLD":
            "ERROR: Sensor readings unavailable. Hold and inspect the machine.",
        "CONTINUE_NORMAL":
            "Normal operation. No rule was triggered."
    }
    return messages.get(action, "Unknown action.")
def log_decision(machine, reading, rule_name, action):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")

    with open(LOG_FILE, "a") as file:
        file.write(
            f"[{timestamp}] {machine} | "
            f"SENSE: {reading} | "
            f"THINK: {rule_name} | ACT: {action}\n"
        )
def monitor_machines():
    print("Five-Machine Monitoring System Started")
    for tick in range(1, 11):
        results = []
        print(f"\nMonitoring Cycle {tick}")
        for machine in MACHINES:
            reading = generate_sensor_data()
            rule_name, action = evaluate_rules(reading)
            outcome = take_action(action)
            urgency = ACTION_PRIORITY[action]
            results.append({
                "machine": machine,
                "reading": reading,
                "rule": rule_name,
                "action": action,
                "urgency": urgency
            })
            print(f"\n{machine}")
            print(f"  Sensor readings : {reading}")
            print(f"  Rule triggered  : {rule_name}")
            print(f"  Action          : {outcome}")
            log_decision(machine, reading, rule_name, action)
        urgent_machines = [
            result for result in results
            if result["action"] != "CONTINUE_NORMAL"
        ]
        if urgent_machines:
            urgent_machines.sort(key=lambda r: r["urgency"])
            top = urgent_machines[0]
            print("\nMACHINE NEEDING IMMEDIATE ATTENTION")
            print(f"Machine : {top['machine']}")
            print(f"Problem : {top['rule']}")
            print(f"Action  : {top['action']}")
            if len(urgent_machines) > 1:
                print("\nOther machines requiring attention:")
                for result in urgent_machines[1:]:
                    print(
                        f"- {result['machine']}: "
                        f"{result['rule']}"
                    )
        else:
            print("\nAll five machines are operating normally.")
        time.sleep(0.5)
    print(f"\nMonitoring completed. Logs saved to {LOG_FILE}.")
if __name__ == "__main__":
    monitor_machines()
