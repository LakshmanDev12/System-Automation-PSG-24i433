

import random
import time

LOG_FILE = "day1_log.txt"

def generate_sensor_data():
    """Return a dict with at least 'temperature', 'pressure', 'vibration', and 'current'."""
    dropout_roll = random.random()
    
    if dropout_roll < 0.05:
        return {
            "temperature": None,
            "pressure": None,
            "vibration": None,
            "current": None
        }

    spike_roll = random.random()
    if spike_roll < 0.05:
        return {
            "temperature": random.uniform(110.0, 150.0),
            "pressure": random.uniform(8.0, 12.0),
            "vibration": random.uniform(90.0, 150.0),
            "current": random.uniform(40.0, 60.0)
        }
    else:
        return {
            "temperature": round(random.uniform(50.0, 95.0), 1), 
            "pressure": round(random.uniform(1.5, 4.5), 2),      
            "vibration": round(random.uniform(10.0, 45.0), 1),    
            "current": round(random.uniform(5.0, 18.0), 1)       
        }

RULES = [
    {
        "name": "HIGH_TEMP", 
        "priority": 2, 
        "condition": lambda r: r["temperature"] is not None and r["temperature"] > 85.0, 
        "action": "STOP_MACHINE"
    },
    {
        "name": "HIGH_PRESSURE", 
        "priority": 3, 
        "condition": lambda r: r["pressure"] is not None and r["pressure"] > 4.0, 
        "action": "VENT_VALVE"
    },
    {
        "name": "EXCESSIVE_VIBRATION", 
        "priority": 4, 
        "condition": lambda r: r["vibration"] is not None and r["vibration"] > 40.0, 
        "action": "TRIGGER_MAINTENANCE_ALERT"
    },
    {
        "name": "CRITICAL_OVERLOAD", 
        "priority": 1, 
        "condition": lambda r: (r["temperature"] is not None and r["temperature"] > 93.0) and (r["current"] is not None and r["current"] > 15.0), 
        "action": "EMERGENCY_POWER_CUT"
    }
]
def evaluate_rules(reading, rules):
    """Return (rule_name, action) for the first matching rule, checked in
    priority order (lowest number first). If nothing matches, return
    ("NO_RULE_FIRED", "CONTINUE_NORMAL")."""
    
    if reading.get("temperature") is None:
        return "SENSOR_DROPOUT_DETECTED", "LOG_ERROR_AND_HOLD"
        
    sorted_rules = sorted(rules, key=lambda x: x["priority"])
    
    for rule in sorted_rules:
        try:
            if rule["condition"](reading):
                return rule["name"], rule["action"]
        except Exception as e:
            continue
            
    return "NO_RULE_FIRED", "CONTINUE_NORMAL"

def take_action(action):
    """Return a human-readable string describing what happens for this action."""
    action_handlers = {
        "STOP_MACHINE": "CRITICAL: High temperature detected! Shutting down core drive motor immediately.",
        "VENT_VALVE": "WARNING: Pressure threshold exceeded. Opening auxiliary pressure relief vent.",
        "TRIGGER_MAINTENANCE_ALERT": " NOTICE: Vibration levels erratic. Dispatched maintenance log to system engineering dashboard.",
        "EMERGENCY_POWER_CUT": "EMERGENCY: Combined Thermal & Electrical Overload! Tripping main circuit breakers.",
        "LOG_ERROR_AND_HOLD": " ERROR: Sensor data unavailable or corrupted. Holding current operational state.",
        "CONTINUE_NORMAL": " Normal Operations: System metrics stable within nominal safety limits."
    }
    return action_handlers.get(action, f"(no handler yet for action: {action})")

def log_decision(reading, rule_name, action):
    """Append one line to LOG_FILE with the timestamp, reading, rule fired, and action."""
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    log_entry = f"[{timestamp}] SENSE: {reading} | THINK: {rule_name} | ACT: {action}\n"
    
    with open(LOG_FILE, "a") as f:
        f.write(log_entry)

def main():
    print("=== Starting 23IF02 Automated System Rule Engine Execution ===\n")
    for tick in range(1, 11):
        reading = generate_sensor_data()
        rule_name, action = evaluate_rules(reading, RULES)
        outcome = take_action(action)

        print(f"[Tick {tick:02d}] SENSE -> {reading}")
        print(f"           THINK -> {rule_name}")
        print(f"           ACT   -> {outcome}\n")

        log_decision(reading, rule_name, action)
        time.sleep(0.2)
    print(f"=== Demonstration Run Complete. Decisions written to {LOG_FILE} ===")

if __name__ == "__main__":
    main()

