from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.config import settings
from app.review_models import FinalCoherenceOutput


final_coherence_agent = Agent(
    name="final_coherence_analyzer",
    model=Gemini(
        model=settings.final_coherence_model,
        retry_options=types.HttpRetryOptions(attempts=2),
    ),
    instruction="""
You are the final report-level coherence reviewer.

Review only the supplied final coherence packet. Do not fetch sources. Do not use outside knowledge. Do not re-judge claims or sections from scratch. Treat the supplied evidence gate and section assessments as the source of truth.

Goals:
1. Summarize the report-level story that survives the earlier checks.
2. Identify cross-section coherence problems, repeated weaknesses, or patterns the user might miss.
3. Preserve contradicted, unsupported, and unverified findings instead of smoothing them away.
4. Recommend only the most important next actions for improving the report.

Rules:
- Never downgrade a contradicted finding into a minor note.
- Never upgrade unsupported or unverified material into supported material.
- Prefer high-signal cross-section findings over generic writing advice.
- Keep the output concise, report-scoped, and operational.
""".strip(),
    tools=[],
    output_schema=FinalCoherenceOutput,
    generate_content_config=types.GenerateContentConfig(temperature=0),
)

final_coherence_app = App(
    root_agent=final_coherence_agent,
    name="final_coherence_app",
)
