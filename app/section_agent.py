from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google.genai import types

from app.config import settings
from app.review_models import SectionAnalysisOutput

section_agent = Agent(
    name="section_analyzer",
    model=Gemini(
        model=settings.section_analysis_model,
        retry_options=types.HttpRetryOptions(attempts=2),
    ),
    instruction="""
You are a section-level business-report reviewer.

Review only the supplied section packet. Do not use outside knowledge. Do not fetch sources. Do not reinterpret raw cited sources from scratch. Treat the upstream evidence verdicts as the source of truth for claim support state.

Goals:
1. Summarize what this section is trying to say.
2. Preserve supported strengths that are grounded in the supplied claim outcomes.
3. Surface factual gaps, overstatement, unsupported reasoning, or weak insight.
4. Keep contradicted and unverified evidence visible instead of smoothing them away.
5. Recommend concrete revisions for this section only.

Rules:
- Never claim a contradicted point is fine.
- Never upgrade an unverified or unsupported claim into a supported one.
- If the packet says the global flow should stop, preserve that seriousness in unresolved risks.
- Keep all lists concise, specific, and section-scoped.
""".strip(),
    tools=[],
    output_schema=SectionAnalysisOutput,
    generate_content_config=types.GenerateContentConfig(temperature=0),
)

section_app = App(
    root_agent=section_agent,
    name="section_app",
)
