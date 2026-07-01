# Testing Plan

This document defines how the work is verified: test commands, scenarios, regression checks, security/privacy checks, and known testing gaps.

## 1. Test Commands

```bash
python -m pytest tests/unit tests/integration
python tests/eval/run_fixed_fixture_eval.py --refresh-source-fixtures
```

Current local status (2026-06-28):
- `python -m pytest tests/unit tests/integration` -> `106 passed, 9 warnings`
- latest full fixed-fixture replay: `42 / 45` passed, `0` false supports
- report-3-only rerun with the dead proxy cleared and Gemini traffic allowed to run: `14 / 15` passed, `0` false supports

## 2. Automated Tests

| Area | Test Needed | Status |
|---|---|---|
| DOCX intake | Reject invalid DOCX packages and missing References/Bibliography structure on the slice fixture path | implemented |
| Sentence boundaries | Preserve decimals and common dotted terms instead of splitting claims at every period | implemented |
| Citation direction | Attach clear markers deterministically and require previous/next/both confirmation for boundary ambiguity | implemented |
| Citation scope | Keep the anchor plus at most two preceding same-paragraph sentences; following text stays context only | implemented |
| Citation mapping | Preserve exact cited sentence, paragraph/section location, citation marker, and mapped bibliography entry | implemented |
| HTML extraction | Convert cited HTML bytes into normalized inspectable text blocks with stable locators, including meaningful leaf-like modern-layout prose containers and narrow clean-table row linearization for filing-style HTML | implemented |
| Text-PDF extraction | Convert cited text-layer PDF bytes into page-based text blocks | implemented |
| Text-PDF hybrid table extraction | Preserve ordinary PDF prose while emitting additional conservative table-row blocks when layout text clearly exposes table-like rows | implemented in working tree |
| OCR-required PDF handling | Return explicit `ocr_required` for PDFs without a usable text layer | implemented |
| Passage retrieval | Return traceable candidate passages and rank them deterministically from extracted source text | implemented |
| Evidence payload assembly | Build a bounded evidence-review payload from approved claim plus ranked passages | implemented |
| Pre-judge unverified handling | Short-circuit to explicit `Unverified` when extraction/retrieval already makes judgment impossible | implemented |
| Deterministic review orchestration | Run extraction, ranking, and pre-judge assembly end to end for one claim/source pair | implemented |
| Gemini placeholder guard | Refuse the live judge when `.env` still contains placeholders | implemented |
| ADK judgment seam | Execute prepared evidence through Agent, Runner, Session, and final Event; validate schema and filter unknown passage IDs | implemented |
| Exact-source fetch guard | Fetch supported public cited sources, block unsafe hosts, and fail cleanly on fetch errors | implemented |
| Browser-rendered source fallback | Retry public HTML after HTTP 403 or timeout-like exact-fetch failure in an isolated browser, retain main content, and preserve audit method | implemented |
| Generic anchor retrieval | Preserve decimals, derive anchors from the claim, rank compact seeds first, then expand selected seeds into bounded adjacent context | implemented |
| Local browser shell | Serve the first-slice page and keep it wired to prepare/run contracts | implemented |
| Sequential multi-claim batch path | Run selected sentence/reference pairs through the batch contract and preserve per-item statuses | implemented |
| Evidence result contract | Store verdict, reason, source status, passage locators, and recommended action without mixing status fields | implemented for first slice |
| Product execution audit | Preserve approved claim/source provenance, stopping stage, extraction/retrieval counts, candidate passages, and model-called status in every review outcome | implemented |
| Post-evidence gate | Derive a deterministic stop/continue recommendation from checked evidence outcomes without hiding claim detail | implemented |
| Section packet builder | Exclude reference sections, keep section-scoped claim outcomes, and deterministically subchunk oversized sections | implemented |
| Section worker seam | Execute one tool-free ADK section worker per packet and preserve structured section output | implemented |
| Final coherence packet builder | Preserve gate state and compact section digests while avoiding raw whole-report text by default | implemented |
| Final coherence worker seam | Execute one tool-free final ADK worker only after section analysis is complete | implemented |
| Quantitative-business retrieval policy | Verify deterministic handling of entity, metric, period, unit/currency, direction, scope, contradiction, and qualifier cases for the narrowed domain | implemented |
| Retriever hardening follow-up | Verify diversity backfill, atomic structured table rows, neutral fallback phrase mismatches, and occurrence-level period-year handling | implemented |
| Fragment-control plus identity follow-up | Verify general fragment demotion, conservative subject-overlap bonus, and protection for structured table rows | implemented |
| Fixed-fixture harness support | Parse the staged answer key, align it to the staged report fixtures, and serve local exact-source snapshots into the real batch review route | implemented |

## 3. Acceptance Criteria / Validation

| Requirement | Validation Method | Status |
|---|---|---|
| One supported DOCX fixture reaches claim approval with exact citation provenance preserved | Deterministic integration test plus fixture inspection | implemented |
| After approval, the system checks only the exact cited source or explicit uploaded fallback and does not search for alternatives | Integration test and trace inspection | implemented |
| Passage selection is deterministic and returns inspectable locators | Deterministic tests with expected ranked passages | implemented |
| Retrieval/access failure becomes `Unverified`, never `Unsupported` or `Contradicted` | Deterministic tests | implemented |
| The result view shows claim, verdict/source status, reason, and warnings without hiding the critical state | Browser-shell route test plus manual UI check after the quoting fix | implemented |
| The result view explains whether failure occurred during fetch, extraction, retrieval, model configuration, or completed judgment | Integration tests plus Microsoft HTTP 403 fixture replay | implemented |
| The live evidence judge returns one of the five evidence outcomes with a reason and next action | ADK seam tests plus real-example live checks | implemented and re-confirmed with the five-case eval |
| Section analysis runs only on eligible sections and returns grounded structured section results | Unit/integration tests plus compact local section-analysis eval | implemented |
| Final coherence runs only after completed section analysis and returns bounded report-level findings | Unit/integration tests plus compact local final-coherence eval | implemented |
| The narrowed quantitative-business retriever contract does not pretend to support OCR, PDF/scanned table reconstruction, or semantic paraphrase retrieval | Doc/test contract plus targeted deterministic cases | implemented |
| The staged fixed-fixture harness reuses the real batch review flow and preserves expected verdicts, actual verdicts, and retrieved evidence for inspection | Harness parser/unit coverage plus local replay command | implemented |

## 3A. Minimum Evaluation Contract

The evidence layer has cleared this gate through deterministic checks, two real Microsoft cases, and the compact five-case multi-verdict eval.

| Category | Required evidence | Pass rule |
|---|---|---|
| Deterministic provenance | One end-to-end fixture keeps report location, citation, reference, claim ID, and source/passage IDs linked | 100% |
| Safety/provenance failure handling | Bad extraction or weak retrieval coverage never produce a false supported-style verdict | 100% |
| Evidence classification | Compact eval set on the slice path | passed 5 of 5 cases |
| High-impact safety | No case labeled high-impact may be falsely marked `Supported by Cited Source` | passed 100%; zero false support |
| User checkpoint | Claim approval pause is reachable and auditable before evidence review starts | 100% |

Current compact ADK evidence eval (2026-06-22): 5/5 correct, zero false support,
6.575 seconds, and 5,012 total tokens.

## 3B. Slice 2 Validation Contract

| Requirement | Validation | Pass rule |
|---|---|---|
| Confirmation gate | API/UI test proves no source or model work starts before confirmation | 100% |
| Source reuse | Two or more claims sharing one source trigger one fetch and one extraction | 100% |
| Claim isolation | Shared source text produces separate ranked passages, verdicts, and traces per claim | 100% |
| Failure isolation | One failed source does not stop claims linked to other sources | 100% |
| Recovery targeting | Uploaded exact-source copy retries only unresolved claims linked to that source | 100% |
| Attention filtering | Only failed unique sources appear under `Sources needing attention` | 100% |
| Coverage | Selected, completed, unresolved, deselected, verdict, and failed-source counts agree with item results | 100% |
| Regression | Existing unit/integration suite remains green; semantic eval is replaced for the five-verdict contract | 100% |

Final live check is user-run and monitored: at least two claims share one source,
plus one failed-source upload/retry case.

## 3C. Retrieval V2 Validation Contract

| Requirement | Validation | Pass rule |
|---|---|---|
| Five verdicts | Runtime schema, judge instructions, eval data, and results contain only the approved five verdicts | 100% |
| Partial explanation | Every Partially Supported reason names verified and missing/conflicting material parts | 100% |
| Central precedence | Wrong central number, direction, period, or fact becomes Contradicted | 100% |
| Anchor recall | BLS-style `147,000`, June 2025, and nonfarm-payroll anchors retrieve the decisive passage | 100% |
| Qualifier coverage | Material scope qualifiers receive dedicated evidence candidates where matches exist | 100% |
| Boilerplate resistance | Technical notes/definitions cannot displace stronger exact anchor matches | 100% |
| Bounded packet | Return up to five meaningful traceable passages with no filler | 100% |
| Safety | Weak access/extraction/coverage remains Unverified; no false Supported verdict | 100% |

## 3D. Gate Validation Contract

| Requirement | Validation | Pass rule |
|---|---|---|
| Contradiction stop | Any checked `Contradicted` claim produces a stop-and-fix gate recommendation | 100% |
| Warning-only continue | Unsupported-only and unverified-only checked results stay visible as warnings without a contradiction stop | 100% |
| Incomplete review protection | Selected claims with no evidence outcome yet produce `review_incomplete` rather than a false continue signal | 100% |
| UI visibility | The local batch result view shows the gate summary without hiding claim-level evidence detail | 100% |

## 3E. Section Analysis Validation Contract

| Requirement | Validation | Pass rule |
|---|---|---|
| Section eligibility | Reference/bibliography sections are excluded from section-worker input | 100% |
| Deterministic packet | Each eligible section gets one inspectable packet with stable IDs/order and section-scoped claim outcomes | 100% |
| Oversized section handling | Large sections are deterministically subchunked instead of being sent whole | 100% |
| Worker isolation | One section worker receives one packet, no tools, and no raw whole-report sprawl | 100% |
| Parallel section execution | Multiple section workers can run in bounded parallelism without re-fetching evidence or recomputing claim verdicts | 100% |
| Grounded output | Section findings preserve contradicted/unverified evidence state and do not smooth it into generic summary language | 100% |

Compact local section-analysis eval (2026-06-22): 2/2 cases passed in
4.744 seconds using the live tool-free ADK section worker.

## 3F. Final Coherence Validation Contract

| Requirement | Validation | Pass rule |
|---|---|---|
| Final prerequisite | Final coherence blocks until section analysis has completed successfully | 100% |
| Bounded report packet | Final packet preserves gate state and section digests without raw whole-report text by default | 100% |
| Evidence preservation | Final output keeps contradictions, unsupported findings, and unverified risks visible | 100% |
| Cross-section insight | Final output adds report-level patterns or priority actions rather than restating only one section | 100% |
| No re-judging | Final coherence does not re-fetch sources or recompute claim/section judgments | 100% |

Compact local final-coherence eval (2026-06-22): 2/2 cases passed in
5.223 seconds using the live tool-free ADK final worker.

## 3G. Quantitative-Business Retrieval Validation Contract

| Requirement | Validation | Pass rule |
|---|---|---|
| Domain focus | Retrieval rules are framed for quantitative business-performance, market-statistics, and official economic-release claims | 100% |
| Hybrid metric matching | Known metrics match deterministically; niche metrics can still match through exact-phrase fallback without semantic expansion | 100% |
| Period safety | Finance-style period flexibility improves recall without silently inventing quarter/year mappings | 100% |
| Conservative scope | Company-wide claims are not casually supported by narrowed segment/product/geography evidence | 100% |
| Conservative units | Unit normalization does not create fake agreement across materially different business/population concepts | 100% |
| Contradiction retention | Same-entity/same-metric conflict evidence can remain in the candidate set for Gemini to judge | 100% |
| Explicit non-goals | OCR, PDF/scanned table reconstruction, embeddings, and semantic paraphrase retrieval remain out of scope | 100% |

Current deterministic retriever verification (2026-06-24): targeted retriever suite `13/13`
green, targeted orchestrator suite `3/3` green, and full `tests/unit tests/integration`
regression `81/81` green after the domain-specialized retriever swap.

Current alias-pass verification (2026-06-26): targeted retriever suite `18/18`
green, targeted orchestrator suite `3/3` green, and full `tests/unit tests/integration`
regression `86/86` green after the conservative filing-language alias pass.

Current narrow HTML-table verification (2026-06-26): targeted source-adapter and retriever
suite `27/27` green, and full `tests/unit tests/integration` regression `90/90`
green after adding clean HTML table row extraction plus a table-backed EPS retrieval proof.

Current stacked-header HTML-table verification (2026-06-26): targeted source-adapter and
retriever suite `29/29` green, and full `tests/unit tests/integration` regression `92/92`
green after preserving stacked header context in the visible row evidence trace.

Current fixed-fixture harness support verification (2026-06-26): focused support suite
`4/4` green, full `tests/unit tests/integration` regression `96/96` green, and the live
replay command is now available at `python tests/eval/run_fixed_fixture_eval.py --refresh-source-fixtures`.

Current working-tree hardening verification (2026-06-28): the standard
`tests/unit tests/integration` command now runs without backup-folder collection
collisions and is green at `106/106`.

Current latest full fixed-fixture replay (2026-06-28): `42 / 45` passed,
classification accuracy `0.9333`, zero false supports, and gate failed. The remaining
misses are no longer dominated by source-access breakage. They now cluster around three
conservative undercalls: one dense filing partial-support case, one rounded-prose
versus exact-value case, and one Statistics Canada retrieval-fragment case.

Current HTML/web-source fix verification (2026-06-28): targeted source-adapter plus
agent coverage `32/32` green, full `tests/unit tests/integration` regression `106/106`
green, saved NVIDIA/Q4 fixture extraction now emits readable blocks through the normal
adapter path, timeout-style fallback is covered by integration tests, and the refreshed
full fixed-fixture replay is now complete.

Current Statistics Canada retrieval verification (2026-06-28): report 3 now completes
through the existing code at `14/15` with zero false supports when the dead local proxy
is cleared and Gemini traffic is allowed to run. The fresh-vegetables miss is now fixed:
the richer source sentence reaches the top-five evidence set again. One remaining miss is
still not an access failure: for the `food purchased from stores` claim, generic CPI prose
and a bare `May 2026 4.3%` fragment still outrank the richer nearby subject-specific
sentence in the current lexical scorer.

Current fragment/identity bucket verification (2026-06-28): focused retriever suite
`27/27` green, full `tests/unit tests/integration` regression `106/106` green, and the
report-3-only replay improved from `13/15` to `14/15` with zero false supports.

## 4. Manual Test Cases

| Scenario | Steps | Expected Result | Status |
|---|---|---|---|
| Happy path | Parse the supported slice fixture through deterministic intake | Traceable sections, citations, references, and claim-ready sentence records are produced | implemented |
| Invalid input | Parse non-DOCX bytes or a DOCX missing required citation/reference structure | Intake raises a plain-language validation error | implemented |
| OCR-only PDF | Run the review with an image-only PDF | The result is `prejudge_unverified` with `ocr_required` | implemented |
| Placeholder key | Run the review with an HTML source while `.env` still contains placeholders | The result is `awaiting_model_config` and no live model call is attempted | implemented |
| Exact-source fetch | Run the review without uploading a source file | The route fetches the cited source when allowed, or returns explicit `Unverified` on blocked fetch | implemented |
| Browser shell | Open `/local/review`, prepare one DOCX, choose one sentence/reference pair, and run automatic source access | Page loads, form progression works, and result states are visible | implemented |
| Source-access recovery | Force automatic source access to fail | Source upload appears only after the failure and can be used for recovery | implemented |
| Repeat failed-source retry | Upload a wrong or unusable exact-source copy, then try to upload a corrected copy | The upload affordance should remain available until recovery succeeds | known gap |
| Batch review | Open `/local/review`, select multiple prepared claims, and run the sequential batch path | Batch summary and per-item statuses are visible and inspectable | implemented |
| Post-evidence gate | Run a batch with at least one contradicted claim, then another with only unsupported/unverified findings | The gate summary stops the first and warns-only on the second | implemented at the response/UI seam; broader live product run pending |
| Slice 2 source reuse | Select at least two claims citing the same source | The source is fetched/extracted once; each claim has separate evidence and verdict | implemented; automated and user-run on a six-claim batch |
| Slice 2 attention recovery | Let one unique source fail, finish unrelated claims, then upload an exact source copy | Only the failed source appears; only its unresolved linked claims retry | implemented; automated, manual pending |
| Statistics Canada PDF recovery | Upload the 20-page text PDF after webpage SSL timeout | Exact uploaded copy completes judgment; `88,000` is supported while the broad-scope qualifier is not | implemented; manually observed |
| BLS long-page retrieval | Check the June 2025 `147,000` nonfarm-payroll claim against the archived release | Decisive release passage outranks technical notes | implemented; live retest passed after `<pre>` extraction fix |
| Clean HTML filing table | Check a filing-style HTML table where the key metric appears in a row with period headers | The row becomes an inspectable text block and the claim can match it deterministically | implemented in deterministic tests; live public-source validation pending |
| Stacked HTML filing header | Check a filing-style HTML table where category headers and date headers are split across two header rows | The visible evidence trace preserves the nearest combined header context for each value column | implemented in deterministic tests; live public-source validation pending |
| Fixed-fixture verdict replay | Refresh the local source snapshot cache, then run the 45 staged claims through the real batch review route | Expected vs actual verdicts, reasons, and candidate passages are saved to `tmp/fixed-fixture-eval-results.json` | implemented; live run should be executed from the local machine when network/model access is available |
| Statistics Canada report-3 rerun | Re-run only report 3 with local fixtures, a cleared dead proxy, and working Gemini access | The run completes and isolates only true retrieval/judgment misses | implemented; current result `14/15` |
| NVIDIA/Q4 saved HTML extraction | Run the HTML adapter on a saved fetched NVIDIA IR page that visibly contains prose and tables | The adapter emits readable blocks instead of `empty_html_text` | implemented on the saved fixture path |
| DORA-style HTML extraction | Check a cited page whose substantive prose lives in modern layout containers such as `div`/`section` under `Abstract` | Meaningful prose is extracted with inherited heading context when the page structure cooperates | not yet confirmed end to end |
| Real cited-source verification | Run public examples without uploaded fallback and compare the verdict against the cited page | The Microsoft supported and contradicted cases pass; broader domains remain an eval gap | partially implemented |
| Microsoft FY2025/Q3 real-page check | Run both exact URLs through automatic browser fallback and the live judge | `[1]` supported; `[2]` contradicted with 13% reported versus 15% constant-currency explanation | implemented |

## 5. Error Handling Checks

- [x] Errors are understandable.
- [x] The app/script does not fail silently.
- [x] Invalid input is handled safely.
- [x] The user knows what to fix.

## 6. Security and Privacy Checks

- [x] No secrets are committed.
- [x] External services are documented.
- [x] User data handling is clear at the current local-first scope.
- [ ] Sensitive data is not logged unnecessarily.

## 7. Regression Checks

- [x] The local browser shell still requires a successful prepare step before the run form is usable.
- [x] Exact-source-only checking remains enforced through exact cited-source fetch or explicit uploaded source copies.
- [x] `citation_status`, `source_status`, and `evidence_verdict` remain separate.
- [x] Deterministic DOCX intake still preserves section/paragraph/sentence provenance and numbered-citation mapping.
- [x] Decimal values remain intact and ambiguous boundary citations cannot run without direction confirmation.
- [x] HTML and text-PDF source extraction still produce inspectable locators, and OCR-only PDFs still fail explicitly.
- [x] Narrow clean-HTML financial tables can now become inspectable row evidence blocks without duplicating nearby prose.
- [x] Clean stacked HTML headers can now stay attached to their corresponding value columns in the visible evidence trace.
- [x] The staged answer key and staged reports now align again for the fixed-fixture harness.
- [x] Deterministic passage ranking still returns traceable candidate passages and ignores low-signal blocks.
- [x] Pre-judge evidence assembly still preserves claim/source/passage provenance and short-circuits obvious `Unverified` cases before model use.
- [x] Deterministic one-claim/one-source orchestration still returns either pre-judge `Unverified` or a judge payload without invoking Gemini.
- [x] Placeholder `.env` configuration still blocks live Gemini calls cleanly instead of attempting a network verdict.
- [x] Prepared evidence reaches the model only through the tool-free ADK judge; parsing, source access, extraction, and ranking remain deterministic.
- [x] Single and batch outcomes preserve the same execution-audit contract without adding persistent report/source logging.
- [x] Multi-claim source grouping reuses extraction without sharing claim-specific passage rankings.
- [x] Failed-source recovery retries only unresolved claims linked to the uploaded exact source copy.
- [x] The batch response now preserves a deterministic gate recommendation derived from evidence outcomes.
- [x] Section packets remain deterministic and section-scoped after the section-analysis slice.
- [x] Final coherence now depends on stored section-analysis outputs instead of recomputing earlier stages.

## 8. Known Testing Gaps

- [x] Live source fetching is implemented only for the exact cited source; deterministic tests use synthetic responses and the Microsoft replay exercises the real browser path.
- [x] Manual UI wiring has now been exercised enough to catch and fix a browser-side script regression.
- [ ] Real public-source verification still needs broader multi-domain evaluation beyond the Microsoft, Statistics Canada, and BLS checks exercised so far.
- [x] Failed-source recovery now keeps the retry affordance visible so the user can recover from a wrong uploaded file.
- [x] Microsoft HTTP 403 responses now fall back to isolated browser rendering; `[1]` and `[2]` both complete with the expected live verdicts.
- [x] Multi-source concurrency is now in scope and implemented with bounded worker overlap.
- [x] Section-analysis behavior is now implemented and locally eval'd with a compact live contract.
- [x] Final coherence analysis is now implemented and locally eval'd with a compact live contract.
- [ ] End-to-end dashboard and PDF audit rendering are out of scope for this slice.
- [ ] Visual-review behavior is deferred and not part of the active quantitative-business MVP.