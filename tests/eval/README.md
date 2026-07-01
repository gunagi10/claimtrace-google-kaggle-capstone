# Eval Notes

This folder contains the runnable evaluation harnesses for the capstone.

Project-facing interpretation of the latest results lives in:

- `docs/EVALUATION_SUMMARY.md`

This README stays focused on mechanics: what exists, how to run it, and where output lands.

## Current Eval Layers

- `run_first_slice_eval.py`: first-slice API-path eval
- `run_evidence_outcome_eval.py`: compact live ADK evidence-verdict eval
- `run_section_analysis_eval.py`: compact section-analysis eval
- `run_final_coherence_eval.py`: compact final-coherence eval
- `run_fixed_fixture_eval.py`: staged-report fixed-fixture harness over the real batch claim-review path

## Fixed-Fixture Harness

Prefer the lightweight fixed-fixture harness over a duplicate verifier or heavier platform.

Design goals:

- reuse the real claim-verification pipeline
- run against fixed local report fixtures
- compare expected vs actual verdicts
- save retrieved evidence and pass/fail output for inspection

Implemented shape:

- the answer key remains the expectation source of truth
- the three staged report `.docx` files remain the report-input source of truth
- small artificial report fixtures are tracked under `tests/eval/fixtures/seed_material/`
- local cited-source snapshots are cached under `tmp/fixed_fixture_sources/`
- the harness reuses the real batch review path instead of a simplified parallel implementation
- output is written to `tmp/fixed-fixture-eval-results.json`

This should stay lightweight:

- no duplicate simplified verifier
- no database
- no UI
- no cloud-only eval dependency

## Current Seed Materials

The staged seed materials live at:

- `tests/eval/fixtures/seed_material/BRV_Report_1_Coca_Cola_FPA_Performance_Review.docx`
- `tests/eval/fixtures/seed_material/BRV_Report_2_NVIDIA_IR_Earnings_Briefing.docx`
- `tests/eval/fixtures/seed_material/BRV_Report_3_Canadian_Grocery_Strategy_Snapshot.docx`
- `tests/eval/fixtures/seed_material/BRV_Test_Fixtures_Answer_Key.docx`

These are for reproducible evaluation work, not production runtime inputs.
The larger downloaded source snapshots remain local generated artifacts under `tmp/fixed_fixture_sources/`.

## Main Command

```bash
python tests/eval/run_fixed_fixture_eval.py --refresh-source-fixtures
```

What it does:

- parses the answer key and aligns it to the staged report fixtures
- refreshes local exact-source snapshots when requested
- runs the real batch review flow against those local source fixtures
- compares expected vs actual verdicts for all 45 staged claims
- saves inspectable case-level output, including retrieved candidate passages

Useful options:

- `--report-id 1`
- `--report-id 2`
- `--report-id 3`
- omit `--refresh-source-fixtures` to reuse the existing local snapshot cache

## Current Full-Run Reference

Latest verified full rerun on the current codebase:

- `42 / 45` passed
- `93.3%` accuracy
- `0` false-support decisions

See `docs/EVALUATION_SUMMARY.md` for the actual interpretation and failure analysis.

## Output Behavior

Current output path:

- `tmp/fixed-fixture-eval-results.json`

Important note:

- this is a latest-run artifact
- a later report-specific rerun can overwrite a previous full-run artifact

So if you run:

- full eval today
- then `--report-id 3` tomorrow

the later report-specific run will replace the earlier JSON unless historical snapshots are saved separately.
