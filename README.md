---
title: CardioMate V0.0 Beta
sdk: gradio
app_file: app.py
license: mit
---

# CardioMate V0.0 (Beta)

CardioMate is a Gradio + OpenAI SDK portfolio app that helps users understand their estimated 10-year ASCVD cardiovascular risk, learn what the score means in simple language, and download colorful PDF reports and day-wise lifestyle plans.

> Medical disclaimer: CardioMate is for education and wellness planning only. It is not a diagnosis, treatment plan, or emergency service. Users should review results with a qualified clinician.

## Features

- Conversational cardiovascular risk intake with OpenAI tool calling.
- ASCVD 10-year risk score calculation.
- Simple risk explanation and personalized goal recommendations.
- Diet and physical activity planning for 15, 30, 60, or 90 days.
- Rich PDF downloads for assessment results and day-wise progress tracking.
- Rule-based fallback when no OpenAI API key is configured.


## Required ASCVD Inputs

- Sex
- Race category used by the pooled cohort equations: Black or non-Black
- Age
- Systolic blood pressure
- Total cholesterol
- HDL cholesterol
- Current smoking status
- Blood pressure treatment or hypertension status
- Diabetes status

## Notes

The ASCVD pooled cohort equations are intended mainly for adults ages 40-79. CardioMate still collects user information outside that range, but it asks users to verify with a clinician when the score may not apply.
