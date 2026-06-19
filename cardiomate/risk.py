from __future__ import annotations

from dataclasses import dataclass
from typing import Any

try:
    from ascvd import compute_ten_year_score
except Exception:  # pragma: no cover - used only when dependency is unavailable
    compute_ten_year_score = None


REQUIRED_FIELDS = [
    "isMale",
    "isBlack",
    "smoker",
    "hypertensive",
    "diabetic",
    "age",
    "systolicBloodPressure",
    "totalCholesterol",
    "hdl",
]

FIELD_LABELS = {
    "name": "Name",
    "isMale": "Sex is male",
    "isBlack": "Race category is Black",
    "smoker": "Current smoker",
    "hypertensive": "Hypertension/BP treatment",
    "diabetic": "Diabetes",
    "age": "Age",
    "systolicBloodPressure": "Systolic blood pressure",
    "totalCholesterol": "Total cholesterol",
    "hdl": "HDL cholesterol",
    "height_cm": "Height (cm)",
    "weight_kg": "Weight (kg)",
    "diet_preference": "Diet preference",
    "activity_level": "Activity level",
    "goal_focus": "Goal focus",
}


@dataclass
class RiskResult:
    ten_year_risk: float
    category: str
    input_data: dict[str, Any]
    caveat: str | None = None


def clean_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    text = str(value).strip().lower()
    if text in {"yes", "y", "true", "1", "male", "m", "black"}:
        return True
    if text in {"no", "n", "false", "0", "female", "f", "non-black", "nonblack"}:
        return False
    return None


def normalize_user_data(data: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(data)
    for key in ["isMale", "isBlack", "smoker", "hypertensive", "diabetic"]:
        if key in normalized:
            normalized[key] = clean_bool(normalized.get(key))
    for key in ["age", "systolicBloodPressure", "totalCholesterol", "hdl"]:
        value = normalized.get(key)
        if value not in (None, ""):
            try:
                normalized[key] = int(float(value))
            except (TypeError, ValueError):
                normalized[key] = None
    for key in ["height_cm", "weight_kg"]:
        value = normalized.get(key)
        if value not in (None, ""):
            try:
                normalized[key] = round(float(value), 1)
            except (TypeError, ValueError):
                normalized[key] = None
    return normalized


def validate_user_data(data: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_user_data(data)
    missing = [field for field in REQUIRED_FIELDS if normalized.get(field) is None]
    warnings: list[str] = []
    age = normalized.get("age")
    if isinstance(age, int) and not 40 <= age <= 79:
        warnings.append("ASCVD pooled cohort equations are mainly validated for ages 40-79.")
    sbp = normalized.get("systolicBloodPressure")
    if isinstance(sbp, int) and not 90 <= sbp <= 220:
        warnings.append("Systolic blood pressure looks outside the usual calculator range.")
    total = normalized.get("totalCholesterol")
    if isinstance(total, int) and not 130 <= total <= 320:
        warnings.append("Total cholesterol looks outside the usual calculator range.")
    hdl = normalized.get("hdl")
    if isinstance(hdl, int) and not 20 <= hdl <= 100:
        warnings.append("HDL cholesterol looks outside the usual calculator range.")
    return {"complete": len(missing) == 0, "missing_fields": missing, "warnings": warnings}


def categorize_risk(percent: float) -> str:
    if percent < 5:
        return "Low"
    if percent < 7.5:
        return "Borderline"
    if percent < 20:
        return "Intermediate"
    return "High"


def _fallback_score(data: dict[str, Any]) -> float:
    score = 2.0
    score += max(0, data["age"] - 40) * 0.22
    score += max(0, data["systolicBloodPressure"] - 120) * 0.06
    score += max(0, data["totalCholesterol"] - 180) * 0.025
    score += max(0, 55 - data["hdl"]) * 0.08
    score += 3.0 if data["smoker"] else 0
    score += 2.5 if data["diabetic"] else 0
    score += 1.5 if data["hypertensive"] else 0
    score += 1.0 if data["isMale"] else 0
    score += 0.8 if data["isBlack"] else 0
    return min(max(score, 1.0), 35.0)


def estimate_ascvd_risk(data: dict[str, Any]) -> RiskResult:
    normalized = normalize_user_data(data)
    validation = validate_user_data(normalized)
    if not validation["complete"]:
        missing = ", ".join(validation["missing_fields"])
        raise ValueError(f"Missing required fields: {missing}")

    estimator_input = {field: normalized[field] for field in REQUIRED_FIELDS}
    caveat = None
    if compute_ten_year_score:
        raw_score = compute_ten_year_score(**estimator_input)
        percent = float(raw_score) * 100 if float(raw_score) <= 1 else float(raw_score)
    else:
        percent = _fallback_score(estimator_input)
        caveat = "Using fallback estimate because the ascvd package is unavailable."

    percent = round(percent, 1)
    return RiskResult(
        ten_year_risk=percent,
        category=categorize_risk(percent),
        input_data=normalized,
        caveat=caveat,
    )


def missing_fields_text(data: dict[str, Any]) -> str:
    validation = validate_user_data(data)
    if validation["complete"]:
        return "All required ASCVD fields are complete."
    labels = [FIELD_LABELS.get(field, field) for field in validation["missing_fields"]]
    return "Missing: " + ", ".join(labels)
