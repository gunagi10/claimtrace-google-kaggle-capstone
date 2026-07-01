from __future__ import annotations

import hashlib
import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path
from zipfile import ZipFile

from app.docx_intake import parse_docx_bytes
from app.review_models import (
    ExtractedSourceDocument,
    ReferenceEntry,
    SourceExtractionStatus,
    SourceFetchStatus,
    SourceKind,
    SourceRecord,
)
from app.source_adapters import SourcePayload
from app.source_fetcher import (
    SourceFetchOutcome,
    fetch_exact_source,
    fetch_rendered_exact_source,
    should_try_browser_fallback,
)


ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = ROOT.parent.parent
SEED_MATERIAL_DIR = ROOT / "fixtures" / "seed_material"
ANSWER_KEY_PATH = SEED_MATERIAL_DIR / "BRV_Test_Fixtures_Answer_Key.docx"
SOURCE_FIXTURE_DIR = PROJECT_ROOT / "tmp" / "fixed_fixture_sources"
SOURCE_FIXTURE_MANIFEST_PATH = SOURCE_FIXTURE_DIR / "manifest.json"
DOCX_CONTENT_TYPE = (
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
)

_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
_REPORT_HEADER_RE = re.compile(r"^Answer Key for Report (\d+)$")
_CLAIM_LINE_RE = re.compile(r"^Claim (\d+): verdict = (.+)$")
_CITATION_MARKER_RE = re.compile(r"\s*\[\d+\]")


@dataclass(frozen=True)
class ExpectedClaim:
    claim_number: int
    expected_verdict: str
    sentence_excerpt: str
    citation_label: str
    why: str


@dataclass(frozen=True)
class ReportExpectation:
    report_id: int
    report_title: str
    claims: tuple[ExpectedClaim, ...]


@dataclass(frozen=True)
class FixedFixtureCase:
    case_id: str
    report_id: int
    report_title: str
    report_path: Path
    sentence_id: str
    reference_id: str
    sentence_text: str
    expected_verdict: str
    expected_why: str
    canonical_url: str
    source_kind: SourceKind


def read_docx_paragraphs(path: Path) -> list[str]:
    with ZipFile(path) as archive:
        xml = archive.read("word/document.xml")
    root = ET.fromstring(xml)
    paragraphs: list[str] = []
    for paragraph in root.findall(".//w:body/w:p", _DOCX_NS):
        text = "".join(
            fragment.text or "" for fragment in paragraph.findall(".//w:t", _DOCX_NS)
        ).strip()
        if text:
            paragraphs.append(text)
    return paragraphs


def normalize_claim_text(text: str) -> str:
    text = text.replace("’", "'")
    text = _CITATION_MARKER_RE.sub("", text.strip())
    text = re.sub(r"\s+([.,;:])", r"\1", text)
    return " ".join(text.split())


def parse_answer_key(path: Path = ANSWER_KEY_PATH) -> list[ReportExpectation]:
    paragraphs = read_docx_paragraphs(path)
    reports: list[ReportExpectation] = []
    current_report_id: int | None = None
    current_title: str | None = None
    current_claims: list[ExpectedClaim] = []
    current_claim_data: dict[str, object] | None = None
    expecting_title = False

    def flush_current_report() -> None:
        nonlocal current_report_id, current_title, current_claims
        if current_report_id is None:
            return
        if current_title is None:
            raise ValueError(
                f"Answer key report {current_report_id} is missing its title line."
            )
        reports.append(
            ReportExpectation(
                report_id=current_report_id,
                report_title=current_title,
                claims=tuple(current_claims),
            )
        )
        current_report_id = None
        current_title = None
        current_claims = []

    for paragraph in paragraphs:
        report_match = _REPORT_HEADER_RE.match(paragraph)
        if report_match:
            if current_claim_data is not None:
                raise ValueError(
                    "Answer key ended a report while a claim record was still incomplete."
                )
            flush_current_report()
            current_report_id = int(report_match.group(1))
            expecting_title = True
            continue

        if expecting_title:
            current_title = paragraph
            expecting_title = False
            continue

        claim_match = _CLAIM_LINE_RE.match(paragraph)
        if claim_match:
            if current_report_id is None:
                raise ValueError("Claim appeared before any report header in answer key.")
            raw_verdict = claim_match.group(2).split("(", 1)[0].strip().lower()
            verdict_map = {
                "supported": "supported_by_cited_source",
                "partially supported": "partially_supported",
                "contradicted": "contradicted",
                "unsupported": "unsupported",
                "unverified": "unverified",
            }
            if raw_verdict not in verdict_map:
                raise ValueError(f"Unknown answer-key verdict: {claim_match.group(2)}")
            current_claim_data = {
                "claim_number": int(claim_match.group(1)),
                "expected_verdict": verdict_map[raw_verdict],
            }
            continue

        if paragraph.startswith("sentence excerpt:"):
            if current_claim_data is None:
                raise ValueError("sentence excerpt appeared before a claim header.")
            current_claim_data["sentence_excerpt"] = paragraph.split(":", 1)[1].strip()
            continue

        if paragraph.startswith("citation:"):
            if current_claim_data is None:
                raise ValueError("citation appeared before a claim header.")
            current_claim_data["citation_label"] = paragraph.split(":", 1)[1].strip()
            continue

        if paragraph.startswith("why:"):
            if current_claim_data is None:
                raise ValueError("why line appeared before a claim header.")
            current_claim_data["why"] = paragraph.split(":", 1)[1].strip()
            missing = {
                key
                for key in ("sentence_excerpt", "citation_label", "why")
                if key not in current_claim_data
            }
            if missing:
                raise ValueError(
                    "Answer key claim is incomplete. Missing fields: "
                    + ", ".join(sorted(missing))
                )
            current_claims.append(
                ExpectedClaim(
                    claim_number=current_claim_data["claim_number"],  # type: ignore[arg-type]
                    expected_verdict=current_claim_data["expected_verdict"],  # type: ignore[arg-type]
                    sentence_excerpt=current_claim_data["sentence_excerpt"],  # type: ignore[arg-type]
                    citation_label=current_claim_data["citation_label"],  # type: ignore[arg-type]
                    why=current_claim_data["why"],  # type: ignore[arg-type]
                )
            )
            current_claim_data = None
            continue

        if paragraph == "Conclusion Logic Trap":
            break

    if current_claim_data is not None:
        raise ValueError("Answer key ended while a claim record was still incomplete.")
    flush_current_report()
    return reports


def load_fixed_fixture_cases(
    *,
    answer_key_path: Path = ANSWER_KEY_PATH,
    seed_material_dir: Path = SEED_MATERIAL_DIR,
) -> list[FixedFixtureCase]:
    expectations = {item.report_id: item for item in parse_answer_key(answer_key_path)}
    report_paths = sorted(seed_material_dir.glob("BRV_Report_*_*.docx"))
    cases: list[FixedFixtureCase] = []

    for report_path in report_paths:
        report_match = re.match(r"^BRV_Report_(\d+)_", report_path.name)
        if not report_match:
            continue
        report_id = int(report_match.group(1))
        expectation = expectations.get(report_id)
        if expectation is None:
            raise ValueError(
                f"No answer-key entry was found for report fixture {report_path.name}."
            )

        parsed = parse_docx_bytes(report_path.name, report_path.read_bytes())
        actual_sentences = parsed.claim_ready_sentences
        if len(actual_sentences) != len(expectation.claims):
            raise ValueError(
                f"Report {report_id} claim count mismatch: "
                f"{len(actual_sentences)} fixture claims vs {len(expectation.claims)} answer-key claims."
            )

        references_by_id = {
            reference.reference_id: reference for reference in parsed.references
        }
        for expected_claim, actual_sentence in zip(
            expectation.claims,
            actual_sentences,
            strict=True,
        ):
            expected_text = normalize_claim_text(expected_claim.sentence_excerpt)
            actual_text = normalize_claim_text(actual_sentence.sentence_text)
            if expected_text != actual_text:
                raise ValueError(
                    f"Report {report_id} claim {expected_claim.claim_number} does not align "
                    f"with the staged report fixture.\n"
                    f"Expected: {expected_claim.sentence_excerpt}\n"
                    f"Actual:   {actual_sentence.sentence_text}"
                )
            citation_number = expected_claim.citation_label.strip()[1:-1]
            reference_id = f"reference-{citation_number}"
            if reference_id not in actual_sentence.reference_ids:
                raise ValueError(
                    f"Report {report_id} claim {expected_claim.claim_number} expected "
                    f"{reference_id}, but the parsed report sentence maps to "
                    f"{actual_sentence.reference_ids}."
                )
            reference = references_by_id[reference_id]
            cases.append(
                FixedFixtureCase(
                    case_id=f"report-{report_id}-claim-{expected_claim.claim_number}",
                    report_id=report_id,
                    report_title=expectation.report_title,
                    report_path=report_path,
                    sentence_id=actual_sentence.sentence_id,
                    reference_id=reference_id,
                    sentence_text=normalize_claim_text(actual_sentence.sentence_text),
                    expected_verdict=expected_claim.expected_verdict,
                    expected_why=expected_claim.why,
                    canonical_url=reference.canonical_url or "",
                    source_kind=reference.source_kind,
                )
            )
    return cases


def refresh_source_fixture_library(
    *,
    cases: list[FixedFixtureCase],
    fixture_dir: Path = SOURCE_FIXTURE_DIR,
    manifest_path: Path = SOURCE_FIXTURE_MANIFEST_PATH,
) -> dict[str, dict]:
    fixture_dir.mkdir(parents=True, exist_ok=True)
    manifest_entries: dict[str, dict] = {}
    unique_cases: dict[str, FixedFixtureCase] = {}
    for case in cases:
        unique_cases.setdefault(case.canonical_url, case)

    for canonical_url, case in sorted(unique_cases.items()):
        reference = ReferenceEntry(
            reference_id=case.reference_id,
            citation_label=f"[{case.reference_id.split('-', 1)[1]}]",
            raw_bibliography_text=canonical_url,
            canonical_url=canonical_url,
            source_kind=case.source_kind,
        )
        source_id = f"fixture-source-{case.report_id}-{case.reference_id}"
        fetch_outcome = fetch_exact_source(reference, source_id)
        method = "exact_url_fetch"
        if fetch_outcome.payload is None and should_try_browser_fallback(
            reference, fetch_outcome
        ):
            fetch_outcome = fetch_rendered_exact_source(reference, source_id)
            method = "browser_rendered_fetch"

        if fetch_outcome.payload is not None:
            payload = fetch_outcome.payload
            extension = (
                ".pdf"
                if payload.reference.source_kind == SourceKind.TEXT_PDF
                else ".html"
            )
            hashed = hashlib.sha1(canonical_url.encode("utf-8")).hexdigest()[:12]
            filename = f"report-{case.report_id}-{case.reference_id}-{hashed}{extension}"
            output_path = fixture_dir / filename
            output_path.write_bytes(payload.body)
            manifest_entries[canonical_url] = {
                "status": "ok",
                "report_id": case.report_id,
                "reference_id": case.reference_id,
                "source_kind": payload.reference.source_kind.value,
                "content_type": payload.content_type,
                "canonical_url": canonical_url,
                "final_canonical_url": payload.reference.canonical_url,
                "filename": filename,
                "fetch_method": method,
            }
            continue

        failure_document = fetch_outcome.failure_document
        if failure_document is None:
            raise ValueError(
                f"Source fetch produced neither a payload nor a failure document for {canonical_url}."
            )
        manifest_entries[canonical_url] = {
            "status": "failed",
            "report_id": case.report_id,
            "reference_id": case.reference_id,
            "source_kind": case.source_kind.value,
            "content_type": None,
            "canonical_url": canonical_url,
            "final_canonical_url": canonical_url,
            "filename": None,
            "fetch_method": method,
            "failure_reason": failure_document.source_record.failure_reason,
            "warnings": failure_document.warnings,
            "http_status_code": fetch_outcome.http_status_code,
        }

    manifest = {"entries": manifest_entries}
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    return manifest_entries


def load_source_fixture_manifest(
    manifest_path: Path = SOURCE_FIXTURE_MANIFEST_PATH,
) -> dict[str, dict]:
    if not manifest_path.exists():
        raise FileNotFoundError(
            "Local source fixture manifest is missing. Run the fixed-fixture harness "
            "with --refresh-source-fixtures first."
        )
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    return payload["entries"]


def build_local_source_fetch(
    *,
    manifest_entries: dict[str, dict],
    fixture_dir: Path = SOURCE_FIXTURE_DIR,
):
    def _local_fetch(reference: ReferenceEntry, source_id: str) -> SourceFetchOutcome:
        canonical_url = (reference.canonical_url or "").strip()
        entry = manifest_entries.get(canonical_url)
        if entry is None:
            raise ValueError(
                "No local source fixture entry was found for "
                f"{reference.reference_id}: {canonical_url}"
            )
        if entry["status"] == "failed":
            return SourceFetchOutcome(
                failure_document=ExtractedSourceDocument(
                    source_record=SourceRecord(
                        source_id=source_id,
                        reference_id=reference.reference_id,
                        source_kind=SourceKind(entry["source_kind"]),
                        canonical_url=canonical_url,
                        fetch_status=SourceFetchStatus.FAILED,
                        extraction_status=SourceExtractionStatus.PENDING,
                        failure_reason=entry["failure_reason"],
                    ),
                    warnings=list(entry.get("warnings") or []),
                ),
                http_status_code=entry.get("http_status_code"),
            )

        filename = entry.get("filename")
        if not filename:
            raise ValueError(f"Local source fixture entry is missing a filename: {entry}")
        file_path = fixture_dir / filename
        if not file_path.exists():
            raise FileNotFoundError(f"Local source fixture file is missing: {file_path}")

        return SourceFetchOutcome(
            payload=SourcePayload(
                source_id=source_id,
                reference=reference.model_copy(
                    update={
                        "canonical_url": entry.get("final_canonical_url")
                        or canonical_url,
                        "source_kind": SourceKind(entry["source_kind"]),
                    }
                ),
                body=file_path.read_bytes(),
                content_type=entry.get("content_type"),
            )
        )

    return _local_fetch


def build_report_batch_request_payload(
    cases: list[FixedFixtureCase],
    *,
    report_id: int,
) -> str:
    report_cases = [case for case in cases if case.report_id == report_id]
    if not report_cases:
        raise ValueError(f"No fixed-fixture cases were found for report {report_id}.")
    selections = [
        {"sentence_id": case.sentence_id, "reference_id": case.reference_id}
        for case in report_cases
    ]
    return json.dumps(selections)
