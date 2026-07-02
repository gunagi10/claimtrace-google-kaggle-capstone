import logging
import os

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import HTMLResponse
from google.adk.cli.fast_api import get_fast_api_app

from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback
from app.config import settings
from app.local_review_page import render_local_review_page
from app.review_api import (
    RunBatchReviewResponse,
    RunFinalCoherenceResponse,
    RunSectionAnalysisResponse,
    PrepareReviewResponse,
    RunReviewResponse,
    prepare_review_from_docx,
    retry_batch_source,
    run_batch_final_coherence,
    run_batch_section_analysis,
    run_batch_claim_review,
    run_single_claim_review,
)
from app.review_models import CitationDirection, FIRST_SLICE_CONTRACT

setup_telemetry()
logger = logging.getLogger(__name__)
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",") if os.getenv("ALLOW_ORIGINS") else None
)

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=True,
    artifact_service_uri=None,
    allow_origins=allow_origins,
    session_service_uri=None,
    otel_to_cloud=False,
)
app.title = settings.app_name
app.description = "Local shell for the ClaimTrace capstone"


@app.get("/local/review", response_class=HTMLResponse)
def local_review_page() -> HTMLResponse:
    return HTMLResponse(render_local_review_page())


@app.get("/local-health")
def local_healthcheck() -> dict[str, str]:
    return {
        "status": "ok",
        "app_name": settings.app_name,
        "default_model": settings.default_gemini_model,
        "section_analysis_model": settings.section_analysis_model,
        "final_coherence_model": settings.final_coherence_model,
    }


@app.get("/contracts/first-slice")
def first_slice_contract() -> dict:
    return FIRST_SLICE_CONTRACT.model_dump(mode="json")


@app.post("/local/review/prepare", response_model=PrepareReviewResponse)
async def local_prepare_review(docx_file: UploadFile) -> PrepareReviewResponse:
    return await prepare_review_from_docx(docx_file)


@app.post("/local/review/run", response_model=RunReviewResponse)
async def local_run_review(
    docx_file: UploadFile = File(...),
    source_file: UploadFile | None = File(None),
    sentence_id: str = Form(...),
    reference_id: str = Form(...),
    approved_claim_text: str | None = Form(None),
    citation_direction: CitationDirection | None = Form(None),
    local_context: str = Form(""),
) -> RunReviewResponse:
    return await run_single_claim_review(
        docx_file=docx_file,
        source_file=source_file,
        sentence_id=sentence_id,
        reference_id=reference_id,
        approved_claim_text=approved_claim_text,
        citation_direction=citation_direction,
        local_context=local_context,
    )


@app.post("/local/review/run-batch", response_model=RunBatchReviewResponse)
async def local_run_batch_review(
    docx_file: UploadFile = File(...),
    review_pairs_json: str = Form(...),
    local_context: str = Form(""),
) -> RunBatchReviewResponse:
    return await run_batch_claim_review(
        docx_file=docx_file,
        review_pairs_json=review_pairs_json,
        local_context=local_context,
    )


@app.post(
    "/local/review/run-batch/retry-source",
    response_model=RunBatchReviewResponse,
)
async def local_retry_batch_source(
    review_id: str = Form(...),
    reference_id: str = Form(...),
    source_file: UploadFile = File(...),
) -> RunBatchReviewResponse:
    return await retry_batch_source(
        review_id=review_id,
        reference_id=reference_id,
        source_file=source_file,
    )


@app.post(
    "/local/review/run-batch/sections",
    response_model=RunSectionAnalysisResponse,
)
async def local_run_batch_section_analysis(
    review_id: str = Form(...),
) -> RunSectionAnalysisResponse:
    return await run_batch_section_analysis(review_id=review_id)


@app.post(
    "/local/review/run-batch/coherence",
    response_model=RunFinalCoherenceResponse,
)
async def local_run_batch_final_coherence(
    review_id: str = Form(...),
) -> RunFinalCoherenceResponse:
    return await run_batch_final_coherence(review_id=review_id)


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    logger.info("feedback_received", extra={"feedback": feedback.model_dump()})
    return {"status": "success"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
