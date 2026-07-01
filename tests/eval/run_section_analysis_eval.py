from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any

from app.config import settings
from app.review_models import SectionPacket
from app.section_judge import analyze_section_packet


ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "datasets" / "section-analysis.json"
DEFAULT_OUTPUT = ROOT.parent.parent / "tmp" / "section-analysis-results.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the local ADK section-analysis evaluation."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def _joined_text(values: list[str] | None) -> str:
    return " ".join(values or []).lower()


def _concept_groups_pass(text: str, groups: list[list[str]]) -> bool:
    normalized = text.lower()
    return all(
        any(concept.lower() in normalized for concept in alternatives)
        for alternatives in groups
    )


def _validate_field(
    *,
    field_name: str,
    text: str,
    groups: list[list[str]] | None,
    errors: list[str],
) -> None:
    if groups and not _concept_groups_pass(text, groups):
        errors.append(f"{field_name} missed one or more required concept groups")


async def run_case(case: dict[str, Any]) -> dict[str, Any]:
    packet = SectionPacket.model_validate(case["packet"])
    expectations = case["expectations"]
    started = perf_counter()
    try:
        assessment = await analyze_section_packet(packet)
    except Exception as exc:
        return {
            "case_id": case["case_id"],
            "passed": False,
            "failure_category": "runtime_or_schema_error",
            "failure_reason": str(exc),
            "elapsed_seconds": round(perf_counter() - started, 3),
        }

    errors: list[str] = []
    if assessment.needs_human_attention != expectations["needs_human_attention"]:
        errors.append(
            "needs_human_attention mismatch: "
            f"expected {expectations['needs_human_attention']}, "
            f"got {assessment.needs_human_attention}"
        )

    _validate_field(
        field_name="summary",
        text=assessment.summary.lower(),
        groups=expectations.get("summary_concept_groups"),
        errors=errors,
    )
    _validate_field(
        field_name="factual_strengths",
        text=_joined_text(assessment.factual_strengths),
        groups=expectations.get("strength_concept_groups"),
        errors=errors,
    )
    _validate_field(
        field_name="factual_gaps",
        text=_joined_text(assessment.factual_gaps),
        groups=expectations.get("gap_concept_groups"),
        errors=errors,
    )
    _validate_field(
        field_name="unresolved_risks",
        text=_joined_text(assessment.unresolved_risks),
        groups=expectations.get("risk_concept_groups"),
        errors=errors,
    )
    _validate_field(
        field_name="recommended_revisions",
        text=_joined_text(assessment.recommended_revisions),
        groups=expectations.get("revision_concept_groups"),
        errors=errors,
    )

    min_risk_count = expectations.get("min_unresolved_risk_count")
    if isinstance(min_risk_count, int) and len(assessment.unresolved_risks) < min_risk_count:
        errors.append(
            f"expected at least {min_risk_count} unresolved risks, got {len(assessment.unresolved_risks)}"
        )

    max_risk_count = expectations.get("max_unresolved_risk_count")
    if isinstance(max_risk_count, int) and len(assessment.unresolved_risks) > max_risk_count:
        errors.append(
            f"expected at most {max_risk_count} unresolved risks, got {len(assessment.unresolved_risks)}"
        )

    return {
        "case_id": case["case_id"],
        "passed": not errors,
        "failure_category": None if not errors else "contract_mismatch",
        "failure_reason": None if not errors else "; ".join(errors),
        "elapsed_seconds": round(perf_counter() - started, 3),
        "assessment": assessment.model_dump(),
    }


async def evaluate(dataset_path: Path) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    results = [await run_case(case) for case in dataset["cases"]]
    total = len(results)
    passed = sum(result["passed"] for result in results)
    return {
        "summary": {
            "passed_cases": passed,
            "total_cases": total,
            "pass_rate": passed / total if total else 0,
            "gate_passed": passed == total,
            "elapsed_seconds": round(
                sum(result["elapsed_seconds"] for result in results), 3
            ),
        },
        "results": results,
    }


def main() -> None:
    args = parse_args()
    if not settings.gemini_config_ready():
        raise SystemExit("Gemini config is not ready in the local .env file.")
    report = asyncio.run(evaluate(args.dataset))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    if not report["summary"]["gate_passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
