from __future__ import annotations

from typing import Any


def build_recommendations(data: dict[str, Any], risk_percent: float, category: str) -> list[str]:
    recs = [
        "Review your ASCVD result with a qualified clinician, especially before changing medication.",
        "Aim for a heart-supportive eating pattern: more vegetables, fruits, pulses, whole grains, nuts, and unsaturated oils.",
        "Track blood pressure, activity, sleep, and meals weekly so progress is visible.",
    ]
    if category in {"Intermediate", "High"}:
        recs.append("Ask your clinician whether cholesterol-lowering therapy and tighter blood pressure targets are appropriate.")
    if data.get("smoker"):
        recs.append("Make smoking cessation the highest-impact goal; ask about counseling, nicotine replacement, or medication options.")
    if data.get("hypertensive") or data.get("systolicBloodPressure", 0) >= 130:
        recs.append("Prioritize sodium reduction, home BP checks, medication adherence if prescribed, and regular follow-up.")
    if data.get("diabetic"):
        recs.append("Coordinate glucose, blood pressure, kidney, and cholesterol goals with your diabetes care team.")
    if data.get("hdl", 100) < 40:
        recs.append("Use regular aerobic activity, resistance training, and unsaturated fats to support HDL and metabolic health.")
    if data.get("totalCholesterol", 0) >= 200:
        recs.append("Reduce saturated fat, fried foods, ultra-processed snacks, and increase soluble fiber such as oats, beans, and psyllium.")
    return recs


def daily_plan(data: dict[str, Any], risk_percent: float, category: str, days: int) -> list[dict[str, str]]:
    preference = (data.get("diet_preference") or "heart-healthy").lower()
    activity = (data.get("activity_level") or "beginner").lower()
    smoker = bool(data.get("smoker"))
    hypertensive = bool(data.get("hypertensive") or data.get("systolicBloodPressure", 0) >= 130)

    meals = [
        "Oats or millet porridge with fruit; dal/beans with vegetables; grilled fish/tofu/chicken with salad.",
        "Vegetable omelet or sprouts; brown rice/roti with lentils; curd, salad, and sauteed greens.",
        "Greek yogurt or unsweetened curd with nuts; chickpea bowl; vegetable soup with whole-grain toast.",
        "Idli/dosa with sambar or whole-grain toast; rajma/chana; paneer/tofu/fish with mixed vegetables.",
    ]
    if "vegetarian" in preference:
        meals = [meal.replace("fish/tofu/chicken", "tofu/paneer/beans").replace("fish", "tofu") for meal in meals]

    plan: list[dict[str, str]] = []
    for day in range(1, days + 1):
        phase = "Foundation" if day <= days * 0.33 else "Build" if day <= days * 0.66 else "Strengthen"
        walk_minutes = 15 + min(30, (day // 4) * 5)
        if "active" in activity or "advanced" in activity:
            walk_minutes += 15
        strength = "2 rounds body-weight strength" if day % 3 == 0 else "Mobility and stretching"
        sodium = "Keep salt modest and avoid packaged salty snacks." if hypertensive else "Choose mostly home-cooked meals."
        smoke = "Record triggers and use a quit-support step today." if smoker else "Avoid tobacco exposure."
        plan.append(
            {
                "day": str(day),
                "phase": phase,
                "food": meals[(day - 1) % len(meals)],
                "activity": f"{walk_minutes} min brisk walk + {strength}.",
                "focus": f"{sodium} {smoke}",
                "tracker": "Mood: ___  BP: ___  Steps/min: ___  Completed: yes/no",
            }
        )
    return plan
