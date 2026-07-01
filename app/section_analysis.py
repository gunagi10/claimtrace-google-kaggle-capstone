from __future__ import annotations

import asyncio
import re
from time import perf_counter

from pydantic import BaseModel, Field

from app.config import settings
from app.review_models import (
    BatchGateRecommendation,
    DocumentSection,
    ParsedDocument,
    SectionAssessment,
    SectionClaimOutcome,
    SectionCoverageSummary,
    SectionGateContext,
    SectionPacket,
    SectionSubchunk,
)
from app.section_judge import SectionJudgeConfigurationError, analyze_section_packet


REFERENCE_SECTION_TITLES = {"references", "bibliography", "sources"}


class SectionAnalysisRunItem(BaseModel):
    section_id: str
    status: str
    packet: SectionPacket
    assessment: SectionAssessment | None = None
    message: str | None = None


class SectionWorkerTiming(BaseModel):
    section_id: str
    started_offset_ms: int
    finished_offset_ms: int
    duration_ms: int


class SectionConcurrencyDebug(BaseModel):
    max_concurrent_workers_configured: int
    max_concurrent_workers_seen: int
    total_elapsed_ms: int
    section_workers: list[SectionWorkerTiming] = Field(default_factory=list)


class SectionRunOutcome(BaseModel):
    items: list[SectionAnalysisRunItem] = Field(default_factory=list)
    concurrency_debug: SectionConcurrencyDebug


def build_section_packets(
    *,
    parsed: ParsedDocument,
    claim_outcomes: list[SectionClaimOutcome],
    gate: BatchGateRecommendation,
    max_section_words: int | None = None,
    max_subchunk_words: int | None = None,
) -> list[SectionPacket]:
    section_word_limit = max_section_words or settings.section_max_words
    subchunk_word_limit = max_subchunk_words or settings.section_subchunk_max_words
    claim_outcomes_by_section: dict[str, list[SectionClaimOutcome]] = {}
    for claim_outcome in claim_outcomes:
        claim_outcomes_by_section.setdefault(claim_outcome.section_id, []).append(
            claim_outcome
        )

    total_sentences_by_section: dict[str, int] = {}
    for sentence in parsed.claim_ready_sentences:
        total_sentences_by_section[sentence.section_id] = (
            total_sentences_by_section.get(sentence.section_id, 0) + 1
        )

    packets: list[SectionPacket] = []
    for section in sorted(parsed.sections, key=lambda item: item.order):
        if not _is_eligible_section(section):
            continue

        section_text = _section_text(section)
        word_count = _word_count(section_text)
        is_oversized = word_count > section_word_limit
        subchunks = (
            _build_subchunks(section, max_subchunk_words=subchunk_word_limit)
            if is_oversized
            else []
        )
        checked_claims = sorted(
            claim_outcomes_by_section.get(section.section_id, []),
            key=lambda claim: claim.sentence_id,
        )
        coverage_summary = SectionCoverageSummary(
            checked_claim_count=len(checked_claims),
            contradicted_count=sum(
                1
                for claim in checked_claims
                if claim.evidence_verdict == "contradicted"
            ),
            unsupported_count=sum(
                1 for claim in checked_claims if claim.evidence_verdict == "unsupported"
            ),
            unverified_count=sum(
                1 for claim in checked_claims if claim.evidence_verdict == "unverified"
            ),
            deselected_count=max(
                total_sentences_by_section.get(section.section_id, 0) - len(checked_claims),
                0,
            ),
        )
        packets.append(
            SectionPacket(
                section_id=section.section_id,
                heading=section.heading,
                order=section.order,
                section_text=(
                    _build_oversized_section_synopsis(subchunks)
                    if is_oversized
                    else section_text
                ),
                word_count=word_count,
                is_oversized=is_oversized,
                subchunks=subchunks,
                checked_claims=checked_claims,
                gate_context=SectionGateContext(
                    global_gate_status=gate.status,
                    global_gate_summary=gate.summary,
                    global_stop_recommended=gate.status == "stop_and_fix",
                    section_has_contradiction=coverage_summary.contradicted_count > 0,
                    section_has_warning=(
                        coverage_summary.unsupported_count > 0
                        or coverage_summary.unverified_count > 0
                    ),
                ),
                coverage_summary=coverage_summary,
                unresolved_risks=_build_unresolved_risks(
                    checked_claims=checked_claims,
                    gate=gate,
                ),
                visual_context=[],
            )
        )
    return packets


async def run_section_packets_with_bounded_concurrency(
    *,
    packets: list[SectionPacket],
    max_concurrent_workers: int | None = None,
) -> SectionRunOutcome:
    configured_workers = max_concurrent_workers or settings.section_max_concurrent_workers
    semaphore = asyncio.Semaphore(configured_workers)
    started_at = perf_counter()
    active_workers = 0
    max_workers_seen = 0

    async def _bounded_worker(packet: SectionPacket) -> tuple[SectionAnalysisRunItem, SectionWorkerTiming]:
        nonlocal active_workers, max_workers_seen
        async with semaphore:
            active_workers += 1
            max_workers_seen = max(max_workers_seen, active_workers)
            worker_started_at = perf_counter()
            try:
                try:
                    assessment = await analyze_section_packet(packet)
                except SectionJudgeConfigurationError as exc:
                    item = SectionAnalysisRunItem(
                        section_id=packet.section_id,
                        status="awaiting_model_config",
                        packet=packet,
                        message=str(exc),
                    )
                else:
                    item = SectionAnalysisRunItem(
                        section_id=packet.section_id,
                        status="completed",
                        packet=packet,
                        assessment=assessment,
                    )
            finally:
                worker_finished_at = perf_counter()
                active_workers -= 1
            return item, SectionWorkerTiming(
                section_id=packet.section_id,
                started_offset_ms=round((worker_started_at - started_at) * 1000),
                finished_offset_ms=round((worker_finished_at - started_at) * 1000),
                duration_ms=round((worker_finished_at - worker_started_at) * 1000),
            )

    worker_outcomes = await asyncio.gather(
        *[asyncio.create_task(_bounded_worker(packet)) for packet in packets]
    )
    finished_at = perf_counter()
    items = [item for item, _timing in worker_outcomes]
    timings = [timing for _item, timing in worker_outcomes]
    timings.sort(key=lambda timing: (timing.started_offset_ms, timing.section_id))
    return SectionRunOutcome(
        items=items,
        concurrency_debug=SectionConcurrencyDebug(
            max_concurrent_workers_configured=configured_workers,
            max_concurrent_workers_seen=max_workers_seen,
            total_elapsed_ms=round((finished_at - started_at) * 1000),
            section_workers=timings,
        ),
    )


def _is_eligible_section(section: DocumentSection) -> bool:
    return (
        section.heading.strip().lower() not in REFERENCE_SECTION_TITLES
        and bool(_section_text(section).strip())
    )


def _section_text(section: DocumentSection) -> str:
    return "\n\n".join(paragraph.text.strip() for paragraph in section.paragraphs if paragraph.text.strip())


def _build_subchunks(
    section: DocumentSection,
    *,
    max_subchunk_words: int,
) -> list[SectionSubchunk]:
    chunks: list[str] = []
    current_parts: list[str] = []
    current_word_count = 0

    for paragraph in _paragraphs_for_chunking(section):
        paragraph_word_count = _word_count(paragraph)
        if paragraph_word_count > max_subchunk_words:
            if current_parts:
                chunks.append("\n\n".join(current_parts))
                current_parts = []
                current_word_count = 0
            chunks.extend(_split_long_paragraph(paragraph, max_subchunk_words))
            continue

        if current_parts and current_word_count + paragraph_word_count > max_subchunk_words:
            chunks.append("\n\n".join(current_parts))
            current_parts = [paragraph]
            current_word_count = paragraph_word_count
            continue

        current_parts.append(paragraph)
        current_word_count += paragraph_word_count

    if current_parts:
        chunks.append("\n\n".join(current_parts))

    return [
        SectionSubchunk(
            subchunk_id=f"{section.section_id}-subchunk-{index}",
            section_id=section.section_id,
            order=index,
            content=chunk,
            word_count=_word_count(chunk),
        )
        for index, chunk in enumerate(chunks, start=1)
    ]


def _paragraphs_for_chunking(section: DocumentSection) -> list[str]:
    return [paragraph.text.strip() for paragraph in section.paragraphs if paragraph.text.strip()]


def _split_long_paragraph(paragraph: str, max_subchunk_words: int) -> list[str]:
    words = paragraph.split()
    return [
        " ".join(words[index : index + max_subchunk_words])
        for index in range(0, len(words), max_subchunk_words)
    ]


def _build_oversized_section_synopsis(subchunks: list[SectionSubchunk]) -> str:
    if not subchunks:
        return ""
    lead_sentences: list[str] = []
    for subchunk in subchunks[:3]:
        lead_sentences.append(_first_sentence(subchunk.content))
    return " ".join(sentence for sentence in lead_sentences if sentence).strip()


def _first_sentence(text: str) -> str:
    match = re.search(r"^.*?(?:[.!?](?:\s|$)|$)", text.strip())
    return match.group(0).strip() if match else text.strip()


def _build_unresolved_risks(
    *,
    checked_claims: list[SectionClaimOutcome],
    gate: BatchGateRecommendation,
) -> list[str]:
    risks: list[str] = []
    if any(claim.evidence_verdict == "contradicted" for claim in checked_claims):
        risks.append(
            "One or more checked claims in this section are contradicted by the cited source."
        )
    if any(claim.evidence_verdict == "unsupported" for claim in checked_claims):
        risks.append(
            "One or more checked claims in this section remain unsupported by the cited source."
        )
    if any(claim.evidence_verdict == "unverified" for claim in checked_claims):
        risks.append(
            "One or more checked claims in this section remain unverified because source access or evidence coverage was insufficient."
        )
    if gate.status == "stop_and_fix":
        risks.append(
            "The global gate recommends stopping to fix evidence issues before later analysis."
        )

    unique_risks: list[str] = []
    for risk in risks:
        if risk not in unique_risks:
            unique_risks.append(risk)
    return unique_risks


def _word_count(text: str) -> int:
    return len(text.split())
