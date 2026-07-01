from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from app.config import settings
from tests.eval.fixed_fixture_support import (
    ANSWER_KEY_PATH,
    DOCX_CONTENT_TYPE,
    SEED_MATERIAL_DIR,
    SOURCE_FIXTURE_DIR,
    build_local_source_fetch,
    build_report_batch_request_payload,
    load_fixed_fixture_cases,
    load_source_fixture_manifest,
    refresh_source_fixture_library,
)


DEFAULT_OUTPUT = (
    Path(__file__).resolve().parent.parent.parent / "tmp" / "fixed-fixture-eval-results.json"
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run the lightweight fixed-fixture evaluation harness against the real "
            "batch claim-review pipeline."
        )
    )
    parser.add_argument("--answer-key", type=Path, default=ANSWER_KEY_PATH)
    parser.add_argument("--seed-dir", type=Path, default=SEED_MATERIAL_DIR)
    parser.add_argument("--source-fixture-dir", type=Path, default=SOURCE_FIXTURE_DIR)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--refresh-source-fixtures",
        action="store_true",
        help="Fetch or refresh local exact-source snapshots before running the eval.",
    )
    parser.add_argument(
        "--report-id",
        type=int,
        action="append",
        help="Limit the eval to one or more report IDs.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    from fastapi.testclient import TestClient

    from app.fast_api_app import app
    import app.review_api as review_api

    if not settings.gemini_config_ready():
        raise SystemExit("Gemini config is not ready in the local .env file.")

    cases = load_fixed_fixture_cases(
        answer_key_path=args.answer_key,
        seed_material_dir=args.seed_dir,
    )
    manifest_path = args.source_fixture_dir / "manifest.json"
    if args.report_id:
        requested = set(args.report_id)
        cases = [case for case in cases if case.report_id in requested]
        if not cases:
            raise SystemExit(
                f"No fixed-fixture cases matched the requested report IDs: {sorted(requested)}"
            )

    if args.refresh_source_fixtures or not manifest_path.exists():
        refresh_source_fixture_library(
            cases=cases,
            fixture_dir=args.source_fixture_dir,
            manifest_path=manifest_path,
        )

    manifest_entries = load_source_fixture_manifest(manifest_path)
    local_fetch = build_local_source_fetch(
        manifest_entries=manifest_entries,
        fixture_dir=args.source_fixture_dir,
    )
    client = TestClient(app)

    original_fetch = review_api.fetch_exact_source
    try:
        review_api.fetch_exact_source = local_fetch
        report = evaluate(cases, manifest_path=manifest_path, client=client)
    finally:
        review_api.fetch_exact_source = original_fetch

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))

    if not report["summary"]["gate_passed"]:
        raise SystemExit(1)


def evaluate(cases: list[Any], *, manifest_path: Path, client: Any) -> dict[str, Any]:
    reports = sorted({case.report_id for case in cases})
    results = [run_report(cases, report_id=report_id, client=client) for report_id in reports]
    total_cases = sum(report["summary"]["total_cases"] for report in results)
    passed_cases = sum(report["summary"]["passed_cases"] for report in results)
    false_support_count = sum(
        report["summary"]["false_support_count"] for report in results
    )
    return {
        "summary": {
            "reports_run": reports,
            "passed_cases": passed_cases,
            "total_cases": total_cases,
            "classification_accuracy": passed_cases / total_cases if total_cases else 0,
            "false_support_count": false_support_count,
            "gate_passed": passed_cases == total_cases and false_support_count == 0,
            "source_fixture_manifest": str(manifest_path),
        },
        "reports": results,
    }


def run_report(cases: list[Any], *, report_id: int, client: Any) -> dict[str, Any]:
    report_cases = [case for case in cases if case.report_id == report_id]
    if not report_cases:
        raise ValueError(f"No cases were found for report {report_id}.")

    response = client.post(
        "/local/review/run-batch",
        data={
            "review_pairs_json": build_report_batch_request_payload(
                cases, report_id=report_id
            ),
            "local_context": report_cases[0].report_title,
        },
        files={
            "docx_file": (
                report_cases[0].report_path.name,
                report_cases[0].report_path.read_bytes(),
                DOCX_CONTENT_TYPE,
            )
        },
    )

    if response.status_code != 200:
        raise ValueError(
            f"Fixed-fixture report {report_id} failed before verdict comparison: "
            f"HTTP {response.status_code} {response.text}"
        )

    payload = response.json()
    items = payload["items"]
    if len(items) != len(report_cases):
        raise ValueError(
            f"Fixed-fixture report {report_id} returned {len(items)} items for "
            f"{len(report_cases)} expected cases."
        )

    case_results: list[dict[str, Any]] = []
    passed_cases = 0
    false_support_count = 0
    for expected_case, item in zip(report_cases, items, strict=True):
        result = item["result"]
        assessment = result.get("assessment") or {}
        actual_verdict = assessment.get("verdict")
        passed = actual_verdict == expected_case.expected_verdict
        false_support = (
            expected_case.expected_verdict != "supported_by_cited_source"
            and actual_verdict == "supported_by_cited_source"
        )
        if passed:
            passed_cases += 1
        if false_support:
            false_support_count += 1

        trace = result.get("trace") or {}
        case_results.append(
            {
                "case_id": expected_case.case_id,
                "sentence_id": expected_case.sentence_id,
                "reference_id": expected_case.reference_id,
                "expected_verdict": expected_case.expected_verdict,
                "actual_verdict": actual_verdict,
                "passed": passed,
                "false_support": false_support,
                "status": result.get("status"),
                "expected_why": expected_case.expected_why,
                "actual_reason": assessment.get("reason"),
                "selected_passage_ids": assessment.get("passage_ids") or [],
                "candidate_passages": trace.get("candidate_passages") or [],
                "source_method": trace.get("source_method"),
                "canonical_url": trace.get("canonical_url"),
                "stopped_stage": trace.get("stopped_stage"),
            }
        )

    return {
        "report_id": report_id,
        "report_title": report_cases[0].report_title,
        "report_path": str(report_cases[0].report_path),
        "summary": {
            "passed_cases": passed_cases,
            "total_cases": len(report_cases),
            "classification_accuracy": (
                passed_cases / len(report_cases) if report_cases else 0
            ),
            "false_support_count": false_support_count,
            "gate_passed": passed_cases == len(report_cases) and false_support_count == 0,
        },
        "cases": case_results,
    }


if __name__ == "__main__":
    main()
