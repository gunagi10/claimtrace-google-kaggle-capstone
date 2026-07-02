import json

from fastapi.testclient import TestClient

from app.fast_api_app import app
from app.config import settings
from app.review_models import (
    EvidenceAssessment,
    EvidenceVerdict,
    ExtractedSourceDocument,
    ReferenceEntry,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
    SourceRecord,
)
from app.source_adapters import SourcePayload
from app.source_fetcher import SourceFetchOutcome
import app.review_api as review_api


client = TestClient(app)


def test_healthcheck_exposes_local_safe_defaults() -> None:
    response = client.get("/local-health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "app_name": "brv-capstone",
        "default_model": settings.default_gemini_model,
        "section_analysis_model": settings.section_analysis_model,
        "final_coherence_model": settings.final_coherence_model,
    }


def test_local_review_page_renders_browser_shell() -> None:
    response = client.get("/local/review")

    assert response.status_code == 200
    assert "ClaimTrace" in response.text
    assert "Review Result" in response.text
    assert "Raw response" in response.text
    assert "Citation direction" in response.text
    assert "Claim to check" in response.text
    assert "Local report context" not in response.text
    assert "We couldn't open the cited source automatically." in response.text
    assert 'id="sourceFallbackBox" class="status-box warn hidden"' in response.text
    assert "Possible citation scope" in response.text
    assert "Both sentences" in response.text
    assert "Execution Audit" in response.text
    assert "OCR-only PDFs return" in response.text
    assert "/local/review/prepare" in response.text
    assert "/local/review/run" in response.text
    assert "/local/review/run-batch" in response.text
    assert "/local/review/run-batch/retry-source" in response.text
    assert "/local/review/run-batch/sections" in response.text
    assert "/local/review/run-batch/coherence" in response.text
    assert 'id="batchSelectionDetails" class="claim-selection hidden"' in response.text
    assert "Confirm and run selected claims" in response.text
    assert "4. Run Section Analysis" in response.text
    assert "5. Run Final Coherence" in response.text
    assert "Run section analysis" in response.text
    assert "Run final coherence" in response.text
    assert "Download markdown summary" in response.text
    assert "Batch Review Result" in response.text
    assert "1-1 Claim Checks" in response.text
    assert 'data-result-tab=' in response.text
    assert 'id="batchTimingSummary" class="status-box timing-summary hidden"' in response.text
    assert 'id="sectionTimingSummary" class="status-box timing-summary hidden"' in response.text
    assert "Sources needing attention" in response.text
    assert "Temporary parallel-worker debug" in response.text
    assert "Temporary section-worker debug" in response.text
    assert "retry with a different exact source copy if needed" in response.text
    assert "question-card" in response.text
    assert "answer-card" in response.text
    assert response.text.count('return lines.join("\\n");') == 2
    assert "confirm up to 10 cited claims" not in response.text
    assert "Up to 10 confirmed claims" not in response.text


def test_first_slice_contract_includes_text_pdf_and_ocr_rule() -> None:
    response = client.get("/contracts/first-slice")

    assert response.status_code == 200
    payload = response.json()

    assert payload["supported_source_kinds"] == ["html", "text_pdf"]
    assert "OCR-only PDFs" in payload["unsupported_source_behavior"]


def test_prepare_review_endpoint_returns_sentence_and_reference_inventory() -> None:
    response = client.post(
        "/local/review/prepare",
        files={"docx_file": ("report.docx", _docx_fixture_bytes(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["claim_ready_sentences"][0]["sentence_id"] == "sentence-1"
    assert payload["claim_ready_sentences"][0]["citation_direction"] == "backward"
    assert payload["claim_ready_sentences"][0]["requires_citation_direction_confirmation"] is False
    assert payload["references"][0]["reference_id"] == "reference-1"


def test_ambiguous_boundary_citation_requires_direction_confirmation() -> None:
    response = client.post(
        "/local/review/run",
        data={
            "sentence_id": "sentence-1",
            "reference_id": "reference-1",
            "local_context": "",
        },
        files={
            "docx_file": (
                "report.docx",
                _ambiguous_docx_fixture_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
    )

    assert response.status_code == 400
    assert "previous sentence, the next sentence, or both" in response.json()["detail"]


def test_ambiguous_boundary_citation_uses_confirmed_forward_claim() -> None:
    original_api_key = settings.google_api_key
    try:
        settings.google_api_key = None
        response = client.post(
            "/local/review/run",
            data={
                "sentence_id": "sentence-1",
                "reference_id": "reference-1",
                "citation_direction": "forward",
                "local_context": "",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _ambiguous_docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
                "source_file": (
                    "source.html",
                    b"<html><body><p>The source says ChatGPT is very good.</p></body></html>",
                    "text/html",
                ),
            },
        )
    finally:
        settings.google_api_key = original_api_key

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "awaiting_model_config"
    assert payload["judge_payload"]["atomic_claim"] == "The source says ChatGPT is very good."


def test_run_review_returns_awaiting_model_config_when_judge_payload_is_ready() -> None:
    original_api_key = settings.google_api_key
    try:
        settings.google_api_key = None
        response = client.post(
            "/local/review/run",
            data={
                "sentence_id": "sentence-1",
                "reference_id": "reference-1",
                "local_context": "Executive summary results",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
                "source_file": (
                    "source.html",
                    b"<html><body><h1>Results</h1><p>Revenue grew 12 percent year over year.</p></body></html>",
                    "text/html",
                ),
            },
        )
    finally:
        settings.google_api_key = original_api_key

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "awaiting_model_config"
    assert payload["judge_payload"]["claim_id"] == "claim-sentence-1"
    assert payload["trace"]["source_method"] == "uploaded_source_copy"
    assert payload["trace"]["stopped_stage"] == "model_configuration"
    assert payload["trace"]["candidate_passage_count"] >= 1
    assert payload["trace"]["model_called"] is False


def test_run_review_returns_prejudge_unverified_for_ocr_required_pdf() -> None:
    response = client.post(
        "/local/review/run",
        data={
            "sentence_id": "sentence-2",
            "reference_id": "reference-2",
            "local_context": "Executive summary results",
        },
        files={
            "docx_file": (
                "report.docx",
                _docx_fixture_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "source_file": (
                "source.pdf",
                _blank_pdf_bytes(),
                "application/pdf",
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "prejudge_unverified"
    assert payload["assessment"]["verdict"] == "unverified"
    assert "ocr_required" in payload["assessment"]["warnings"]
    assert payload["trace"]["stopped_stage"] == "source_extraction"
    assert payload["trace"]["model_called"] is False


def test_run_review_fetches_source_when_no_upload_is_provided(monkeypatch) -> None:
    original_api_key = settings.google_api_key

    def fake_fetch_exact_source(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=b"<html><body><h1>Results</h1><p>Revenue grew 12 percent year over year.</p></body></html>",
                content_type="text/html",
            )
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)

    try:
        settings.google_api_key = None
        response = client.post(
            "/local/review/run",
            data={
                "sentence_id": "sentence-1",
                "reference_id": "reference-1",
                "local_context": "Executive summary results",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
    finally:
        settings.google_api_key = original_api_key

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "awaiting_model_config"
    assert payload["judge_payload"]["source_fetch_status"] == "fetched"
    assert payload["trace"]["source_method"] == "exact_url_fetch"


def test_run_review_uses_browser_fallback_after_http_403(monkeypatch) -> None:
    original_api_key = settings.google_api_key
    original_browser_enabled = settings.browser_render_enabled

    def fake_fetch_exact_source(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            failure_document=ExtractedSourceDocument(
                source_record=SourceRecord(
                    source_id=source_id,
                    reference_id=reference.reference_id,
                    source_kind=reference.source_kind,
                    canonical_url=reference.canonical_url,
                    fetch_status=SourceFetchStatus.FAILED,
                    extraction_status=SourceExtractionStatus.PENDING,
                    failure_reason="The cited source returned HTTP 403 during fetch.",
                ),
                warnings=["source_fetch_failed"],
            ),
            http_status_code=403,
        )

    def fake_browser_fetch(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=b"<main><p>Revenue grew 12 percent year over year.</p></main>",
                content_type="text/html",
            ),
            http_status_code=200,
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)
    monkeypatch.setattr(review_api, "fetch_rendered_exact_source", fake_browser_fetch)

    try:
        settings.google_api_key = None
        settings.browser_render_enabled = True
        response = client.post(
            "/local/review/run",
            data={
                "sentence_id": "sentence-1",
                "reference_id": "reference-1",
                "local_context": "Executive summary results",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
    finally:
        settings.google_api_key = original_api_key
        settings.browser_render_enabled = original_browser_enabled

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "awaiting_model_config"
    assert payload["trace"]["source_method"] == "browser_rendered_fetch"
    assert payload["trace"]["source_fetch_status"] == "fetched"


def test_run_review_uses_browser_fallback_after_timeout_like_fetch_failure(monkeypatch) -> None:
    original_api_key = settings.google_api_key
    original_browser_enabled = settings.browser_render_enabled

    def fake_fetch_exact_source(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            failure_document=ExtractedSourceDocument(
                source_record=SourceRecord(
                    source_id=source_id,
                    reference_id=reference.reference_id,
                    source_kind=reference.source_kind,
                    canonical_url=reference.canonical_url,
                    fetch_status=SourceFetchStatus.FAILED,
                    extraction_status=SourceExtractionStatus.PENDING,
                    failure_reason="The cited source could not be fetched: The read operation timed out.",
                ),
                warnings=["source_fetch_failed", "source_fetch_timeout"],
            )
        )

    def fake_browser_fetch(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=b"<main><p>Revenue grew 12 percent year over year.</p></main>",
                content_type="text/html",
            ),
            http_status_code=200,
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)
    monkeypatch.setattr(review_api, "fetch_rendered_exact_source", fake_browser_fetch)

    try:
        settings.google_api_key = None
        settings.browser_render_enabled = True
        response = client.post(
            "/local/review/run",
            data={
                "sentence_id": "sentence-1",
                "reference_id": "reference-1",
                "local_context": "Executive summary results",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
    finally:
        settings.google_api_key = original_api_key
        settings.browser_render_enabled = original_browser_enabled

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "awaiting_model_config"
    assert payload["trace"]["source_method"] == "browser_rendered_fetch"
    assert payload["trace"]["source_fetch_status"] == "fetched"


def test_run_review_returns_prejudge_unverified_when_fetch_is_blocked(monkeypatch) -> None:
    def fake_fetch_exact_source(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            failure_document=ExtractedSourceDocument(
                source_record=SourceRecord(
                    source_id=source_id,
                    reference_id=reference.reference_id,
                    source_kind=reference.source_kind,
                    canonical_url=reference.canonical_url,
                    fetch_status=SourceFetchStatus.FAILED,
                    extraction_status=SourceExtractionStatus.PENDING,
                    failure_reason="Loopback and private source addresses are blocked in this stage.",
                ),
                warnings=["blocked_source_url"],
            )
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)

    response = client.post(
        "/local/review/run",
        data={
            "sentence_id": "sentence-1",
            "reference_id": "reference-1",
            "local_context": "Executive summary results",
        },
        files={
            "docx_file": (
                "report.docx",
                _docx_fixture_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "prejudge_unverified"
    assert payload["assessment"]["source_fetch_status"] == "failed"
    assert "source_fetch_failed" in payload["assessment"]["warnings"]
    assert payload["trace"]["stopped_stage"] == "source_fetch"
    assert payload["trace"]["canonical_url"] == "https://example.com/report"
    assert payload["trace"]["source_failure_reason"] == (
        "Loopback and private source addresses are blocked in this stage."
    )
    assert payload["trace"]["candidate_passage_count"] == 0
    assert payload["trace"]["model_called"] is False


def test_completed_review_keeps_passages_and_marks_model_called(monkeypatch) -> None:
    async def fake_judge(payload):
        return EvidenceAssessment(
            claim_id=payload.claim_id,
            source_id=payload.source_id,
            verdict=EvidenceVerdict.SUPPORTED,
            reason="The cited passage directly supports the approved claim.",
            recommended_action="No evidence correction is required.",
            source_fetch_status=payload.source_fetch_status,
            source_extraction_status=payload.source_extraction_status,
            passage_ids=[payload.candidate_passages[0].passage_id],
        )

    monkeypatch.setattr(review_api, "judge_evidence_payload", fake_judge)

    response = client.post(
        "/local/review/run",
        data={
            "sentence_id": "sentence-1",
            "reference_id": "reference-1",
            "local_context": "Executive summary results",
        },
        files={
            "docx_file": (
                "report.docx",
                _docx_fixture_bytes(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ),
            "source_file": (
                "source.html",
                b"<html><body><p>Revenue grew 12 percent year over year.</p></body></html>",
                "text/html",
            ),
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "completed"
    assert payload["judge_payload"]["candidate_passages"]
    assert payload["trace"]["stopped_stage"] == "completed"
    assert payload["trace"]["model_called"] is True
    assert payload["trace"]["candidate_passage_count"] >= 1


def test_run_batch_review_returns_mixed_item_statuses(monkeypatch) -> None:
    original_api_key = settings.google_api_key

    def fake_fetch_exact_source(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
        if reference.reference_id == "reference-1":
            return SourceFetchOutcome(
                payload=SourcePayload(
                    source_id=source_id,
                    reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                    body=b"<html><body><h1>Results</h1><p>Revenue grew 12 percent year over year.</p></body></html>",
                    content_type="text/html",
                )
            )
        return SourceFetchOutcome(
            failure_document=ExtractedSourceDocument(
                source_record=SourceRecord(
                    source_id=source_id,
                    reference_id=reference.reference_id,
                    source_kind=reference.source_kind,
                    canonical_url=reference.canonical_url,
                    fetch_status=SourceFetchStatus.FAILED,
                    extraction_status=SourceExtractionStatus.PENDING,
                    failure_reason="Loopback and private source addresses are blocked in this stage.",
                ),
                warnings=["blocked_source_url"],
            )
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)

    try:
        settings.google_api_key = None
        response = client.post(
            "/local/review/run-batch",
            data={
                "review_pairs_json": '[{"sentence_id":"sentence-1","reference_id":"reference-1"},{"sentence_id":"sentence-2","reference_id":"reference-2"}]',
                "local_context": "Executive summary results",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
    finally:
        settings.google_api_key = original_api_key

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_selected"] == 2
    assert payload["awaiting_model_config_count"] == 1
    assert payload["prejudge_unverified_count"] == 1
    assert payload["items"][0]["result"]["status"] == "awaiting_model_config"
    assert payload["items"][1]["result"]["status"] == "prejudge_unverified"
    assert payload["gate"] == {
        "status": "review_incomplete",
        "summary": "Evidence review is incomplete: 1 selected claim(s) still have no evidence outcome.",
        "checked_claim_count": 1,
        "pending_claim_count": 1,
        "contradiction_count": 0,
        "unsupported_count": 0,
        "unverified_count": 1,
        "contradiction_sentence_ids": [],
        "warning_sentence_ids": ["sentence-2"],
        "user_override_allowed": True,
        "user_override_applied": False,
    }
    assert payload["coverage"] == {
        "total_available": 2,
        "selected": 2,
        "completed": 0,
        "unresolved": 2,
        "deselected": 0,
        "verdict_counts": {"unverified": 1},
    }
    assert payload["unique_source_count"] == 2
    assert payload["sources_needing_attention"] == [
        {
            "reference_id": "reference-2",
            "canonical_url": "https://example.com/report.pdf",
            "failure_reason": (
                "Loopback and private source addresses are blocked in this stage."
            ),
            "affected_sentence_ids": ["sentence-2"],
            "accepted_upload_types": ["text/html", "application/pdf"],
        }
    ]
    assert payload["concurrency_debug"]["max_concurrent_workers_configured"] == 5
    assert payload["concurrency_debug"]["max_concurrent_workers_seen"] >= 1
    assert len(payload["concurrency_debug"]["source_workers"]) == 2


def test_batch_reuses_one_source_for_two_claims(monkeypatch) -> None:
    original_api_key = settings.google_api_key
    fetch_calls = 0
    extraction_calls = 0
    real_extract = review_api.extract_source_document

    def fake_fetch_exact_source(
        reference: ReferenceEntry, source_id: str
    ) -> SourceFetchOutcome:
        nonlocal fetch_calls
        fetch_calls += 1
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=(
                    b"<html><body><h1>Results</h1>"
                    b"<p>Revenue grew 12 percent year over year.</p>"
                    b"<p>Operating margin improved to 18 percent.</p>"
                    b"</body></html>"
                ),
                content_type="text/html",
            )
        )

    def counting_extract(payload: SourcePayload):
        nonlocal extraction_calls
        extraction_calls += 1
        return real_extract(payload)

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)
    monkeypatch.setattr(review_api, "extract_source_document", counting_extract)

    try:
        settings.google_api_key = None
        response = client.post(
            "/local/review/run-batch",
            data={
                "review_pairs_json": (
                    '[{"sentence_id":"sentence-1","reference_id":"reference-1"},'
                    '{"sentence_id":"sentence-2","reference_id":"reference-1"}]'
                ),
                "local_context": "",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _same_source_docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                ),
            },
        )
    finally:
        settings.google_api_key = original_api_key

    assert response.status_code == 200
    payload = response.json()
    assert fetch_calls == 1
    assert extraction_calls == 1
    assert payload["total_selected"] == 2
    assert [item["result"]["judge_payload"]["claim_id"] for item in payload["items"]] == [
        "claim-sentence-1",
        "claim-sentence-2",
    ]


def test_batch_source_recovery_retries_only_linked_unresolved_claims(
    monkeypatch,
) -> None:
    original_api_key = settings.google_api_key
    fetched_references: list[str] = []

    def fake_fetch_exact_source(
        reference: ReferenceEntry, source_id: str
    ) -> SourceFetchOutcome:
        fetched_references.append(reference.reference_id)
        if reference.reference_id == "reference-1":
            return SourceFetchOutcome(
                payload=SourcePayload(
                    source_id=source_id,
                    reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                    body=b"<html><body><p>Revenue grew 12 percent.</p></body></html>",
                    content_type="text/html",
                )
            )
        return SourceFetchOutcome(
            failure_document=ExtractedSourceDocument(
                source_record=SourceRecord(
                    source_id=source_id,
                    reference_id=reference.reference_id,
                    source_kind=reference.source_kind,
                    canonical_url=reference.canonical_url,
                    fetch_status=SourceFetchStatus.FAILED,
                    extraction_status=SourceExtractionStatus.PENDING,
                    failure_reason="The cited source could not be opened.",
                ),
                warnings=["source_fetch_failed"],
            )
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)

    try:
        settings.google_api_key = None
        initial = client.post(
            "/local/review/run-batch",
            data={
                "review_pairs_json": (
                    '[{"sentence_id":"sentence-1","reference_id":"reference-1"},'
                    '{"sentence_id":"sentence-2","reference_id":"reference-2"}]'
                ),
                "local_context": "",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        review_id = initial.json()["review_id"]
        retried = client.post(
            "/local/review/run-batch/retry-source",
            data={"review_id": review_id, "reference_id": "reference-2"},
            files={
                "source_file": (
                    "cited-source.html",
                    b"<html><body><p>Operating margin improved to 18 percent.</p></body></html>",
                    "text/html",
                )
            },
        )
    finally:
        settings.google_api_key = original_api_key

    assert initial.status_code == 200
    assert retried.status_code == 200
    payload = retried.json()
    assert fetched_references == ["reference-1", "reference-2"]
    assert payload["review_id"] == review_id
    assert payload["sources_needing_attention"] == []
    assert payload["items"][0]["result"]["trace"]["source_method"] == "exact_url_fetch"
    assert payload["items"][1]["result"]["trace"]["source_method"] == "uploaded_source_copy"
    assert payload["items"][1]["result"]["status"] == "awaiting_model_config"


def test_batch_accepts_more_than_ten_selected_claims(monkeypatch) -> None:
    original_api_key = settings.google_api_key

    def fake_fetch_exact_source(
        reference: ReferenceEntry, source_id: str
    ) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=(
                    f"<html><body><p>{reference.reference_id} supports its claim.</p></body></html>"
                ).encode("utf-8"),
                content_type="text/html",
            )
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)

    selections = [
        {"sentence_id": f"sentence-{index}", "reference_id": f"reference-{index}"}
        for index in range(1, 12)
    ]

    try:
        settings.google_api_key = None
        response = client.post(
            "/local/review/run-batch",
            data={"review_pairs_json": json.dumps(selections), "local_context": ""},
            files={
                "docx_file": (
                    "report.docx",
                    _many_claims_docx_fixture_bytes(11),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
    finally:
        settings.google_api_key = original_api_key

    assert response.status_code == 200
    payload = response.json()
    assert payload["total_selected"] == 11
    assert payload["coverage"]["selected"] == 11
    assert payload["coverage"]["total_available"] == 11
    assert payload["unique_source_count"] == 11
    assert payload["awaiting_model_config_count"] == 11
    assert len(payload["items"]) == 11
    assert payload["concurrency_debug"]["max_concurrent_workers_configured"] == 5
    assert len(payload["concurrency_debug"]["source_workers"]) == 11


def test_section_analysis_runs_one_result_per_eligible_section(monkeypatch) -> None:
    original_api_key = settings.google_api_key

    def fake_fetch_exact_source(
        reference: ReferenceEntry, source_id: str
    ) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=(
                    b"<html><body><h1>Results</h1>"
                    b"<p>Revenue grew 12 percent year over year.</p>"
                    b"<p>Margin improved to 18 percent.</p>"
                    b"</body></html>"
                ),
                content_type="text/html",
            )
        )

    async def fake_judge(payload):
        return EvidenceAssessment(
            claim_id=payload.claim_id,
            source_id=payload.source_id,
            verdict=EvidenceVerdict.SUPPORTED,
            reason="The cited source supports the checked claim.",
            recommended_action="No change needed.",
            source_fetch_status=payload.source_fetch_status,
            source_extraction_status=payload.source_extraction_status,
            passage_ids=[payload.candidate_passages[0].passage_id],
        )

    async def fake_analyze_section_packet(packet):
        from app.review_models import SectionAssessment

        return SectionAssessment(
            section_id=packet.section_id,
            heading=packet.heading,
            order=packet.order,
            summary="Section summary.",
            factual_strengths=["The section's supported claims align with the cited evidence."],
            factual_gaps=[],
            insight_issues=[],
            unresolved_risks=[],
            recommended_revisions=[],
            needs_human_attention=False,
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)
    monkeypatch.setattr(review_api, "judge_evidence_payload", fake_judge)
    import app.section_analysis as section_analysis

    monkeypatch.setattr(
        section_analysis,
        "analyze_section_packet",
        fake_analyze_section_packet,
    )

    try:
        settings.google_api_key = "test-key"
        initial = client.post(
            "/local/review/run-batch",
            data={
                "review_pairs_json": (
                    '[{"sentence_id":"sentence-1","reference_id":"reference-1"},'
                    '{"sentence_id":"sentence-2","reference_id":"reference-2"}]'
                ),
                "local_context": "",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        review_id = initial.json()["review_id"]
        section_response = client.post(
            "/local/review/run-batch/sections",
            data={"review_id": review_id},
        )
    finally:
        settings.google_api_key = original_api_key

    assert initial.status_code == 200
    assert section_response.status_code == 200
    payload = section_response.json()
    assert payload["review_id"] == review_id
    assert payload["eligible_section_count"] == 1
    assert payload["completed_count"] == 1
    assert payload["items"][0]["status"] == "completed"
    assert payload["items"][0]["packet"]["heading"] == "Executive Summary"
    assert payload["items"][0]["assessment"]["heading"] == "Executive Summary"


def test_section_analysis_blocks_when_gate_is_not_ready(monkeypatch) -> None:
    original_api_key = settings.google_api_key

    def fake_fetch_exact_source(
        reference: ReferenceEntry, source_id: str
    ) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=b"<html><body><p>Revenue grew 12 percent year over year.</p></body></html>",
                content_type="text/html",
            )
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)

    try:
        settings.google_api_key = None
        initial = client.post(
            "/local/review/run-batch",
            data={
                "review_pairs_json": '[{"sentence_id":"sentence-1","reference_id":"reference-1"}]',
                "local_context": "",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        review_id = initial.json()["review_id"]
        section_response = client.post(
            "/local/review/run-batch/sections",
            data={"review_id": review_id},
        )
    finally:
        settings.google_api_key = original_api_key

    assert initial.status_code == 200
    assert section_response.status_code == 400
    assert "cannot start section analysis" in section_response.json()["detail"].lower()


def test_final_coherence_blocks_until_section_analysis_has_run(monkeypatch) -> None:
    original_api_key = settings.google_api_key

    def fake_fetch_exact_source(
        reference: ReferenceEntry, source_id: str
    ) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=(
                    b"<html><body><h1>Results</h1>"
                    b"<p>Revenue grew 12 percent year over year.</p>"
                    b"</body></html>"
                ),
                content_type="text/html",
            )
        )

    async def fake_judge(payload):
        return EvidenceAssessment(
            claim_id=payload.claim_id,
            source_id=payload.source_id,
            verdict=EvidenceVerdict.SUPPORTED,
            reason="The cited source supports the checked claim.",
            recommended_action="No change needed.",
            source_fetch_status=payload.source_fetch_status,
            source_extraction_status=payload.source_extraction_status,
            passage_ids=[payload.candidate_passages[0].passage_id],
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)
    monkeypatch.setattr(review_api, "judge_evidence_payload", fake_judge)

    try:
        settings.google_api_key = "test-key"
        initial = client.post(
            "/local/review/run-batch",
            data={
                "review_pairs_json": '[{"sentence_id":"sentence-1","reference_id":"reference-1"}]',
                "local_context": "",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        review_id = initial.json()["review_id"]
        coherence_response = client.post(
            "/local/review/run-batch/coherence",
            data={"review_id": review_id},
        )
    finally:
        settings.google_api_key = original_api_key

    assert initial.status_code == 200
    assert coherence_response.status_code == 400
    assert "section analysis" in coherence_response.json()["detail"].lower()


def test_final_coherence_runs_after_section_analysis(monkeypatch) -> None:
    original_api_key = settings.google_api_key

    def fake_fetch_exact_source(
        reference: ReferenceEntry, source_id: str
    ) -> SourceFetchOutcome:
        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                body=(
                    b"<html><body><h1>Results</h1>"
                    b"<p>Revenue grew 12 percent year over year.</p>"
                    b"<p>Margin improved to 18 percent.</p>"
                    b"</body></html>"
                ),
                content_type="text/html",
            )
        )

    async def fake_judge(payload):
        return EvidenceAssessment(
            claim_id=payload.claim_id,
            source_id=payload.source_id,
            verdict=EvidenceVerdict.SUPPORTED,
            reason="The cited source supports the checked claim.",
            recommended_action="No change needed.",
            source_fetch_status=payload.source_fetch_status,
            source_extraction_status=payload.source_extraction_status,
            passage_ids=[payload.candidate_passages[0].passage_id],
        )

    async def fake_analyze_section_packet(packet):
        from app.review_models import SectionAssessment

        return SectionAssessment(
            section_id=packet.section_id,
            heading=packet.heading,
            order=packet.order,
            summary="Section summary.",
            factual_strengths=["Supported section fact."],
            factual_gaps=[],
            insight_issues=[],
            unresolved_risks=[],
            recommended_revisions=[],
            needs_human_attention=False,
        )

    async def fake_run_final_coherence(packet):
        from app.review_models import FinalCoherenceAssessment

        assert packet.report_coverage.completed_section_count == 1
        assert packet.global_gate.status == "continue"
        return FinalCoherenceAssessment(
            report_summary="The report is coherent and the checked sections stay aligned.",
            coherence_strengths=["The report maintains a consistent topline story."],
            coherence_issues=[],
            soundness_issues=[],
            noteworthy_patterns=["No cross-section conflict was found in the checked material."],
            priority_actions=["Proceed with a light final human read."],
            unresolved_risks=[],
            needs_human_attention=False,
        )

    monkeypatch.setattr(review_api, "fetch_exact_source", fake_fetch_exact_source)
    monkeypatch.setattr(review_api, "judge_evidence_payload", fake_judge)
    import app.section_analysis as section_analysis

    monkeypatch.setattr(
        section_analysis,
        "analyze_section_packet",
        fake_analyze_section_packet,
    )
    monkeypatch.setattr(review_api, "run_final_coherence", fake_run_final_coherence)

    try:
        settings.google_api_key = "test-key"
        initial = client.post(
            "/local/review/run-batch",
            data={
                "review_pairs_json": (
                    '[{"sentence_id":"sentence-1","reference_id":"reference-1"},'
                    '{"sentence_id":"sentence-2","reference_id":"reference-2"}]'
                ),
                "local_context": "",
            },
            files={
                "docx_file": (
                    "report.docx",
                    _docx_fixture_bytes(),
                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                )
            },
        )
        review_id = initial.json()["review_id"]
        section_response = client.post(
            "/local/review/run-batch/sections",
            data={"review_id": review_id},
        )
        coherence_response = client.post(
            "/local/review/run-batch/coherence",
            data={"review_id": review_id},
        )
    finally:
        settings.google_api_key = original_api_key

    assert initial.status_code == 200
    assert section_response.status_code == 200
    assert coherence_response.status_code == 200
    payload = coherence_response.json()
    assert payload["status"] == "completed"
    assert payload["packet"]["report_coverage"]["completed_section_count"] == 1
    assert payload["assessment"]["priority_actions"] == [
        "Proceed with a light final human read."
    ]


def _docx_fixture_bytes() -> bytes:
    import zipfile
    from io import BytesIO

    document_xml = """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Executive Summary</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Revenue grew 12 percent year over year.[1] Margin improved to 18 percent.[2]</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>References</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[1] https://example.com/report</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[2] https://example.com/report.pdf</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\" />")
        archive.writestr("_rels/.rels", "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\" />")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _same_source_docx_fixture_bytes() -> bytes:
    import zipfile
    from io import BytesIO

    document_xml = """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Executive Summary</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Revenue grew 12 percent year over year.[1] Operating margin improved to 18 percent.[1]</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>References</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[1] https://example.com/report</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types" />',
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships" />',
        )
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _many_claims_docx_fixture_bytes(claim_count: int) -> bytes:
    import zipfile
    from io import BytesIO

    claim_sentences = " ".join(
        f"Metric {index} improved by {index} percent.[{index}]"
        for index in range(1, claim_count + 1)
    )
    reference_lines = "".join(
        f'<w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[{index}] https://example.com/report-{index}</w:t></w:r></w:p>'
        for index in range(1, claim_count + 1)
    )
    document_xml = f"""
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Executive Summary</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>{claim_sentences}</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>References</w:t></w:r></w:p>
        {reference_lines}
      </w:body>
    </w:document>
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "[Content_Types].xml",
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types" />',
        )
        archive.writestr(
            "_rels/.rels",
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships" />',
        )
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def _blank_pdf_bytes() -> bytes:
    return b"""%PDF-1.4
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


def _ambiguous_docx_fixture_bytes() -> bytes:
    import zipfile
    from io import BytesIO

    document_xml = """
    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
      <w:body>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>Results</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>Background statement. [1] The source says ChatGPT is very good.</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr><w:r><w:t>References</w:t></w:r></w:p>
        <w:p><w:pPr><w:pStyle w:val="Normal"/></w:pPr><w:r><w:t>[1] https://example.com/report</w:t></w:r></w:p>
      </w:body>
    </w:document>
    """
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", "<Types xmlns=\"http://schemas.openxmlformats.org/package/2006/content-types\" />")
        archive.writestr("_rels/.rels", "<Relationships xmlns=\"http://schemas.openxmlformats.org/package/2006/relationships\" />")
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()
