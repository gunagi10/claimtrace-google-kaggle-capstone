from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import uuid4

from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from app.agent import app as judge_app
from app.config import settings
from app.review_models import EvidenceVerdict, JudgeOutput

ROOT = Path(__file__).resolve().parent
DEFAULT_DATASET = ROOT / "datasets" / "evidence-outcomes.json"
DEFAULT_OUTPUT = ROOT.parent.parent / "tmp" / "evidence-outcome-results.json"
USAGE_FIELDS = (
    "prompt_token_count",
    "candidates_token_count",
    "thoughts_token_count",
    "cached_content_token_count",
    "total_token_count",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the compact local ADK evidence-outcome evaluation."
    )
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    return parser.parse_args()


def content_text(value: dict[str, Any]) -> str:
    content = value.get("response", value)
    return "".join(
        part.get("text", "")
        for part in content.get("parts", [])
        if isinstance(part, dict)
    )


def read_case(case: dict[str, Any]) -> tuple[str, str, bool, list[list[str]]]:
    prompt = content_text(case["prompt"])
    reference = json.loads(content_text(case["reference"]))
    return (
        prompt,
        reference["expected_verdict"],
        reference["high_impact"],
        reference.get("reason_concept_groups", []),
    )


def usage_counts(usage_metadata: Any) -> dict[str, int]:
    if usage_metadata is None:
        return {}
    counts: dict[str, int] = {}
    for field in USAGE_FIELDS:
        value = (
            usage_metadata.get(field)
            if isinstance(usage_metadata, dict)
            else getattr(usage_metadata, field, None)
        )
        if isinstance(value, int):
            counts[field] = value
    return counts


async def run_agent(prompt: str) -> tuple[JudgeOutput, dict[str, int]]:
    session_service = InMemorySessionService()
    session_id = f"eval-{uuid4().hex}"
    user_id = "evidence-outcome-eval"
    await session_service.create_session(
        app_name=judge_app.name,
        user_id=user_id,
        session_id=session_id,
    )
    runner = Runner(app=judge_app, session_service=session_service)
    final_text: str | None = None
    usage: dict[str, int] = {}
    try:
        async for event in runner.run_async(
            user_id=user_id,
            session_id=session_id,
            new_message=types.Content(
                role="user",
                parts=[types.Part.from_text(text=prompt)],
            ),
        ):
            for field, value in usage_counts(event.usage_metadata).items():
                usage[field] = usage.get(field, 0) + value
            if event.is_final_response() and event.content:
                text_parts = [part.text for part in event.content.parts if part.text]
                if text_parts:
                    final_text = "".join(text_parts)
    finally:
        await runner.close()

    if not final_text:
        raise ValueError("ADK evidence judge returned no final response.")
    return JudgeOutput.model_validate_json(final_text), usage


async def run_case(case: dict[str, Any]) -> dict[str, Any]:
    prompt, expected_verdict, high_impact, reason_concept_groups = read_case(case)
    started = perf_counter()
    try:
        output, usage = await run_agent(prompt)
    except Exception as exc:
        return {
            "case_id": case["eval_case_id"],
            "expected_verdict": expected_verdict,
            "actual_verdict": None,
            "passed": False,
            "false_support": False,
            "failure_category": "runtime_or_schema_error",
            "failure_reason": str(exc),
            "elapsed_seconds": round(perf_counter() - started, 3),
            "usage": {},
        }

    actual_verdict = output.verdict.value
    lowered_reason = output.reason.lower()
    reason_contract_passed = all(
        any(concept.lower() in lowered_reason for concept in group)
        for group in reason_concept_groups
    )
    passed = actual_verdict == expected_verdict and reason_contract_passed
    false_support = (
        high_impact
        and expected_verdict != EvidenceVerdict.SUPPORTED.value
        and actual_verdict == EvidenceVerdict.SUPPORTED.value
    )
    return {
        "case_id": case["eval_case_id"],
        "expected_verdict": expected_verdict,
        "actual_verdict": actual_verdict,
        "passed": passed,
        "reason_contract_passed": reason_contract_passed,
        "false_support": false_support,
        "failure_category": (
            None
            if passed
            else "verdict_mismatch"
            if actual_verdict != expected_verdict
            else "reason_contract_mismatch"
        ),
        "failure_reason": None if passed else output.reason,
        "reason": output.reason,
        "passage_ids": output.passage_ids,
        "elapsed_seconds": round(perf_counter() - started, 3),
        "usage": usage,
    }


async def evaluate(dataset_path: Path) -> dict[str, Any]:
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    results = [await run_case(case) for case in dataset["eval_cases"]]
    total = len(results)
    passed = sum(result["passed"] for result in results)
    false_supports = sum(result["false_support"] for result in results)
    total_usage = {
        field: sum(result["usage"].get(field, 0) for result in results)
        for field in USAGE_FIELDS
    }
    return {
        "summary": {
            "passed_cases": passed,
            "total_cases": total,
            "classification_accuracy": passed / total if total else 0,
            "false_support_count": false_supports,
            "classification_gate_passed": passed / total >= 0.85 if total else False,
            "safety_gate_passed": false_supports == 0,
            "elapsed_seconds": round(
                sum(result["elapsed_seconds"] for result in results), 3
            ),
            "usage": total_usage,
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
    if not (
        report["summary"]["classification_gate_passed"]
        and report["summary"]["safety_gate_passed"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
