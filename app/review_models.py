from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class CitationMappingStatus(StrEnum):
    MAPPED = "mapped"
    AMBIGUOUS = "ambiguous"
    UNMAPPED = "unmapped"
    POTENTIAL_MISSING_CITATION = "potential_missing_citation"


class CitationDirection(StrEnum):
    BACKWARD = "backward"
    FORWARD = "forward"
    BOTH = "both"
    AMBIGUOUS = "ambiguous"


class SourceKind(StrEnum):
    HTML = "html"
    TEXT_PDF = "text_pdf"


class SourceFetchStatus(StrEnum):
    PENDING = "pending"
    FETCHED = "fetched"
    FAILED = "failed"


class SourceExtractionStatus(StrEnum):
    PENDING = "pending"
    EXTRACTED = "extracted"
    OCR_REQUIRED = "ocr_required"
    EXTRACTION_FAILED = "extraction_failed"


class EvidenceVerdict(StrEnum):
    SUPPORTED = "supported_by_cited_source"
    PARTIALLY_SUPPORTED = "partially_supported"
    UNSUPPORTED = "unsupported"
    CONTRADICTED = "contradicted"
    UNVERIFIED = "unverified"


class ReviewStage(StrEnum):
    UPLOADED = "uploaded"
    PARSED = "parsed"
    CLAIMS_PREPARED = "claims_prepared"
    AWAITING_CLAIM_APPROVAL = "awaiting_claim_approval"
    EVIDENCE_RUNNING = "evidence_running"
    EVIDENCE_REVIEWED = "evidence_reviewed"
    SECTION_ANALYSIS_RUNNING = "section_analysis_running"
    SECTION_ANALYSIS_REVIEWED = "section_analysis_reviewed"
    FINAL_COHERENCE_RUNNING = "final_coherence_running"
    FINAL_COHERENCE_REVIEWED = "final_coherence_reviewed"
    FAILED = "failed"


class DocumentLocator(BaseModel):
    section_id: str
    paragraph_id: str
    sentence_index: int


class DocumentParagraph(BaseModel):
    paragraph_id: str
    section_id: str
    order: int
    text: str
    style_id: str | None = None


class DocumentSection(BaseModel):
    section_id: str
    heading: str
    order: int
    paragraphs: list[DocumentParagraph] = Field(default_factory=list)


class SourceLocator(BaseModel):
    heading: str | None = None
    page_number: int | None = None
    text_span_label: str | None = None


class ReferenceEntry(BaseModel):
    reference_id: str
    citation_label: str
    raw_bibliography_text: str
    canonical_url: str | None = None
    source_kind: SourceKind


class CitationOccurrence(BaseModel):
    citation_id: str
    raw_marker: str
    sentence_text: str
    reference_id: str | None = None
    mapping_status: CitationMappingStatus
    locator: DocumentLocator


class CitationDirectionCandidate(BaseModel):
    direction: CitationDirection
    sentence_text: str
    sentence_index: int


class AtomicClaim(BaseModel):
    claim_id: str
    atomic_claim: str
    original_sentence: str
    section_id: str
    paragraph_id: str
    citation_ids: list[str] = Field(default_factory=list)
    qualifiers: list[str] = Field(default_factory=list)
    decomposition_confidence: float | None = None


class ClaimReadySentence(BaseModel):
    sentence_id: str
    sentence_text: str
    section_id: str
    paragraph_id: str
    sentence_index: int
    citation_ids: list[str] = Field(default_factory=list)
    reference_ids: list[str] = Field(default_factory=list)
    citation_direction: CitationDirection = CitationDirection.BACKWARD
    citation_direction_candidates: list[CitationDirectionCandidate] = Field(
        default_factory=list
    )
    citation_scope_sentences: list[str] = Field(default_factory=list)
    following_context_sentences: list[str] = Field(default_factory=list)
    requires_citation_direction_confirmation: bool = False


class SourceRecord(BaseModel):
    source_id: str
    reference_id: str
    source_kind: SourceKind
    canonical_url: str | None = None
    fetch_status: SourceFetchStatus = SourceFetchStatus.PENDING
    extraction_status: SourceExtractionStatus = SourceExtractionStatus.PENDING
    content_hash: str | None = None
    failure_reason: str | None = None

    def blocks_evidence_review(self) -> bool:
        return (
            self.extraction_status
            in {
                SourceExtractionStatus.OCR_REQUIRED,
                SourceExtractionStatus.EXTRACTION_FAILED,
            }
            or self.fetch_status == SourceFetchStatus.FAILED
        )


class EvidencePassage(BaseModel):
    passage_id: str
    source_id: str
    text: str
    locator: SourceLocator
    retrieval_score: float | None = None


class SourceTextBlock(BaseModel):
    block_id: str
    source_id: str
    text: str
    locator: SourceLocator


class ExtractedSourceDocument(BaseModel):
    source_record: SourceRecord
    blocks: list[SourceTextBlock] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidenceAssessment(BaseModel):
    claim_id: str
    source_id: str
    verdict: EvidenceVerdict
    reason: str
    recommended_action: str
    source_fetch_status: SourceFetchStatus
    source_extraction_status: SourceExtractionStatus
    passage_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    @classmethod
    def unverified_for_ocr_required_pdf(
        cls,
        *,
        claim_id: str,
        source_id: str,
    ) -> EvidenceAssessment:
        return cls(
            claim_id=claim_id,
            source_id=source_id,
            verdict=EvidenceVerdict.UNVERIFIED,
            reason=(
                "The cited PDF does not expose a usable text layer. OCR is not "
                "supported in this stage, so the source could not be reviewed "
                "defensibly."
            ),
            recommended_action=(
                "Upload a text-extractable copy or review the source manually."
            ),
            source_fetch_status=SourceFetchStatus.FETCHED,
            source_extraction_status=SourceExtractionStatus.OCR_REQUIRED,
            warnings=["ocr_required"],
        )


class JudgeOutput(BaseModel):
    verdict: EvidenceVerdict
    reason: str
    recommended_action: str
    passage_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class EvidenceReviewPayload(BaseModel):
    claim_id: str
    atomic_claim: str
    original_sentence: str
    section_id: str
    paragraph_id: str
    citation_ids: list[str] = Field(default_factory=list)
    source_id: str
    reference_id: str
    canonical_url: str | None = None
    source_fetch_status: SourceFetchStatus
    source_extraction_status: SourceExtractionStatus
    source_warnings: list[str] = Field(default_factory=list)
    local_context: str = ""
    candidate_passages: list[EvidencePassage] = Field(default_factory=list)


class ReviewTrace(BaseModel):
    approved_claim: str
    citation_ids: list[str] = Field(default_factory=list)
    citation_direction: CitationDirection
    reference_id: str
    canonical_url: str | None = None
    source_method: str
    stopped_stage: str
    source_fetch_status: SourceFetchStatus
    source_extraction_status: SourceExtractionStatus
    source_failure_reason: str | None = None
    extracted_block_count: int = 0
    candidate_passage_count: int = 0
    candidate_passages: list[EvidencePassage] = Field(default_factory=list)
    model_called: bool = False
    model_name: str | None = None


class DeterministicReviewOutcome(BaseModel):
    claim_id: str
    source_id: str
    assessment: EvidenceAssessment | None = None
    judge_payload: EvidenceReviewPayload | None = None
    source_document: ExtractedSourceDocument | None = None
    candidate_passages: list[EvidencePassage] = Field(default_factory=list)


class ReviewJobState(BaseModel):
    review_job_id: str
    stage: ReviewStage
    selected_claim_ids: list[str] = Field(default_factory=list)
    selected_source_ids: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ParsedDocument(BaseModel):
    sections: list[DocumentSection]
    references: list[ReferenceEntry]
    citation_occurrences: list[CitationOccurrence]
    claim_ready_sentences: list[ClaimReadySentence]
    warnings: list[str] = Field(default_factory=list)


class FirstSliceContract(BaseModel):
    name: str
    supported_source_kinds: list[SourceKind]
    unsupported_source_behavior: str
    excluded_features: list[str]
    model_placeholder: str


FIRST_SLICE_CONTRACT = FirstSliceContract(
    name="single_source_evidence_check",
    supported_source_kinds=[SourceKind.HTML, SourceKind.TEXT_PDF],
    unsupported_source_behavior=(
        "OCR-only PDFs return an explicit unverified/ocr_required outcome."
    ),
    excluded_features=[
        "ocr",
        "visual_review",
        "multi_source_parallelism",
        "claim_batching_over_10",
        "section_review",
        "cohesion_review",
        "pdf_audit_download",
    ],
    model_placeholder="gemini-2.0-flash-lite",
)


class BatchGateRecommendation(BaseModel):
    status: str
    summary: str
    checked_claim_count: int
    pending_claim_count: int
    contradiction_count: int = 0
    unsupported_count: int = 0
    unverified_count: int = 0
    contradiction_sentence_ids: list[str] = Field(default_factory=list)
    warning_sentence_ids: list[str] = Field(default_factory=list)
    user_override_allowed: bool = True
    user_override_applied: bool = False


class BatchCoverage(BaseModel):
    total_available: int
    selected: int
    completed: int
    unresolved: int
    deselected: int
    verdict_counts: dict[str, int] = Field(default_factory=dict)


class SectionSubchunk(BaseModel):
    subchunk_id: str
    section_id: str
    order: int
    content: str
    word_count: int


class SectionClaimOutcome(BaseModel):
    sentence_id: str
    claim_id: str
    approved_claim_text: str
    original_sentence: str
    section_id: str
    paragraph_id: str
    citation_ids: list[str] = Field(default_factory=list)
    reference_id: str
    evidence_verdict: EvidenceVerdict
    evidence_reason: str
    recommended_action: str
    linked_passage_ids: list[str] = Field(default_factory=list)
    source_fetch_status: SourceFetchStatus
    source_extraction_status: SourceExtractionStatus
    warnings: list[str] = Field(default_factory=list)


class SectionCoverageSummary(BaseModel):
    checked_claim_count: int
    contradicted_count: int = 0
    unsupported_count: int = 0
    unverified_count: int = 0
    deselected_count: int = 0


class SectionGateContext(BaseModel):
    global_gate_status: str
    global_gate_summary: str
    global_stop_recommended: bool
    section_has_contradiction: bool = False
    section_has_warning: bool = False


class SectionPacket(BaseModel):
    section_id: str
    heading: str
    order: int
    section_text: str
    word_count: int
    is_oversized: bool = False
    subchunks: list[SectionSubchunk] = Field(default_factory=list)
    checked_claims: list[SectionClaimOutcome] = Field(default_factory=list)
    gate_context: SectionGateContext
    coverage_summary: SectionCoverageSummary
    unresolved_risks: list[str] = Field(default_factory=list)
    visual_context: list[str] = Field(default_factory=list)


class SectionAnalysisOutput(BaseModel):
    section_id: str
    summary: str
    factual_strengths: list[str] = Field(default_factory=list)
    factual_gaps: list[str] = Field(default_factory=list)
    insight_issues: list[str] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    recommended_revisions: list[str] = Field(default_factory=list)
    needs_human_attention: bool = False


class SectionAssessment(BaseModel):
    section_id: str
    heading: str
    order: int
    summary: str
    factual_strengths: list[str] = Field(default_factory=list)
    factual_gaps: list[str] = Field(default_factory=list)
    insight_issues: list[str] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    recommended_revisions: list[str] = Field(default_factory=list)
    needs_human_attention: bool = False


class FinalSectionDigest(BaseModel):
    section_id: str
    heading: str
    order: int
    checked_claim_count: int
    contradicted_count: int = 0
    unsupported_count: int = 0
    unverified_count: int = 0
    deselected_count: int = 0
    section_has_contradiction: bool = False
    section_has_warning: bool = False
    needs_human_attention: bool = False
    summary: str
    factual_strengths: list[str] = Field(default_factory=list)
    factual_gaps: list[str] = Field(default_factory=list)
    insight_issues: list[str] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    recommended_revisions: list[str] = Field(default_factory=list)


class ReportCoverageSummary(BaseModel):
    selected_claim_count: int
    completed_claim_count: int
    unresolved_claim_count: int
    deselected_claim_count: int
    contradicted_claim_count: int = 0
    unsupported_claim_count: int = 0
    unverified_claim_count: int = 0
    eligible_section_count: int = 0
    completed_section_count: int = 0
    human_attention_section_count: int = 0


class FinalCoherencePacket(BaseModel):
    review_id: str
    global_gate: BatchGateRecommendation
    report_coverage: ReportCoverageSummary
    section_digests: list[FinalSectionDigest] = Field(default_factory=list)
    unresolved_report_risks: list[str] = Field(default_factory=list)


class FinalCoherenceOutput(BaseModel):
    report_summary: str
    coherence_strengths: list[str] = Field(default_factory=list)
    coherence_issues: list[str] = Field(default_factory=list)
    soundness_issues: list[str] = Field(default_factory=list)
    noteworthy_patterns: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    needs_human_attention: bool = False


class FinalCoherenceAssessment(BaseModel):
    report_summary: str
    coherence_strengths: list[str] = Field(default_factory=list)
    coherence_issues: list[str] = Field(default_factory=list)
    soundness_issues: list[str] = Field(default_factory=list)
    noteworthy_patterns: list[str] = Field(default_factory=list)
    priority_actions: list[str] = Field(default_factory=list)
    unresolved_risks: list[str] = Field(default_factory=list)
    needs_human_attention: bool = False
