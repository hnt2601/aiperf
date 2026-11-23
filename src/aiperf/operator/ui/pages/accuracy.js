// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { html } from 'htm/preact';
import { useState, useEffect } from 'preact/hooks';
import { query, setQuery } from '../lib/router.js';
import { LoadingPanel } from '../components/spinner.js';
import { ModelPill } from '../components/pills.js';
import {
  DIRECTION_GLYPH,
  DIRECTION_LABEL,
  FALLBACK_LABEL,
  barPercent,
  buildQuery,
  describeLoadError,
  fmtCi,
  fmtCount,
  fmtRate,
  groupByBenchmark,
  judgeText,
  labelsText,
  rowNotes,
  safeHttpUrl,
} from './accuracy-helpers.js';

// Read-only JSON served by PerfLedger (perfledger-mcp, route GET /api/accuracy) and mapped under the UI's own prefix by the
// gateway in front of this UI, so the browser reuses the dashboard's origin and credentials (no CORS, no extra sign-in).
// Resolved against the page's own location, like lib/base-path.js does on newer builds. Deliberately not imported from there:
// that module does not exist in 0.13.0 (f3a76e5), and a missing static import would stop the whole SPA from loading.
const API_URL = new URL('perfledger-api/accuracy', document.baseURI).pathname;

async function fetchAccuracy(filters, signal) {
  const res = await fetch(API_URL + buildQuery(filters), {
    headers: { Accept: 'application/json' },
    credentials: 'same-origin',
    signal,
  });
  const text = await res.text();
  if (!res.ok) throw new Error(`API ${res.status}: ${text.slice(0, 200)}`);
  try {
    return JSON.parse(text);
  } catch {
    // Without the route, the SPA fallback answers 200 with index.html.
    throw new Error(`API ${res.status}: response is not JSON`);
  }
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? String(iso)
    : d.toLocaleString([], { month: 'short', day: 'numeric', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export function TaskRows({ row }) {
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
          ${row.tasks.map((t) => html`
            <tr class="job-table-row" key=${t.task} data-testid="accuracy-task-row">
              <td class="job-table-td">${t.task}</td>
              <td class="job-table-td">${t.metric}</td>
              <td class="job-table-td accuracy-rate">
                <span class="accuracy-rate__value">${fmtRate(t.rate)}</span>
                <span class="accuracy-bar" aria-hidden="true">
                  <span
                    class=${'accuracy-bar__fill accuracy-bar__fill--' + t.direction}
                    style=${'width:' + barPercent(t.rate) + '%'}
                  ></span>
                </span>
              </td>
              <td class="job-table-td">${fmtCi(t.ci)}</td>
              <td class="job-table-td">${fmtCount(t.count, t.total)}</td>
              <td class="job-table-td" title=${DIRECTION_LABEL[t.direction] ?? t.direction}>
                <span aria-hidden="true">${DIRECTION_GLYPH[t.direction] ?? '◆'}</span> ${DIRECTION_LABEL[t.direction] ?? t.direction}
              </td>
              <td class="job-table-td">${labelsText(t.labels)}</td>
              <td class="job-table-td">${t.unparsed ?? '—'}</td>
              <td class="job-table-td">${t.grader_errors ?? 0}</td>
            </tr>
          `)}
        </tbody>
      </table>
    </div>
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
