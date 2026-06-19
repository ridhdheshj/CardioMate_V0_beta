from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from cardiomate import APP_NAME
from cardiomate.planner import build_recommendations, daily_plan
from cardiomate.risk import FIELD_LABELS


PRIMARY = colors.HexColor("#0F766E")
ACCENT = colors.HexColor("#F97316")
SOFT = colors.HexColor("#ECFDF5")
DARK = colors.HexColor("#0F172A")


def _styles() -> dict[str, ParagraphStyle]:
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("Title", parent=base["Title"], textColor=PRIMARY, fontSize=24, leading=28, spaceAfter=14),
        "h1": ParagraphStyle("Heading", parent=base["Heading1"], textColor=DARK, fontSize=16, leading=20, spaceBefore=12),
        "body": ParagraphStyle("Body", parent=base["BodyText"], fontSize=10, leading=14),
        "small": ParagraphStyle("Small", parent=base["BodyText"], fontSize=8, leading=10, textColor=colors.HexColor("#475569")),
        "callout": ParagraphStyle("Callout", parent=base["BodyText"], fontSize=11, leading=15, textColor=DARK),
    }


def _header_footer(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(PRIMARY)
    canvas.rect(0, A4[1] - 0.35 * inch, A4[0], 0.35 * inch, fill=1, stroke=0)
    canvas.setFillColor(colors.white)
    canvas.setFont("Helvetica-Bold", 9)
    canvas.drawString(0.45 * inch, A4[1] - 0.23 * inch, APP_NAME)
    canvas.setFillColor(colors.HexColor("#64748B"))
    canvas.setFont("Helvetica", 8)
    canvas.drawRightString(A4[0] - 0.45 * inch, 0.35 * inch, f"Page {doc.page}")
    canvas.restoreState()


def _p(text: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(str(text).replace("\n", "<br/>"), style)


def _risk_color(category: str):
    return {
        "Low": colors.HexColor("#16A34A"),
        "Borderline": colors.HexColor("#CA8A04"),
        "Intermediate": colors.HexColor("#EA580C"),
        "High": colors.HexColor("#DC2626"),
    }.get(category, PRIMARY)


def _build_path(prefix: str) -> str:
    safe_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(tempfile.gettempdir(), f"{prefix}_{safe_time}.pdf")


def create_assessment_pdf(session: dict[str, Any]) -> str:
    risk = session.get("risk") or {}
    data = session.get("data") or {}
    if not risk:
        raise ValueError("No completed ASCVD risk assessment is available yet.")

    path = _build_path("cardiomate_assessment")
    doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=36, leftMargin=36, topMargin=54, bottomMargin=40)
    s = _styles()
    recs = build_recommendations(data, risk["ten_year_risk"], risk["category"])
    story = [
        _p("CardioMate Cardiovascular Risk Report", s["title"]),
        _p("Educational wellness report. Please review medical decisions with a qualified clinician.", s["small"]),
        Spacer(1, 10),
        Table(
            [[_p(f"{risk['ten_year_risk']}%", s["title"]), _p(f"{risk['category']} estimated 10-year ASCVD risk", s["callout"])]],
            colWidths=[1.6 * inch, 4.7 * inch],
            style=TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), SOFT),
                ("BOX", (0, 0), (-1, -1), 1, _risk_color(risk["category"])),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("PADDING", (0, 0), (-1, -1), 12),
            ]),
        ),
        _p("Your Inputs", s["h1"]),
    ]

    rows = [["Factor", "Value"]]
    for key, value in data.items():
        if value is not None and key in FIELD_LABELS:
            rows.append([FIELD_LABELS[key], str(value)])
    story.append(Table(rows, colWidths=[2.8 * inch, 3.5 * inch], style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("PADDING", (0, 0), (-1, -1), 7),
    ])))
    story.append(_p("Personal Goals and Recommendations", s["h1"]))
    for item in recs:
        story.append(_p(f"- {item}", s["body"]))
    story.append(_p("Safety Note", s["h1"]))
    story.append(_p("Seek urgent care for chest pain, stroke symptoms, severe shortness of breath, fainting, or sudden severe weakness. This app does not provide diagnosis or emergency triage.", s["body"]))
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return path


def create_plan_pdf(session: dict[str, Any], days: int) -> str:
    risk = session.get("risk") or {"ten_year_risk": 0, "category": "Not calculated"}
    data = session.get("data") or {}
    path = _build_path(f"cardiomate_{days}_day_plan")
    doc = SimpleDocTemplate(path, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=54, bottomMargin=40)
    s = _styles()
    plan = daily_plan(data, risk["ten_year_risk"], risk["category"], days)
    story = [
        _p(f"{days}-Day Heart Health Plan", s["title"]),
        _p(f"Built for {APP_NAME}. Use this as a progress tracker and discuss changes with your care team.", s["small"]),
        Spacer(1, 8),
    ]
    rows = [["Day", "Phase", "Food direction", "Activity", "Progress tracker"]]
    for item in plan:
        rows.append([
            item["day"],
            item["phase"],
            _p(item["food"], s["small"]),
            _p(item["activity"], s["small"]),
            _p(item["tracker"], s["small"]),
        ])
    story.append(Table(rows, colWidths=[0.35 * inch, 0.75 * inch, 2.1 * inch, 1.65 * inch, 1.75 * inch], repeatRows=1, style=TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), PRIMARY),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CBD5E1")),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F8FAFC")]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("PADDING", (0, 0), (-1, -1), 5),
    ])))
    story.append(PageBreak())
    story.append(_p("Daily Focus Guide", s["h1"]))
    for item in plan[: min(days, 30)]:
        story.append(_p(f"Day {item['day']}: {item['focus']}", s["body"]))
    doc.build(story, onFirstPage=_header_footer, onLaterPages=_header_footer)
    return path
