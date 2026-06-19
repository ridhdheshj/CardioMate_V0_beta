from __future__ import annotations

import json
import os
import re
from copy import deepcopy
from typing import Any

import gradio as gr
from dotenv import load_dotenv
from openai import OpenAI

from cardiomate import APP_NAME
from cardiomate.pdf_report import create_assessment_pdf, create_plan_pdf
from cardiomate.planner import build_recommendations
from cardiomate.prompts import INTRO_MESSAGE, SYSTEM_PROMPT
from cardiomate.risk import (
    FIELD_LABELS,
    estimate_ascvd_risk,
    missing_fields_text,
    normalize_user_data,
    validate_user_data,
)

load_dotenv()

MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY")) if os.getenv("OPENAI_API_KEY") else None


def default_state() -> dict[str, Any]:
    return {"data": {}, "risk": None, "events": []}


def ensure_state(state: dict[str, Any] | None) -> dict[str, Any]:
    if not state:
        return default_state()
    state.setdefault("data", {})
    state.setdefault("risk", None)
    state.setdefault("events", [])
    return state


def record_user_details(state: dict[str, Any], **kwargs) -> dict[str, Any]:
    state = ensure_state(state)
    aliases = {
        "sex": "isMale",
        "race_black": "isBlack",
        "bp_treatment": "hypertensive",
        "blood_pressure_treatment": "hypertensive",
        "sbp": "systolicBloodPressure",
        "total_cholesterol": "totalCholesterol",
        "hdl_cholesterol": "hdl",
    }
    cleaned = {}
    for key, value in kwargs.items():
        target = aliases.get(key, key)
        if value not in (None, ""):
            cleaned[target] = value
    state["data"].update(normalize_user_data(cleaned))
    state["events"].append({"type": "data_update", "data": deepcopy(state["data"])})
    validation = validate_user_data(state["data"])
    return {"stored": state["data"], **validation}


def validate_user_data_tool(state: dict[str, Any]) -> dict[str, Any]:
    return validate_user_data(ensure_state(state)["data"])


def ascvd_risk_estimator_tool(state: dict[str, Any]) -> dict[str, Any]:
    state = ensure_state(state)
    result = estimate_ascvd_risk(state["data"])
    state["risk"] = {
        "ten_year_risk": result.ten_year_risk,
        "category": result.category,
        "caveat": result.caveat,
    }
    state["events"].append({"type": "risk_calculated", "risk": deepcopy(state["risk"])})
    return {"risk": state["risk"], "input_data": result.input_data}


TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "record_user_details",
            "description": "Store cardiovascular risk details extracted from the user message.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "isMale": {"type": "boolean"},
                    "isBlack": {"type": "boolean"},
                    "smoker": {"type": "boolean"},
                    "hypertensive": {"type": "boolean"},
                    "diabetic": {"type": "boolean"},
                    "age": {"type": "integer"},
                    "systolicBloodPressure": {"type": "integer"},
                    "totalCholesterol": {"type": "integer"},
                    "hdl": {"type": "integer"},
                    "height_cm": {"type": "number"},
                    "weight_kg": {"type": "number"},
                    "diet_preference": {"type": "string"},
                    "activity_level": {"type": "string"},
                    "goal_focus": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_user_data",
            "description": "Check whether all required ASCVD risk fields are present.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ascvd_risk_estimator",
            "description": "Calculate the 10-year ASCVD risk after all required fields are collected.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def tool_dispatch(name: str, args: dict[str, Any], state: dict[str, Any]) -> dict[str, Any]:
    if name == "record_user_details":
        return record_user_details(state, **args)
    if name == "validate_user_data":
        return validate_user_data_tool(state)
    if name == "ascvd_risk_estimator":
        return ascvd_risk_estimator_tool(state)
    raise ValueError(f"Unknown tool: {name}")


def compact_state_context(state: dict[str, Any]) -> str:
    return json.dumps(
        {
            "collected_data": state.get("data", {}),
            "validation": validate_user_data(state.get("data", {})),
            "risk": state.get("risk"),
        },
        indent=2,
    )


def history_to_messages(history: list[Any]) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = []
    for item in history or []:
        if isinstance(item, dict) and item.get("role") in {"user", "assistant"}:
            messages.append({"role": item["role"], "content": item.get("content", "")})
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            user_text, assistant_text = item
            if user_text:
                messages.append({"role": "user", "content": str(user_text)})
            if assistant_text:
                messages.append({"role": "assistant", "content": str(assistant_text)})
    return messages


def openai_agent_reply(message: str, history: list[Any], state: dict[str, Any]) -> str:
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "system", "content": "Current session state:\n" + compact_state_context(state)},
    ]
    messages.extend(history_to_messages(history)[-12:])
    messages.append({"role": "user", "content": message})

    for _ in range(6):
        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOLS,
            temperature=0.3,
        )
        choice = response.choices[0]
        assistant_message = choice.message
        if not assistant_message.tool_calls:
            return assistant_message.content or "I could not generate a response. Please try again."

        messages.append(assistant_message.model_dump(exclude_none=True))
        for call in assistant_message.tool_calls:
            args = json.loads(call.function.arguments or "{}")
            result = tool_dispatch(call.function.name, args, state)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call.id,
                    "content": json.dumps(result),
                }
            )
    return fallback_reply(message, state)


def parse_free_text(message: str) -> dict[str, Any]:
    text = message.lower()
    data: dict[str, Any] = {}

    if re.search(r"\b(female|woman|girl)\b", text):
        data["isMale"] = False
    if re.search(r"\b(male|man|boy)\b", text):
        data["isMale"] = True
    if "non-black" in text or "non black" in text:
        data["isBlack"] = False
    elif re.search(r"\bblack\b", text):
        data["isBlack"] = True
    if re.search(r"\b(non[- ]?smoker|do not smoke|don't smoke|no smoking)\b", text):
        data["smoker"] = False
    elif re.search(r"\b(smoker|smoke|smoking)\b", text):
        data["smoker"] = True
    if re.search(r"\b(no diabetes|not diabetic)\b", text):
        data["diabetic"] = False
    elif re.search(r"\b(diabetes|diabetic)\b", text):
        data["diabetic"] = True
    if re.search(r"\b(no hypertension|not hypertensive|no bp medicine|no blood pressure medicine)\b", text):
        data["hypertensive"] = False
    elif re.search(r"\b(hypertension|hypertensive|bp medicine|blood pressure medicine|bp treatment)\b", text):
        data["hypertensive"] = True

    patterns = {
        "age": r"(?:age|aged|i am|i'm)\s*(\d{2})",
        "systolicBloodPressure": r"(?:systolic|sbp|blood pressure|bp)\D{0,8}(\d{2,3})",
        "totalCholesterol": r"(?:total cholesterol|cholesterol|tc)\D{0,8}(\d{2,3})",
        "hdl": r"(?:hdl)\D{0,8}(\d{2,3})",
        "height_cm": r"(?:height)\D{0,8}(\d{2,3}(?:\.\d+)?)",
        "weight_kg": r"(?:weight)\D{0,8}(\d{2,3}(?:\.\d+)?)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text)
        if match:
            data[key] = match.group(1)
    return normalize_user_data(data)


def fallback_reply(message: str, state: dict[str, Any]) -> str:
    extracted = parse_free_text(message)
    if extracted:
        record_user_details(state, **extracted)

    validation = validate_user_data(state["data"])
    if not validation["complete"]:
        return (
            "I have saved what I could understand. "
            f"{missing_fields_text(state['data'])}. "
            "You can reply naturally, for example: 'I am 55, male, non-Black, non-smoker, "
            "BP 145, total cholesterol 220, HDL 45, diabetic no, BP treatment yes.'"
        )

    if state.get("risk") is None:
        ascvd_risk_estimator_tool(state)

    risk = state["risk"]
    recs = build_recommendations(state["data"], risk["ten_year_risk"], risk["category"])
    return (
        f"Your estimated 10-year ASCVD risk is {risk['ten_year_risk']}%, which is in the "
        f"{risk['category'].lower()} category. This means that out of 100 people with a similar "
        "risk profile, about this many may have a heart attack or stroke over 10 years. "
        f"Top next step: {recs[0]} You can now download the full PDF report or generate a day-wise plan."
    )


def respond(message: str, history: list[Any], state: dict[str, Any], plan_days: int):
    state = ensure_state(state)
    history = history or []
    if not message.strip():
        return "", history, state, status_markdown(state)

    if client:
        try:
            reply = openai_agent_reply(message, history, state)
        except Exception as exc:
            reply = f"I had trouble reaching the OpenAI model, so I used the local fallback. ({exc})\n\n"
            reply += fallback_reply(message, state)
    else:
        reply = fallback_reply(message, state)

    history = history + [{"role": "user", "content": message}, {"role": "assistant", "content": reply}]
    return "", history, state, status_markdown(state)


def status_markdown(state: dict[str, Any] | None) -> str:
    state = ensure_state(state)
    risk = state.get("risk")
    validation = validate_user_data(state.get("data", {}))
    rows = [f"**Assessment status:** {'Complete' if validation['complete'] else 'In progress'}"]
    if risk:
        rows.append(f"**ASCVD risk:** {risk['ten_year_risk']}% ({risk['category']})")
    else:
        rows.append(f"**Needed:** {missing_fields_text(state.get('data', {}))}")
    if validation.get("warnings"):
        rows.append("**Check:** " + " ".join(validation["warnings"]))
    return "\n\n".join(rows)


def download_report(state: dict[str, Any] | None):
    state = ensure_state(state)
    if not state.get("risk"):
        return None, "Complete the ASCVD assessment first, then download the report."
    return create_assessment_pdf(state), "Assessment PDF is ready."


def download_plan(state: dict[str, Any] | None, plan_days: int):
    state = ensure_state(state)
    if not state.get("risk"):
        validation = validate_user_data(state.get("data", {}))
        if validation["complete"]:
            ascvd_risk_estimator_tool(state)
        else:
            return None, "Complete the ASCVD assessment first, then generate a plan."
    return create_plan_pdf(state, int(plan_days)), f"{plan_days}-day plan PDF is ready."


def reset_chat():
    return [{"role": "assistant", "content": INTRO_MESSAGE}], default_state(), status_markdown(default_state()), None, None


CSS = """
.gradio-container { max-width: 1180px !important; }
#hero {
  background: linear-gradient(135deg, #0f766e 0%, #14b8a6 55%, #f97316 100%);
  color: white;
  padding: 28px;
  border-radius: 8px;
  margin-bottom: 14px;
}
#hero h1 { margin: 0 0 8px 0; font-size: 34px; letter-spacing: 0; }
#hero p { margin: 0; font-size: 16px; max-width: 850px; }
.status-card {
  border: 1px solid #dbeafe;
  background: #f8fafc;
  padding: 14px;
  border-radius: 8px;
}
"""


with gr.Blocks(theme=gr.themes.Soft(primary_hue="teal", secondary_hue="orange"), css=CSS, title=APP_NAME) as demo:
    app_state = gr.State(default_state())
    gr.HTML(
        f"""
        <div id="hero">
          <h1>{APP_NAME}</h1>
          <p>Your conversational ASCVD risk educator, goal coach, and PDF plan builder.</p>
        </div>
        """
    )
    with gr.Row():
        with gr.Column(scale=7):
            chatbot = gr.Chatbot(
                value=[{"role": "assistant", "content": INTRO_MESSAGE}],
                height=520,
                label="CardioMate chat",
            )
            with gr.Row():
                user_input = gr.Textbox(
                    placeholder="Tell me your details or ask a cardiovascular health question...",
                    scale=8,
                    show_label=False,
                )
                send_btn = gr.Button("Send", variant="primary", scale=1)
            gr.Examples(
                examples=[
                    "I am 55, male, non-Black, non-smoker, BP 145, total cholesterol 220, HDL 45, diabetic no, BP treatment yes.",
                    "What does ASCVD risk mean in simple words?",
                    "I want a vegetarian 30 day diet and activity plan.",
                ],
                inputs=user_input,
            )
        with gr.Column(scale=3):
            gr.Markdown("### Progress")
            status = gr.Markdown(value=status_markdown(default_state()), elem_classes=["status-card"])
            plan_days = gr.Dropdown([15, 30, 60, 90], value=30, label="Plan duration")
            report_btn = gr.Button("Download assessment PDF")
            plan_btn = gr.Button("Download plan PDF")
            report_file = gr.File(label="Assessment report")
            plan_file = gr.File(label="Plan report")
            file_status = gr.Markdown()
            reset_btn = gr.Button("Start new assessment")
            gr.Markdown(
                "CardioMate is educational and does not replace medical care. "
                "For chest pain, stroke symptoms, fainting, or severe shortness of breath, seek urgent care."
            )

    send_event = user_input.submit(
        respond,
        inputs=[user_input, chatbot, app_state, plan_days],
        outputs=[user_input, chatbot, app_state, status],
    )
    send_btn.click(
        respond,
        inputs=[user_input, chatbot, app_state, plan_days],
        outputs=[user_input, chatbot, app_state, status],
    )
    report_btn.click(download_report, inputs=app_state, outputs=[report_file, file_status])
    plan_btn.click(download_plan, inputs=[app_state, plan_days], outputs=[plan_file, file_status])
    reset_btn.click(reset_chat, outputs=[chatbot, app_state, status, report_file, plan_file])


if __name__ == "__main__":
    demo.launch()
