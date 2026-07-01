from __future__ import annotations

import json
from pathlib import Path

from app.review_models import SourceKind
from tests.eval.fixed_fixture_support import (
    ANSWER_KEY_PATH,
    SEED_MATERIAL_DIR,
    build_local_source_fetch,
    build_report_batch_request_payload,
    load_fixed_fixture_cases,
    parse_answer_key,
)


def test_parse_answer_key_reads_three_reports_with_fifteen_claims_each() -> None:
    reports = parse_answer_key(ANSWER_KEY_PATH)

    assert [report.report_id for report in reports] == [1, 2, 3]
    assert [len(report.claims) for report in reports] == [15, 15, 15]
    assert reports[0].claims[12].expected_verdict == "contradicted"
    assert reports[1].claims[11].expected_verdict == "partially_supported"
    assert reports[2].claims[9].expected_verdict == "unverified"


def test_load_fixed_fixture_cases_aligns_answer_key_to_report_docs() -> None:
    cases = load_fixed_fixture_cases(
        answer_key_path=ANSWER_KEY_PATH,
        seed_material_dir=SEED_MATERIAL_DIR,
    )

    assert len(cases) == 45
    assert cases[0].case_id == "report-1-claim-1"
    assert cases[9].case_id == "report-1-claim-10"
    assert cases[9].expected_verdict == "supported_by_cited_source"
    assert cases[10].case_id == "report-1-claim-11"
    assert cases[10].expected_verdict == "unverified"
    assert cases[25].report_id == 2
    assert cases[40].report_id == 3


def test_build_report_batch_request_payload_keeps_fixture_order() -> None:
    cases = load_fixed_fixture_cases(
        answer_key_path=ANSWER_KEY_PATH,
        seed_material_dir=SEED_MATERIAL_DIR,
    )

    payload = json.loads(build_report_batch_request_payload(cases, report_id=2))

    assert len(payload) == 15
    assert payload[0] == {"sentence_id": "sentence-1", "reference_id": "reference-1"}
    assert payload[-1] == {
        "sentence_id": "sentence-15",
        "reference_id": "reference-5",
    }


def test_local_source_fetch_can_serve_payload_and_expected_failure() -> None:
    fixture_dir = Path.cwd()
    manifest_entries = {
        "https://example.com/supported": {
            "status": "ok",
            "source_kind": "html",
            "content_type": "text/html",
            "final_canonical_url": "https://example.com/supported",
            "filename": "tests/eval/README.md",
        },
        "https://example.com/missing": {
            "status": "failed",
            "source_kind": "html",
            "failure_reason": "The cited source hostname could not be resolved: example.com.",
            "warnings": ["source_fetch_failed"],
            "http_status_code": None,
        },
    }
    fetch = build_local_source_fetch(
        manifest_entries=manifest_entries,
        fixture_dir=fixture_dir,
    )

    supported_reference = _reference("reference-1", "https://example.com/supported")
    supported = fetch(supported_reference, "source-1")
    assert supported.payload is not None
    assert supported.payload.content_type == "text/html"
    assert supported.payload.reference.source_kind == SourceKind.HTML

    missing_reference = _reference("reference-2", "https://example.com/missing")
    missing = fetch(missing_reference, "source-2")
    assert missing.failure_document is not None
    assert missing.failure_document.source_record.fetch_status.value == "failed"
    assert "source_fetch_failed" in missing.failure_document.warnings


def _reference(reference_id: str, canonical_url: str):
    from app.review_models import ReferenceEntry

    return ReferenceEntry(
        reference_id=reference_id,
        citation_label=f"[{reference_id.split('-', 1)[1]}]",
        raw_bibliography_text=canonical_url,
        canonical_url=canonical_url,
        source_kind=SourceKind.HTML,
    )
