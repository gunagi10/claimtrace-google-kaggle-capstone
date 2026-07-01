from app.review_models import SourceExtractionStatus, SourceKind
from app.source_adapters import SourcePayload, extract_source_document


def test_html_source_adapter_extracts_text_blocks_with_heading_locators() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=_reference_entry(SourceKind.HTML, "https://example.com/report"),
        body=(
            b"<html><body><h1>Results</h1><p>Revenue grew 12 percent year over year.</p>"
            b"<p>Margin improved to 18 percent.</p></body></html>"
        ),
        content_type="text/html",
    )

    extracted = extract_source_document(payload)

    assert extracted.source_record.extraction_status == SourceExtractionStatus.EXTRACTED
    assert len(extracted.blocks) == 2
    assert extracted.blocks[0].locator.heading == "Results"
    assert "Revenue grew 12 percent year over year." in extracted.blocks[0].text


def test_html_source_adapter_prefers_main_content_and_keeps_nested_text() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=_reference_entry(SourceKind.HTML, "https://example.com/report"),
        body=(
            b"<html><body><nav><p>Navigation revenue 999%</p></nav>"
            b"<main><h1>Fiscal Year Results</h1>"
            b"<p>Microsoft <strong>operating income</strong> increased 17%.</p>"
            b"<ul><li>Revenue was $281.7 billion.</li></ul></main>"
            b"<footer><p>Footer revenue 888%</p></footer></body></html>"
        ),
        content_type="text/html",
    )

    extracted = extract_source_document(payload)
    extracted_text = " ".join(block.text for block in extracted.blocks)

    assert "Microsoft operating income increased 17%." in extracted_text
    assert "Revenue was $281.7 billion." in extracted_text
    assert "Navigation revenue" not in extracted_text
    assert "Footer revenue" not in extracted_text


def test_html_source_adapter_extracts_preformatted_main_content() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=_reference_entry(SourceKind.HTML, "https://example.com/report"),
        body=(
            b"<html><body><nav><pre>Navigation note</pre></nav>"
            b"<main><h1>Employment Situation News Release</h1>"
            b"<pre>Total nonfarm payroll employment increased by 147,000 in June 2025.</pre>"
            b"</main></body></html>"
        ),
        content_type="text/html",
    )

    extracted = extract_source_document(payload)
    extracted_text = " ".join(block.text for block in extracted.blocks)

    assert extracted.source_record.extraction_status == SourceExtractionStatus.EXTRACTED
    assert len(extracted.blocks) == 1
    assert extracted.blocks[0].locator.heading == "Employment Situation News Release"
    assert "Total nonfarm payroll employment increased by 147,000 in June 2025." in extracted_text
    assert "Navigation note" not in extracted_text


def test_html_source_adapter_does_not_get_stuck_after_void_skip_tags() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=_reference_entry(SourceKind.HTML, "https://example.com/report"),
        body=(
            b"<html><body><form>"
            b"<input type='hidden' value='token'>"
            b"<main><h1>Quarterly Results</h1>"
            b"<p>Revenue was $81.6 billion.</p></main>"
            b"</form></body></html>"
        ),
        content_type="text/html",
    )

    extracted = extract_source_document(payload)

    assert extracted.source_record.extraction_status == SourceExtractionStatus.EXTRACTED
    assert len(extracted.blocks) == 1
    assert extracted.blocks[0].locator.heading == "Quarterly Results"
    assert extracted.blocks[0].text == "Revenue was $81.6 billion."


def test_html_source_adapter_extracts_financial_table_rows() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=_reference_entry(SourceKind.HTML, "https://example.com/filing"),
        body=(
            b"<html><body><main><h1>Quarterly Results</h1>"
            b"<table>"
            b"<caption>Consolidated Statements of Income</caption>"
            b"<tr><th></th><th>Three months ended September 26, 2025</th><th>Three months ended September 27, 2024</th></tr>"
            b"<tr><td>Revenue</td><td>$94.9 billion</td><td>$83.4 billion</td></tr>"
            b"<tr><td>Diluted net income per share</td><td>$0.86</td><td>$0.97</td></tr>"
            b"</table></main></body></html>"
        ),
        content_type="text/html",
    )

    extracted = extract_source_document(payload)

    assert extracted.source_record.extraction_status == SourceExtractionStatus.EXTRACTED
    assert len(extracted.blocks) == 2
    assert extracted.blocks[0].locator.heading == "Quarterly Results"
    assert "Table: Consolidated Statements of Income." in extracted.blocks[0].text
    assert "Row: Revenue." in extracted.blocks[0].text
    assert (
        "Three months ended September 26, 2025: $94.9 billion."
        in extracted.blocks[0].text
    )
    assert (
        "Three months ended September 27, 2024: $0.97."
        in extracted.blocks[1].text
    )


def test_html_source_adapter_keeps_prose_and_table_rows_without_duplication() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=_reference_entry(SourceKind.HTML, "https://example.com/filing"),
        body=(
            b"<html><body><main><h1>Annual Results</h1>"
            b"<p>Management highlighted stronger cash generation in fiscal 2025.</p>"
            b"<table>"
            b"<tr><th></th><th>Fiscal 2025</th><th>Fiscal 2024</th></tr>"
            b"<tr><td>Cash provided by operating activities</td><td>$12.4 billion</td><td>$10.9 billion</td></tr>"
            b"</table></main></body></html>"
        ),
        content_type="text/html",
    )

    extracted = extract_source_document(payload)
    texts = [block.text for block in extracted.blocks]

    assert len(texts) == 2
    assert texts[0] == "Management highlighted stronger cash generation in fiscal 2025."
    assert "Row: Cash provided by operating activities." in texts[1]
    assert "Fiscal 2025: $12.4 billion." in texts[1]


def test_html_source_adapter_preserves_stacked_table_headers() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=_reference_entry(SourceKind.HTML, "https://example.com/filing"),
        body=(
            b"<html><body><main><h1>Second Quarter Results</h1>"
            b"<table>"
            b"<caption>Consolidated Statements of Income</caption>"
            b"<tr><th></th><th colspan='2'>Three months ended</th><th colspan='2'>Six months ended</th></tr>"
            b"<tr><th></th><th>June 27, 2025</th><th>June 28, 2024</th><th>June 27, 2025</th><th>June 28, 2024</th></tr>"
            b"<tr><td>Diluted net income per share</td><td>$0.88</td><td>$0.56</td><td>$1.65</td><td>$1.29</td></tr>"
            b"</table></main></body></html>"
        ),
        content_type="text/html",
    )

    extracted = extract_source_document(payload)

    assert extracted.source_record.extraction_status == SourceExtractionStatus.EXTRACTED
    assert len(extracted.blocks) == 1
    assert "Table: Consolidated Statements of Income." in extracted.blocks[0].text
    assert "Row: Diluted net income per share." in extracted.blocks[0].text
    assert "Three months ended June 27, 2025: $0.88." in extracted.blocks[0].text
    assert "Three months ended June 28, 2024: $0.56." in extracted.blocks[0].text
    assert "Six months ended June 27, 2025: $1.65." in extracted.blocks[0].text
    assert "Six months ended June 28, 2024: $1.29." in extracted.blocks[0].text


def test_html_source_adapter_skips_low_signal_layout_table() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=_reference_entry(SourceKind.HTML, "https://example.com/page"),
        body=(
            b"<html><body><main><h1>Overview</h1>"
            b"<p>Revenue discussion stays in prose.</p>"
            b"<table>"
            b"<tr><td>Home</td><td>About</td><td>Contact</td></tr>"
            b"<tr><td>Products</td><td>Pricing</td><td>Support</td></tr>"
            b"</table></main></body></html>"
        ),
        content_type="text/html",
    )

    extracted = extract_source_document(payload)

    assert len(extracted.blocks) == 1
    assert extracted.blocks[0].text == "Revenue discussion stays in prose."


def test_text_pdf_source_adapter_extracts_page_text_blocks() -> None:
    payload = SourcePayload(
        source_id="source-2",
        reference=_reference_entry(SourceKind.TEXT_PDF, "https://example.com/report.pdf"),
        body=_text_pdf_bytes(),
        content_type="application/pdf",
    )

    extracted = extract_source_document(payload)

    assert extracted.source_record.extraction_status == SourceExtractionStatus.EXTRACTED
    assert len(extracted.blocks) == 1
    assert extracted.blocks[0].locator.page_number == 1
    assert "Revenue grew 12 percent year over year." in extracted.blocks[0].text


def test_text_pdf_source_adapter_returns_ocr_required_for_image_only_pdf() -> None:
    payload = SourcePayload(
        source_id="source-3",
        reference=_reference_entry(SourceKind.TEXT_PDF, "https://example.com/scanned.pdf"),
        body=_blank_pdf_bytes(),
        content_type="application/pdf",
    )

    extracted = extract_source_document(payload)

    assert extracted.source_record.extraction_status == SourceExtractionStatus.OCR_REQUIRED
    assert extracted.source_record.blocks_evidence_review() is True
    assert extracted.blocks == []
    assert "ocr_required" in extracted.warnings


def _reference_entry(source_kind: SourceKind, url: str):
    from app.review_models import ReferenceEntry

    return ReferenceEntry(
        reference_id="reference-1",
        citation_label="1",
        raw_bibliography_text=url,
        canonical_url=url,
        source_kind=source_kind,
    )


def _text_pdf_bytes() -> bytes:
    pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 66 >>
stream
BT
/F1 12 Tf
72 720 Td
(Revenue grew 12 percent year over year.) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000241 00000 n
0000000358 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
428
%%EOF
"""
    return pdf


def _blank_pdf_bytes() -> bytes:
    pdf = b"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >>
endobj
xref
0 4
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
trailer
<< /Size 4 /Root 1 0 R >>
startxref
186
%%EOF
"""
    return pdf


def test_text_pdf_source_adapter_extracts_layout_table_rows_conservatively() -> None:
    from app.source_adapters import TextPdfSourceAdapter

    adapter = TextPdfSourceAdapter()
    blocks, carried_context = adapter._extract_table_like_blocks(
        layout_text=(
            "Q3 Fiscal 2026 Summary\n"
            "GAAP\n"
            "($ in millions, except earnings per share)    Q3 FY26    Q2 FY26    Q3 FY25    Q/Q    Y/Y\n"
            "Revenue                                      $57,006    $46,743    $35,082    22%    62%\n"
            "Diluted earnings per share                     $1.30      $1.08      $0.78    20%    67%\n"
        ),
        source_id="source-2",
        page_number=1,
        table_index_start=0,
        carried_context=None,
    )

    assert len(blocks) == 2
    assert blocks[0].locator.page_number == 1
    assert blocks[0].locator.heading == "Q3 Fiscal 2026 Summary"
    assert "Table: Q3 Fiscal 2026 Summary." in blocks[0].text
    assert "Headers: GAAP | ($ in millions, except earnings per share) Q3 FY26 Q2 FY26 Q3 FY25 Q/Q Y/Y." in blocks[0].text
    assert "Row: Revenue $57,006 $46,743 $35,082 22% 62%." in blocks[0].text
    assert "Q3 FY26: $57,006" not in blocks[0].text
    assert carried_context is None
