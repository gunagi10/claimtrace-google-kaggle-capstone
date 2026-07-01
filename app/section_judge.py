from __future__ import annotations

from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import settings
from app.review_models import SectionAnalysisOutput, SectionAssessment, SectionPacket
from app.section_agent import section_app


class SectionJudgeConfigurationError(ValueError):
    """Raised when Gemini section-analysis configuration is missing or incomplete."""


async def analyze_section_packet(packet: SectionPacket) -> SectionAssessment:
    if not settings.gemini_config_ready():
        raise SectionJudgeConfigurationError(
            "Gemini section-analysis configuration is missing. Populate the .env placeholders before running the live section-analysis step."
        )

    parsed = await _run_section_agent(packet)
    return SectionAssessment(
        section_id=packet.section_id,
        heading=packet.heading,
        order=packet.order,
        summary=parsed.summary,
        factual_strengths=parsed.factual_strengths,
        factual_gaps=parsed.factual_gaps,
        insight_issues=parsed.insight_issues,
        unresolved_risks=parsed.unresolved_risks,
        recommended_revisions=parsed.recommended_revisions,
        needs_human_attention=parsed.needs_human_attention,
    )


async def _run_section_agent(packet: SectionPacket) -> SectionAnalysisOutput:
    session_service = InMemorySessionService()
    session_id = f"section-{uuid4().hex}"
    user_id = "local-review"
    await session_service.create_session(
        app_name=section_app.name,
        user_id=user_id,
        session_id=session_id,
    )
    runner = Runner(app=section_app, session_service=session_service)
    final_text: str | None = None
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=_build_prompt(packet))],
            ),
        ):
            if event.is_final_response() and event.content:
                text_parts = [part.text for part in event.content.parts if part.text]
                if text_parts:
                    final_text = "".join(text_parts)
    finally:
        await runner.close()

    if not final_text:
        raise SectionJudgeConfigurationError(
            "ADK section-analysis worker returned no final response."
        )
    try:
        return SectionAnalysisOutput.model_validate_json(final_text)
    except ValueError as exc:
        raise SectionJudgeConfigurationError(
            "ADK section-analysis worker returned an unexpected structured response."
        ) from exc


def _build_prompt(packet: SectionPacket) -> str:
    claim_lines = []
    for claim in packet.checked_claims:
        claim_lines.append(
            (
                f"- sentence_id: {claim.sentence_id}; claim_id: {claim.claim_id}; "
                f"claim: {claim.approved_claim_text}; verdict: {claim.evidence_verdict}; "
                f"reason: {claim.evidence_reason}; action: {claim.recommended_action}; "
                f"reference_id: {claim.reference_id}; passage_ids: {claim.linked_passage_ids}; "
                f"warnings: {claim.warnings}"
            )
        )

    subchunk_lines = []
    for subchunk in packet.subchunks:
        subchunk_lines.append(
            f"- {subchunk.subchunk_id} (order={subchunk.order}, words={subchunk.word_count}): {subchunk.content}"
        )

    return f"""
Section:
- section_id: {packet.section_id}
- heading: {packet.heading}
- order: {packet.order}
- word_count: {packet.word_count}
- is_oversized: {packet.is_oversized}

Section text:
{packet.section_text}

Section subchunks:
{chr(10).join(subchunk_lines) if subchunk_lines else "- none"}

Checked claims in this section:
{chr(10).join(claim_lines) if claim_lines else "- none"}

Coverage summary:
- checked_claim_count: {packet.coverage_summary.checked_claim_count}
- contradicted_count: {packet.coverage_summary.contradicted_count}
- unsupported_count: {packet.coverage_summary.unsupported_count}
- unverified_count: {packet.coverage_summary.unverified_count}
- deselected_count: {packet.coverage_summary.deselected_count}

Gate context:
- global_gate_status: {packet.gate_context.global_gate_status}
- global_gate_summary: {packet.gate_context.global_gate_summary}
- global_stop_recommended: {packet.gate_context.global_stop_recommended}
- section_has_contradiction: {packet.gate_context.section_has_contradiction}
- section_has_warning: {packet.gate_context.section_has_warning}

Unresolved risks:
{chr(10).join(f"- {risk}" for risk in packet.unresolved_risks) if packet.unresolved_risks else "- none"}
""".strip()
