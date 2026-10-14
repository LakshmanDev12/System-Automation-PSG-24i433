"""Technician maintenance log analysis module using regex, keyword dictionaries, and stateful tracking.

Identifies mechanical wear, thermal degradation, acoustic anomalies, lubrication issues,
and repairs without relying on external LLMs or paid APIs.
"""

from collections import defaultdict
from dataclasses import dataclass, field
import datetime
import re
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class LogEntry:
    raw_text: str
    timestamp: Optional[str]
    arm_id: Optional[str]
    joint_ids: List[str]
    is_relevant: bool
    is_repair: bool
    fault_categories: List[str]
    severity_score: float
    matched_keywords: List[str]
    explanation: str


@dataclass
class ArmJointMaintenanceStatus:
    arm_id: str
    joint_id: str
    concern_score: float  # [0.0, 1.0]
    active_issues: List[str] = field(default_factory=list)
    resolved_issues: List[str] = field(default_factory=list)
    explanations: List[str] = field(default_factory=list)


# Synonyms mapping to canonical joint IDs
JOINT_NAME_MAP = {
    "base": "joint_1",
    "j1": "joint_1",
    "joint 1": "joint_1",
    "joint_1": "joint_1",
    "shoulder": "joint_2",
    "j2": "joint_2",
    "joint 2": "joint_2",
    "joint_2": "joint_2",
    "elbow": "joint_3",
    "j3": "joint_3",
    "joint 3": "joint_3",
    "joint_3": "joint_3",
    "wrist 1": "joint_4",
    "wrist_1": "joint_4",
    "j4": "joint_4",
    "joint 4": "joint_4",
    "joint_4": "joint_4",
    "wrist 2": "joint_5",
    "wrist_2": "joint_5",
    "j5": "joint_5",
    "joint 5": "joint_5",
    "joint_5": "joint_5",
    "wrist 3": "joint_6",
    "wrist_3": "joint_6",
    "j6": "joint_6",
    "joint 6": "joint_6",
    "joint_6": "joint_6",
}

# Categorized dictionary of fault patterns with weights
FAULT_KEYWORDS: Dict[str, Tuple[str, float]] = {
    "grinding": ("bearing/gear", 0.60),
    "spalling": ("gearbox/bearing", 0.65),
    "gearbox backlash": ("mechanical_backlash", 0.55),
    "backlash increased": ("mechanical_backlash", 0.50),
    "clicking noise": ("bearing/gear", 0.40),
    "abnormal noise": ("acoustic_anomaly", 0.35),
    "chatter": ("mechanical_oscillation", 0.35),
    "excessive vibration": ("vibration_wear", 0.55),
    "increasing vibration": ("vibration_wear", 0.45),
    "vibration observed": ("vibration_wear", 0.35),
    "overheating": ("thermal_wear", 0.55),
    "temperature rising": ("thermal_wear", 0.40),
    "motor temperature": ("thermal_wear", 0.35),
    "torque fluctuations": ("torque_instability", 0.40),
    "torque spikes": ("torque_instability", 0.45),
    "play detected": ("joint_wear", 0.35),
    "slight play": ("joint_wear", 0.25),
    "lubrication degraded": ("lubrication", 0.40),
    "oil leak": ("lubrication", 0.45),
    "grease blackened": ("lubrication", 0.40),
}

# Repair / Resolution indicators
REPAIR_KEYWORDS: List[str] = [
    "replaced",
    "lubrication completed",
    "re-greased",
    "repaired",
    "tightened",
    "calibrated",
    "serviced",
    "component swapped",
    "restored to nominal",
    "bearing replaced",
    "motor replaced",
    "overhaul completed",
    "alignment restored"
]

# Unrelated operational / administrative keywords
IRRELEVANT_KEYWORDS: List[str] = [
    "production schedule",
    "assembly line cleaned",
    "operator shift changed",
    "routine inventory",
    "shift change",
    "safety audit passed",
    "cleaning completed",
    "meeting attended",
    "batch run completed",
    "floor swept"
]


class MaintenanceLogAnalyzer:
    """
    Parses unstructured maintenance logs, extracts entity references,
    tracks temporal state of mechanical concerns, and credits verified repairs.
    """

    def __init__(self, config: Dict[str, Any]):
        self.config = config
        cfg = config.get("maintenance_log_analysis", {})
        self.monitor_threshold = float(cfg.get("monitor_concern_threshold", 0.30))
        self.maintenance_threshold = float(cfg.get("maintenance_concern_threshold", 0.60))

        # Internal state per (arm_id, joint_id) -> ArmJointMaintenanceStatus
        self.statuses: Dict[Tuple[str, str], ArmJointMaintenanceStatus] = {}
        for arm_i in range(1, 7):
            arm_id = f"arm_{arm_i}"
            for j_i in range(1, 7):
                joint_id = f"joint_{j_i}"
                self.statuses[(arm_id, joint_id)] = ArmJointMaintenanceStatus(
                    arm_id=arm_id,
                    joint_id=joint_id,
                    concern_score=0.0
                )

        self.parsed_entries: List[LogEntry] = []

    def extract_arm_id(self, text: str) -> Optional[str]:
        """Extracts canonical arm ID like 'arm_1' from free text."""
        match = re.search(r"\b(?:arm|robot)[\s_\-#]?([1-6])\b", text, re.IGNORECASE)
        if match:
            return f"arm_{match.group(1)}"
        return None

    def extract_joint_ids(self, text: str) -> List[str]:
        """Extracts canonical joint IDs from free text."""
        text_lower = text.lower()
        joints: Set[str] = set()

        # Check explicit joint patterns (e.g., joint 1, j2, joint_3)
        explicit = re.findall(r"\b(?:joint|j)[\s_]?([1-6])\b", text_lower)
        for num in explicit:
            joints.add(f"joint_{num}")

        # Check named joints
        if "shoulder" in text_lower:
            joints.add("joint_2")
        if "elbow" in text_lower:
            joints.add("joint_3")
        if "base" in text_lower:
            joints.add("joint_1")
        if "wrist" in text_lower:
            # If specific wrist mentioned
            if "wrist 1" in text_lower or "wrist_1" in text_lower or "pitch" in text_lower:
                joints.add("joint_4")
            elif "wrist 2" in text_lower or "wrist_2" in text_lower or "yaw" in text_lower:
                joints.add("joint_5")
            elif "wrist 3" in text_lower or "wrist_3" in text_lower or "roll" in text_lower:
                joints.add("joint_6")
            else:
                # Generic wrist refers to all wrist joints
                joints.update(["joint_4", "joint_5", "joint_6"])

        return sorted(list(joints))

    def extract_timestamp(self, text: str) -> Optional[str]:
        """Extracts ISO or standard date/time strings if present."""
        match = re.search(r"\b(\d{4}-\d{2}-\d{2}(?:[T\s]\d{2}:\d{2}(?::\d{2})?)?)\b", text)
        if match:
            return match.group(1)
        return None

    def parse_entry(self, raw_line: str) -> LogEntry:
        """Parses a single free-text log entry."""
        cleaned = raw_line.strip()
        timestamp = self.extract_timestamp(cleaned)
        arm_id = self.extract_arm_id(cleaned)
        joint_ids = self.extract_joint_ids(cleaned)

        text_lower = cleaned.lower()

        # Check if text is unrelated operational chatter
        is_irrelevant = any(irr in text_lower for irr in IRRELEVANT_KEYWORDS)
        has_repair = any(rep in text_lower for rep in REPAIR_KEYWORDS)

        matched_faults: List[str] = []
        categories: List[str] = []
        total_fault_severity = 0.0

        category_max_weights: Dict[str, float] = {}
        for keyword in sorted(FAULT_KEYWORDS.keys(), key=len, reverse=True):
            if keyword in text_lower:
                # Avoid matching sub-phrases if a longer super-phrase already matched
                if any(keyword in longer for longer in matched_faults):
                    continue
                matched_faults.append(keyword)
                cat, weight = FAULT_KEYWORDS[keyword]
                if cat not in categories:
                    categories.append(cat)
                category_max_weights[cat] = max(category_max_weights.get(cat, 0.0), weight)

        total_fault_severity = sum(category_max_weights.values())

        if is_irrelevant and not matched_faults and not has_repair:
            return LogEntry(
                raw_text=cleaned,
                timestamp=timestamp,
                arm_id=arm_id,
                joint_ids=joint_ids,
                is_relevant=False,
                is_repair=False,
                fault_categories=[],
                severity_score=0.0,
                matched_keywords=[],
                explanation="Operational note with no mechanical maintenance relevance."
            )

        if has_repair:
            matched_repairs = [r for r in REPAIR_KEYWORDS if r in text_lower]
            return LogEntry(
                raw_text=cleaned,
                timestamp=timestamp,
                arm_id=arm_id,
                joint_ids=joint_ids,
                is_relevant=True,
                is_repair=True,
                fault_categories=["repair_resolution"],
                severity_score=0.0,
                matched_keywords=matched_repairs,
                explanation=f"Documented maintenance repair/resolution: {matched_repairs}"
            )

        if matched_faults:
            # Cap severity score at 1.0
            sev = min(1.0, total_fault_severity)
            return LogEntry(
                raw_text=cleaned,
                timestamp=timestamp,
                arm_id=arm_id,
                joint_ids=joint_ids,
                is_relevant=True,
                is_repair=False,
                fault_categories=categories,
                severity_score=sev,
                matched_keywords=matched_faults,
                explanation=f"Fault indicators identified: {matched_faults} (Categories: {categories})"
            )

        # Fallback for unclassified notes
        return LogEntry(
            raw_text=cleaned,
            timestamp=timestamp,
            arm_id=arm_id,
            joint_ids=joint_ids,
            is_relevant=False,
            is_repair=False,
            fault_categories=[],
            severity_score=0.0,
            matched_keywords=[],
            explanation="General observation without recognized maintenance keywords."
        )

    def process_log_file(self, file_content_or_path: str) -> List[LogEntry]:
        """
        Parses full log file, maintains stateful concern scores,
        and applies repairs only to verified arms/joints.
        """
        # Check if input is path or direct text
        lines: List[str] = []
        try:
            with open(file_content_or_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
        except Exception:
            lines = file_content_or_path.splitlines()

        self.parsed_entries.clear()

        for line in lines:
            if not line.strip() or line.strip().startswith("#"):
                continue

            entry = self.parse_entry(line)
            self.parsed_entries.append(entry)

            if not entry.is_relevant or not entry.arm_id:
                continue

            # Determine affected joints
            affected_joints = entry.joint_ids if entry.joint_ids else [f"joint_{i}" for i in range(1, 7)]

            for j_id in affected_joints:
                key = (entry.arm_id, j_id)
                status = self.statuses[key]

                if entry.is_repair:
                    # Completed repair clears previously accumulated concern for this arm and joint!
                    status.resolved_issues.extend(status.active_issues)
                    status.active_issues.clear()
                    status.concern_score = 0.0
                    status.explanations.append(
                        f"Concern cleared by repair: '{entry.raw_text}'"
                    )
                else:
                    # Accumulate concern with diminishing marginal increment
                    new_concern = status.concern_score + (1.0 - status.concern_score) * entry.severity_score
                    status.concern_score = round(min(1.0, new_concern), 4)
                    status.active_issues.append(entry.raw_text)
                    status.explanations.append(
                        f"Concern increased to {status.concern_score:.2f} by finding: '{entry.raw_text}'"
                    )

        return self.parsed_entries

    def get_arm_concern(self, arm_id: str) -> Tuple[float, List[str], List[str]]:
        """
        Aggregates maintenance concern for an entire arm across all joints.

        Returns:
            (max_concern_score, list_of_active_issues, list_of_explanations)
        """
        max_score = 0.0
        all_active: List[str] = []
        all_explanations: List[str] = []

        for j_i in range(1, 7):
            j_id = f"joint_{j_i}"
            st = self.statuses.get((arm_id, j_id))
            if st:
                if st.concern_score > max_score:
                    max_score = st.concern_score
                all_active.extend(st.active_issues)
                all_explanations.extend(st.explanations)

        return max_score, all_active, all_explanations

    def get_summary_dict(self) -> Dict[str, Any]:
        """Returns structured JSON-serializable maintenance status for all arms."""
        summary = {}
        for arm_i in range(1, 7):
            arm_id = f"arm_{arm_i}"
            score, active, expl = self.get_arm_concern(arm_id)
            summary[arm_id] = {
                "max_concern_score": round(score, 4),
                "active_issue_count": len(active),
                "active_issues": active,
                "explanations": expl,
                "joints": {
                    f"joint_{j}": {
                        "concern_score": self.statuses[(arm_id, f"joint_{j}")].concern_score,
                        "active_issues": self.statuses[(arm_id, f"joint_{j}")].active_issues,
                        "resolved_issues": self.statuses[(arm_id, f"joint_{j}")].resolved_issues,
                    }
                    for j in range(1, 7)
                }
            }
        return summary
