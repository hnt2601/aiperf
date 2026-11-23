// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { html } from 'htm/preact';
import { useState, useEffect } from 'preact/hooks';
import { query, setQuery } from '../lib/router.js';
import { LoadingPanel } from '../components/spinner.js';
import { ModelPill } from '../components/pills.js';
import {
  DIRECTION_GLYPH,
  FALLBACK_LABEL,
  TASK_ROWS_COLLAPSED,
  barPercent,
  buildCompareQuery,
  buildQuery,
  compareReasonText,
  describeLoadError,
  directionText,
  fmtCi,
  fmtCount,
  fmtDelta,
  fmtP,
  fmtRate,
  groupByBenchmark,
  isUngraded,
  judgeText,
  labelsText,
  readingText,
  rowNotes,
  runLabel,
  safeHttpUrl,
  visibleTasks,
} from './accuracy-helpers.js';

// Read-only JSON served by PerfLedger (perfledger-mcp, route GET /api/accuracy) and mapped under the UI's own prefix by the
// gateway in front of this UI, so the browser reuses the dashboard's origin and credentials (no CORS, no extra sign-in).
// Resolved against the page's own location, like lib/base-path.js does on newer builds. Deliberately not imported from there:
// that module does not exist in 0.13.0 (f3a76e5), and a missing static import would stop the whole SPA from loading.
const API_URL = new URL('perfledger-api/accuracy', document.baseURI).pathname;
// Paired comparison of two runs (GET /api/accuracy/compare): same prefix and same gateway as the list route.
const COMPARE_URL = new URL('perfledger-api/accuracy/compare', document.baseURI).pathname;

async function getJson(url, signal) {
  const res = await fetch(url, {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
    signal,
  });
  const text = await res.text();
  if (!res.ok) {
    // Structured errors carry a readable message; anything else (e.g. a gateway error page) keeps its raw text.
    let message = text.slice(0, 200);
    try {
      message = JSON.parse(text)?.error?.message ?? message;
    } catch {
      /* keep the raw text */
    }
    throw new Error(`API ${res.status}: ${message}`);
  }
  try {
    return JSON.parse(text);
  } catch {
    // Without the route, the SPA fallback answers 200 with index.html.
    throw new Error(`API ${res.status}: response is not JSON`);
  }
}

const fetchAccuracy = (filters, signal) => getJson(API_URL + buildQuery(filters), signal);
const fetchCompare = (candidate, baseline, signal) => getJson(COMPARE_URL + buildCompareQuery(candidate, baseline), signal);

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleString([], { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function TaskRows({ row }) {
  // Benchmarks such as MMLU-Pro have dozens of tasks: collapsed after a dozen, with a toggle.
  const [expanded, setExpanded] = useState(false);
  const tasks = row.tasks ?? [];
  const shown = visibleTasks(tasks, expanded);
  const ungraded = isUngraded(row);
  return html`
    <div class="job-table-wrapper">
      <table class="job-table accuracy-table" aria-label=${'Per-task results for ' + (row.model ?? 'run')}>
        <thead>
          <tr>
            <th class="job-table-th" scope="col">Task</th>
            <th class="job-table-th" scope="col">Metric</th>
            <th class="job-table-th" scope="col">Rate</th>
            <th class="job-table-th" scope="col">95% CI</th>
            <th class="job-table-th" scope="col">Count</th>
            <th class="job-table-th" scope="col">Direction</th>
            <th class="job-table-th" scope="col">Labels</th>
            <th class="job-table-th" scope="col">Unparsed</th>
            <th class="job-table-th" scope="col">Grader errors</th>
          </tr>
        </thead>
        <tbody>
          ${shown.map((t) => html`
            <tr class="job-table-row" key=${t.task} data-testid="accuracy-task-row">
              <td class="job-table-td">${t.task}</td>
              <td class="job-table-td">${t.metric ?? '—'}</td>
              <td class="job-table-td accuracy-rate">
                <span class="accuracy-rate__value">${fmtRate(t.rate)}</span>
                <span class="accuracy-bar" aria-hidden="true">
                  <span
                    class=${'accuracy-bar__fill accuracy-bar__fill--' + (t.direction ?? 'neutral')}
                    style=${'width:' + barPercent(t.rate) + '%'}
                  ></span>
                </span>
              </td>
              <td class="job-table-td">${fmtCi(t.ci)}</td>
              <td class="job-table-td">${ungraded ? `${t.total ?? '—'} generated` : fmtCount(t.count, t.total)}</td>
              <td class="job-table-td" title=${directionText(t.direction)}>
                ${t.direction && html`<span aria-hidden="true">${DIRECTION_GLYPH[t.direction] ?? '◆'}</span> `}${directionText(t.direction)}
              </td>
              <td class="job-table-td">${labelsText(t.labels)}</td>
              <td class="job-table-td">${t.unparsed ?? '—'}</td>
              <td class="job-table-td">${t.grader_errors ?? 0}</td>
            </tr>
          `)}
        </tbody>
      </table>
    </div>
    ${tasks.length > TASK_ROWS_COLLAPSED && html`
      <button
        type="button"
        class="filter-tab accuracy-toggle"
        data-testid="accuracy-toggle-tasks"
        onclick=${() => setExpanded((v) => !v)}
      >
        ${expanded ? 'Show fewer tasks' : `Show all ${tasks.length} tasks`}
      </button>
    `}
  `;
}

/** "graded: sandbox" / "not graded" pills; plain inline runs (the normal case) get none. */
function GradingPill({ row }) {
  if (isUngraded(row)) {
    return html`<span class="meta-pill accuracy-pill--warn" title="Generation only; scores come from the sandbox grading step">not graded</span>`;
  }
  if (row.grading?.mode === 'sandbox') {
    return html`<span class="meta-pill" title=${row.grading.graded_from ? 'Graded from generation ' + row.grading.graded_from : 'Graded in the sandbox'}>graded: sandbox</span>`;
  }
  return null;
}

export function CompareTable({ data }) {
  const rows = [...(data.tasks ?? [])];
  if (data.overall) rows.push({ task: 'Overall', metric: data.overall.metric ?? '', overall: true, ...data.overall });
  return html`
    <div class="job-table-wrapper">
      <table class="job-table accuracy-table" aria-label="Paired comparison per task">
        <thead>
          <tr>
            <th class="job-table-th" scope="col">Task</th>
            <th class="job-table-th" scope="col">Metric</th>
            <th class="job-table-th" scope="col">Baseline</th>
            <th class="job-table-th" scope="col">Candidate</th>
            <th class="job-table-th" scope="col">Δ metric</th>
            <th class="job-table-th" scope="col" title="Problems where only the baseline was good / only the candidate was good">Only base / only cand</th>
            <th class="job-table-th" scope="col">McNemar</th>
            <th class="job-table-th" scope="col">Reading</th>
          </tr>
        </thead>
        <tbody>
          ${rows.map((t) => html`
            <tr class=${'job-table-row' + (t.overall ? ' accuracy-compare__overall' : '')} key=${t.task} data-testid="accuracy-compare-row">
              <td class="job-table-td">${t.task}</td>
              <td class="job-table-td">${t.metric ?? '—'}${t.direction ? html` <span aria-hidden="true">${DIRECTION_GLYPH[t.direction] ?? ''}</span>` : ''}</td>
              <td class="job-table-td">${fmtRate(t.baseline_metric_rate)}</td>
              <td class="job-table-td">${fmtRate(t.candidate_metric_rate)}</td>
              <td class="job-table-td">${fmtDelta(t.metric_delta_pp)}</td>
              <td class="job-table-td">${t.b ?? '—'} / ${t.c ?? '—'} <span class="text-dim">(n=${t.paired ?? '—'})</span></td>
              <td class="job-table-td">${fmtP(t.p_value)}</td>
              <td class=${'job-table-td accuracy-reading accuracy-reading--' + (t.better ?? 'none')}>${readingText(t)}</td>
            </tr>
          `)}
        </tbody>
      </table>
    </div>
  `;
}

export function ComparePanel({ rows, candidate, baseline, onChange }) {
  const [state, setState] = useState({ loading: false, error: null, payload: null });
  const ready = Boolean(candidate && baseline);

  useEffect(() => {
    if (!ready) {
      setState({ loading: false, error: null, payload: null });
      return undefined;
    }
    const ac = new AbortController();
    setState({ loading: true, error: null, payload: null });
    fetchCompare(candidate, baseline, ac.signal)
      .then((payload) => setState({ loading: false, error: null, payload }))
      .catch((err) => {
        if (err?.name === 'AbortError') return;
        setState({ loading: false, error: describeLoadError(err?.message ?? err), payload: null });
      });
    return () => ac.abort();
  }, [candidate, baseline, ready]);

  const options = (current, other) => rows.map((r) => html`
    <option key=${r.point_id} value=${r.point_id} selected=${r.point_id === current} disabled=${r.point_id === other}>${runLabel(r)}</option>
  `);
  const { loading, error, payload } = state;
  const data = payload?.data;
  return html`
    <section class="card accuracy-compare" data-testid="accuracy-compare">
      <h2 class="accuracy-group__title">Compare two runs</h2>
      <div class="text-dim accuracy-meta">
        Paired by problem (McNemar exact test). Descriptive only: this is not the gate verdict. Δ is candidate − baseline in the task's own metric.
      </div>
      <div class="accuracy-compare__pickers">
        <label class="metric-selector-label" for="accuracy-cand">Candidate</label>
        <select id="accuracy-cand" class="metric-selector-select" onchange=${(e) => onChange({ cand: e.target.value || undefined })}>
          <option value="">Select a run…</option>
          ${options(candidate, baseline)}
        </select>
        <label class="metric-selector-label" for="accuracy-base">Baseline</label>
        <select id="accuracy-base" class="metric-selector-select" onchange=${(e) => onChange({ base: e.target.value || undefined })}>
          <option value="">Select a run…</option>
          ${options(baseline, candidate)}
        </select>
        ${ready && html`<button type="button" class="filter-tab" onclick=${() => onChange({ cand: undefined, base: undefined })}>Clear</button>`}
      </div>
      ${loading && html`<${LoadingPanel} label="Comparing…" testid="accuracy-compare-loading" />`}
      ${error && html`<div class="error-banner" role="alert" data-testid="accuracy-compare-error">${error}</div>`}
      ${data && !data.comparable && html`
        <div class="accuracy-notes" data-testid="accuracy-compare-reason">${compareReasonText(data.reason)}</div>
      `}
      ${data?.comparable && html`<${CompareTable} data=${data} />`}
      ${(payload?.warnings ?? []).length > 0 && html`
        <ul class="accuracy-notes" data-testid="accuracy-compare-notes">
          ${payload.warnings.map((w) => html`<li key=${w}>${w}</li>`)}
        </ul>
      `}
    </section>
  `;
}

export function RunCard({ row }) {
  const notes = rowNotes(row);
  const judge = judgeText(row.judge);
  const runUrl = safeHttpUrl(row.dashboard_url);
  return html`
    <section class="card accuracy-run" data-testid="accuracy-run">
      <div class="accuracy-run__head">
        <${ModelPill} model=${row.model ?? row.model_prefix ?? '—'} />
        <span class="meta-pill">${row.hw ?? '—'}${row.num_gpus ? ' ×' + row.num_gpus : ''}</span>
        <span class="meta-pill" title="Ledger status">${row.status ?? '—'}</span>
        <${GradingPill} row=${row} />
        ${row.kind === 'behavior' && html`<span class="meta-pill" title="Gate mode">gate: ${row.gate?.mode ?? 'report'}</span>`}
        <span class="text-dim">${formatDate(row.recorded_at)} · sweep ${row.sweep_id ?? '—'}</span>
      </div>
      ${row.overall && html`
        <div class="accuracy-overall" data-testid="accuracy-overall">
          Overall ${row.overall.metric}: <strong>${fmtRate(row.overall.rate)}</strong>
          (95% CI ${fmtCi(row.overall.ci)}, ${fmtCount(row.overall.count, row.overall.total)})
        </div>
      `}
      <${TaskRows} row=${row} />
      ${judge && html`<div class="text-dim accuracy-meta">Judge: ${judge}</div>`}
      ${notes.length > 0 && html`
        <ul class="accuracy-notes" data-testid="accuracy-notes">
          ${notes.map((n) => html`<li key=${n}>${n}</li>`)}
        </ul>
      `}
      <div class="text-dim accuracy-meta">
        ${row.evidence_uri && html`Evidence <code>${row.evidence_uri}</code>`}
        ${runUrl && html` · <a href=${runUrl} target="_blank" rel="noopener noreferrer">Open AIPerf run ↗</a>`}
      </div>
    </section>
  `;
}

export function Accuracy() {
  const q = query.value;
  const benchmark = q.benchmark ?? '';
  const kind = q.kind ?? '';
  const urlModel = q.model ?? '';
  const candidate = q.cand ?? '';
  const baseline = q.base ?? '';
  const [model, setModel] = useState(urlModel);
  const [nonce, setNonce] = useState(0);
  const [state, setState] = useState({ loading: true, error: null, payload: null });

  useEffect(() => { if (model !== urlModel) setModel(urlModel); /* eslint-disable-line */ }, [urlModel]);
  useEffect(() => {
    const t = setTimeout(() => { if (model !== urlModel) setQuery({ model }); }, 200);
    return () => clearTimeout(t);
  }, [model, urlModel]);

  useEffect(() => {
    const ac = new AbortController();
    setState((s) => ({ ...s, loading: true, error: null }));
    fetchAccuracy({ benchmark, kind, model: urlModel }, ac.signal)
      .then((payload) => setState({ loading: false, error: null, payload }))
      .catch((err) => {
        if (err?.name === 'AbortError') return;
        setState((s) => ({ loading: false, error: describeLoadError(err?.message ?? err), payload: s.payload }));
      });
    return () => ac.abort();
  }, [benchmark, kind, urlModel, nonce]);

  const { loading, error, payload } = state;
  const rows = payload?.data?.rows ?? [];
  const facets = payload?.data?.facets ?? { benchmarks: [], kinds: [] };
  const groups = groupByBenchmark(rows);
  const warnings = payload?.warnings ?? [];

  return html`
    <div class="accuracy-page" data-testid="page-accuracy">
      <div class="card accuracy-label" data-testid="accuracy-label" style="margin-bottom: var(--space-4)">
        <strong>${payload?.label ?? FALLBACK_LABEL}</strong>
        <div class="text-dim">
          Accuracy and behavior eval results recorded by PerfLedger. Behavior metrics are rates of a behavior occurring,
          not correctness; their direction is stated per task.
        </div>
      </div>

      <div class="card" style="margin-bottom: var(--space-4); display: flex; align-items: center; gap: var(--space-6); flex-wrap: wrap">
        <div style="display: flex; align-items: center; gap: var(--space-2)">
          <label class="metric-selector-label" for="accuracy-benchmark">Benchmark</label>
          <select
            id="accuracy-benchmark"
            class="metric-selector-select"
            value=${benchmark}
            onchange=${(e) => setQuery({ benchmark: e.target.value || undefined })}
          >
            <option value="">All</option>
            ${facets.benchmarks.map((b) => html`<option key=${b} value=${b} selected=${b === benchmark}>${b}</option>`)}
          </select>
        </div>
        <div style="display: flex; align-items: center; gap: var(--space-2)">
          <label class="metric-selector-label" for="accuracy-kind">Kind</label>
          <select
            id="accuracy-kind"
            class="metric-selector-select"
            value=${kind}
            onchange=${(e) => setQuery({ kind: e.target.value || undefined })}
          >
            <option value="">All</option>
            <option value="accuracy" selected=${kind === 'accuracy'}>Accuracy</option>
            <option value="behavior" selected=${kind === 'behavior'}>Behavior</option>
          </select>
        </div>
        <div style="display: flex; align-items: center; gap: var(--space-2)">
          <label class="metric-selector-label" for="accuracy-model">Model</label>
          <input
            id="accuracy-model"
            class="metric-selector-select"
            type="text"
            placeholder="Filter by model…"
            value=${model}
            oninput=${(e) => setModel(e.target.value)}
            style="min-width: 160px"
          />
        </div>
        <button type="button" class="filter-tab" onclick=${() => setNonce((n) => n + 1)} aria-label="Refresh accuracy results">
          Refresh
        </button>
        ${payload && html`<span class="text-dim" data-testid="accuracy-total">${payload.data?.total ?? rows.length} run(s)</span>`}
      </div>

      ${error && html`
        <div class="error-banner" role="alert" data-testid="accuracy-error" style="margin-bottom: var(--space-4)">
          ${error}
        </div>
      `}
      ${warnings.length > 0 && html`
        <ul class="accuracy-notes" data-testid="accuracy-warnings" style="margin-bottom: var(--space-4)">
          ${warnings.map((w) => html`<li key=${w}>${w}</li>`)}
        </ul>
      `}
      ${loading && html`<div class="card"><${LoadingPanel} label="Loading accuracy results…" testid="accuracy-loading" /></div>`}

      ${(rows.length >= 2 || candidate || baseline) && html`
        <${ComparePanel} rows=${rows} candidate=${candidate} baseline=${baseline} onChange=${setQuery} />
      `}

      ${!loading && !error && groups.length === 0 && html`
        <div class="card empty-state" data-testid="accuracy-empty">
          No accuracy or behavior eval runs match these filters.
        </div>
      `}

      ${groups.map((g) => html`
        <div key=${g.benchmark + g.kind} style="margin-bottom: var(--space-6)">
          <h2 class="accuracy-group__title" data-testid="accuracy-group">
            ${g.benchmark}
            <span class="meta-pill">${g.kind}</span>
          </h2>
          ${g.rows.map((row) => html`<${RunCard} key=${row.point_id} row=${row} />`)}
        </div>
      `)}
    </div>
  `;
}
