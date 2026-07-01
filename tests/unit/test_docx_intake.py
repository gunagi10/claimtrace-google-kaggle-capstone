from io import BytesIO
import zipfile

import pytest

from app.docx_intake import DocxIntakeError, parse_docx_bytes, validate_docx_upload
from app.review_models import CitationDirection, CitationMappingStatus, SourceKind


W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"


def test_parse_docx_supported_fixture_produces_traceable_records() -> None:
    content = _build_docx_bytes(
        [
            ("Heading1", "Executive Summary"),
            ("Normal", "Revenue grew 12% year over year.[1] Margin improved to 18%.[2]"),
            ("Heading1", "References"),
            ("Normal", "[1] https://example.com/revenue"),
            ("Normal", "[2] https://example.com/margin.pdf"),
        ]
    )

    parsed = parse_docx_bytes("report.docx", content)

    assert parsed.sections[1].heading == "Executive Summary"
    assert len(parsed.references) == 2
    assert parsed.references[0].source_kind == SourceKind.HTML
    assert parsed.references[1].source_kind == SourceKind.TEXT_PDF
    assert len(parsed.citation_occurrences) == 2
    assert all(
        citation.mapping_status == CitationMappingStatus.MAPPED
        for citation in parsed.citation_occurrences
    )
    assert len(parsed.claim_ready_sentences) == 2
    assert parsed.claim_ready_sentences[0].reference_ids == ["reference-1"]


def test_parse_docx_rejects_missing_references_heading() -> None:
    content = _build_docx_bytes(
        [
            ("Heading1", "Executive Summary"),
            ("Normal", "Revenue grew 12% year over year.[1]"),
            ("Normal", "[1] https://example.com/revenue"),
        ]
    )

    with pytest.raises(DocxIntakeError, match="References or Bibliography"):
        parse_docx_bytes("report.docx", content)


def test_parse_docx_marks_unmapped_citation_when_reference_is_missing() -> None:
    content = _build_docx_bytes(
        [
            ("Heading1", "Executive Summary"),
            ("Normal", "Revenue grew 12% year over year.[2]"),
            ("Heading1", "References"),
            ("Normal", "[1] https://example.com/revenue"),
        ]
    )

    parsed = parse_docx_bytes("report.docx", content)

    assert parsed.citation_occurrences[0].mapping_status == CitationMappingStatus.UNMAPPED
    assert parsed.citation_occurrences[0].reference_id is None


def test_decimal_does_not_split_the_cited_sentence_and_scope_stays_in_paragraph() -> None:
    content = _build_docx_bytes(
        [
            ("Heading1", "Financial Performance"),
            (
                "Normal",
                "Microsoft reported fiscal-year revenue of $281.7 billion. "
                "Full-year operating income reached $128.5 billion, increasing "
                "17 percent from the prior fiscal year [1].",
            ),
            (
                "Normal",
                "This new paragraph must not enter the earlier citation scope.",
            ),
            ("Heading1", "References"),
            ("Normal", "[1] https://example.com/results"),
        ]
    )

    parsed = parse_docx_bytes("report.docx", content)

    claim = parsed.claim_ready_sentences[0]
    assert claim.sentence_text == (
        "Full-year operating income reached $128.5 billion, increasing "
        "17 percent from the prior fiscal year [1]."
    )
    assert claim.citation_direction == CitationDirection.BACKWARD
    assert claim.requires_citation_direction_confirmation is False
    assert claim.citation_scope_sentences == [
        "Microsoft reported fiscal-year revenue of $281.7 billion.",
        (
            "Full-year operating income reached $128.5 billion, increasing "
            "17 percent from the prior fiscal year [1]."
        ),
    ]
    assert claim.following_context_sentences == []


def test_common_abbreviations_and_initialisms_do_not_split_the_cited_sentence() -> None:
    content = _build_docx_bytes(
        [
            ("Heading1", "Results"),
            (
                "Normal",
                "Microsoft Corp. reported U.S. revenue of $128.5 billion [1].",
            ),
            ("Heading1", "References"),
            ("Normal", "[1] https://example.com/results"),
        ]
    )

    parsed = parse_docx_bytes("report.docx", content)

    assert parsed.claim_ready_sentences[0].sentence_text == (
        "Microsoft Corp. reported U.S. revenue of $128.5 billion [1]."
    )


@pytest.mark.parametrize(
    ("paragraph_text", "expected_direction", "expected_sentence"),
    [
        ("Revenue grew 12 percent [1].", CitationDirection.BACKWARD, "Revenue grew 12 percent [1]."),
        ("Revenue grew 12 percent.[1]", CitationDirection.BACKWARD, "Revenue grew 12 percent[1]."),
        ("[1] Revenue grew 12 percent.", CitationDirection.FORWARD, "[1] Revenue grew 12 percent."),
    ],
)
def test_clear_citation_positions_attach_deterministically(
    paragraph_text: str,
    expected_direction: CitationDirection,
    expected_sentence: str,
) -> None:
    content = _build_docx_bytes(
        [
            ("Heading1", "Results"),
            ("Normal", paragraph_text),
            ("Heading1", "References"),
            ("Normal", "[1] https://example.com/results"),
        ]
    )

    parsed = parse_docx_bytes("report.docx", content)

    claim = parsed.claim_ready_sentences[0]
    assert claim.citation_direction == expected_direction
    assert claim.sentence_text == expected_sentence
    assert claim.requires_citation_direction_confirmation is False


def test_boundary_citation_requires_previous_next_or_both_confirmation() -> None:
    content = _build_docx_bytes(
        [
            ("Heading1", "Results"),
            ("Normal", "Background statement. [1] The source says ChatGPT is very good. Follow-up interpretation."),
            ("Heading1", "References"),
            ("Normal", "[1] https://example.com/results"),
        ]
    )

    parsed = parse_docx_bytes("report.docx", content)

    claim = parsed.claim_ready_sentences[0]
    assert claim.citation_direction == CitationDirection.AMBIGUOUS
    assert claim.requires_citation_direction_confirmation is True
    assert [candidate.direction for candidate in claim.citation_direction_candidates] == [
        CitationDirection.BACKWARD,
        CitationDirection.FORWARD,
    ]
    assert [candidate.sentence_text for candidate in claim.citation_direction_candidates] == [
        "Background statement.",
        "The source says ChatGPT is very good.",
    ]
    assert claim.following_context_sentences == ["Follow-up interpretation."]


def test_validate_docx_upload_rejects_non_docx_bytes() -> None:
    with pytest.raises(DocxIntakeError, match="valid DOCX package"):
        validate_docx_upload("report.docx", b"not-a-docx")


def _build_docx_bytes(paragraphs: list[tuple[str, str]]) -> bytes:
    document_xml = _document_xml(paragraphs)
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\" />")
        archive.writestr("_rels/.rels", "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\" />")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _document_xml(paragraphs: list[tuple[str, str]]) -> str:
    body = []
    for style_id, text in paragraphs:
        body.append(
            f"""
            <w:p>
              <w:pPr><w:pStyle w:val="{style_id}"/></w:pPr>
              <w:r><w:t>{_escape_xml(text)}</w:t></w:r>
            </w:p>
            """
        )

    return f"""
    <w:document xmlns:w="{W_NS}">
      <w:body>
        {''.join(body)}
      </w:body>
    </w:document>
    """


def _escape_xml(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )
