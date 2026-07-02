# ClaimTrace

Trace the source. Then let AI review what's left.

ClaimTrace is a local-first capstone project for checking whether quantitative business claims are actually supported by their cited sources. It is designed for reports where citations look plausible, but the real question is narrower and more important: does the cited source support this exact claim?

## What It Does

ClaimTrace takes a `.docx` business report with numbered citations, maps claim-ready sentences to bibliography entries, fetches each cited HTML or text-layer PDF source once, retrieves up to five bounded evidence passages, and sends only that evidence packet to a Gemini judge through Google ADK.

The output is a structured verdict for each selected claim:

- `supported_by_cited_source`
- `partially_supported`
- `unsupported`
- `contradicted`
- `unverified`

Contradictions are treated as hard stops. Unsupported and unverified claims become warnings before section-level and final-coherence review.

## Why This Exists

AI-generated business reports can include citations that are real but weak: the source exists, yet it may not support the exact number, period, qualifier, geography, or metric in the report. ClaimTrace focuses on that high-value slice instead of trying to become a general report grader.

The intended users are finance, investor relations, consulting, market intelligence, economic research, and strategy teams reviewing citation-backed quantitative claims.

## How It Works

1. Upload a `.docx` report with numbered citations and a `References` or `Bibliography` section.
2. Review the parsed claim-to-reference mapping and confirm ambiguous citation direction when needed.
3. Fetch the exact cited source once per reference, with safe public HTTP/HTML/PDF handling and isolated browser fallback when enabled.
4. Preserve source structure such as headings, page labels, and table-row context where extraction supports it.
5. Rank up to five candidate passages with deterministic anchors: metric, value, period, entity, direction, qualifier, and scope.
6. Ask Gemini to judge only the bounded evidence packet, not the whole internet or the whole document.
7. Run section analysis and final coherence only after the evidence gate is clear enough to continue.

For the detailed retrieval, chunking, and ranking design, see [Retrieval Design](docs/RETRIEVAL_DESIGN.md).

## Google x Kaggle Course Concepts Applied

ClaimTrace applies ideas from the Google x Kaggle course readings in a practical, scoped way:

**Day 1: New SDLC with vibe coding**

- Built the project in working slices: document intake, exact-source fetching, deterministic retrieval, ADK/Gemini judging, section review, final coherence, and fixed-fixture evaluation.
- Treated the model as one part of a larger system, with deterministic code handling source access, passage selection, stopping rules, and traceability.
- Kept human judgment in the loop for claim selection and ambiguous citation direction.

**Day 2: Agent tools and interoperability**

- Used Google ADK for the evidence-judge agent boundary.
- Kept the architecture simple instead of adding MCP, A2A, or A2UI without a real product need.
- Connected the agent to the rest of the app through local FastAPI routes, source-fetching utilities, and structured evidence packets.

**Day 3: Agent skills and progressive disclosure**

- Used small project instruction and routing files during development instead of one giant prompt.
- Loaded task-specific context only when needed.
- Split project knowledge across focused docs for scope, testing, evaluation, and build-loop state.

**Day 4: Security and evaluation**

- Added unit tests, integration tests, eval scripts, and a fixed-fixture harness with 45 claim cases.
- Kept `.env` local and used `.env.example` for public configuration.
- Blocked private, loopback, link-local, and unsafe source targets.
- Returned `unverified` when source access, extraction, or passage coverage was not strong enough for a defensible judgment.
- Preserved trace details such as source status, extraction status, candidate passages, and whether the model ran.
- Current fixed-fixture result: `42 / 45` with `0` false-support decisions.

**Day 5: Spec-driven production-grade development**

- Kept durable project intent in versioned files instead of only in chat.
- Broke development into feature buckets with visible acceptance criteria.
- Checked behavior changes against tests and evals before documenting them as complete.
- Documented limitations clearly so the project is presented as a scoped local prototype, not a production SaaS app.

## Current Evaluation

The main reproducible evaluation is a lightweight fixed-fixture harness around the real `/local/review/run-batch` pipeline.

Latest documented full fixture replay:

- 3 fixed `.docx` reports
- 45 claim cases
- 42 / 45 exact verdict matches
- 93.3% classification accuracy
- 0 false-support decisions

The three misses are conservative undercalls, not false confirmations:

- A dense filing case where partial support was not surfaced clearly enough.
- A rounded-value case where `$75.246B` was judged as only partial support for `$75.2B`.
- A Statistics Canada fragment-selection case where a short row-like fragment outranked a fuller subject sentence.

Unit and integration regression status:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit tests\integration
```

Current local result: `106 passed, 9 warnings`.

## Demo Files

The demo fixtures are stored separately from the scored eval fixtures:

```text
demo/fixtures/
  ClaimTrace_Demo_Canadian_Grocery_Good_Conclusion.docx
  ClaimTrace_Demo_Canadian_Grocery_Bad_Conclusion.docx
```

The video demo uses the Canadian grocery strategy report in two versions:

- a good-conclusion version with a cautious, evidence-led recommendation
- a bad-conclusion version where the final recommendation overreaches from the cited evidence

This shows the intended workflow: first check whether cited claims are supported, then use the section and final-coherence review to catch what is still risky in the report narrative.

## Scope And Limitations

ClaimTrace is submission-ready as a scoped local prototype, not as a production SaaS app.

Current limitations:

- No OCR for scanned PDFs.
- No full table reconstruction.
- No multi-source citation reasoning for a single claim.
- No semantic retrieval fallback for paraphrased evidence.
- Dynamic websites can still fail or require uploaded source copies.
- Public-source coverage has been tested on a narrow fixture set, not the whole web.
- Some internal code could be refactored, but the current capstone priority is verified behavior over cleanup.

These limits are deliberate. The project is strongest when judged as a quantitative cited-source verifier for expected `.docx` inputs, not as a universal fact-checking assistant.

## Stack

| Layer | Choice |
|---|---|
| Language | Python 3.13 |
| Web app | FastAPI |
| Agent framework | Google ADK |
| Model | Gemini, when configured |
| Validation | Pydantic |
| Source fetching | HTTPX and optional Playwright/browser fallback |
| Document parsing | DOCX parsing, HTML extraction, text-layer PDF extraction |
| Testing | Pytest plus fixed-fixture eval harness |
| Deployment | Local-first prototype |

## Quick Start

Prerequisites:

- Python 3.11 to 3.13
- `uv` for dependency installation

If `uv` is not installed yet:

```powershell
python -m pip install uv
```

Install project dependencies:

```powershell
uv sync
```

Create your local `.env` file:

```powershell
Copy-Item .env.example .env
```

Then open `.env` and add your Google API key:

```env
BRV_GEMINI_MODEL=gemini-flash-lite-latest
GOOGLE_GENAI_USE_VERTEXAI=false
GOOGLE_API_KEY=
GOOGLE_CLOUD_PROJECT=
GOOGLE_CLOUD_LOCATION=global
BRV_SOURCE_FETCH_TIMEOUT_SECONDS=12
BRV_SOURCE_MAX_DOWNLOAD_BYTES=4194304
BRV_SOURCE_FETCH_MAX_REDIRECTS=3

BRV_SECTION_ANALYSIS_MODEL=gemini-2.5-flash
BRV_FINAL_COHERENCE_MODEL=gemini-2.5-flash
```

Run ClaimTrace locally:

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.fast_api_app:app --reload
```

Open:

```text
http://127.0.0.1:8000/local/review
```

If Gemini configuration is missing, ClaimTrace stops at `awaiting_model_config` instead of pretending the live judge ran.

## Test And Eval Commands

Run the regular test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\unit tests\integration
```

Run the fixed-fixture eval with existing local source snapshots:

```powershell
.\.venv\Scripts\python.exe tests\eval\run_fixed_fixture_eval.py
```

Refresh source snapshots before replaying the fixed-fixture eval:

```powershell
.\.venv\Scripts\python.exe tests\eval\run_fixed_fixture_eval.py --refresh-source-fixtures
```

The fixture harness includes its small artificial report fixtures under `tests/eval/fixtures/seed_material`. Source snapshots and latest-run output still live under `tmp/` because they are generated/local validation artifacts.
