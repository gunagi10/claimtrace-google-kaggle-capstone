from __future__ import annotations

from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.config import settings
from app.final_coherence_agent import final_coherence_app
from app.review_models import (
    FinalCoherenceAssessment,
    FinalCoherenceOutput,
    FinalCoherencePacket,
)


class FinalCoherenceConfigurationError(ValueError):
    """Raised when Gemini final-coherence configuration is missing or incomplete."""


async def analyze_final_coherence_packet(
    packet: FinalCoherencePacket,
) -> FinalCoherenceAssessment:
    if not settings.gemini_config_ready():
        raise FinalCoherenceConfigurationError(
            "Gemini final-coherence configuration is missing. Populate the .env placeholders before running the live final coherence step."
        )

    parsed = await _run_final_coherence_agent(packet)
    return FinalCoherenceAssessment(
        report_summary=parsed.report_summary,
        coherence_strengths=parsed.coherence_strengths,
        coherence_issues=parsed.coherence_issues,
        soundness_issues=parsed.soundness_issues,
        noteworthy_patterns=parsed.noteworthy_patterns,
        priority_actions=parsed.priority_actions,
        unresolved_risks=parsed.unresolved_risks,
        needs_human_attention=parsed.needs_human_attention,
    )


async def _run_final_coherence_agent(
    packet: FinalCoherencePacket,
) -> FinalCoherenceOutput:
    session_service = InMemorySessionService()
    session_id = f"coherence-{uuid4().hex}"
    user_id = "local-review"
    await session_service.create_session(
        app_name=final_coherence_app.name,
        user_id=user_id,
        session_id=session_id,
    )
    runner = Runner(app=final_coherence_app, session_service=session_service)
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
        raise FinalCoherenceConfigurationError(
            "ADK final-coherence worker returned no final response."
        )
    try:
        return FinalCoherenceOutput.model_validate_json(final_text)
    except ValueError as exc:
        raise FinalCoherenceConfigurationError(
            "ADK final-coherence worker returned an unexpected structured response."
        ) from exc


def _build_prompt(packet: FinalCoherencePacket) -> str:
    section_lines = []
    for section in packet.section_digests:
        section_lines.append(
            f"""
- section_id: {section.section_id}
  heading: {section.heading}
  order: {section.order}
  checked_claim_count: {section.checked_claim_count}
  contradicted_count: {section.contradicted_count}
  unsupported_count: {section.unsupported_count}
  unverified_count: {section.unverified_count}
  deselected_count: {section.deselected_count}
  section_has_contradiction: {section.section_has_contradiction}
  section_has_warning: {section.section_has_warning}
  needs_human_attention: {section.needs_human_attention}
  summary: {section.summary}
  factual_strengths: {section.factual_strengths}
  factual_gaps: {section.factual_gaps}
  insight_issues: {section.insight_issues}
  unresolved_risks: {section.unresolved_risks}
  recommended_revisions: {section.recommended_revisions}
""".strip()
        )

    return f"""
Review:
- review_id: {packet.review_id}

Global gate:
- status: {packet.global_gate.status}
- summary: {packet.global_gate.summary}
- checked_claim_count: {packet.global_gate.checked_claim_count}
- pending_claim_count: {packet.global_gate.pending_claim_count}
- contradiction_count: {packet.global_gate.contradiction_count}
- unsupported_count: {packet.global_gate.unsupported_count}
- unverified_count: {packet.global_gate.unverified_count}
- contradiction_sentence_ids: {packet.global_gate.contradiction_sentence_ids}
- warning_sentence_ids: {packet.global_gate.warning_sentence_ids}

Report coverage:
- selected_claim_count: {packet.report_coverage.selected_claim_count}
- completed_claim_count: {packet.report_coverage.completed_claim_count}
- unresolved_claim_count: {packet.report_coverage.unresolved_claim_count}
- deselected_claim_count: {packet.report_coverage.deselected_claim_count}
- contradicted_claim_count: {packet.report_coverage.contradicted_claim_count}
- unsupported_claim_count: {packet.report_coverage.unsupported_claim_count}
- unverified_claim_count: {packet.report_coverage.unverified_claim_count}
- eligible_section_count: {packet.report_coverage.eligible_section_count}
- completed_section_count: {packet.report_coverage.completed_section_count}
- human_attention_section_count: {packet.report_coverage.human_attention_section_count}

Section digests:
{chr(10).join(section_lines) if section_lines else "- none"}

Unresolved report risks:
{chr(10).join(f"- {risk}" for risk in packet.unresolved_report_risks) if packet.unresolved_report_risks else "- none"}
""".strip()
