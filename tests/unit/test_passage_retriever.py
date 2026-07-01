from app.passage_retriever import (
    RetrievalQuery,
    _chunk_blocks,
    retrieve_candidate_passages,
)
from app.review_models import (
    ExtractedSourceDocument,
    ReferenceEntry,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
    SourceLocator,
    SourceRecord,
    SourceTextBlock,
)
from app.source_adapters import SourcePayload, extract_source_document


def test_retriever_ranks_passage_with_matching_numbers_and_terms_first() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="block-1",
                source_id="source-1",
                text="Revenue grew 12 percent year over year. Margin improved to 18 percent.",
                locator=SourceLocator(
                    heading="Results", text_span_label="html-block-1"
                ),
            ),
            SourceTextBlock(
                block_id="block-2",
                source_id="source-1",
                text="Employee satisfaction remained stable across the quarter.",
                locator=SourceLocator(heading="People", text_span_label="html-block-2"),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Revenue grew 12 percent year over year.",
            local_context="Executive summary results",
            top_k=2,
        ),
    )

    assert len(passages) == 1
    assert passages[0].locator.heading == "Results"
    assert "12 percent" in passages[0].text


def test_retriever_chunks_large_blocks_without_losing_locator_shape() -> None:
    long_block = SourceTextBlock(
        block_id="block-1",
        source_id="source-1",
        text=(
            "Revenue grew in North America. Revenue grew in Europe. "
            "Revenue grew in Asia Pacific. Revenue grew in Latin America."
        ),
        locator=SourceLocator(heading="Geography", text_span_label="html-block-1"),
    )
    document = _document_with_blocks([long_block])

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Revenue grew in Asia Pacific.",
            max_chars_per_passage=45,
            top_k=5,
        ),
    )

    assert passages
    assert all(p.locator.heading == "Geography" for p in passages)
    assert all("chunk-" in (p.locator.text_span_label or "") for p in passages)
    assert "Asia Pacific" in passages[0].text


def test_retriever_returns_no_candidates_for_empty_or_low_signal_blocks() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="block-1",
                source_id="source-1",
                text="General introductory language with no matching details.",
                locator=SourceLocator(heading="Intro", text_span_label="html-block-1"),
            )
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Revenue grew 12 percent year over year.",
            local_context="margin 18 percent",
        ),
    )

    assert passages == []


def test_retriever_preserves_decimal_values_in_source_passages() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="block-1",
                source_id="source-1",
                text="Operating income was $128.5 billion and increased 17%.",
                locator=SourceLocator(
                    heading="Fiscal Year 2025 Results",
                    text_span_label="html-block-1",
                ),
            )
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text=(
                "Full-year operating income reached $128.5 billion, increasing "
                "17 percent from the prior fiscal year."
            )
        ),
    )

    assert "$128.5 billion" in passages[0].text
    assert "$128. 5" not in passages[0].text


def test_retriever_uses_adjacent_period_and_metric_blocks_for_q3_evidence() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="block-1",
                source_id="source-1",
                text=(
                    "Microsoft Corp. announced results for the quarter ended "
                    "March 31, 2025, compared with the prior fiscal year."
                ),
                locator=SourceLocator(
                    heading="Third Quarter Results",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="block-2",
                source_id="source-1",
                text=(
                    "Revenue was $70.1 billion and increased 13% "
                    "(up 15% in constant currency)."
                ),
                locator=SourceLocator(
                    heading="Third Quarter Results",
                    text_span_label="html-block-2",
                ),
            ),
            SourceTextBlock(
                block_id="block-3",
                source_id="source-1",
                text=(
                    "Microsoft 365 Commercial cloud revenue growth was 12% "
                    "(up 15% in constant currency)."
                ),
                locator=SourceLocator(
                    heading="Business Highlights",
                    text_span_label="html-block-3",
                ),
            ),
            SourceTextBlock(
                block_id="block-4",
                source_id="source-1",
                text="All information in this release is as of March 31, 2025.",
                locator=SourceLocator(
                    heading="Forward-Looking Statements",
                    text_span_label="html-block-4",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text=(
                "Microsoft reported 15 percent revenue growth for the quarter "
                "ended March 31, 2025."
            ),
            local_context="Quarterly Performance",
            top_k=3,
        ),
    )

    assert any(
        "quarter ended March 31, 2025" in passage.text
        and "Revenue was $70.1 billion" in passage.text
        for passage in passages
    )
    assert "Revenue was $70.1 billion" in passages[0].text
    assert passages[0].retrieval_score is not None


def test_retriever_prioritizes_bls_payroll_result_over_technical_notes() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="technical-note-1",
                source_id="source-1",
                text=(
                    "Technical note: U.S. employers added 147,000 nonfarm payroll "
                    "jobs in June 2025 is an example of how the establishment-survey "
                    "estimate may be described after seasonal adjustment."
                ),
                locator=SourceLocator(
                    heading="June 2025 nonfarm payroll employment technical note",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="technical-note-2",
                source_id="source-1",
                text=(
                    "Methodology for the statement that U.S. employers added 147,000 "
                    "nonfarm payroll jobs in June 2025 includes sampling, imputation, "
                    "and seasonal-adjustment procedures."
                ),
                locator=SourceLocator(
                    heading="Methodology and definitions",
                    text_span_label="html-block-2",
                ),
            ),
            SourceTextBlock(
                block_id="technical-note-3",
                source_id="source-1",
                text=(
                    "Footnote for U.S. employers added 147,000 nonfarm payroll jobs "
                    "in June 2025: estimates are subject to revision."
                ),
                locator=SourceLocator(
                    heading="Footnotes",
                    text_span_label="html-block-3",
                ),
            ),
            SourceTextBlock(
                block_id="payroll-result",
                source_id="source-1",
                text=(
                    "Total nonfarm payroll employment rose by 147,000 in June. "
                    "Employment continued to trend up in state government and health care."
                ),
                locator=SourceLocator(
                    heading="The Employment Situation — June 2025",
                    text_span_label="html-block-4",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text=(
                "U.S. employers added 147,000 nonfarm payroll jobs in June 2025."
            ),
            top_k=3,
        ),
    )

    assert passages[0].passage_id.startswith("payroll-result")
    assert "Total nonfarm payroll employment rose by 147,000" in passages[0].text


def test_retriever_normalizes_number_unit_variants() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="result",
                source_id="source-1",
                text="Payroll employment rose by 147 thousand jobs in June 2025.",
                locator=SourceLocator(
                    heading="Employment Situation",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="noise",
                source_id="source-1",
                text="The labor market report contains revised historical estimates.",
                locator=SourceLocator(
                    heading="Background",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Nonfarm payrolls increased by 147,000 jobs in June 2025.",
        ),
    )

    assert passages[0].passage_id.startswith("result")


def test_retriever_adds_qualifier_passage_without_filling_with_boilerplate() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="central-result",
                source_id="source-1",
                text="Total nonfarm payroll employment increased by 147,000 in June 2025.",
                locator=SourceLocator(
                    heading="Employment Situation",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="scope-result",
                source_id="source-1",
                text=(
                    "Employment rose in state government and health care, declined in "
                    "federal government, and changed little in other major industries."
                ),
                locator=SourceLocator(
                    heading="Industry detail",
                    text_span_label="html-block-2",
                ),
            ),
            SourceTextBlock(
                block_id="methodology",
                source_id="source-1",
                text=(
                    "Methodology and definitions explain sampling error, seasonal "
                    "adjustment, and benchmark revisions for payroll employment."
                ),
                locator=SourceLocator(
                    heading="Technical note",
                    text_span_label="html-block-3",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text=(
                "Nonfarm payroll employment increased by 147,000 in June 2025 "
                "across all industries."
            ),
            top_k=5,
        ),
    )

    passage_ids = {passage.passage_id.split("-chunk-")[0] for passage in passages}
    assert passage_ids == {"central-result", "scope-result"}


def test_retriever_uses_metric_phrase_fallback_for_niche_business_metric() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="exact-metric",
                source_id="source-1",
                text="Net dollar retention was 118 percent in Q1 2025.",
                locator=SourceLocator(
                    heading="Key Metrics",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="generic-metric",
                source_id="source-1",
                text="Retention was 118 percent in Q1 2025.",
                locator=SourceLocator(
                    heading="Summary",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Net dollar retention was 118 percent in Q1 2025.",
            top_k=2,
        ),
    )

    assert passages[0].passage_id.startswith("exact-metric")


def test_retriever_prefers_total_company_scope_over_segment_scope() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="segment-scope",
                source_id="source-1",
                text="Azure revenue grew 12 percent in Q1 2025.",
                locator=SourceLocator(
                    heading="Cloud segment",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="total-scope",
                source_id="source-1",
                text="Total company revenue grew 12 percent in Q1 2025.",
                locator=SourceLocator(
                    heading="Results",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Total company revenue grew 12 percent in Q1 2025.",
            top_k=2,
        ),
    )

    assert passages[0].passage_id.startswith("total-scope")


def test_retriever_prefers_exact_unit_family_over_nearby_user_count_metrics() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="subscriber-metric",
                source_id="source-1",
                text="Subscribers increased 12 percent in 2025.",
                locator=SourceLocator(
                    heading="Subscriber Trends",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="customer-metric",
                source_id="source-1",
                text="Customers increased 12 percent in 2025.",
                locator=SourceLocator(
                    heading="Customer Trends",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Customers increased 12 percent in 2025.",
            top_k=2,
        ),
    )

    assert passages[0].passage_id.startswith("customer-metric")


def test_retriever_uses_sentence_overlap_to_keep_neighboring_context() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="overlap-block",
                source_id="source-1",
                text=(
                    "Revenue was $70 billion. "
                    "Enterprise demand stayed strong. "
                    "Operating margin reached 22 percent in Q1 2025."
                ),
                locator=SourceLocator(
                    heading="Quarterly Results",
                    text_span_label="html-block-1",
                ),
            )
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Operating margin reached 22 percent in Q1 2025.",
            max_chars_per_passage=45,
            top_k=5,
        ),
    )

    assert any(
        "Enterprise demand stayed strong." in passage.text
        and "Operating margin reached 22 percent in Q1 2025." in passage.text
        for passage in passages
    )


def test_retriever_retains_conflicting_numeric_passage_for_judge() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="supported-result",
                source_id="source-1",
                text="Revenue grew 12 percent in Q1 2025.",
                locator=SourceLocator(
                    heading="Results",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="contradicting-result",
                source_id="source-1",
                text="Revenue grew 9 percent in Q1 2025.",
                locator=SourceLocator(
                    heading="Results",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Revenue grew 12 percent in Q1 2025.",
            top_k=5,
        ),
    )

    assert any("12 percent" in passage.text for passage in passages)
    assert any("9 percent" in passage.text for passage in passages)


def test_retriever_matches_net_revenue_alias_without_preferring_organic_revenue() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="reported-revenue",
                source_id="source-1",
                text="Net revenues increased 12 percent to $12.5 billion in Q1 2026.",
                locator=SourceLocator(
                    heading="Financial Highlights",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="organic-revenue",
                source_id="source-1",
                text="Organic revenue increased 12 percent in Q1 2026.",
                locator=SourceLocator(
                    heading="Growth Drivers",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Net revenue increased 12 percent to $12.5 billion in Q1 2026.",
            top_k=2,
        ),
    )

    assert passages[0].passage_id.startswith("reported-revenue")


def test_retriever_matches_operating_cash_flow_alias_without_collapsing_into_free_cash_flow() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="operating-cash-flow",
                source_id="source-1",
                text="Net cash provided by operating activities was $7.4 billion in 2025.",
                locator=SourceLocator(
                    heading="Cash Flow Highlights",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="free-cash-flow",
                source_id="source-1",
                text="Free cash flow was $5.3 billion in 2025.",
                locator=SourceLocator(
                    heading="Non-GAAP Measures",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Cash flow from operating activities was $7.4 billion in 2025.",
            top_k=2,
        ),
    )

    assert passages[0].passage_id.startswith("operating-cash-flow")


def test_retriever_matches_operating_income_alias_without_preferring_operating_margin() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="operating-income",
                source_id="source-1",
                text="Income from operations was $3.2 billion in Q3 2025.",
                locator=SourceLocator(
                    heading="Results",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="operating-margin",
                source_id="source-1",
                text="Operating margin was 24.5 percent in Q3 2025.",
                locator=SourceLocator(
                    heading="Margins",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Profit from operations was $3.2 billion in Q3 2025.",
            top_k=2,
        ),
    )

    assert passages[0].passage_id.startswith("operating-income")


def test_retriever_matches_eps_aliases_in_filing_style_wording() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="eps-row",
                source_id="source-1",
                text="Diluted net income per share was $0.86 for the third quarter of 2025.",
                locator=SourceLocator(
                    heading="Quarterly Highlights",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="basic-eps-row",
                source_id="source-1",
                text="Basic income per share was $0.91 for the third quarter of 2025.",
                locator=SourceLocator(
                    heading="Quarterly Highlights",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Diluted earnings per share were $0.86 in the third quarter of 2025.",
            top_k=2,
        ),
    )

    assert passages[0].passage_id.startswith("eps-row")


def test_retriever_matches_gross_profit_margin_alias_without_preferring_gross_profit_amount() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="gross-margin",
                source_id="source-1",
                text="Gross profit margin was 42.1 percent in 2025.",
                locator=SourceLocator(
                    heading="Margins",
                    text_span_label="html-block-1",
                ),
            ),
            SourceTextBlock(
                block_id="gross-profit",
                source_id="source-1",
                text="Gross profit was $4.2 billion in 2025.",
                locator=SourceLocator(
                    heading="Results",
                    text_span_label="html-block-2",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Gross margin was 42.1 percent in 2025.",
            top_k=2,
        ),
    )

    assert passages[0].passage_id.startswith("gross-margin")


def test_retriever_matches_extracted_html_table_row_for_eps_claim() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=ReferenceEntry(
            reference_id="reference-1",
            citation_label="1",
            raw_bibliography_text="https://example.com/filing",
            canonical_url="https://example.com/filing",
            source_kind=SourceKind.HTML,
        ),
        body=(
            b"<html><body><main><h1>Quarterly Results</h1>"
            b"<table>"
            b"<caption>Consolidated Statements of Income</caption>"
            b"<tr><th></th><th>Three months ended September 26, 2025</th><th>Three months ended September 27, 2024</th></tr>"
            b"<tr><td>Diluted net income per share</td><td>$0.86</td><td>$0.97</td></tr>"
            b"</table></main></body></html>"
        ),
        content_type="text/html",
    )
    document = extract_source_document(payload)

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text=(
                "Diluted EPS was $0.86 for the three months ended September 26, 2025."
            ),
            top_k=3,
        ),
    )

    assert passages
    assert "Diluted net income per share" in passages[0].text
    assert "September 26, 2025: $0.86" in passages[0].text


def test_retriever_matches_stacked_header_html_table_row_for_quarterly_eps_claim() -> None:
    payload = SourcePayload(
        source_id="source-1",
        reference=ReferenceEntry(
            reference_id="reference-1",
            citation_label="1",
            raw_bibliography_text="https://example.com/filing",
            canonical_url="https://example.com/filing",
            source_kind=SourceKind.HTML,
        ),
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
    document = extract_source_document(payload)

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text=(
                "Diluted EPS was $0.88 for the three months ended June 27, 2025."
            ),
            top_k=3,
        ),
    )

    assert passages
    assert "Three months ended June 27, 2025: $0.88" in passages[0].text
    assert "Six months ended June 27, 2025: $1.65" in passages[0].text




def test_retriever_keeps_structured_table_rows_atomic_and_out_of_boundary_windows() -> None:
    """Table rows already carry their own context and must not become hybrids."""

    revenue_row = (
        "Table: Q3 Fiscal 2026 Summary. "
        "Headers: GAAP | ($ in millions, except earnings per share) "
        "Q3 FY26 Q2 FY26 Q3 FY25 Q/Q Y/Y. "
        "Row: Revenue $57,006 $46,743 $35,082 22% 62%."
    )
    gross_margin_row = (
        "Table: Q3 Fiscal 2026 Summary. "
        "Headers: Non-GAAP | ($ in millions, except earnings per share) "
        "Q3 FY26 Q2 FY26 Q3 FY25 Q/Q Y/Y. "
        "Row: Gross margin 73.6% 72.7% 75.0% 0.9 pts (1.4) pts."
    )
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="page-1",
                source_id="source-1",
                text=(
                    "As of the end of the third quarter, the company had $62.2 "
                    "billion remaining under its share repurchase authorization."
                ),
                locator=SourceLocator(page_number=1, text_span_label="page-1"),
            ),
            SourceTextBlock(
                block_id="page-1-table-1-row-1",
                source_id="source-1",
                text=revenue_row,
                locator=SourceLocator(
                    heading="Q3 Fiscal 2026 Summary",
                    page_number=1,
                    text_span_label="page-1-table-1-row-1",
                ),
            ),
            SourceTextBlock(
                block_id="page-1-table-1-row-2",
                source_id="source-1",
                text=gross_margin_row,
                locator=SourceLocator(
                    heading="Q3 Fiscal 2026 Summary",
                    page_number=1,
                    text_span_label="page-1-table-1-row-2",
                ),
            ),
            SourceTextBlock(
                block_id="page-1-following-prose",
                source_id="source-1",
                text="NVIDIA will pay its next quarterly cash dividend of $0.01 per share.",
                locator=SourceLocator(
                    page_number=1,
                    text_span_label="page-1-following-prose",
                ),
            ),
        ]
    )

    candidates = _chunk_blocks(
        document.blocks,
        max_chars_per_passage=600,
        max_overlap_overflow_chars=180,
    )
    table_candidates = [candidate for candidate in candidates if " Row: " in candidate.text]

    assert len(table_candidates) == 2
    assert not any("boundary-window" in candidate.passage_id for candidate in candidates)
    assert revenue_row in {candidate.text for candidate in table_candidates}
    assert gross_margin_row in {candidate.text for candidate in table_candidates}

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text=(
                "NVIDIA's Q3 fiscal 2026 revenue was $57,006 and non-GAAP "
                "gross margin was 73.6%."
            ),
            top_k=5,
            max_chars_per_passage=600,
        ),
    )

    assert all(
        not (
            "share repurchase authorization" in passage.text
            and "Row: Revenue" in passage.text
        )
        for passage in passages
    )
    assert all(
        not (
            "Row: Revenue" in passage.text
            and "Row: Gross margin" in passage.text
        )
        for passage in passages
    )


def test_retriever_does_not_penalize_reordered_fallback_metric_wording() -> None:
    from app.passage_retriever import _anchors, _metric_mismatch_penalty

    claim = _anchors("Fresh vegetable prices rose 9.0% year over year in May 2026.")
    reordered_evidence = _anchors(
        "On a year-over-year basis, prices for fresh vegetables increased 9.0% in May."
    )
    canonical_conflict = _anchors("Operating margin increased 9.0% in May 2026.")

    # No exact fallback phrase overlap is uncertainty, not a proven metric conflict.
    assert _metric_mismatch_penalty(claim, reordered_evidence, coverage=set()) == 0.0

    # The stronger guard still applies when known canonical metrics conflict.
    revenue_claim = _anchors("Revenue increased 9.0% in May 2026.")
    assert _metric_mismatch_penalty(revenue_claim, canonical_conflict, coverage=set()) == 10.0


def test_retriever_does_not_double_count_bare_calendar_years_as_numbers() -> None:
    from app.passage_retriever import _anchors, _matching_coverage

    claim = _anchors("Fresh vegetable prices rose 9.0% year over year in May 2026.")
    transportation = _anchors("Transportation May 2026 9.0% (12-month change).")

    assert "month:2026-may" in transportation.dates
    assert "2026" not in transportation.numbers
    assert "9" in transportation.numbers

    coverage = _matching_coverage(claim, transportation)
    assert "date:month:2026-may" in coverage
    assert "number:2026" not in coverage


def test_retriever_prefers_richer_subject_passage_over_bare_numeric_fragment() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="block-17",
                source_id="source-1",
                text="May 2026",
                locator=SourceLocator(
                    heading="Consumer Price Index, May 2026",
                    page_number=1,
                    text_span_label="html-block-17",
                ),
            ),
            SourceTextBlock(
                block_id="block-18",
                source_id="source-1",
                text="9.0%",
                locator=SourceLocator(
                    heading="Consumer Price Index, May 2026",
                    page_number=1,
                    text_span_label="html-block-18",
                ),
            ),
            SourceTextBlock(
                block_id="block-27",
                source_id="source-1",
                text=(
                    "On a year-over-year basis, prices for fresh vegetables increased "
                    "9.0% in May, following a 4.1% rise in April."
                ),
                locator=SourceLocator(
                    heading="Consumer Price Index, May 2026",
                    page_number=1,
                    text_span_label="html-block-27",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Fresh vegetable prices rose 9.0% year over year in May 2026.",
            local_context="Consumer Price Index, May 2026",
            top_k=3,
        ),
    )

    assert passages
    assert "prices for fresh vegetables increased 9.0%" in passages[0].text
    assert passages[0].text != "9.0%"


def test_retriever_prefers_richer_food_inflation_passage_over_bare_numeric_fragment() -> None:
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="block-9",
                source_id="source-1",
                text="May 2026",
                locator=SourceLocator(
                    heading="Consumer Price Index, May 2026",
                    page_number=1,
                    text_span_label="html-block-9",
                ),
            ),
            SourceTextBlock(
                block_id="block-10",
                source_id="source-1",
                text="4.3%",
                locator=SourceLocator(
                    heading="Consumer Price Index, May 2026",
                    page_number=1,
                    text_span_label="html-block-10",
                ),
            ),
            SourceTextBlock(
                block_id="block-29",
                source_id="source-1",
                text=(
                    "Collectively, higher prices for fresh fruit and fresh vegetables "
                    "contributed to an acceleration in inflation for food purchased "
                    "from stores, rising 4.3% year over year in May."
                ),
                locator=SourceLocator(
                    heading="Consumer Price Index, May 2026",
                    page_number=1,
                    text_span_label="html-block-29",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text=(
                "Food purchased from stores rose 4.3% year over year in May 2026."
            ),
            local_context="Consumer Price Index, May 2026",
            top_k=3,
        ),
    )

    assert passages
    assert "food purchased from stores" in passages[0].text
    assert passages[0].text != "4.3%"


def test_retriever_does_not_demote_structured_table_rows_as_numeric_fragments() -> None:
    row_text = (
        "Table: Consumer Price Detail. Headers: Category | May 2026 | 12-month change. "
        "Row: Fresh vegetables 9.0%."
    )
    document = _document_with_blocks(
        [
            SourceTextBlock(
                block_id="block-17",
                source_id="source-1",
                text="9.0%",
                locator=SourceLocator(
                    heading="Consumer Price Index, May 2026",
                    page_number=1,
                    text_span_label="html-block-17",
                ),
            ),
            SourceTextBlock(
                block_id="table-row-1",
                source_id="source-1",
                text=row_text,
                locator=SourceLocator(
                    heading="Consumer Price Detail",
                    page_number=1,
                    text_span_label="page-1-table-1-row-1",
                ),
            ),
        ]
    )

    passages = retrieve_candidate_passages(
        document,
        RetrievalQuery(
            claim_text="Fresh vegetable prices rose 9.0% year over year in May 2026.",
            top_k=2,
        ),
    )

    assert passages
    assert passages[0].text == row_text


def test_retriever_keeps_calendar_year_when_it_is_an_explicit_measurement() -> None:
    from app.passage_retriever import _anchors

    employment = _anchors("The company hired 2026 employees in 2025.")
    currency = _anchors("The charge was $2,026 in 2025.")

    assert "2026" in employment.numbers
    assert "2026:employee" in employment.number_units
    assert "2026" in currency.numbers
    assert "2026:currency" in currency.number_units


def _document_with_blocks(blocks: list[SourceTextBlock]) -> ExtractedSourceDocument:
    return ExtractedSourceDocument(
        source_record=SourceRecord(
            source_id="source-1",
            reference_id="reference-1",
            source_kind=SourceKind.HTML,
            canonical_url="https://example.com/report",
            fetch_status=SourceFetchStatus.FETCHED,
            extraction_status=SourceExtractionStatus.EXTRACTED,
        ),
        blocks=blocks,
    )
