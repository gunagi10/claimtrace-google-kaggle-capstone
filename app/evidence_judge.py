from __future__ import annotations

from uuid import uuid4

from google.genai import types
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService

from app.agent import app as judge_app
from app.config import settings
from app.review_models import (
    EvidenceAssessment,
    EvidenceReviewPayload,
    JudgeOutput,
)


class JudgeConfigurationError(ValueError):
    """Raised when Gemini judge configuration is missing or incomplete."""


async def judge_evidence_payload(payload: EvidenceReviewPayload) -> EvidenceAssessment:
    if not settings.gemini_config_ready():
        raise JudgeConfigurationError(
            "Gemini judge configuration is missing. Populate the .env placeholders before running the live judge step."
        )

    parsed = await _run_judge_agent(payload)

    valid_passage_ids = {passage.passage_id for passage in payload.candidate_passages}
    kept_passage_ids = [pid for pid in parsed.passage_ids if pid in valid_passage_ids]

    return EvidenceAssessment(
        claim_id=payload.claim_id,
        source_id=payload.source_id,
        verdict=parsed.verdict,
        reason=parsed.reason,
        recommended_action=parsed.recommended_action,
        source_fetch_status=payload.source_fetch_status,
        source_extraction_status=payload.source_extraction_status,
        passage_ids=kept_passage_ids,
        warnings=parsed.warnings,
    )


async def _run_judge_agent(payload: EvidenceReviewPayload) -> JudgeOutput:
    session_service = InMemorySessionService()
    session_id = f"judge-{uuid4().hex}"
    user_id = "local-review"
    await session_service.create_session(
        app_name=judge_app.name,
        user_id=user_id,
        session_id=session_id,
    )
    runner = Runner(app=judge_app, session_service=session_service)
    final_text: str | None = None
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=_build_prompt(payload))],
            ),
        ):
            if event.is_final_response() and event.content:
                text_parts = [part.text for part in event.content.parts if part.text]
                if text_parts:
                    final_text = "".join(text_parts)
    finally:
        await runner.close()

    if not final_text:
        raise JudgeConfigurationError("ADK evidence judge returned no final response.")
    try:
        return JudgeOutput.model_validate_json(final_text)
    except ValueError as exc:
        raise JudgeConfigurationError(
            "ADK evidence judge returned an unexpected structured response."
        ) from exc


def _build_prompt(payload: EvidenceReviewPayload) -> str:
    passage_lines = []
    for passage in payload.candidate_passages:
        locator = []
        if passage.locator.heading:
            locator.append(f"heading={passage.locator.heading}")
        if passage.locator.page_number is not None:
            locator.append(f"page={passage.locator.page_number}")
        if passage.locator.text_span_label:
            locator.append(f"span={passage.locator.text_span_label}")
        locator_text = ", ".join(locator) if locator else "no-locator"
        passage_lines.append(
            f"- {passage.passage_id} ({locator_text}): {passage.text}"
        )

    return f"""
Claim:
- claim_id: {payload.claim_id}
- atomic_claim: {payload.atomic_claim}
- original_sentence: {payload.original_sentence}
- section_id: {payload.section_id}
- paragraph_id: {payload.paragraph_id}
- citation_ids: {payload.citation_ids}

Source:
- source_id: {payload.source_id}
- reference_id: {payload.reference_id}
- canonical_url: {payload.canonical_url}
- source_fetch_status: {payload.source_fetch_status}
- source_extraction_status: {payload.source_extraction_status}
- source_warnings: {payload.source_warnings}

Candidate passages:
{chr(10).join(passage_lines)}
""".strip()
