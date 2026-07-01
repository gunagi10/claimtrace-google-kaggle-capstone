from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from typing import Any
import zipfile

from fastapi.testclient import TestClient

from app.config import settings
from app.fast_api_app import app
from app.review_models import (
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


ROOT = Path(__file__).resolve().parent
CASES_PATH = ROOT / "first_slice_cases.json"
DOCX_CONTENT_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
client = TestClient(app)


def main() -> None:
    case_data = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results: list[dict[str, Any]] = []

    for case in case_data["cases"]:
        results.append(run_case(case))

    print(json.dumps({"results": results}, indent=2))

    failed = [result for result in results if result["outcome"] == "failed"]
    if failed:
        raise SystemExit(1)


def run_case(case: dict[str, Any]) -> dict[str, Any]:
    original_api_key = settings.google_api_key
    original_fetch = review_api.fetch_exact_source

    try:
        mode = case["mode"]
        if mode == "placeholder_config":
            settings.google_api_key = None
        elif mode == "live_judge":
            if not settings.gemini_config_ready():
                return {
                    "case_id": case["case_id"],
                    "outcome": "skipped",
                    "reason": "Gemini config is not ready in .env yet.",
                }

        patched_fetch = build_fetch_patch(case["source_mode"])
        if patched_fetch is not None:
            review_api.fetch_exact_source = patched_fetch

        response = client.post(
            "/local/review/run",
            data={
                "sentence_id": select_sentence_id(case["source_mode"]),
                "reference_id": select_reference_id(case["source_mode"]),
                "local_context": "Executive summary results",
            },
            files=build_request_files(case["source_mode"]),
        )

        payload = response.json()
        errors = validate_payload(case, response.status_code, payload)
        return {
            "case_id": case["case_id"],
            "outcome": "passed" if not errors else "failed",
            "http_status": response.status_code,
            "status": payload.get("status"),
            "verdict": (payload.get("assessment") or {}).get("verdict"),
            "errors": errors,
        }
    finally:
        settings.google_api_key = original_api_key
        review_api.fetch_exact_source = original_fetch


def build_request_files(source_mode: str) -> dict[str, tuple[str, bytes, str]]:
    files: dict[str, tuple[str, bytes, str]] = {
        "docx_file": ("report.docx", build_docx_fixture_bytes(), DOCX_CONTENT_TYPE),
    }
    if source_mode == "upload_html_supported":
        files["source_file"] = (
            "source.html",
            b"<html><body><h1>Results</h1><p>Revenue grew 12 percent year over year.</p></body></html>",
            "text/html",
        )
    elif source_mode == "upload_html_unsupported":
        files["source_file"] = (
            "source.html",
            b"<html><body><h1>Results</h1><p>Revenue was flat year over year.</p></body></html>",
            "text/html",
        )
    elif source_mode == "upload_pdf_ocr_required":
        files["source_file"] = ("source.pdf", build_blank_pdf_bytes(), "application/pdf")
    return files


def build_fetch_patch(source_mode: str):
    if source_mode == "fetch_html_supported":
        def fake_fetch(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
            return SourceFetchOutcome(
                payload=SourcePayload(
                    source_id=source_id,
                    reference=reference.model_copy(update={"source_kind": SourceKind.HTML}),
                    body=b"<html><body><h1>Results</h1><p>Revenue grew 12 percent year over year.</p></body></html>",
                    content_type="text/html",
                )
            )
        return fake_fetch

    if source_mode == "fetch_blocked":
        def fake_fetch(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
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
        return fake_fetch

    return None


def select_sentence_id(source_mode: str) -> str:
    if source_mode == "upload_pdf_ocr_required":
        return "sentence-2"
    return "sentence-1"


def select_reference_id(source_mode: str) -> str:
    if source_mode == "upload_pdf_ocr_required":
        return "reference-2"
    return "reference-1"


def validate_payload(
    case: dict[str, Any],
    http_status: int,
    payload: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    if http_status != 200:
        errors.append(f"expected HTTP 200, got {http_status}")

    expected_status = case.get("expected_status")
    if expected_status and payload.get("status") != expected_status:
        errors.append(f"expected status {expected_status}, got {payload.get('status')}")

    expected_verdict = case.get("expected_verdict")
    actual_verdict = (payload.get("assessment") or {}).get("verdict")
    if expected_verdict and actual_verdict != expected_verdict:
        errors.append(f"expected verdict {expected_verdict}, got {actual_verdict}")

    for forbidden in case.get("forbid_verdicts", []):
        if actual_verdict == forbidden:
            errors.append(f"forbidden verdict returned: {forbidden}")

    actual_warnings = (payload.get("assessment") or {}).get("warnings") or []
    for warning in case.get("expected_warnings", []):
        if warning not in actual_warnings:
            errors.append(f"missing expected warning: {warning}")

    return errors


def build_docx_fixture_bytes() -> bytes:
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


def build_blank_pdf_bytes() -> bytes:
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


if __name__ == "__main__":
    main()
