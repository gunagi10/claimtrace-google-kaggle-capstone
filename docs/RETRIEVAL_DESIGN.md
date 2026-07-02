# Retrieval Design

ClaimTrace uses retrieval before Gemini because cited sources are often long, noisy, and expensive to send to a model whole. The goal is not to make Gemini read everything. The goal is to use deterministic code to narrow each cited source into a small, inspectable evidence packet, then ask Gemini to judge only what remains.

In plain terms:

- deterministic code handles parsing, source access, extraction, chunking, scoring, and stopping rules
- Gemini handles the final evidence judgment after the packet is bounded
- the trace keeps enough detail to explain why the model saw those passages
- failures stay visible instead of being hidden behind a confident answer

This is the main engineering tradeoff in the project. Even as a vibe-coding capstone, token cost, source noise, and auditability still matter.

## Pipeline

```text
DOCX report
  -> claim and citation parsing
  -> exact cited-source fetch
  -> HTML/PDF source extraction
  -> source blocks
  -> candidate passage chunking
  -> anchor extraction
  -> scoring and ranking
  -> up to 5 diverse evidence passages
  -> Gemini/ADK evidence judgment
  -> trace, section review, final coherence
```

## Design Decisions Worth Noticing

These are the main retrieval choices that shaped the implementation:

- Exact cited source first. ClaimTrace checks the source the report cited, not a better source found later through search.
- Deterministic before nondeterministic. Python handles parsing, fetching, extraction, chunking, scoring, source grouping, and stopping rules before Gemini sees anything.
- Seed first, then expand. The retriever scores compact evidence units before expanding selected passages into bounded nearby context. This keeps the model packet small without losing qualifier sentences.
- Up to five meaningful passages. The packet is allowed to include more than one passage so contradiction, qualifier, and partial-support evidence can survive, but it is still capped to avoid source dumps.
- Quantitative-business anchors. The retriever is tuned around numbers, units, periods, business metrics, entities, direction, scope, and qualifiers because those are the common failure points in business reports.
- Topic around the number matters. A bare `4.3%` is not automatically better than a fuller sentence explaining what the 4.3% measures.
- Contradiction evidence stays eligible. The retriever should not filter only for support; it must keep materially conflicting evidence when the central identity overlaps.
- Table rows are evidence units when safe. Clean HTML filing tables and conservative text-PDF row shapes can become traceable rows, but the project does not claim general table reconstruction.
- No publisher-specific bandaids. Fixes are meant to be general retrieval/extraction rules, not special rules for one Statistics Canada, NVIDIA, BLS, DORA, or demo fixture page.
- No semantic shortcut in this MVP. Embeddings, fuzzy matching, and broad paraphrase retrieval are intentionally out of scope so the behavior stays inspectable and easy to evaluate.

## 1. Claim And Citation Parsing

Relevant files:

- `app/docx_intake.py`
- `app/review_models.py`

What it does:

- reads `.docx` report bytes
- finds sections, paragraphs, sentences, and numbered citations
- maps citation labels such as `[1]` to bibliography entries
- produces claim-ready sentences instead of sending the whole report forward
- preserves provenance through section IDs, paragraph IDs, sentence IDs, citation IDs, and reference IDs
- avoids common sentence-splitting mistakes around decimals and dotted terms
- flags ambiguous citation direction when a citation could refer backward, forward, or both

Key functions and models:

- `parse_docx_bytes`: converts a report upload into a structured parsed document.
- `ClaimReadySentence`: stores one reviewable cited sentence plus provenance.
- `ReferenceEntry`: stores one bibliography entry and its canonical URL.
- `ParsedDocument`: stores the sections, references, warnings, and claim-ready sentences.

Deliberate choice:

- ClaimTrace does not ask Gemini to find claims in an unstructured report. It first creates a deterministic claim/reference map so the user can approve what will be checked.

## 2. Exact Source Fetching

Relevant files:

- `app/source_fetcher.py`
- `app/review_api.py`

What it does:

- fetches only the exact cited URL
- blocks unsafe targets such as loopback, private, link-local, or unresolvable hosts
- applies timeout, redirect, and download-size limits
- supports public HTML and text-layer PDF sources
- can use isolated browser rendering for some public HTML failures
- groups selected claims by source so a batch review fetches each cited source once

Key functions:

- `fetch_exact_source`: fetches the cited source through the normal safe HTTP path.
- `fetch_rendered_exact_source`: uses isolated browser rendering when configured and appropriate.
- `should_try_browser_fallback`: decides whether a failed public HTML fetch deserves a browser retry.
- `_run_source_groups_with_bounded_concurrency`: runs source groups with up to five source workers.
- `_run_single_source_group`: fetches and extracts one source, then runs its linked claims against it.

Deliberate choice:

- The app does not search the web for a better source. A citation review should test the source the report actually cited.

## 3. Source Extraction

Relevant files:

- `app/source_adapters.py`
- `app/review_models.py`

What it does:

- converts fetched HTML or PDF bytes into normalized `SourceTextBlock` records
- keeps locator details such as heading, page number, and text span labels
- extracts meaningful prose from modern HTML containers such as `div`, `section`, `article`, and `dd`
- emits narrow table-row evidence blocks for clean HTML tables
- preserves stacked table headers when the HTML exposes them clearly
- preserves normal PDF prose while adding conservative row-like table blocks when layout text makes that safe
- returns explicit extraction status instead of pretending OCR-only PDFs are readable

Key functions and models:

- `extract_source_document`: routes a source payload to the right adapter.
- `ExtractedSourceDocument`: stores the extracted source record, blocks, and warnings.
- `SourceTextBlock`: stores one traceable unit of source text.
- `_extract_table_like_blocks`: creates conservative row-level PDF table evidence when layout text supports it.
- `_build_table_row_texts`: converts clean HTML tables into row-level text with header context.
- `_linearize_table_row`: turns one table row into readable evidence text.

Deliberate choice:

- ClaimTrace tries to preserve useful table context, but it does not claim general table reconstruction. If the source is too visual or OCR-only, the safer outcome is `unverified`.

## 4. Passage Chunking

Relevant file:

- `app/passage_retriever.py`

What it does:

- turns extracted source blocks into bounded evidence passages
- splits prose into sentence-safe chunks
- keeps nearby sentence overlap when context spans a boundary
- creates boundary-window passages for adjacent prose blocks that share context
- keeps structured table rows atomic so they do not become misleading hybrids
- caps the evidence packet so Gemini does not receive the whole source

Key functions:

- `retrieve_candidate_passages`: public entry point that returns up to five evidence passages.
- `_chunk_blocks`: turns source blocks into candidate passages.
- `_chunk_single_block`: splits one prose block into sentence-safe chunks.
- `_build_passage`: creates one traceable passage from one block.
- `_build_window_passage`: creates one bounded passage across adjacent prose blocks.
- `_is_structured_table_row_block`: detects adapter-produced table rows that should stay atomic.

Deliberate choice:

- Chunking is not just about length. It protects context. For example, table rows are already compact evidence records, while prose sometimes needs one neighboring sentence to remain understandable.

## 5. Anchor Extraction

Relevant file:

- `app/passage_retriever.py`

What it does:

- extracts structured signals from both the claim and candidate passages
- normalizes numbers, magnitudes, units, and currencies
- extracts dates, months, years, quarters, and fiscal years
- detects known business metrics and fallback metric phrases
- detects entities, direction words, scope language, and qualifiers
- keeps keywords as a very low-weight fallback rather than the main scoring signal

Key functions and models:

- `_anchors`: builds the full anchor set for a text span.
- `_number_anchors`: normalizes numbers, magnitudes, units, and currencies.
- `_dates`: extracts month, year, quarter, and fiscal-year signals.
- `_metrics`: matches known safe business metric phrases.
- `_metric_phrase_fallbacks`: keeps niche metrics discoverable without making them canonical identities.
- `_entities`: extracts capitalized entity-style phrases.
- `_directions`: detects increase, decrease, and stable language.
- `_scopes`: detects total-company, geography, segment, industry, and universal scope signals.
- `_qualifiers`: detects qualifiers such as adjusted, organic, non-GAAP, seasonally adjusted, preliminary, forecast, and revised.

Deliberate choice:

- ClaimTrace does not rank passages by generic keyword overlap alone. A passage with the right number but the wrong topic can be worse than a passage with slightly fewer numeric matches but the right metric, entity, period, and scope.

## 6. Scoring System

Relevant file:

- `app/passage_retriever.py`

Main scoring weights:

| Anchor type | Weight |
|---|---:|
| number with unit | 11.0 |
| metric | 10.0 |
| number | 9.0 |
| date | 8.0 |
| metric phrase | 8.0 |
| entity | 6.0 |
| scope | 6.0 |
| qualifier | 6.0 |
| direction | 5.0 |
| currency | 4.0 |
| direction conflict | 4.0 |
| number conflict | 4.0 |
| qualifier context | 3.0 |
| keyword | 0.3 |

Other scoring features:

- a passage must have central overlap before it can score meaningfully
- material coverage gets a small breadth bonus, capped at 7.0
- matching local context keywords and entities can help, but do not dominate
- headings such as summary, key findings, overview, or results can receive small boosts
- boilerplate sections such as technical notes, definitions, methodology, and footnotes are penalized
- boilerplate penalty is reduced when the passage still has central evidence overlap

Key functions:

- `_score_candidate`: scores one candidate passage against the claim.
- `_matching_coverage`: records which anchors match between claim and passage.
- `_coverage_weight`: maps an anchor to its point value.
- `_heading_priority_boost`: gives small help to useful source headings.
- `_boilerplate_penalty`: demotes technical-note and methodology-style content.

Deliberate choice:

- Numbers are important, but they are not enough. The scoring system also rewards the topic around the number: metric, period, entity, scope, direction, and qualifiers. This is why the retriever tries to promote richer subject-specific sentences over bare numeric fragments.

Penalty and bonus details:

| Rule | Effect |
|---|---:|
| canonical metric mismatch | -10.0 |
| quarter mismatch | -10.0 |
| month mismatch | -9.0 |
| fiscal-year mismatch | -8.0 |
| year mismatch | -6.0 |
| currency mismatch | -10.0 |
| total-company claim vs narrowed evidence | -10.0 |
| universal claim vs segment/geography/narrowed evidence | -8.0 |
| high-signal summary/findings heading | +6.0 |
| overview/introduction/results heading | +2.0 |
| identity overlap, two or more terms | +2.5 per term, capped at +6.0 |
| single identity overlap for single-term claim identity | +1.5 |
| bare numeric fragment when a richer nearby passage tells the same story | -6.0 base, with small extra penalties for weaker identity/material coverage |

Why this matters:

- The point system is deliberately asymmetric. Strong central matches can pull evidence up, but dangerous mismatches in metric, period, currency, or scope can push tempting passages down.
- Fallback metric phrases are discovery hints, not hard identities. If a niche phrase changes word order, ClaimTrace avoids turning that absence into negative evidence too early.
- Identity overlap is a bonus, not a hard filter. That helps topic-specific sentences rise without blocking contradiction evidence that may use different wording.

## 7. Mismatch Penalties And Contradiction Retention

Relevant file:

- `app/passage_retriever.py`

What it does:

- penalizes known canonical metric mismatches
- penalizes period mismatches, with stricter penalties for months and quarters
- penalizes currency mismatch
- penalizes narrow segment/geography evidence when the claim is total-company or universal
- keeps potential contradiction evidence in the candidate set when it shares central identity with the claim

Key functions:

- `_metric_mismatch_penalty`: penalizes known metric conflicts while keeping fallback phrase uncertainty neutral.
- `_period_mismatch_penalty`: penalizes wrong period evidence.
- `_currency_mismatch_penalty`: penalizes mismatched currencies.
- `_scope_mismatch_penalty`: penalizes narrow evidence for broad claims.
- `_has_direction_conflict`: detects a direction conflict when central evidence overlaps.
- `_has_number_conflict`: detects a numeric conflict with shared identity, date, metric, or unit family.

Deliberate choice:

- The retriever should not only find supporting passages. It should also keep conflicting passages when they are relevant, because Gemini needs to see conflicts to choose `contradicted` or `partially_supported`.

## 8. Diversity, Identity, And Fragment Control

Relevant file:

- `app/passage_retriever.py`

What it does:

- selects up to five useful passages
- avoids near-duplicate passages
- favors new material that adds non-keyword evidence coverage
- backfills positive-score passages if diversity filtering leaves unused slots
- gives a conservative bonus when a passage shares meaningful subject identity with the claim
- demotes ultra-short numeric fragments when a nearby richer passage tells the same number/date/unit story
- protects structured table rows from being treated as weak numeric fragments

Key functions:

- `_select_diverse_passages`: chooses the final evidence packet.
- `_is_near_duplicate`: prevents the packet from being filled with repeated versions of the same text.
- `_apply_identity_and_fragment_adjustments`: applies subject-overlap bonuses and fragment penalties.
- `_identity_bonus`: rewards meaningful subject overlap with the claim.
- `_fragment_penalty`: demotes bare numeric fragments when richer nearby evidence is available.
- `_is_fragment_like_candidate`: identifies short number/date-only fragments.
- `_shares_fragment_story`: checks whether a fragment and richer passage are about the same numeric story.

Deliberate choice:

- A source page can contain fragments like `May 2026` and `4.3%` that match the claim numerically but do not explain the claim. ClaimTrace tries to prefer the richer sentence that says what the number is about, such as food purchased from stores or fresh vegetables.

## 9. Evidence Packet Assembly

Relevant files:

- `app/review_orchestrator.py`
- `app/evidence_input.py`
- `app/review_models.py`

What it does:

- runs the deterministic source-document review path
- retrieves candidate passages
- short-circuits to `unverified` when source access, extraction, or retrieval is too weak
- builds the bounded payload that Gemini sees
- keeps claim, source, and passage provenance together

Key functions and models:

- `run_deterministic_evidence_review_from_document`: turns one claim plus one extracted source into either a pre-judge assessment or a judge payload.
- `EvidenceReviewPayload`: the small evidence packet sent to Gemini.
- `EvidenceAssessment`: the structured result returned after judgment.
- `EvidenceVerdict`: the fixed verdict taxonomy.

Deliberate choice:

- Gemini does not receive raw whole-source text. It receives a bounded packet with the approved claim, source metadata, source status, warnings, and selected evidence passages.

## 10. Gemini Judgment After Retrieval

Relevant files:

- `app/agent.py`
- `app/evidence_judge.py`

What it does:

- runs a tool-free Google ADK evidence judge
- uses Gemini only after deterministic retrieval has selected the evidence packet
- keeps temperature at `0`
- validates the output against a schema
- filters returned passage IDs so the judge cannot cite passages that were not in the packet

Key functions:

- `root_agent`: defines the ADK evidence judge instruction and model settings.
- `judge_evidence_payload`: runs the judge and returns a validated evidence assessment.
- `_run_judge_agent`: creates the ADK runner/session and collects the final model event.
- `_build_prompt`: formats the bounded evidence packet for the judge.

Deliberate choice:

- The model is used for semantic judgment, not for source discovery, source parsing, or uncontrolled browsing.

## 11. Batch Source Reuse And Traceability

Relevant file:

- `app/review_api.py`

What it does:

- groups selected claims by cited source
- fetches and extracts each unique source once
- runs claim-specific retrieval and judgment separately
- lets unrelated claims continue when one source fails
- stores enough review context for section analysis and final coherence
- returns a trace with source method, fetch status, extraction status, candidate passage count, stopped stage, and model-called flag

Key functions and models:

- `run_batch_claim_review`: batch entry point for selected claim/reference pairs.
- `_run_source_groups_with_bounded_concurrency`: runs grouped sources with bounded parallelism.
- `_run_prepared_claim_against_source_document`: runs one prepared claim against one extracted source document.
- `_build_review_trace`: creates the audit trace for one review outcome.
- `ReviewTrace`: stores the product-facing execution trace.

Deliberate choice:

- Source reuse reduces duplicate fetch/extraction work without merging claim judgments together. Each claim still gets its own retrieval and verdict.

## 12. What The Eval Taught

Relevant files:

- `tests/eval/run_fixed_fixture_eval.py`
- `tests/eval/fixed_fixture_support.py`
- `docs/EVALUATION_SUMMARY.md`
- `docs/TESTING.md`

Current fixed-fixture result:

- 45 claim cases
- 42 exact verdict matches
- 93.3% classification accuracy
- 0 false-support decisions

What worked:

- all expected contradicted fixture cases were caught
- all expected unsupported fixture cases were caught
- all broken-link or typo cases stayed safely unverified
- table-derived evidence became much stronger after table-row extraction work

Remaining retrieval limits:

- dense filing evidence can hide partial support
- rounded prose values can be treated more conservatively than exact table values
- statistics-style HTML can still over-rank short numeric fragments over richer subject-specific prose

Deliberate choice:

- The eval goal is not maximum auto-approval. The safer failure mode is a conservative undercall, not a false supported verdict.

## What This Design Avoids

ClaimTrace could have been simpler if it just sent the full source to Gemini, but that would make the result harder to debug and more expensive to run. It could also have been more powerful if it used embeddings or fuzzy semantic matching, but that would make the first public capstone harder to evaluate honestly.

The current design avoids:

- whole-source Gemini review
- LLM-controlled source discovery
- alternative-source research
- publisher-specific retrieval hacks
- broad stemming or fuzzy matching across all anchors
- embeddings or semantic paraphrase retrieval
- OCR and scanned-PDF table reconstruction
- persistent source caching or a database

Those are not all bad ideas forever. They are just outside this MVP because the current project is trying to prove a narrower thing: cited-source verification can be useful when deterministic retrieval controls the evidence packet and the model judges only the bounded result.

## Final Design Principle

ClaimTrace uses deterministic retrieval where evidence control matters and Gemini where judgment matters.

That means:

- exact cited source before model judgment
- source extraction before reasoning
- scoring and ranking before token spending
- bounded evidence packets before Gemini
- visible traces before trust

The result is not a universal fact-checker. It is a scoped cited-source verifier designed to make quantitative business evidence checks cheaper, smaller, safer, and easier to debug.
