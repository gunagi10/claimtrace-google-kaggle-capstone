# Evaluation Summary

## Scope

This document summarizes what the current evaluation actually shows, beyond raw pass/fail counts.

The main reproducible evaluation for the capstone is the fixed-fixture harness:

```bash
python tests/eval/run_fixed_fixture_eval.py --refresh-source-fixtures
```

It runs three staged DOCX report fixtures with 15 cited-claim cases each, for 45 total cases, against the real batch review path using local source snapshots.

## Latest Full Fixed-Fixture Result

Latest full rerun on the current codebase:

- `42 / 45` passed
- classification accuracy: `93.3%`
- `0` false-support decisions
- each report: `14 / 15`

Current full-run artifact:

- `tmp/fixed-fixture-eval-results.json`

Important note:

- this file is a latest-run artifact, not a historical archive
- a later report-specific rerun can overwrite a previous full-run artifact

## What The Result Means

The strongest current evaluation signal is not just the `42 / 45` score. It is the combination of:

- high overall accuracy on the fixed 45-case set
- `0` false-support decisions
- correct handling of all expected `Contradicted`, `Unsupported`, and `Unverified` fixture cases

The remaining misses are conservative undercalls, not unsafe overclaims. In other words, the current system is more likely to say "not fully supported" when the evidence packet is weak or incomplete than to invent support that is not there.

That is an important capstone property because the product goal is evidence defensibility, not aggressive auto-approval.

## The Three Current Misses

### 1. Report 1 Claim 12

Expected:

- `Partially Supported`

Actual:

- `Unsupported`

What happened:

- the filing supports that Q1 net operating revenue increased
- but it does not support the stronger causal statement that U.S. concentrate operations drove the entire increase
- the current retrieval/evidence assembly did not present the "supported part plus unsupported overreach" clearly enough, so the case fell to `Unsupported`

What this means:

- mixed support inside dense filing/table-heavy evidence is still a weak spot

### 2. Report 2 Claim 2

Expected:

- `Supported by Cited Source`

Actual:

- `Partially Supported`

What happened:

- the claim uses `$75.246 billion`
- the retrieved source passage states `$75.2 billion, up 92%`
- the judge treated the rounded prose value and the more exact claim value as materially different instead of equivalent

What this means:

- rounded prose versus exact table precision is still a conservative undercall risk

### 3. Report 3 Claim 1

Expected:

- `Supported by Cited Source`

Actual:

- `Partially Supported`

What happened:

- the source really does support both `3.2%` headline CPI and `4.3%` food-purchased-from-stores inflation
- retrieval still selected correct CPI prose plus a bare `May 2026 4.3%` fragment
- it did not consistently select the richer subject-specific sentence needed for full support

What this means:

- statistics-style HTML with short same-number fragments remains a hard retrieval edge case

## What Is Working Well

- No false-support errors in the full 45-case rerun.
- All expected `Contradicted` fixture cases were correctly identified.
- All expected `Unsupported` fixture cases were correctly identified.
- All expected `Unverified` typo/broken-link cases stayed safely `Unverified`.
- Table-derived evidence is materially stronger than earlier checkpoints, including diluted-EPS-style row cases that now pass cleanly.

## Explanation Quality Notes

The current judge reasons are usually correct, but they are not always maximally disciplined.

Observed pattern:

- some supported cases include broader narrative gloss than the minimum evidence required for the claim

This is an explanation-quality limitation, not a verdict-safety failure. The underlying verdict can still be correct while the rationale is slightly more expansive than necessary.

## Current Limitations Supported By Eval

- Deterministic lexical retrieval still has a ceiling when support is split across dense filing prose, table notes, or heavily rephrased wording.
- Rounded prose values versus more exact table values can cause conservative undercalls.
- Statistics-style HTML pages can still over-rank generic same-number prose or isolated numeric fragments above the richer subject-specific sentence needed for full support.
- Multi-source citation clusters are still out of scope for one combined evidence decision.
- OCR-only or image-based documents remain unsupported.

## Practical Interpretation For The Capstone

The current evaluation result supports a careful claim:

- ClaimTrace is already strong at bounded quantitative evidence verification on fixed cited-source cases
- its current failure mode is conservative retrieval/coverage loss, not fabricated support
- the remaining gaps are specific and explainable, which makes them appropriate limitations for the writeup

## Suggested Writeup Line

Suggested short writeup wording:

> On the latest 45-case fixed-fixture evaluation, ClaimTrace classified 42 cases correctly (93.3%) with zero false-support decisions. The remaining errors were conservative undercalls rather than unsafe overclaims, with failures clustering around dense filing/table evidence, rounded prose versus exact table values, and statistics-style HTML pages where short numeric fragments can outrank richer subject-specific passages.
