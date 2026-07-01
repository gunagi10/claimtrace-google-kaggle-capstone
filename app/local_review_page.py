def render_local_review_page() -> str:
    return """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Business Report Verifier</title>
  <style>
    :root {
      --bg: #f5efe2;
      --panel: rgba(255, 250, 240, 0.88);
      --ink: #1f2a2e;
      --muted: #5d6a6f;
      --line: rgba(31, 42, 46, 0.14);
      --accent: #0d7a6b;
      --accent-strong: #084c43;
      --warn: #a85b12;
      --bad: #a52f2f;
      --shadow: 0 18px 50px rgba(31, 42, 46, 0.14);
      --question-bg: #fff8e8;
      --question-border: #e7c978;
      --question-heading: #7a4d00;
      --answer-bg: #eff6ff;
      --answer-border: #9fc4f0;
      --answer-heading: #174a7c;
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      min-height: 100vh;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(13, 122, 107, 0.18), transparent 30%),
        radial-gradient(circle at top right, rgba(168, 91, 18, 0.15), transparent 26%),
        linear-gradient(160deg, #f7f1e7 0%, #efe6d4 100%);
    }

    .shell {
      max-width: 1180px;
      margin: 0 auto;
      padding: 32px 20px 48px;
    }

    .hero {
      display: grid;
      gap: 14px;
      margin-bottom: 22px;
      padding: 26px;
      border: 1px solid var(--line);
      border-radius: 22px;
      background: linear-gradient(135deg, rgba(255, 250, 240, 0.96), rgba(250, 241, 226, 0.88));
      box-shadow: var(--shadow);
    }

    .eyebrow {
      width: fit-content;
      padding: 6px 10px;
      border-radius: 999px;
      background: rgba(13, 122, 107, 0.1);
      color: var(--accent-strong);
      font-size: 0.82rem;
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    h1 {
      margin: 0;
      font-size: clamp(2rem, 4vw, 3.6rem);
      line-height: 0.95;
      letter-spacing: -0.03em;
    }

    .hero p,
    .note,
    .muted,
    label,
    input,
    textarea,
    select,
    button {
      font-family: "Segoe UI", sans-serif;
    }

    .hero p {
      margin: 0;
      max-width: 70ch;
      color: var(--muted);
      line-height: 1.5;
    }

    .notice-strip {
      display: grid;
      gap: 10px;
      padding: 16px 18px;
      border-left: 4px solid var(--warn);
      border-radius: 16px;
      background: rgba(168, 91, 18, 0.08);
    }

    .notice-strip p {
      margin: 0;
      line-height: 1.55;
      color: var(--ink);
    }

    .inline-code {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(31, 42, 46, 0.08);
      font-family: "Cascadia Code", Consolas, monospace;
      font-size: 0.92em;
      white-space: nowrap;
    }

    .grid {
      display: grid;
      gap: 18px;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
    }

    .grid > * {
      min-width: 0;
    }

    .card {
      min-width: 0;
      padding: 22px;
      border: 1px solid var(--line);
      border-radius: 20px;
      background: var(--panel);
      box-shadow: var(--shadow);
    }

    .card h2 {
      margin: 0 0 10px;
      font-size: 1.15rem;
    }

    .question-card {
      background: var(--question-bg);
      border-color: var(--question-border);
    }

    .question-card h2 {
      color: var(--question-heading);
    }

    .answer-card {
      background: #e2efff;
      border-color: #86b3e4;
      box-shadow: 0 18px 50px rgba(23, 74, 124, 0.12);
    }

    .answer-card h2 {
      color: var(--answer-heading);
    }

    .stack {
      display: grid;
      gap: 12px;
    }

    label {
      display: grid;
      gap: 6px;
      color: var(--accent-strong);
      font-weight: 600;
    }

    input[type="file"],
    input[type="text"],
    textarea,
    select {
      width: 100%;
      padding: 12px 14px;
      border: 1px solid rgba(31, 42, 46, 0.18);
      border-radius: 12px;
      background: rgba(255, 255, 255, 0.75);
      color: var(--ink);
      font-size: 0.96rem;
    }

    textarea {
      min-height: 96px;
      resize: vertical;
    }

    button {
      width: fit-content;
      padding: 12px 18px;
      border: 0;
      border-radius: 999px;
      background: var(--accent);
      color: #fff;
      font-weight: 700;
      cursor: pointer;
    }

    button[disabled] {
      cursor: wait;
      opacity: 0.7;
    }

    .pill-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .pill {
      padding: 7px 10px;
      border-radius: 999px;
      background: rgba(13, 122, 107, 0.08);
      color: var(--accent-strong);
      font-size: 0.86rem;
    }

    .status-box,
    .inventory,
    .result-box {
      min-width: 0;
      padding: 16px;
      border-radius: 16px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.58);
      overflow-wrap: anywhere;
    }

    .status-box[data-tone="warn"] {
      border-color: rgba(168, 91, 18, 0.4);
      background: rgba(168, 91, 18, 0.08);
    }

    .status-box[data-tone="bad"] {
      border-color: rgba(165, 47, 47, 0.4);
      background: rgba(165, 47, 47, 0.08);
    }

    .status-box[data-tone="ok"] {
      border-color: rgba(13, 122, 107, 0.35);
      background: rgba(13, 122, 107, 0.08);
    }

    .inventory ul {
      margin: 10px 0 0;
      padding-left: 18px;
    }

    .inventory li {
      overflow-wrap: anywhere;
    }

    .selection-list {
      display: grid;
      gap: 10px;
    }

    .selection-item {
      display: grid;
      gap: 4px;
      padding: 12px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.68);
      font-family: "Segoe UI", sans-serif;
    }

    .selection-item label {
      display: flex;
      gap: 10px;
      align-items: flex-start;
      color: var(--ink);
      font-weight: 600;
    }

    .selection-meta {
      color: var(--muted);
      font-size: 0.9rem;
    }

    .selection-item input[type="text"] {
      margin-top: 6px;
    }

    .claim-selection summary {
      cursor: pointer;
      color: var(--accent-strong);
      font-family: "Segoe UI", sans-serif;
      font-weight: 700;
    }

    .attention-list {
      display: grid;
      gap: 12px;
    }

    pre {
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: "Cascadia Code", Consolas, monospace;
      font-size: 0.9rem;
      line-height: 1.45;
    }

    .result-shell {
      display: grid;
      gap: 14px;
    }

    .result-header {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      align-items: center;
      justify-content: space-between;
    }

    .result-toolbar {
      display: flex;
      flex-wrap: wrap;
      gap: 12px;
      align-items: center;
      justify-content: space-between;
    }

    .result-tabs {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 2px;
    }

    .result-tab-button {
      padding: 10px 14px;
      border: 1px solid rgba(23, 74, 124, 0.22);
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.72);
      color: var(--answer-heading);
      font-family: "Segoe UI", sans-serif;
      font-size: 0.92rem;
      font-weight: 700;
      cursor: pointer;
    }

    .result-tab-button[aria-selected="true"] {
      border-color: rgba(23, 74, 124, 0.42);
      background: rgba(255, 255, 255, 0.98);
      box-shadow: 0 8px 18px rgba(23, 74, 124, 0.08);
    }

    .result-tab-button[aria-selected="false"] {
      opacity: 0.92;
    }

    .result-tab-body {
      display: grid;
      gap: 14px;
    }

    .result-title {
      margin: 0;
      font-size: 1.08rem;
    }

    .badge {
      display: inline-flex;
      align-items: center;
      padding: 7px 10px;
      border-radius: 999px;
      font-family: "Segoe UI", sans-serif;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      text-transform: uppercase;
    }

    .badge[data-tone="ok"] {
      background: rgba(13, 122, 107, 0.12);
      color: var(--accent-strong);
    }

    .badge[data-tone="warn"] {
      background: rgba(168, 91, 18, 0.14);
      color: #7b430d;
    }

    .badge[data-tone="bad"] {
      background: rgba(165, 47, 47, 0.13);
      color: #7a2020;
    }

    .result-grid {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
    }

    .result-panel {
      padding: 14px;
      border-radius: 14px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.68);
    }

    .result-panel h3 {
      margin: 0 0 8px;
      font-size: 0.95rem;
      color: var(--accent-strong);
      font-family: "Segoe UI", sans-serif;
    }

    .result-panel p,
    .result-panel li,
    .result-panel summary,
    .result-panel details {
      font-family: "Segoe UI", sans-serif;
    }

    .result-panel p {
      margin: 0;
      line-height: 1.45;
    }

    .answer-card .pill {
      background: rgba(23, 74, 124, 0.08);
      color: var(--answer-heading);
    }

    .answer-card .result-box {
      border-color: rgba(23, 74, 124, 0.28);
      background: rgba(255, 255, 255, 0.92);
      box-shadow: 0 10px 26px rgba(23, 74, 124, 0.08);
    }

    .answer-card .result-panel {
      border-color: rgba(23, 74, 124, 0.24);
      background: rgba(255, 255, 255, 0.98);
    }

    .answer-card .result-title,
    .answer-card .result-panel h3 {
      color: var(--answer-heading);
    }

    .kv-list {
      display: grid;
      gap: 8px;
      font-family: "Segoe UI", sans-serif;
      font-size: 0.94rem;
    }

    .kv-list div {
      display: grid;
      gap: 2px;
    }

    .kv-list strong {
      color: var(--accent-strong);
    }

    .warning-list,
    .passage-list {
      margin: 0;
      padding-left: 18px;
      display: grid;
      gap: 6px;
    }

    .timing-summary {
      border-color: rgba(23, 74, 124, 0.28);
      background: rgba(239, 246, 255, 0.95);
      color: var(--answer-heading);
      box-shadow: 0 8px 20px rgba(23, 74, 124, 0.08);
    }

    .timing-summary strong {
      display: block;
      margin-bottom: 4px;
      color: var(--answer-heading);
    }

    .bullet-list {
      margin: 8px 0 0;
      padding-left: 18px;
      display: grid;
      gap: 6px;
    }

    .empty-note {
      color: var(--muted);
      font-style: italic;
    }

    details.result-raw {
      border-top: 1px solid var(--line);
      padding-top: 12px;
    }

    details.result-raw summary {
      cursor: pointer;
      color: var(--accent-strong);
      font-weight: 700;
    }

    .hidden {
      display: none;
    }

    @media (max-width: 720px) {
      .shell { padding: 20px 14px 34px; }
      .hero,
      .card { padding: 18px; }
      button { width: 100%; }
      .result-toolbar { align-items: stretch; }
    }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <span class="eyebrow">Local multi-claim review</span>
      <h1>Business Report Verifier</h1>
      <p>
        Prepare one report, confirm the cited claims you want to review, and check them against their exact sources.
        Shared sources are fetched once. HTML and text-layer PDFs only; no OCR or source search.
      </p>
      <div class="notice-strip note">
        <strong>Current limits:</strong>
        <p>
          Scannable-text PDF only. OCR-only PDFs return
          <span class="inline-code">unverified</span> with an
          <span class="inline-code">ocr_required</span> warning. If
          <span class="inline-code">GOOGLE_API_KEY</span> still contains the placeholder,
          the live judge step stops at
          <span class="inline-code">awaiting_model_config</span> instead of pretending it ran.
        </p>
      </div>
    </section>

    <div class="grid">
      <section class="card question-card">
        <h2>1. Prepare Review</h2>
        <div class="stack">
          <label>
            Report DOCX
            <input id="docxFile" type="file" accept=".docx,application/vnd.openxmlformats-officedocument.wordprocessingml.document">
          </label>
          <button id="prepareButton" type="button">Parse DOCX</button>
          <div id="prepareStatus" class="status-box note">Upload one `.docx` to inspect claim-ready sentences and mapped references.</div>
          <div id="inventoryBox" class="inventory hidden"></div>
        </div>
      </section>

      <section class="card question-card">
        <h2>2. Run One Claim Review</h2>
        <div class="stack">
          <label>
            Claim-ready sentence
            <select id="sentenceSelect" disabled>
              <option value="">Prepare a DOCX first</option>
            </select>
          </label>
          <div id="citationScopeBox" class="status-box note">Citation scope will appear after parsing.</div>
          <label>
            Citation direction
            <select id="citationDirectionSelect" disabled>
              <option value="">Prepare a DOCX first</option>
            </select>
          </label>
          <label>
            Mapped reference
            <select id="referenceSelect" disabled>
              <option value="">Prepare a DOCX first</option>
            </select>
          </label>
          <label>
            Claim to check
            <input id="approvedClaimText" type="text" placeholder="The claim selected from your report appears here.">
          </label>
          <div id="sourceFallbackBox" class="status-box warn hidden">
            <strong>We couldn't open the cited source automatically.</strong>
            <label>
              Upload an HTML or PDF copy to rerun this claim
              <input id="sourceFile" type="file" accept=".html,.htm,.pdf,text/html,application/pdf">
            </label>
            <div class="selection-meta">This upload control stays available during the current prepared review so you can retry with a different exact source copy if needed.</div>
          </div>
          <button id="runButton" type="button" disabled>Run review</button>
          <div id="runStatus" class="status-box note">The review form unlocks after a successful parse. The app opens the cited source automatically.</div>
        </div>
      </section>
    </div>

    <section class="card question-card" style="margin-top: 18px;">
      <h2>3. Confirm Multi-Claim Review</h2>
      <div class="stack">
        <div class="note">Valid claims are selected by default. Expand only when you want to inspect, edit, or deselect them. No source or Gemini work starts before confirmation.</div>
        <details id="batchSelectionDetails" class="claim-selection hidden">
          <summary id="batchSelectionSummary">Claims to check</summary>
          <div id="batchSelectionBox" style="margin-top: 12px;"></div>
        </details>
        <div class="pill-row">
          <button id="runBatchButton" type="button" disabled>Confirm and run selected claims</button>
          <button id="skipBatchButton" type="button" disabled>Skip evidence review</button>
        </div>
        <div id="batchStatus" class="status-box note">Prepare a DOCX first, then confirm the claims you want to check.</div>
        <div id="batchTimingSummary" class="status-box timing-summary hidden"></div>
      </div>
    </section>

    <section class="card question-card" style="margin-top: 18px;">
      <h2>4. Run Section Analysis</h2>
      <div class="stack">
        <div class="note">Run section analysis only after the batch evidence result is clear enough to continue.</div>
        <div class="pill-row">
          <button id="runSectionButton" type="button" disabled>Run section analysis</button>
        </div>
        <div id="sectionStatus" class="status-box note">Section analysis unlocks after a batch evidence run that is clear enough to continue.</div>
        <div id="sectionTimingSummary" class="status-box timing-summary hidden"></div>
      </div>
    </section>

    <section class="card question-card" style="margin-top: 18px;">
      <h2>5. Run Final Coherence</h2>
      <div class="stack">
        <div class="note">Run final coherence only after section analysis completes successfully.</div>
        <div class="pill-row">
          <button id="runCoherenceButton" type="button" disabled>Run final coherence</button>
        </div>
        <div id="coherenceStatus" class="status-box note">Final coherence unlocks after section analysis completes.</div>
      </div>
    </section>

    <section class="card answer-card" style="margin-top: 18px;">
      <h2>Result View</h2>
      <div class="result-toolbar">
        <div class="pill-row">
          <span class="pill">User-confirmed claim selection</span>
          <span class="pill">Each exact source fetched once</span>
          <span class="pill">Deterministic passages first</span>
          <span class="pill">Gemini model: gemini-flash-lite-latest</span>
        </div>
        <button id="downloadMarkdownButton" type="button" disabled>Download markdown summary</button>
      </div>
      <div id="resultBox" class="result-box" style="margin-top: 14px;">
        <pre>Result output will appear here.</pre>
      </div>
    </section>
  </main>

  <script>
    const state = {
      preparePayload: null,
      referencesById: new Map(),
      activeSinglePayload: null,
      activeBatchPayload: null,
      activeSectionPayload: null,
      activeCoherencePayload: null,
      activeResultTab: "single",
      batchElapsedMs: null,
      singleClaimRecoveryActive: false,
      batchRecoverySources: [],
    };

    const docxInput = document.getElementById("docxFile");
    const sourceInput = document.getElementById("sourceFile");
    const prepareButton = document.getElementById("prepareButton");
    const runButton = document.getElementById("runButton");
    const sentenceSelect = document.getElementById("sentenceSelect");
    const citationDirectionSelect = document.getElementById("citationDirectionSelect");
    const referenceSelect = document.getElementById("referenceSelect");
    const runBatchButton = document.getElementById("runBatchButton");
    const skipBatchButton = document.getElementById("skipBatchButton");
    const runSectionButton = document.getElementById("runSectionButton");
    const runCoherenceButton = document.getElementById("runCoherenceButton");
    const approvedClaimText = document.getElementById("approvedClaimText");
    const sourceFallbackBox = document.getElementById("sourceFallbackBox");
    const prepareStatus = document.getElementById("prepareStatus");
    const runStatus = document.getElementById("runStatus");
    const batchStatus = document.getElementById("batchStatus");
    const batchTimingSummary = document.getElementById("batchTimingSummary");
    const sectionStatus = document.getElementById("sectionStatus");
    const sectionTimingSummary = document.getElementById("sectionTimingSummary");
    const coherenceStatus = document.getElementById("coherenceStatus");
    const inventoryBox = document.getElementById("inventoryBox");
    const citationScopeBox = document.getElementById("citationScopeBox");
    const batchSelectionBox = document.getElementById("batchSelectionBox");
    const batchSelectionDetails = document.getElementById("batchSelectionDetails");
    const batchSelectionSummary = document.getElementById("batchSelectionSummary");
    const downloadMarkdownButton = document.getElementById("downloadMarkdownButton");
    const resultBox = document.getElementById("resultBox");

    prepareButton.addEventListener("click", prepareReview);
    runButton.addEventListener("click", runReview);
    runBatchButton.addEventListener("click", runBatchReview);
    skipBatchButton.addEventListener("click", skipBatchReview);
    runSectionButton.addEventListener("click", runSectionAnalysis);
    runCoherenceButton.addEventListener("click", runFinalCoherence);
    downloadMarkdownButton.addEventListener("click", downloadCurrentMarkdown);
    batchSelectionBox.addEventListener("change", updateBatchSelectionSummary);
    sentenceSelect.addEventListener("change", syncSelectedSentence);
    citationDirectionSelect.addEventListener("change", syncApprovedClaimFromDirection);
    resultBox.addEventListener("click", handleResultBoxClick);

    function setStatus(node, message, tone) {
      node.textContent = message;
      node.dataset.tone = tone || "";
    }

    function setHtmlStatus(node, html, tone) {
      node.innerHTML = html;
      node.dataset.tone = tone || "";
      node.classList.remove("hidden");
    }

    function handleResultBoxClick(event) {
      const tabButton = event.target.closest(".result-tab-button");
      if (!tabButton) return;
      const nextTab = tabButton.dataset.resultTab || "batch";
      if (!state.activeBatchPayload) return;
      state.activeResultTab = nextTab;
      renderBatchResult(state.activeBatchPayload, { elapsedMs: state.batchElapsedMs });
    }

    function setButtonBusy(button, busyLabel, isBusy) {
      if (!button.dataset.idleLabel) {
        button.dataset.idleLabel = button.textContent;
      }
      button.disabled = isBusy;
      button.textContent = isBusy ? busyLabel : button.dataset.idleLabel;
    }

    function formatElapsed(ms) {
      if (!Number.isFinite(ms) || ms < 0) return "not available";
      if (ms < 1000) return Math.round(ms) + " ms";
      return (ms / 1000).toFixed(2) + " s";
    }

    function needsSourceRecoveryFromStatuses(fetchStatus, extractionStatus) {
      return fetchStatus === "failed"
        || extractionStatus === "ocr_required"
        || extractionStatus === "extraction_failed";
    }

    function payloadNeedsSingleSourceRecovery(payload) {
      if (!payload || typeof payload !== "object") return false;
      const trace = payload.trace || null;
      if (trace && needsSourceRecoveryFromStatuses(trace.source_fetch_status, trace.source_extraction_status)) {
        return true;
      }
      const assessment = payload.assessment || null;
      if (assessment && needsSourceRecoveryFromStatuses(assessment.source_fetch_status, assessment.source_extraction_status)) {
        return true;
      }
      const judgePayload = payload.judge_payload || null;
      if (judgePayload && needsSourceRecoveryFromStatuses(judgePayload.source_fetch_status, judgePayload.source_extraction_status)) {
        return true;
      }
      return false;
    }

    function rememberBatchRecoverySources(payload) {
      const sources = Array.isArray(payload && payload.sources_needing_attention)
        ? payload.sources_needing_attention
        : [];
      for (const source of sources) {
        const normalized = {
          reference_id: source.reference_id,
          canonical_url: source.canonical_url || null,
          failure_reason: source.failure_reason || "The cited source needs a readable uploaded copy.",
          affected_sentence_ids: Array.isArray(source.affected_sentence_ids) ? source.affected_sentence_ids.slice() : [],
          accepted_upload_types: Array.isArray(source.accepted_upload_types) ? source.accepted_upload_types.slice() : [],
        };
        const existingIndex = state.batchRecoverySources.findIndex((item) => item.reference_id === normalized.reference_id);
        if (existingIndex >= 0) {
          state.batchRecoverySources[existingIndex] = normalized;
        } else {
          state.batchRecoverySources.push(normalized);
        }
      }
    }

    function displayedBatchRecoverySources(payload) {
      rememberBatchRecoverySources(payload);
      const visible = new Map();
      const currentSources = Array.isArray(payload && payload.sources_needing_attention)
        ? payload.sources_needing_attention
        : [];
      for (const source of currentSources) {
        visible.set(source.reference_id, { ...source, persistent_recovery: false });
      }
      for (const source of state.batchRecoverySources) {
        if (!visible.has(source.reference_id)) {
          visible.set(source.reference_id, { ...source, persistent_recovery: true });
        }
      }
      return Array.from(visible.values());
    }

    function updateDownloadControl() {
      downloadMarkdownButton.disabled = !(state.activeBatchPayload || state.activeSinglePayload);
    }

    function buildVisibleTimingSummary(debug, label) {
      if (!debug) return "";
      const workerEntries = label === "section"
        ? Array.isArray(debug.section_workers) ? debug.section_workers : []
        : Array.isArray(debug.source_workers) ? debug.source_workers : [];
      if (!workerEntries.length) return "";
      const sequentialMs = workerEntries.reduce((sum, worker) => sum + (worker.duration_ms || 0), 0);
      const observedConcurrent = debug.max_concurrent_workers_seen || 0;
      const configuredConcurrent = debug.max_concurrent_workers_configured || 0;
      const workerLabel = label === "section" ? "section jobs" : "source jobs";
      const outcomeLabel = label === "section" ? "section analysis finished" : "the batch finished";
      return [
        "<strong>Parallel timing</strong>",
        "If these " + escapeHtml(workerLabel) + " ran one by one, the combined worker time would be " + escapeHtml(formatElapsed(sequentialMs)) + ". ",
        "With up to " + escapeHtml(String(observedConcurrent)) + " concurrent worker(s) observed",
        configuredConcurrent ? " out of " + escapeHtml(String(configuredConcurrent)) + " configured" : "",
        ", " + escapeHtml(outcomeLabel) + " in " + escapeHtml(formatElapsed(debug.total_elapsed_ms)) + "."
      ].join("");
    }

    function updateTimingSummaries() {
      const batchPayload = state.activeBatchPayload;
      const batchSummaryHtml = batchPayload && batchPayload.concurrency_debug
        ? buildVisibleTimingSummary(batchPayload.concurrency_debug, "batch")
        : "";
      if (batchSummaryHtml) {
        setHtmlStatus(batchTimingSummary, batchSummaryHtml, "note");
      } else {
        batchTimingSummary.classList.add("hidden");
        batchTimingSummary.innerHTML = "";
      }

      const sectionPayload = state.activeSectionPayload;
      const sectionSummaryHtml = sectionPayload && sectionPayload.concurrency_debug
        ? buildVisibleTimingSummary(sectionPayload.concurrency_debug, "section")
        : "";
      if (sectionSummaryHtml) {
        setHtmlStatus(sectionTimingSummary, sectionSummaryHtml, "note");
      } else {
        sectionTimingSummary.classList.add("hidden");
        sectionTimingSummary.innerHTML = "";
      }
    }

    function buildBulletListHtml(items) {
      if (!Array.isArray(items) || !items.length) return "";
      return "<ul class='bullet-list'>" + items.map((item) => "<li>" + escapeHtml(String(item)) + "</li>").join("") + "</ul>";
    }

    function resetDownstreamAnalysis() {
      state.activeSectionPayload = null;
      state.activeCoherencePayload = null;
      updateWorkflowControls();
      updateDownloadControl();
      updateTimingSummaries();
    }

    function updateWorkflowControls() {
      const batchPayload = state.activeBatchPayload;
      const sectionPayload = state.activeSectionPayload;
      const coherencePayload = state.activeCoherencePayload;
      const gateStatus = batchPayload && batchPayload.gate ? batchPayload.gate.status : "";
      const sectionReady = Boolean(batchPayload) && gateStatus !== "stop_and_fix" && gateStatus !== "review_incomplete";
      runSectionButton.disabled = !sectionReady;
      if (!batchPayload) {
        setStatus(sectionStatus, "Section analysis unlocks after a batch evidence run that is clear enough to continue.", "note");
      } else if (!sectionReady) {
        setStatus(sectionStatus, "Section analysis is blocked until the evidence gate is clear enough to continue.", "warn");
      } else if (sectionPayload) {
        setStatus(
          sectionStatus,
          "Section analysis finished. Eligible sections: " + sectionPayload.eligible_section_count +
          ", completed: " + sectionPayload.completed_count +
          ", awaiting model config: " + sectionPayload.awaiting_model_config_count + ".",
          sectionPayload.awaiting_model_config_count ? "warn" : "ok"
        );
      } else {
        setStatus(sectionStatus, "Section analysis is ready to run from the current batch evidence result.", "ok");
      }

      const sectionComplete = Boolean(sectionPayload)
        && sectionPayload.completed_count === sectionPayload.eligible_section_count
        && sectionPayload.awaiting_model_config_count === 0;
      runCoherenceButton.disabled = !sectionComplete;
      if (!sectionPayload) {
        setStatus(coherenceStatus, "Final coherence unlocks after section analysis completes.", "note");
      } else if (!sectionComplete) {
        setStatus(coherenceStatus, "Final coherence is blocked until all section workers complete successfully.", "warn");
      } else if (coherencePayload) {
        setStatus(
          coherenceStatus,
          "Final coherence finished with status: " + coherencePayload.status + ".",
          coherencePayload.status === "completed" ? "ok" : "warn"
        );
      } else {
        setStatus(coherenceStatus, "Final coherence is ready to run from the current section results.", "ok");
      }
      updateTimingSummaries();
    }

    function renderResult(payload) {
      if (!payload || typeof payload !== "object") {
        resultBox.innerHTML = "<pre>" + escapeHtml(String(payload)) + "</pre>";
        return;
      }

      const status = payload.status || payload.stage || "idle";
      const assessment = payload.assessment || null;
      const judgePayload = payload.judge_payload || null;
      const trace = payload.trace || null;
      if (payloadNeedsSingleSourceRecovery(payload)) {
        state.singleClaimRecoveryActive = true;
      }
      sourceFallbackBox.classList.toggle("hidden", !state.singleClaimRecoveryActive);
      const tone = statusTone(status);
      const sourceMethod = trace
        ? trace.source_method
        : judgePayload
        ? "Exact source fetched or uploaded and prepared for live judgment."
        : assessment && assessment.source_fetch_status === "failed"
          ? "Exact source fetch failed before evidence review could proceed."
          : "Uploaded source copy or deterministic pre-judge result.";

      const sourceStatus = trace
        ? trace.source_fetch_status + " / " + trace.source_extraction_status
        : assessment
        ? assessment.source_fetch_status + " / " + assessment.source_extraction_status
        : judgePayload
          ? judgePayload.source_fetch_status + " / " + judgePayload.source_extraction_status
          : "not available";

      const claimText = trace
        ? trace.approved_claim
        : assessment
        ? (judgePayload && judgePayload.atomic_claim) || payload.claim_text || "Claim text not returned in final assessment payload."
        : judgePayload
          ? judgePayload.atomic_claim
          : payload.atomic_claim || payload.claim_text || "Claim text not available yet.";

      const verdictText = assessment
        ? assessment.verdict
        : status === "awaiting_model_config"
          ? "live judgment paused"
          : "deterministic stage only";

      const reasonText = assessment
        ? assessment.reason
        : payload.message || "The live judge did not run yet.";

      const actionText = assessment
        ? assessment.recommended_action
        : status === "awaiting_model_config"
          ? "Add a real GOOGLE_API_KEY later to enable the live Gemini evidence judge."
          : "Check the warnings and source status before continuing.";

      const warnings = assessment
        ? (assessment.warnings || [])
        : judgePayload
          ? (judgePayload.source_warnings || [])
          : [];

      const candidatePassages = trace && Array.isArray(trace.candidate_passages)
        ? trace.candidate_passages
        : judgePayload && Array.isArray(judgePayload.candidate_passages)
          ? judgePayload.candidate_passages
          : [];
      const passageItems = candidatePassages.length
        ? candidatePassages.map((passage) => {
            const parts = [];
            if (passage.locator && passage.locator.heading) parts.push("heading: " + passage.locator.heading);
            if (passage.locator && passage.locator.page_number) parts.push("page: " + passage.locator.page_number);
            if (passage.locator && passage.locator.text_span_label) parts.push("span: " + passage.locator.text_span_label);
            const locator = parts.length ? " (" + escapeHtml(parts.join(", ")) + ")" : "";
            return "<li><strong>" + escapeHtml(passage.passage_id || "passage") + "</strong>" + locator + "<br>" + escapeHtml(passage.text || "") + "</li>";
          }).join("")
        : "";

      const auditPanel = trace
        ? [
            "  <section class='result-panel'>",
            "    <h3>Execution Audit</h3>",
            "    <div class='kv-list'>",
            "      <div><strong>Stopped stage</strong><span>" + escapeHtml(trace.stopped_stage || "not available") + "</span></div>",
            "      <div><strong>Cited URL</strong><span>" + escapeHtml(trace.canonical_url || "not available") + "</span></div>",
            "      <div><strong>Source method</strong><span>" + escapeHtml(trace.source_method || "not available") + "</span></div>",
            "      <div><strong>Fetch / extraction</strong><span>" + escapeHtml((trace.source_fetch_status || "unknown") + " / " + (trace.source_extraction_status || "unknown")) + "</span></div>",
            "      <div><strong>Extracted blocks</strong><span>" + escapeHtml(String(trace.extracted_block_count || 0)) + "</span></div>",
            "      <div><strong>Candidate passages</strong><span>" + escapeHtml(String(trace.candidate_passage_count || 0)) + "</span></div>",
            "      <div><strong>Gemini called</strong><span>" + (trace.model_called ? "yes" : "no") + "</span></div>",
            "      <div><strong>Configured model</strong><span>" + escapeHtml(trace.model_name || "not available") + "</span></div>",
                 trace.source_failure_reason
                  ? "      <div><strong>Source failure</strong><span>" + escapeHtml(trace.source_failure_reason) + "</span></div>"
                  : "",
            "    </div>",
            "  </section>"
          ].join("")
        : "";

      resultBox.innerHTML = [
        "<div class='result-shell'>",
        "  <div class='result-header'>",
        "    <h3 class='result-title'>Review Result</h3>",
        "    <span class='badge' data-tone='" + tone + "'>" + escapeHtml(status) + "</span>",
        "  </div>",
        "  <div class='result-grid'>",
        "    <section class='result-panel'>",
        "      <h3>Claim</h3>",
        "      <p>" + escapeHtml(claimText) + "</p>",
        "    </section>",
        "    <section class='result-panel'>",
        "      <h3>Main Outcome</h3>",
        "      <div class='kv-list'>",
        "        <div><strong>Verdict or stage</strong><span>" + escapeHtml(verdictText) + "</span></div>",
        "        <div><strong>Reason</strong><span>" + escapeHtml(reasonText) + "</span></div>",
        "        <div><strong>Next action</strong><span>" + escapeHtml(actionText) + "</span></div>",
        "      </div>",
        "    </section>",
        "    <section class='result-panel'>",
        "      <h3>Source Check</h3>",
        "      <div class='kv-list'>",
        "        <div><strong>Method</strong><span>" + escapeHtml(sourceMethod) + "</span></div>",
        "        <div><strong>Source status</strong><span>" + escapeHtml(sourceStatus) + "</span></div>",
        "      </div>",
        "    </section>",
        "  </div>",
             auditPanel,
        "  <section class='result-panel'>",
        "    <h3>Warnings</h3>",
             warnings.length
              ? "<ul class='warning-list'>" + warnings.map((warning) => "<li>" + escapeHtml(warning) + "</li>").join("") + "</ul>"
              : "<p class='empty-note'>No explicit warnings on this result.</p>",
        "  </section>",
        "  <section class='result-panel'>",
        "    <h3>Candidate Passages</h3>",
             passageItems
              ? "<ul class='passage-list'>" + passageItems + "</ul>"
              : "<p class='empty-note'>No candidate passages are shown for this stage.</p>",
        "  </section>",
        "  <details class='result-raw'>",
        "    <summary>Raw response</summary>",
        "    <pre>" + escapeHtml(JSON.stringify(payload, null, 2)) + "</pre>",
        "  </details>",
        "</div>"
      ].join("");
    }

    function statusTone(status) {
      if (status === "completed") return "ok";
      if (status === "awaiting_model_config" || status === "prejudge_unverified") return "warn";
      if (String(status).includes("failed")) return "bad";
      return "warn";
    }

    async function prepareReview() {
      const docxFile = docxInput.files[0];
      if (!docxFile) {
        setStatus(prepareStatus, "Choose a DOCX file first.", "warn");
        return;
      }

      setButtonBusy(prepareButton, "Parsing...", true);
      setStatus(prepareStatus, "Parsing DOCX and building the claim/reference inventory...", "ok");
      inventoryBox.classList.add("hidden");
      sourceFallbackBox.classList.add("hidden");
      sourceInput.value = "";
      state.activeResultTab = "single";
      state.activeSinglePayload = null;
      state.activeBatchPayload = null;
      state.batchElapsedMs = null;
      state.singleClaimRecoveryActive = false;
      state.batchRecoverySources = [];
      resetDownstreamAnalysis();
      renderResult({ stage: "prepare_pending" });

      const formData = new FormData();
      formData.append("docx_file", docxFile);

      try {
        const response = await fetch("/local/review/prepare", {
          method: "POST",
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "Prepare review failed.");
        }

        state.preparePayload = payload;
        state.referencesById = new Map(payload.references.map((reference) => [reference.reference_id, reference]));
        hydrateSentenceOptions(payload.claim_ready_sentences);
        syncSelectedSentence();
        runButton.disabled = false;
        runBatchButton.disabled = false;
        skipBatchButton.disabled = false;
        sentenceSelect.disabled = false;
        referenceSelect.disabled = false;
        setStatus(
          prepareStatus,
          "DOCX parsed. Choose one claim-ready sentence and its mapped reference. The cited source will open automatically.",
          "ok"
        );
        inventoryBox.innerHTML = buildInventoryHtml(payload);
        inventoryBox.classList.remove("hidden");
        batchSelectionBox.innerHTML = buildBatchSelectionHtml(payload.claim_ready_sentences, state.referencesById);
        batchSelectionDetails.classList.remove("hidden");
        batchSelectionDetails.open = false;
        updateBatchSelectionSummary();
        setStatus(batchStatus, "Confirm the selected claims when ready. Shared cited sources will be opened once.", "ok");
        updateWorkflowControls();
        renderResult(payload);
        updateDownloadControl();
      } catch (error) {
        state.preparePayload = null;
        state.activeSinglePayload = null;
        state.activeBatchPayload = null;
        state.batchElapsedMs = null;
        state.singleClaimRecoveryActive = false;
        state.batchRecoverySources = [];
        resetDownstreamAnalysis();
        runButton.disabled = true;
        runBatchButton.disabled = true;
        skipBatchButton.disabled = true;
        sentenceSelect.disabled = true;
        referenceSelect.disabled = true;
        batchSelectionDetails.classList.add("hidden");
        setStatus(prepareStatus, error.message, "bad");
        renderResult({ stage: "prepare_failed", error: error.message });
        updateDownloadControl();
      } finally {
        setButtonBusy(prepareButton, "Parsing...", false);
      }
    }

    async function runReview() {
      const docxFile = docxInput.files[0];
      const sourceFile = sourceInput.files[0];
      const sentenceId = sentenceSelect.value;
      const referenceId = referenceSelect.value;
      const citationDirection = citationDirectionSelect.value;
      if (!docxFile) {
        setStatus(runStatus, "Choose the report DOCX first.", "warn");
        return;
      }
      if (!sentenceId || !referenceId) {
        setStatus(runStatus, "Select one claim-ready sentence and one mapped reference.", "warn");
        return;
      }
      const selectedSentence = getSelectedSentence();
      if (selectedSentence && selectedSentence.requires_citation_direction_confirmation && !citationDirection) {
        setStatus(runStatus, "Confirm whether the citation supports the previous sentence, the next sentence, or both.", "warn");
        return;
      }

      setButtonBusy(runButton, "Running review...", true);
      setStatus(runStatus, "Running deterministic extraction and, if configured, the live Gemini evidence judge. This single-claim path checks one cited source at a time...", "ok");
      const startedAt = performance.now();

      const formData = new FormData();
      formData.append("docx_file", docxFile);
      if (sourceFile) {
        formData.append("source_file", sourceFile);
      }
      formData.append("sentence_id", sentenceId);
      formData.append("reference_id", referenceId);
      formData.append("approved_claim_text", approvedClaimText.value);
      if (citationDirection) {
        formData.append("citation_direction", citationDirection);
      }

      try {
        const response = await fetch("/local/review/run", {
          method: "POST",
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "Run review failed.");
        }

        const tone = payload.status === "completed" ? "ok" : payload.status === "prejudge_unverified" ? "warn" : "warn";
        const elapsedLabel = formatElapsed(performance.now() - startedAt);
        state.activeResultTab = "single";
        state.activeSinglePayload = payload;
        if (payloadNeedsSingleSourceRecovery(payload)) {
          state.singleClaimRecoveryActive = true;
        }
        setStatus(runStatus, "Review finished with status: " + payload.status + ". Analysis time: " + elapsedLabel + ".", tone);
        renderResult(payload);
        updateDownloadControl();
      } catch (error) {
        setStatus(runStatus, error.message, "bad");
        renderResult({ stage: "run_failed", error: error.message });
      } finally {
        setButtonBusy(runButton, "Running review...", false);
      }
    }

    async function runBatchReview() {
      const docxFile = docxInput.files[0];
      if (!docxFile) {
        setStatus(batchStatus, "Choose the report DOCX first.", "warn");
        return;
      }

      const selectedPairs = Array.from(document.querySelectorAll("input[name='batch_sentence']:checked"))
        .map((input) => {
          const item = input.closest(".selection-item");
          const claimInput = item ? item.querySelector(".batch-claim-text") : null;
          return {
            sentence_id: input.value,
            reference_id: input.dataset.referenceId,
            citation_direction: input.dataset.citationDirection || null,
            approved_claim_text: claimInput ? claimInput.value.trim() : null
          };
        })
        .filter((item) => item.sentence_id && item.reference_id);

      if (!selectedPairs.length) {
        setStatus(batchStatus, "Select at least one claim-ready sentence for batch review.", "warn");
        return;
      }

      setButtonBusy(runBatchButton, "Running selected claims...", true);
      setStatus(batchStatus, "Running confirmed claims. Shared sources are reused and checked in parallel when there are multiple unique sources (up to 5 at a time)...", "ok");
      const startedAt = performance.now();
      state.activeResultTab = "batch";
      state.activeSinglePayload = null;
      state.batchRecoverySources = [];
      state.batchElapsedMs = null;
      resetDownstreamAnalysis();

      const formData = new FormData();
      formData.append("docx_file", docxFile);
      formData.append("review_pairs_json", JSON.stringify(selectedPairs));

      try {
        const response = await fetch("/local/review/run-batch", {
          method: "POST",
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "Run batch review failed.");
        }

        const elapsedMs = performance.now() - startedAt;
        setStatus(
          batchStatus,
          "Batch review finished in " + formatElapsed(elapsedMs) + ". Completed: " + payload.completed_count +
          ", unique sources: " + payload.unique_source_count +
          ", awaiting model config: " + payload.awaiting_model_config_count +
          ", prejudge unverified: " + payload.prejudge_unverified_count + ".",
          "ok"
        );
        state.activeBatchPayload = payload;
        state.batchElapsedMs = elapsedMs;
        updateWorkflowControls();
        renderBatchResult(payload, { elapsedMs });
        updateDownloadControl();
      } catch (error) {
        setStatus(batchStatus, error.message, "bad");
        renderResult({ stage: "run_batch_failed", error: error.message });
      } finally {
        setButtonBusy(runBatchButton, "Running selected claims...", false);
      }
    }

    function skipBatchReview() {
      document.querySelectorAll("input[name='batch_sentence']").forEach((input) => {
        input.checked = false;
      });
      updateBatchSelectionSummary();
      state.activeResultTab = "single";
      state.activeBatchPayload = null;
      state.batchRecoverySources = [];
      state.batchElapsedMs = null;
      resetDownstreamAnalysis();
      setStatus(batchStatus, "Evidence review skipped. No source or Gemini work was started.", "warn");
      updateDownloadControl();
    }

    async function runSectionAnalysis() {
      if (!state.activeBatchPayload) {
        setStatus(sectionStatus, "Run the batch evidence review first.", "warn");
        return;
      }

      setButtonBusy(runSectionButton, "Running section analysis...", true);
      setStatus(sectionStatus, "Running one bounded section worker per eligible section...", "ok");
      const formData = new FormData();
      formData.append("review_id", state.activeBatchPayload.review_id);

      try {
        const response = await fetch("/local/review/run-batch/sections", {
          method: "POST",
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "Section analysis failed.");
        }
        state.activeSectionPayload = payload;
        state.activeCoherencePayload = null;
        state.activeResultTab = "section";
        updateWorkflowControls();
        renderBatchResult(state.activeBatchPayload, { elapsedMs: state.batchElapsedMs });
        updateDownloadControl();
      } catch (error) {
        setStatus(sectionStatus, error.message, "bad");
      } finally {
        setButtonBusy(runSectionButton, "Running section analysis...", false);
      }
    }

    async function runFinalCoherence() {
      if (!state.activeBatchPayload || !state.activeSectionPayload) {
        setStatus(coherenceStatus, "Run section analysis first.", "warn");
        return;
      }

      setButtonBusy(runCoherenceButton, "Running final coherence...", true);
      setStatus(coherenceStatus, "Running the bounded report-level coherence worker...", "ok");
      const formData = new FormData();
      formData.append("review_id", state.activeBatchPayload.review_id);

      try {
        const response = await fetch("/local/review/run-batch/coherence", {
          method: "POST",
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok) {
          throw new Error(payload.detail || "Final coherence failed.");
        }
        state.activeCoherencePayload = payload;
        state.activeResultTab = "coherence";
        updateWorkflowControls();
        renderBatchResult(state.activeBatchPayload, { elapsedMs: state.batchElapsedMs });
        updateDownloadControl();
      } catch (error) {
        setStatus(coherenceStatus, error.message, "bad");
      } finally {
        setButtonBusy(runCoherenceButton, "Running final coherence...", false);
      }
    }

    function updateBatchSelectionSummary() {
      const selected = document.querySelectorAll("input[name='batch_sentence']:checked").length;
      const available = document.querySelectorAll("input[name='batch_sentence']").length;
      batchSelectionSummary.textContent = "Claims to check — " + selected + " selected of " + available;
    }

    function hydrateSentenceOptions(sentences) {
      sentenceSelect.innerHTML = "";
      for (const sentence of sentences) {
        const option = document.createElement("option");
        option.value = sentence.sentence_id;
        option.textContent = sentence.sentence_id + " - " + sentence.sentence_text;
        option.dataset.referenceIds = JSON.stringify(sentence.reference_ids || []);
        option.dataset.citationDirection = sentence.citation_direction || "backward";
        option.dataset.requiresCitationDirectionConfirmation = String(Boolean(sentence.requires_citation_direction_confirmation));
        sentenceSelect.appendChild(option);
      }
    }

    function getSelectedSentence() {
      if (!state.preparePayload) return null;
      return (state.preparePayload.claim_ready_sentences || []).find(
        (sentence) => sentence.sentence_id === sentenceSelect.value
      ) || null;
    }

    function syncSelectedSentence() {
      syncReferenceOptions();
      syncCitationOptions();
    }

    function syncCitationOptions() {
      const sentence = getSelectedSentence();
      citationDirectionSelect.innerHTML = "";
      if (!sentence) {
        citationDirectionSelect.disabled = true;
        citationDirectionSelect.innerHTML = "<option value=''>No sentence selected</option>";
        citationScopeBox.textContent = "Citation scope is not available.";
        return;
      }

      const candidates = sentence.citation_direction_candidates || [];
      if (sentence.requires_citation_direction_confirmation) {
        citationDirectionSelect.disabled = false;
        citationDirectionSelect.innerHTML = [
          "<option value=''>Confirmation required</option>",
          "<option value='backward'>Previous sentence</option>",
          "<option value='forward'>Next sentence</option>",
          "<option value='both'>Both sentences</option>"
        ].join("");
        approvedClaimText.value = "";
      } else {
        const direction = sentence.citation_direction || "backward";
        citationDirectionSelect.disabled = true;
        citationDirectionSelect.innerHTML = "<option value='" + escapeHtml(direction) + "'>" + escapeHtml(direction) + " (automatic)</option>";
        const candidate = candidates.find((item) => item.direction === direction);
        approvedClaimText.value = candidate ? candidate.sentence_text : "";
      }

      const scope = sentence.citation_scope_sentences || [];
      const following = sentence.following_context_sentences || [];
      citationScopeBox.innerHTML = [
        "<strong>Possible citation scope</strong>",
        scope.length
          ? "<ol>" + scope.map((text) => "<li>" + escapeHtml(text) + "</li>").join("") + "</ol>"
          : "<p>No scope sentences detected.</p>",
        following.length
          ? "<strong>Following context only</strong><p>" + escapeHtml(following.join(" ")) + "</p>"
          : ""
      ].join("");
      syncApprovedClaimFromDirection();
    }

    function syncApprovedClaimFromDirection() {
      const sentence = getSelectedSentence();
      if (!sentence || !sentence.requires_citation_direction_confirmation) return;
      const direction = citationDirectionSelect.value;
      const candidates = sentence.citation_direction_candidates || [];
      if (direction === "both") {
        approvedClaimText.value = ["backward", "forward"]
          .map((candidateDirection) => candidates.find((item) => item.direction === candidateDirection))
          .filter(Boolean)
          .map((item) => item.sentence_text)
          .join(" ");
        return;
      }
      const candidate = candidates.find((item) => item.direction === direction);
      approvedClaimText.value = candidate ? candidate.sentence_text : "";
    }

    function syncReferenceOptions() {
      const selectedOption = sentenceSelect.selectedOptions[0];
      const allowedReferenceIds = selectedOption ? JSON.parse(selectedOption.dataset.referenceIds || "[]") : [];
      referenceSelect.innerHTML = "";

      if (!allowedReferenceIds.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No mapped reference for this sentence";
        referenceSelect.appendChild(option);
        return;
      }

      for (const referenceId of allowedReferenceIds) {
        const reference = state.referencesById.get(referenceId);
        const option = document.createElement("option");
        option.value = referenceId;
        option.textContent = referenceId + " - " + (reference ? reference.raw_bibliography_text : referenceId);
        referenceSelect.appendChild(option);
      }
    }

    function buildInventoryHtml(payload) {
      const sentenceItems = payload.claim_ready_sentences
        .map((sentence) => "<li><strong>" + escapeHtml(sentence.sentence_id) + "</strong>: " + escapeHtml(sentence.sentence_text) + "</li>")
        .join("");
      const referenceItems = payload.references
        .map((reference) => "<li><strong>" + escapeHtml(reference.reference_id) + "</strong>: " + escapeHtml(reference.raw_bibliography_text) + "</li>")
        .join("");
      return [
        "<strong>Detected inventory</strong>",
        "<ul>" + sentenceItems + "</ul>",
        "<strong>Mapped references</strong>",
        "<ul>" + referenceItems + "</ul>"
      ].join("");
    }

    function buildBatchSelectionHtml(sentences, referencesById) {
      const items = sentences.map((sentence) => {
        const referenceId = (sentence.reference_ids || [])[0] || "";
        const reference = referencesById.get(referenceId);
        const referenceText = reference
          ? reference.reference_id + " - " + reference.raw_bibliography_text
          : "No mapped reference available";
        const requiresDirection = Boolean(sentence.requires_citation_direction_confirmation);
        const disabled = referenceId && !requiresDirection ? "" : " disabled";
        const checked = referenceId && !requiresDirection ? " checked" : "";
        const direction = sentence.citation_direction || "backward";
        const candidates = sentence.citation_direction_candidates || [];
        const candidate = candidates.find((item) => item.direction === direction);
        const claimText = candidate
          ? candidate.sentence_text
          : String(sentence.sentence_text || "").replace(/\[\d+\]/g, "").trim();
        return [
          "<div class='selection-item'>",
          "  <label>",
          "    <input type='checkbox' name='batch_sentence' value='" + escapeHtml(sentence.sentence_id) + "' data-reference-id='" + escapeHtml(referenceId) + "' data-citation-direction='" + escapeHtml(direction) + "'" + checked + disabled + ">",
          "    <span>" + escapeHtml(sentence.sentence_text) + "</span>",
          "  </label>",
          "  <input class='batch-claim-text' type='text' value='" + escapeHtml(claimText) + "'" + disabled + " aria-label='Claim text for " + escapeHtml(sentence.sentence_id) + "'>",
          "  <div class='selection-meta'>Sentence: " + escapeHtml(sentence.sentence_id) + " | Reference: " + escapeHtml(referenceText) + (requiresDirection ? " | Resolve citation direction in single review first" : "") + "</div>",
          "</div>"
        ].join("");
      }).join("");
      return "<div class='selection-list'>" + items + "</div>";
    }

    function renderBatchResult(payload, uiMeta) {
      const coverage = payload.coverage || {};
      const concurrencyDebug = payload.concurrency_debug || null;
      const gate = payload.gate || null;
      const sectionPayload = state.activeSectionPayload;
      const coherencePayload = state.activeCoherencePayload;
      const attentionSources = displayedBatchRecoverySources(payload);
      const elapsedLabel = uiMeta && Number.isFinite(uiMeta.elapsedMs)
        ? formatElapsed(uiMeta.elapsedMs)
        : "not measured";
      const items = (payload.items || []).map((item) => {
        const trace = item.result.trace || null;
        const assessment = item.result.assessment || null;
        const verdict = item.result.assessment && item.result.assessment.verdict
          ? item.result.assessment.verdict
          : item.result.status;
        const reason = assessment && assessment.reason
          ? assessment.reason
          : item.result.message || "No additional reason provided.";
        const action = assessment && assessment.recommended_action
          ? assessment.recommended_action
          : "Resolve the current stage before relying on this claim.";
        const passages = trace && Array.isArray(trace.candidate_passages)
          ? trace.candidate_passages
          : [];
        return [
          "<section class='result-panel'>",
          "  <h3>" + escapeHtml(trace ? trace.approved_claim : item.sentence_id) + "</h3>",
          "  <div class='kv-list'>",
          "    <div><strong>Status</strong><span>" + escapeHtml(item.result.status) + "</span></div>",
          "    <div><strong>Verdict or stage</strong><span>" + escapeHtml(verdict) + "</span></div>",
          "    <div><strong>Reason</strong><span>" + escapeHtml(reason) + "</span></div>",
          "    <div><strong>Recommended action</strong><span>" + escapeHtml(action) + "</span></div>",
          "    <div><strong>Cited source</strong><span>" + escapeHtml(item.reference_id) + (trace && trace.canonical_url ? " — " + escapeHtml(trace.canonical_url) : "") + "</span></div>",
          "  </div>",
          "  <details style='margin-top: 10px;'>",
          "    <summary>Evidence and execution detail</summary>",
               trace
                ? "<p>Stopped at " + escapeHtml(trace.stopped_stage) + "; " + escapeHtml(trace.source_fetch_status + " / " + trace.source_extraction_status) + "; source method: " + escapeHtml(trace.source_method) + "; Gemini called: " + (trace.model_called ? "yes" : "no") + ".</p>"
                : "<p>No execution trace returned.</p>",
               passages.length
                ? "<ul class='passage-list'>" + passages.map((passage) => "<li><strong>" + escapeHtml(passage.passage_id) + "</strong><br>" + escapeHtml(passage.text) + "</li>").join("") + "</ul>"
                : "<p class='empty-note'>No candidate passages for this stage.</p>",
          "  </details>",
          "</section>"
        ].join("");
      }).join("");

      const verdictCounts = Object.entries(coverage.verdict_counts || {})
        .map(([verdict, count]) => "<li>" + escapeHtml(verdict) + ": " + escapeHtml(String(count)) + "</li>")
        .join("");
      const gateTone = gate && gate.status === "stop_and_fix"
        ? "bad"
        : gate && (gate.status === "review_incomplete" || gate.status === "continue_with_warnings")
          ? "warn"
          : "ok";
      const gateHeading = gate && gate.status === "stop_and_fix"
        ? "Stop before later analysis"
        : gate && gate.status === "review_incomplete"
          ? "Evidence review incomplete"
          : gate && gate.status === "continue_with_warnings"
            ? "Continue with warnings"
            : "Clear to continue";
      const gatePanel = gate
        ? [
            "<section class='status-box " + gateTone + "'>",
            "  <h3>" + escapeHtml(gateHeading) + "</h3>",
            "  <p>" + escapeHtml(gate.summary || "") + "</p>",
            "  <div class='kv-list'>",
            "    <div><strong>Checked claims</strong><span>" + escapeHtml(String(gate.checked_claim_count || 0)) + "</span></div>",
            "    <div><strong>Pending claims</strong><span>" + escapeHtml(String(gate.pending_claim_count || 0)) + "</span></div>",
            "    <div><strong>Contradicted</strong><span>" + escapeHtml(String(gate.contradiction_count || 0)) + "</span></div>",
            "    <div><strong>Unsupported</strong><span>" + escapeHtml(String(gate.unsupported_count || 0)) + "</span></div>",
            "    <div><strong>Unverified</strong><span>" + escapeHtml(String(gate.unverified_count || 0)) + "</span></div>",
            "    <div><strong>User override applied</strong><span>" + (gate.user_override_applied ? "yes" : "no") + "</span></div>",
            "  </div>",
            gate.contradiction_sentence_ids && gate.contradiction_sentence_ids.length
              ? "  <p><strong>Contradicted claims:</strong> " + escapeHtml(gate.contradiction_sentence_ids.join(", ")) + "</p>"
              : "",
            gate.warning_sentence_ids && gate.warning_sentence_ids.length
              ? "  <p><strong>Warning claims:</strong> " + escapeHtml(gate.warning_sentence_ids.join(", ")) + "</p>"
              : "",
            "  <p class='selection-meta'>This recommendation is derived deterministically from the current evidence outcomes. Claim-level evidence stays visible below.</p>",
            "</section>"
          ].join("")
        : "<section class='result-panel'><h3>Gate recommendation</h3><p class='empty-note'>No gate recommendation returned.</p></section>";
      const workerTimings = concurrencyDebug && Array.isArray(concurrencyDebug.source_workers)
        ? concurrencyDebug.source_workers.map((worker) => {
            return "<li><strong>" + escapeHtml(worker.reference_id) + "</strong>: " +
              escapeHtml(String(worker.claim_count)) + " claim(s), start " +
              escapeHtml(formatElapsed(worker.started_offset_ms)) + ", finish " +
              escapeHtml(formatElapsed(worker.finished_offset_ms)) + ", duration " +
              escapeHtml(formatElapsed(worker.duration_ms)) + ".</li>";
          }).join("")
        : "";
      const concurrencyPanel = concurrencyDebug
        ? [
            "<details class='result-panel'>",
            "  <summary>Temporary parallel-worker debug</summary>",
            "  <p>Observed max concurrent workers: " + escapeHtml(String(concurrencyDebug.max_concurrent_workers_seen || 0)) +
              " of configured " + escapeHtml(String(concurrencyDebug.max_concurrent_workers_configured || 0)) +
              ". Backend measured total batch worker time: " + escapeHtml(formatElapsed(concurrencyDebug.total_elapsed_ms)) + ".</p>",
            workerTimings
              ? "  <ul class='passage-list'>" + workerTimings + "</ul>"
              : "  <p class='empty-note'>No worker timing details returned.</p>",
            "</details>"
          ].join("")
        : "";
      const sectionConcurrencyDebug = sectionPayload && sectionPayload.concurrency_debug
        ? sectionPayload.concurrency_debug
        : null;
      const sectionWorkerTimings = sectionConcurrencyDebug && Array.isArray(sectionConcurrencyDebug.section_workers)
        ? sectionConcurrencyDebug.section_workers.map((worker) => {
            return "<li><strong>" + escapeHtml(worker.section_id) + "</strong>: start " +
              escapeHtml(formatElapsed(worker.started_offset_ms)) + ", finish " +
              escapeHtml(formatElapsed(worker.finished_offset_ms)) + ", duration " +
              escapeHtml(formatElapsed(worker.duration_ms)) + ".</li>";
          }).join("")
        : "";
      const sectionConcurrencyPanel = sectionConcurrencyDebug
        ? [
            "<details class='result-panel'>",
            "  <summary>Temporary section-worker debug</summary>",
            "  <p>Observed max concurrent section workers: " + escapeHtml(String(sectionConcurrencyDebug.max_concurrent_workers_seen || 0)) +
              " of configured " + escapeHtml(String(sectionConcurrencyDebug.max_concurrent_workers_configured || 0)) +
              ". Backend measured total section worker time: " + escapeHtml(formatElapsed(sectionConcurrencyDebug.total_elapsed_ms)) + ".</p>",
            sectionWorkerTimings
              ? "  <ul class='passage-list'>" + sectionWorkerTimings + "</ul>"
              : "  <p class='empty-note'>No section worker timing details returned.</p>",
            "</details>"
          ].join("")
        : "";
      const sectionItems = sectionPayload && Array.isArray(sectionPayload.items)
        ? sectionPayload.items.map((item) => {
            const assessment = item.assessment || null;
            const packet = item.packet || {};
            return [
              "<section class='result-panel'>",
              "  <h3>" + escapeHtml(packet.heading || item.section_id) + "</h3>",
              "  <div class='kv-list'>",
              "    <div><strong>Status</strong><span>" + escapeHtml(item.status) + "</span></div>",
              "    <div><strong>Checked claims</strong><span>" + escapeHtml(String((packet.coverage_summary || {}).checked_claim_count || 0)) + "</span></div>",
              "    <div><strong>Contradicted</strong><span>" + escapeHtml(String((packet.coverage_summary || {}).contradicted_count || 0)) + "</span></div>",
              "    <div><strong>Warnings</strong><span>" + escapeHtml(String(((packet.coverage_summary || {}).unsupported_count || 0) + ((packet.coverage_summary || {}).unverified_count || 0))) + "</span></div>",
              "  </div>",
                   assessment
                    ? "<p><strong>Summary:</strong> " + escapeHtml(assessment.summary || "No summary returned.") + "</p>"
                    : "<p class='empty-note'>" + escapeHtml(item.message || "No section assessment returned.") + "</p>",
                   assessment && assessment.unresolved_risks && assessment.unresolved_risks.length
                    ? "<div><strong>Unresolved risks:</strong>" + buildBulletListHtml(assessment.unresolved_risks) + "</div>"
                    : "",
                   assessment && assessment.recommended_revisions && assessment.recommended_revisions.length
                    ? "<div><strong>Recommended revisions:</strong>" + buildBulletListHtml(assessment.recommended_revisions) + "</div>"
                    : "",
              "</section>"
            ].join("");
          }).join("")
        : "";
      const sectionPanel = sectionPayload
        ? [
            "<section class='status-box " + (sectionPayload.awaiting_model_config_count ? "warn" : "ok") + "'>",
            "  <h3>Section Analysis</h3>",
            "  <p>Eligible sections: " + escapeHtml(String(sectionPayload.eligible_section_count || 0)) +
              ", completed: " + escapeHtml(String(sectionPayload.completed_count || 0)) +
              ", awaiting model config: " + escapeHtml(String(sectionPayload.awaiting_model_config_count || 0)) + ".</p>",
            sectionItems || "<p class='empty-note'>No section results returned.</p>",
            "</section>"
          ].join("")
        : "<section class='result-panel'><h3>Section Analysis</h3><p class='empty-note'>Run section analysis after the evidence gate is clear enough to continue.</p></section>";
      const coherenceAssessment = coherencePayload ? coherencePayload.assessment : null;
      const coherencePanel = coherencePayload
        ? [
            "<section class='status-box " + (coherencePayload.status === "completed" ? "ok" : "warn") + "'>",
            "  <h3>Final Coherence</h3>",
            "  <p><strong>Status:</strong> " + escapeHtml(coherencePayload.status || "unknown") + "</p>",
            coherenceAssessment
              ? "  <p><strong>Report summary:</strong> " + escapeHtml(coherenceAssessment.report_summary || "") + "</p>"
              : "  <p class='empty-note'>" + escapeHtml(coherencePayload.message || "No final coherence assessment returned.") + "</p>",
            coherenceAssessment && coherenceAssessment.noteworthy_patterns && coherenceAssessment.noteworthy_patterns.length
              ? "  <div><strong>Noteworthy patterns:</strong>" + buildBulletListHtml(coherenceAssessment.noteworthy_patterns) + "</div>"
              : "",
            coherenceAssessment && coherenceAssessment.priority_actions && coherenceAssessment.priority_actions.length
              ? "  <div><strong>Priority actions:</strong>" + buildBulletListHtml(coherenceAssessment.priority_actions) + "</div>"
              : "",
            coherenceAssessment && coherenceAssessment.unresolved_risks && coherenceAssessment.unresolved_risks.length
              ? "  <div><strong>Unresolved risks:</strong>" + buildBulletListHtml(coherenceAssessment.unresolved_risks) + "</div>"
              : "",
            "  <details class='result-raw'>",
            "    <summary>Final coherence raw response</summary>",
            "    <pre>" + escapeHtml(JSON.stringify(coherencePayload, null, 2)) + "</pre>",
            "  </details>",
            "</section>"
          ].join("")
        : "<section class='result-panel'><h3>Final Coherence</h3><p class='empty-note'>Run final coherence after section analysis completes.</p></section>";

      const attentionItems = attentionSources.map((source, index) => {
        const inputId = "batch-source-copy-" + index;
        return [
          "<section class='result-panel' data-source-attention='" + escapeHtml(source.reference_id) + "'>",
          "  <h3>" + escapeHtml(source.reference_id) + "</h3>",
          "  <p>" + escapeHtml(source.failure_reason) + "</p>",
          "  <p><strong>Affected claims:</strong> " + escapeHtml((source.affected_sentence_ids || []).join(", ")) + "</p>",
          "  <label>Upload an exact HTML or text-extractable PDF copy",
          "    <input id='" + inputId + "' type='file' accept='.html,.htm,.pdf,text/html,application/pdf'>",
          "  </label>",
          "  <button class='retry-source-button' type='button' data-reference-id='" + escapeHtml(source.reference_id) + "' data-input-id='" + inputId + "'>Retry affected claims</button>",
          "  <div class='selection-meta'>" + (source.persistent_recovery
              ? "This retry control stays available during the current review in case you need to replace the uploaded exact source copy."
              : "This does not search for or substitute another source.") + "</div>",
          "</section>"
        ].join("");
      }).join("");

      const tabOrder = [
        { id: "batch", label: "Batch Review Result" },
        { id: "claims", label: "1-1 Claim Checks" },
        { id: "section", label: "Section Analysis" },
        { id: "coherence", label: "Final Coherence" },
      ];
      const activeTab = tabOrder.some((tab) => tab.id === state.activeResultTab)
        ? state.activeResultTab
        : "batch";
      state.activeResultTab = activeTab;
      const tabButtons = tabOrder.map((tab) => {
        const selected = tab.id === activeTab ? "true" : "false";
        return "<button class='result-tab-button' type='button' role='tab' aria-selected='" + selected + "' data-result-tab='" + escapeHtml(tab.id) + "'>" + escapeHtml(tab.label) + "</button>";
      }).join("");

      const batchTabContent = [
        "<div class='result-shell'>",
        "  <div class='result-header'>",
        "    <h3 class='result-title'>Batch Review Result</h3>",
        "    <span class='badge' data-tone='warn'>multi-review</span>",
        "  </div>",
        "  <section class='result-panel'><h3>Run Summary</h3><p>Checked " + escapeHtml(String(payload.total_selected || 0)) + " selected claims across " + escapeHtml(String(payload.unique_source_count || 0)) + " unique sources. Shared sources were reused and up to 5 source workers can run in parallel. Analysis time: " + escapeHtml(elapsedLabel) + "." + (concurrencyDebug ? " Observed backend overlap: " + escapeHtml(String(concurrencyDebug.max_concurrent_workers_seen || 0)) + " concurrent worker(s)." : "") + "</p></section>",
        "  <div class='result-grid'>",
        "    <section class='result-panel'><h3>Selected / available</h3><p>" + escapeHtml(String(coverage.selected || 0)) + " / " + escapeHtml(String(coverage.total_available || 0)) + "</p></section>",
        "    <section class='result-panel'><h3>Completed</h3><p>" + escapeHtml(String(coverage.completed || 0)) + "</p></section>",
        "    <section class='result-panel'><h3>Unresolved</h3><p>" + escapeHtml(String(coverage.unresolved || 0)) + "</p></section>",
        "    <section class='result-panel'><h3>Deselected</h3><p>" + escapeHtml(String(coverage.deselected || 0)) + "</p></section>",
        "  </div>",
             gatePanel,
        "  <section class='result-panel'><h3>Verdict counts</h3>" + (verdictCounts ? "<ul>" + verdictCounts + "</ul>" : "<p class='empty-note'>No final verdicts yet.</p>") + "</section>",
        "  <details class='result-raw'>",
        "    <summary>Batch review raw response</summary>",
        "    <pre>" + escapeHtml(JSON.stringify(payload, null, 2)) + "</pre>",
        "  </details>",
        "</div>"
      ].join("");

      const claimsTabContent = [
        "<div class='result-shell'>",
        "  <section class='result-panel'><h3>1-1 Claim Checks</h3><p>Inspect each checked claim, its verdict or stage, and the detailed execution trace below.</p></section>",
             concurrencyPanel,
             items || "<section class='result-panel'><p class='empty-note'>No claim checks are available yet.</p></section>",
             attentionItems
              ? "<section class='status-box warn'><h3>Sources needing attention</h3><div class='attention-list'>" + attentionItems + "</div></section>"
              : "",
        "</div>"
      ].join("");

      const sectionTabContent = [
        "<div class='result-shell'>",
        "  <section class='result-panel'><h3>Section Analysis</h3><p>Review each section summary, its risk signals, and the recommended revisions below.</p></section>",
             sectionConcurrencyPanel,
             sectionPanel,
        "</div>"
      ].join("");

      const coherenceTabContent = [
        "<div class='result-shell'>",
        "  <section class='result-panel'><h3>Final Coherence</h3><p>Review the cross-report summary, recurring patterns, and priority fixes below.</p></section>",
             coherencePanel,
        "</div>"
      ].join("");

      const activeTabContent = {
        batch: batchTabContent,
        claims: claimsTabContent,
        section: sectionTabContent,
        coherence: coherenceTabContent,
      }[activeTab] || batchTabContent;

      resultBox.innerHTML = [
        "<div class='result-shell'>",
        "  <div class='result-tabs' role='tablist' aria-label='Result view sections'>",
             tabButtons,
        "  </div>",
        "  <div class='result-tab-body'>",
             activeTabContent,
        "  </div>",
        "</div>"
      ].join("");
      bindBatchSourceRecoveryActions();
    }

    function buildSingleReviewMarkdown(payload) {
      const assessment = payload.assessment || null;
      const trace = payload.trace || null;
      const judgePayload = payload.judge_payload || null;
      const warnings = assessment
        ? (assessment.warnings || [])
        : judgePayload
          ? (judgePayload.source_warnings || [])
          : [];
      const candidatePassages = trace && Array.isArray(trace.candidate_passages)
        ? trace.candidate_passages
        : judgePayload && Array.isArray(judgePayload.candidate_passages)
          ? judgePayload.candidate_passages
          : [];
      const lines = [
        "# Business Report Verifier Summary",
        "",
        "## Single Claim Review",
        "",
        "- Status: " + String(payload.status || payload.stage || "unknown"),
        "- Claim: " + String((trace && trace.approved_claim) || (judgePayload && judgePayload.atomic_claim) || payload.claim_text || "not available"),
        "- Verdict or stage: " + String(assessment ? assessment.verdict : payload.status || payload.stage || "unknown"),
        "- Reason: " + String(assessment ? assessment.reason : payload.message || "not available"),
        "- Recommended action: " + String(assessment ? assessment.recommended_action : "Check the current result details."),
        "- Source status: " + String(trace
            ? ((trace.source_fetch_status || "unknown") + " / " + (trace.source_extraction_status || "unknown"))
            : assessment
              ? ((assessment.source_fetch_status || "unknown") + " / " + (assessment.source_extraction_status || "unknown"))
              : "not available"),
      ];
      if (warnings.length) {
        lines.push("", "## Warnings", "");
        warnings.forEach((warning) => lines.push("- " + String(warning)));
      }
      if (candidatePassages.length) {
        lines.push("", "## Candidate Passages", "");
        candidatePassages.forEach((passage) => {
          lines.push("- " + String(passage.passage_id || "passage") + ": " + String(passage.text || ""));
        });
      }
      return lines.join("\\n");
    }

    function buildBatchReviewMarkdown() {
      const payload = state.activeBatchPayload;
      if (!payload) return "";
      const coverage = payload.coverage || {};
      const gate = payload.gate || {};
      const sectionPayload = state.activeSectionPayload;
      const coherencePayload = state.activeCoherencePayload;
      const concurrencyDebug = payload.concurrency_debug || null;
      const sectionConcurrencyDebug = sectionPayload && sectionPayload.concurrency_debug
        ? sectionPayload.concurrency_debug
        : null;
      const attentionSources = displayedBatchRecoverySources(payload);
      const lines = [
        "# Business Report Verifier Summary",
        "",
        "## Batch Review Result",
        "",
        "- Review ID: " + String(payload.review_id || "not available"),
        "- Selected claims: " + String(payload.total_selected || 0),
        "- Unique sources: " + String(payload.unique_source_count || 0),
        "- Analysis time: " + formatElapsed(state.batchElapsedMs),
        "- Completed: " + String(payload.completed_count || 0),
        "- Awaiting model config: " + String(payload.awaiting_model_config_count || 0),
        "- Prejudge unverified: " + String(payload.prejudge_unverified_count || 0),
        "",
        "## Coverage",
        "",
        "- Selected / available: " + String(coverage.selected || 0) + " / " + String(coverage.total_available || 0),
        "- Completed: " + String(coverage.completed || 0),
        "- Unresolved: " + String(coverage.unresolved || 0),
        "- Deselected: " + String(coverage.deselected || 0),
        "",
        "## Gate Recommendation",
        "",
        "- Status: " + String(gate.status || "not available"),
        "- Summary: " + String(gate.summary || "not available"),
        "- Contradicted: " + String(gate.contradiction_count || 0),
        "- Unsupported: " + String(gate.unsupported_count || 0),
        "- Unverified: " + String(gate.unverified_count || 0),
      ];
      const verdictEntries = Object.entries(coverage.verdict_counts || {});
      if (verdictEntries.length) {
        lines.push("", "## Verdict Counts", "");
        verdictEntries.forEach(([verdict, count]) => lines.push("- " + String(verdict) + ": " + String(count)));
      }
      if (concurrencyDebug) {
        lines.push("", "## Batch Worker Timing", "");
        lines.push("- Max concurrent workers seen: " + String(concurrencyDebug.max_concurrent_workers_seen || 0) + " of " + String(concurrencyDebug.max_concurrent_workers_configured || 0));
        lines.push("- Total batch worker time: " + formatElapsed(concurrencyDebug.total_elapsed_ms));
        (concurrencyDebug.source_workers || []).forEach((worker) => {
          lines.push("- " + String(worker.reference_id) + ": start " + formatElapsed(worker.started_offset_ms) + ", finish " + formatElapsed(worker.finished_offset_ms) + ", duration " + formatElapsed(worker.duration_ms));
        });
      }
      lines.push("", "## Claim-by-Claim Results", "");
      (payload.items || []).forEach((item) => {
        const trace = item.result.trace || null;
        const assessment = item.result.assessment || null;
        const claimLabel = trace ? trace.approved_claim : item.sentence_id;
        lines.push("### " + String(claimLabel));
        lines.push("");
        lines.push("- Sentence ID: " + String(item.sentence_id));
        lines.push("- Reference ID: " + String(item.reference_id));
        lines.push("- Status: " + String(item.result.status || "unknown"));
        lines.push("- Verdict or stage: " + String(assessment && assessment.verdict ? assessment.verdict : item.result.status || "unknown"));
        lines.push("- Reason: " + String(assessment && assessment.reason ? assessment.reason : item.result.message || "No additional reason provided."));
        lines.push("- Recommended action: " + String(assessment && assessment.recommended_action ? assessment.recommended_action : "Resolve the current stage before relying on this claim."));
        if (trace && Array.isArray(trace.candidate_passages) && trace.candidate_passages.length) {
          lines.push("- Candidate passages:");
          trace.candidate_passages.forEach((passage) => {
            lines.push("  - " + String(passage.passage_id || "passage") + ": " + String(passage.text || ""));
          });
        }
        lines.push("");
      });
      if (attentionSources.length) {
        lines.push("## Source Recovery", "");
        attentionSources.forEach((source) => {
          lines.push("- " + String(source.reference_id) + ": " + String(source.failure_reason || "Retry with an exact source copy if needed."));
        });
        lines.push("");
      }
      if (sectionPayload) {
        lines.push("## Section Analysis", "");
        lines.push("- Eligible sections: " + String(sectionPayload.eligible_section_count || 0));
        lines.push("- Completed: " + String(sectionPayload.completed_count || 0));
        lines.push("- Awaiting model config: " + String(sectionPayload.awaiting_model_config_count || 0));
        if (sectionConcurrencyDebug) {
          lines.push("- Max concurrent section workers seen: " + String(sectionConcurrencyDebug.max_concurrent_workers_seen || 0) + " of " + String(sectionConcurrencyDebug.max_concurrent_workers_configured || 0));
          lines.push("- Total section worker time: " + formatElapsed(sectionConcurrencyDebug.total_elapsed_ms));
        }
        lines.push("");
        (sectionPayload.items || []).forEach((item) => {
          const assessment = item.assessment || null;
          lines.push("### " + String((item.packet || {}).heading || item.section_id));
          lines.push("");
          lines.push("- Status: " + String(item.status || "unknown"));
          lines.push("- Summary: " + String(assessment && assessment.summary ? assessment.summary : item.message || "No section assessment returned."));
          if (assessment && Array.isArray(assessment.unresolved_risks) && assessment.unresolved_risks.length) {
            lines.push("- Unresolved risks:");
            assessment.unresolved_risks.forEach((risk) => lines.push("  - " + String(risk)));
          }
          if (assessment && Array.isArray(assessment.recommended_revisions) && assessment.recommended_revisions.length) {
            lines.push("- Recommended revisions:");
            assessment.recommended_revisions.forEach((revision) => lines.push("  - " + String(revision)));
          }
          lines.push("");
        });
      }
      if (coherencePayload) {
        const assessment = coherencePayload.assessment || null;
        lines.push("## Final Coherence", "");
        lines.push("- Status: " + String(coherencePayload.status || "unknown"));
        lines.push("- Report summary: " + String(assessment && assessment.report_summary ? assessment.report_summary : coherencePayload.message || "No final coherence assessment returned."));
        if (assessment && Array.isArray(assessment.noteworthy_patterns) && assessment.noteworthy_patterns.length) {
          lines.push("- Noteworthy patterns:");
          assessment.noteworthy_patterns.forEach((pattern) => lines.push("  - " + String(pattern)));
        }
        if (assessment && Array.isArray(assessment.priority_actions) && assessment.priority_actions.length) {
          lines.push("- Priority actions:");
          assessment.priority_actions.forEach((action) => lines.push("  - " + String(action)));
        }
        if (assessment && Array.isArray(assessment.unresolved_risks) && assessment.unresolved_risks.length) {
          lines.push("- Unresolved risks:");
          assessment.unresolved_risks.forEach((risk) => lines.push("  - " + String(risk)));
        }
        lines.push("");
      }
      return lines.join("\\n");
    }

    function downloadCurrentMarkdown() {
      const content = state.activeBatchPayload
        ? buildBatchReviewMarkdown()
        : state.activeSinglePayload
          ? buildSingleReviewMarkdown(state.activeSinglePayload)
          : "";
      if (!content) {
        setStatus(batchStatus, "No review result is available to download yet.", "warn");
        return;
      }
      const blob = new Blob([content], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = state.activeBatchPayload
        ? "business-report-verifier-" + String(state.activeBatchPayload.review_id || "batch-review") + "-summary.md"
        : "business-report-verifier-single-claim-summary.md";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    }

    function bindBatchSourceRecoveryActions() {
      document.querySelectorAll(".retry-source-button").forEach((button) => {
        button.addEventListener("click", () => retryBatchSource(button));
      });
    }

    async function retryBatchSource(button) {
      const input = document.getElementById(button.dataset.inputId);
      const sourceFile = input && input.files ? input.files[0] : null;
      if (!sourceFile || !state.activeBatchPayload) {
        setStatus(batchStatus, "Choose an HTML or PDF copy for the failed cited source.", "warn");
        return;
      }

      setButtonBusy(button, "Retrying affected claims...", true);
      const formData = new FormData();
      formData.append("review_id", state.activeBatchPayload.review_id);
      formData.append("reference_id", button.dataset.referenceId);
      formData.append("source_file", sourceFile);
      try {
        const response = await fetch("/local/review/run-batch/retry-source", {
          method: "POST",
          body: formData,
        });
        const payload = await response.json();
        if (!response.ok) throw new Error(payload.detail || "Source recovery failed.");
        state.activeBatchPayload = payload;
        resetDownstreamAnalysis();
        setStatus(batchStatus, "Uploaded copy processed. Only linked unresolved claims were retried.", "ok");
        renderBatchResult(payload, { elapsedMs: state.batchElapsedMs });
        updateDownloadControl();
      } catch (error) {
        setStatus(batchStatus, error.message, "bad");
      } finally {
        setButtonBusy(button, "Retrying affected claims...", false);
      }
    }

    function escapeHtml(value) {
      return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
    }
  </script>
</body>
</html>
""".strip()
