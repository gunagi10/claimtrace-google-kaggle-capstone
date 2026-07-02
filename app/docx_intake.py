"""DOCX intake and citation mapping for the local review flow.

This layer is intentionally deterministic. It turns a Word report into sections,
references, citation occurrences, and claim-ready sentences before any model is
called, so the user can inspect the exact claim/source map.
"""

from __future__ import annotations

import re
import zipfile
from collections import defaultdict
from io import BytesIO
from xml.etree import ElementTree as ET

from app.config import settings
from app.review_models import (
    CitationDirection,
    CitationDirectionCandidate,
    CitationMappingStatus,
    CitationOccurrence,
    ClaimReadySentence,
    DocumentLocator,
    DocumentParagraph,
    DocumentSection,
    ParsedDocument,
    ReferenceEntry,
    SourceKind,
)


W_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
DOCUMENT_XML_PATH = "word/document.xml"
REFERENCE_HEADINGS = {"references", "bibliography"}
CITATION_RE = re.compile(r"\[(\d+)\]")
REFERENCE_PATTERNS = [
    re.compile(r"^\[(\d+)\]\s*(.+)$"),
    re.compile(r"^(\d+)[\.\)]\s+(.+)$"),
]
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
LEADING_CITATIONS_RE = re.compile(r"^(?:\[\d+\]\s*)+")
INLINE_POST_PUNCTUATION_CITATIONS_RE = re.compile(r"([.!?])((?:\[\d+\])+)")
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])(?:\s+|(?=[A-Z]))")
INITIALISM_RE = re.compile(r"\b(?:[A-Z]\.){2,}")
PERIOD_SENTINEL = "\ue000"
COMMON_ABBREVIATIONS = (
    "e.g.",
    "i.e.",
    "Mr.",
    "Mrs.",
    "Ms.",
    "Dr.",
    "Prof.",
    "Inc.",
    "Ltd.",
    "Corp.",
    "No.",
    "vs.",
)


class DocxIntakeError(ValueError):
    """Raised when a DOCX fixture does not meet the supported intake contract."""


def validate_docx_upload(filename: str, content: bytes) -> None:
    if not filename.lower().endswith(".docx"):
        raise DocxIntakeError("Only .docx uploads are supported in this stage.")

    if len(content) > settings.docx_max_upload_bytes:
        raise DocxIntakeError("DOCX upload exceeds the 20 MB hard limit.")

    if not zipfile.is_zipfile(BytesIO(content)):
        raise DocxIntakeError("The uploaded file is not a valid DOCX package.")


def parse_docx_bytes(filename: str, content: bytes) -> ParsedDocument:
    """Parse a supported DOCX into the structured review model.

    The parser keeps enough location data to trace a later evidence verdict back
    to the original section, paragraph, sentence, citation, and bibliography row.
    """

    validate_docx_upload(filename, content)

    with zipfile.ZipFile(BytesIO(content)) as archive:
        if DOCUMENT_XML_PATH not in archive.namelist():
            raise DocxIntakeError("The DOCX package is missing word/document.xml.")

        try:
            root = ET.fromstring(archive.read(DOCUMENT_XML_PATH))
        except ET.ParseError as exc:
            raise DocxIntakeError("The DOCX document.xml could not be parsed.") from exc

    sections: list[DocumentSection] = []
    references: list[ReferenceEntry] = []
    citations: list[CitationOccurrence] = []
    pending_citation_labels: list[str] = []
    claim_ready_sentences: list[ClaimReadySentence] = []
    claim_sentence_labels: list[list[str]] = []
    reference_groups: dict[str, list[ReferenceEntry]] = defaultdict(list)
    warnings: list[str] = []

    current_section = DocumentSection(
        section_id="section-1",
        heading="Document",
        order=1,
    )
    sections.append(current_section)
    section_counter = 1
    paragraph_counter = 0
    citation_counter = 0
    sentence_counter = 0
    in_references = False
    saw_references_heading = False

    for paragraph_xml in root.findall(".//w:body/w:p", W_NS):
        paragraph_text = _paragraph_text(paragraph_xml).strip()
        if not paragraph_text:
            continue

        style_id = _paragraph_style_id(paragraph_xml)
        if _is_heading(style_id):
            heading_text = paragraph_text.strip()
            if heading_text.lower() in REFERENCE_HEADINGS:
                in_references = True
                saw_references_heading = True
            else:
                in_references = False
                section_counter += 1
                current_section = DocumentSection(
                    section_id=f"section-{section_counter}",
                    heading=heading_text,
                    order=section_counter,
                )
                sections.append(current_section)
            continue

        if in_references:
            reference_entry = _parse_reference_entry(paragraph_text, len(references) + 1)
            if reference_entry is None:
                warnings.append(f"Unparsed reference paragraph: {paragraph_text}")
                continue
            references.append(reference_entry)
            reference_groups[reference_entry.citation_label].append(reference_entry)
            continue

        paragraph_counter += 1
        paragraph = DocumentParagraph(
            paragraph_id=f"paragraph-{paragraph_counter}",
            section_id=current_section.section_id,
            order=paragraph_counter,
            text=paragraph_text,
            style_id=style_id,
        )
        current_section.paragraphs.append(paragraph)

        sentence_chunks = _sentence_chunks(paragraph_text)
        for local_sentence_index, sentence_text in enumerate(sentence_chunks):
            markers = CITATION_RE.findall(sentence_text)
            if not markers:
                continue

            (
                citation_direction,
                direction_candidates,
                anchor_sentence_index,
            ) = _classify_citation_direction(sentence_chunks, local_sentence_index)
            scope_sentences = _citation_scope_sentences(
                sentence_chunks,
                anchor_sentence_index=anchor_sentence_index,
                citation_sentence_index=local_sentence_index,
                citation_direction=citation_direction,
            )
            following_context = _following_context_sentences(
                sentence_chunks,
                anchor_sentence_index=(
                    local_sentence_index
                    if citation_direction == CitationDirection.AMBIGUOUS
                    else anchor_sentence_index
                ),
            )

            claim_sentence_text = sentence_text
            if (
                citation_direction == CitationDirection.BACKWARD
                and anchor_sentence_index != local_sentence_index
            ):
                claim_sentence_text = (
                    f"{sentence_chunks[anchor_sentence_index]} "
                    f"{' '.join(f'[{marker}]' for marker in markers)}"
                ).strip()

            sentence_counter += 1
            sentence_citation_ids: list[str] = []

            for marker in markers:
                citation_counter += 1
                citation = CitationOccurrence(
                    citation_id=f"citation-{citation_counter}",
                    raw_marker=f"[{marker}]",
                    sentence_text=claim_sentence_text,
                    reference_id=None,
                    mapping_status=CitationMappingStatus.UNMAPPED,
                    locator=DocumentLocator(
                        section_id=current_section.section_id,
                        paragraph_id=paragraph.paragraph_id,
                        sentence_index=local_sentence_index,
                    ),
                )
                citations.append(citation)
                pending_citation_labels.append(marker)
                sentence_citation_ids.append(citation.citation_id)

            claim_ready_sentences.append(
                ClaimReadySentence(
                    sentence_id=f"sentence-{sentence_counter}",
                    sentence_text=claim_sentence_text,
                    section_id=current_section.section_id,
                    paragraph_id=paragraph.paragraph_id,
                    sentence_index=local_sentence_index,
                    citation_ids=sentence_citation_ids,
                    reference_ids=[],
                    citation_direction=citation_direction,
                    citation_direction_candidates=direction_candidates,
                    citation_scope_sentences=scope_sentences,
                    following_context_sentences=following_context,
                    requires_citation_direction_confirmation=(
                        citation_direction == CitationDirection.AMBIGUOUS
                    ),
                )
            )
            claim_sentence_labels.append(markers)

            if citation_direction == CitationDirection.AMBIGUOUS:
                marker_text = ", ".join(f"[{marker}]" for marker in markers)
                warnings.append(
                    f"Citation {marker_text} appears between two sentences and requires "
                    "previous, next, or both confirmation before review."
                )

    if not saw_references_heading:
        raise DocxIntakeError(
            "The DOCX is missing a References or Bibliography heading."
        )
    if not references:
        raise DocxIntakeError("The DOCX references section contains no numbered entries.")
    if not citations:
        raise DocxIntakeError("The DOCX body contains no numbered citations such as [1].")

    for citation, citation_label in zip(citations, pending_citation_labels, strict=True):
        mapping_status, reference_id = _resolve_reference(citation_label, reference_groups)
        citation.mapping_status = mapping_status
        citation.reference_id = reference_id

    for claim_ready_sentence, citation_labels in zip(
        claim_ready_sentences,
        claim_sentence_labels,
        strict=True,
    ):
        mapped_reference_ids: list[str] = []
        for citation_label in citation_labels:
            _, reference_id = _resolve_reference(citation_label, reference_groups)
            if reference_id is not None:
                mapped_reference_ids.append(reference_id)
        claim_ready_sentence.reference_ids = _ordered_unique(mapped_reference_ids)

    return ParsedDocument(
        sections=sections,
        references=references,
        citation_occurrences=citations,
        claim_ready_sentences=claim_ready_sentences,
        warnings=warnings,
    )


def _paragraph_text(paragraph_xml: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph_xml.iter():
        tag = _local_name(node.tag)
        if tag == "t" and node.text:
            parts.append(node.text)
        elif tag == "tab":
            parts.append("\t")
        elif tag in {"br", "cr"}:
            parts.append(" ")

    text = "".join(parts)
    return re.sub(r"\s+", " ", text).strip()


def _paragraph_style_id(paragraph_xml: ET.Element) -> str | None:
    style = paragraph_xml.find("./w:pPr/w:pStyle", W_NS)
    if style is None:
        return None
    return style.attrib.get(f"{{{W_NS['w']}}}val")


def _is_heading(style_id: str | None) -> bool:
    return bool(style_id and style_id.lower().startswith("heading"))


def _parse_reference_entry(text: str, index: int) -> ReferenceEntry | None:
    for pattern in REFERENCE_PATTERNS:
        match = pattern.match(text)
        if not match:
            continue
        label, raw_reference_text = match.groups()
        canonical_url = _first_url(raw_reference_text)
        return ReferenceEntry(
            reference_id=f"reference-{index}",
            citation_label=label,
            raw_bibliography_text=raw_reference_text.strip(),
            canonical_url=canonical_url,
            source_kind=_infer_source_kind(canonical_url),
        )
    return None


def _first_url(text: str) -> str | None:
    match = URL_RE.search(text)
    return match.group(0) if match else None


def _infer_source_kind(url: str | None) -> SourceKind:
    if url and ".pdf" in url.lower():
        return SourceKind.TEXT_PDF
    return SourceKind.HTML


def _resolve_reference(
    citation_label: str,
    reference_groups: dict[str, list[ReferenceEntry]],
) -> tuple[CitationMappingStatus, str | None]:
    matches = reference_groups.get(citation_label, [])
    if len(matches) == 1:
        return CitationMappingStatus.MAPPED, matches[0].reference_id
    if len(matches) > 1:
        return CitationMappingStatus.AMBIGUOUS, None
    return CitationMappingStatus.UNMAPPED, None


def _sentence_chunks(text: str) -> list[str]:
    normalized = INLINE_POST_PUNCTUATION_CITATIONS_RE.sub(r"\2\1", text)
    protected = _protect_non_boundary_periods(normalized)
    sentences = [
        _restore_protected_periods(chunk).strip()
        for chunk in SENTENCE_BOUNDARY_RE.split(protected)
        if chunk.strip()
    ]
    return sentences or [text.strip()]


def _classify_citation_direction(
    sentence_chunks: list[str],
    citation_sentence_index: int,
) -> tuple[CitationDirection, list[CitationDirectionCandidate], int]:
    """Classify whether a citation attaches backward, forward, or ambiguously.

    When a leading citation could refer to the previous sentence or the sentence
    that follows it, the safer product behavior is to ask the user instead of
    silently choosing one direction.
    """

    sentence_text = sentence_chunks[citation_sentence_index]
    substantive_text = _without_citation_markers(sentence_text)
    starts_with_citation = bool(LEADING_CITATIONS_RE.match(sentence_text))
    has_previous_sentence = citation_sentence_index > 0

    if starts_with_citation and substantive_text and has_previous_sentence:
        previous_index = citation_sentence_index - 1
        return (
            CitationDirection.AMBIGUOUS,
            [
                CitationDirectionCandidate(
                    direction=CitationDirection.BACKWARD,
                    sentence_text=_without_citation_markers(
                        sentence_chunks[previous_index]
                    ),
                    sentence_index=previous_index,
                ),
                CitationDirectionCandidate(
                    direction=CitationDirection.FORWARD,
                    sentence_text=substantive_text,
                    sentence_index=citation_sentence_index,
                ),
            ],
            citation_sentence_index,
        )

    if starts_with_citation and substantive_text:
        return (
            CitationDirection.FORWARD,
            [
                CitationDirectionCandidate(
                    direction=CitationDirection.FORWARD,
                    sentence_text=substantive_text,
                    sentence_index=citation_sentence_index,
                )
            ],
            citation_sentence_index,
        )

    if starts_with_citation and has_previous_sentence:
        previous_index = citation_sentence_index - 1
        return (
            CitationDirection.BACKWARD,
            [
                CitationDirectionCandidate(
                    direction=CitationDirection.BACKWARD,
                    sentence_text=_without_citation_markers(
                        sentence_chunks[previous_index]
                    ),
                    sentence_index=previous_index,
                )
            ],
            previous_index,
        )

    return (
        CitationDirection.BACKWARD,
        [
            CitationDirectionCandidate(
                direction=CitationDirection.BACKWARD,
                sentence_text=substantive_text,
                sentence_index=citation_sentence_index,
            )
        ],
        citation_sentence_index,
    )


def _citation_scope_sentences(
    sentence_chunks: list[str],
    *,
    anchor_sentence_index: int,
    citation_sentence_index: int,
    citation_direction: CitationDirection,
) -> list[str]:
    scope_end = (
        citation_sentence_index
        if citation_direction == CitationDirection.AMBIGUOUS
        else anchor_sentence_index
    )
    scope_start = max(0, scope_end - 2)
    return [
        sentence_chunks[index]
        for index in range(scope_start, scope_end + 1)
        if _without_citation_markers(sentence_chunks[index])
    ]


def _following_context_sentences(
    sentence_chunks: list[str],
    *,
    anchor_sentence_index: int,
) -> list[str]:
    following_index = anchor_sentence_index + 1
    if following_index >= len(sentence_chunks):
        return []
    return [sentence_chunks[following_index]]


def _without_citation_markers(text: str) -> str:
    cleaned = CITATION_RE.sub("", text)
    cleaned = re.sub(r"\s+([.!?])", r"\1", cleaned)
    return " ".join(cleaned.split())


def _protect_non_boundary_periods(text: str) -> str:
    protected = re.sub(r"(?<=\d)\.(?=\d)", PERIOD_SENTINEL, text)

    for abbreviation in COMMON_ABBREVIATIONS:
        protected = re.sub(
            re.escape(abbreviation),
            abbreviation.replace(".", PERIOD_SENTINEL),
            protected,
            flags=re.IGNORECASE,
        )

    protected = INITIALISM_RE.sub(
        lambda match: match.group(0).replace(".", PERIOD_SENTINEL),
        protected,
    )
    protected = URL_RE.sub(_protect_url_periods, protected)
    return protected


def _protect_url_periods(match: re.Match[str]) -> str:
    token = match.group(0)
    trailing_punctuation = ""
    while token and token[-1] in ".!?":
        trailing_punctuation = token[-1] + trailing_punctuation
        token = token[:-1]
    return token.replace(".", PERIOD_SENTINEL) + trailing_punctuation


def _restore_protected_periods(text: str) -> str:
    return text.replace(PERIOD_SENTINEL, ".")


def _ordered_unique(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
