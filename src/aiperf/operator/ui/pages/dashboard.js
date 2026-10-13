// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

import { html } from 'htm/preact';
import { useState, useEffect } from 'preact/hooks';
import { api, poll } from '../lib/api.js';
import { jobs, sweeps, clusterInfo, dedupeByNsName } from '../lib/state.js';
import { phaseColor, modelColor, palette, colors } from '../lib/theme.js';
import { buildJobPath, navigate, hashUrl, query, setQuery } from '../lib/router.js';
import { KpiCard } from '../components/kpi-card.js';
import { ChartWrapper } from '../components/chart-wrapper.js';
import { ClusterStatsBanner } from '../components/cluster-stats-banner.js';
import { NsPill, ModelPill } from '../components/pills.js';
import { RelativeTime } from '../components/time.js';
import { LoadingPanel } from '../components/spinner.js';
import { fmtNumber, fmtInt, fmtThroughput, fmtLatencyStr, fmtMilliseconds, fmtReqPerSecond } from '../lib/format.js';
import { CHART_TYPOGRAPHY } from '../lib/typography.js';
import { recentJobs } from './dashboard-helpers.js';
import { childBadge, deriveRun, facetValues } from '../lib/grouping.js';
import { ModelCards, dashboardJobs, liveJobs, finishedJobsWithin, groupByRun } from '../components/model-cards.js';

const shortModel = (m) => (m ? String(m).split('/').pop() : null);

// Upper bound on rows in the "Finished in the last 24 h" table; the Jobs page
// has the rest. A single sweep contributes one row per point, so this is
// sized for a few sweeps rather than the old five-row "Recent Jobs" table.
const RECENT_LIMIT = 30;

/**
 * Record-holding run for one field across every completed job.
 *
 * These tiles scan the whole cluster, so the candidates are unrelated
 * experiments: different models, sequence lengths, concurrencies, hardware.
 * The extreme is therefore a property of one specific run, never a capability
 * of the cluster -- "best TTFT" across a mixed population is usually just the
 * smallest model on the shortest prompt. The returned `model` and `candidates`
 * exist so the tile can say whose number it is and how mixed the field was,
 * instead of presenting a bare figure that invites the cluster-capability
 * reading.
 */
function findExtreme(jobList, field, betterThan) {
  let value = null;
  let name = null;
  let model = null;
  let candidates = 0;
  const models = new Set();
  for (const job of jobList) {
    const phase = (job.phase ?? '').toLowerCase();
    if (phase !== 'completed' && phase !== 'succeeded') continue;
    const val = job[field] ?? null;
    if (val == null) continue;
    candidates += 1;
    models.add(job.model ?? 'unknown');
    if (value === null || betterThan(val, value)) {
      value = val;
      name = job.name;
      model = job.model ?? null;
    }
  }
  return { value, name, model, candidates, distinctModels: models.size };
}

const findBest = (jobList, field) => findExtreme(jobList, field, (a, b) => a > b);
const findMin = (jobList, field) => findExtreme(jobList, field, (a, b) => a < b);

// The Recent Jobs bars are scaled to the largest value in the table, and the
// rows are independent benchmarks on different models and settings. Bar length
// therefore encodes position within this table, not relative performance --
// say so, because a shared baseline is the standard visual signal for "these
// are directly comparable".
const BAR_SCALE_HINT = 'Bar length is relative to the largest value in this table. Each row is a separate benchmark with its own model and settings, so the bars show position within this table, not which deployment is faster.';

/** Subtitle for a record tile: which run set the number, on which model. */
function recordSub(record) {
  if (!record?.name) return '';
  const model = shortModel(record.model);
  return model ? `${record.name} · ${model}` : record.name;
}

/** Tooltip spelling out that a record tile describes one run, not the cluster. */
function recordTitle(record, what) {
  if (!record?.name) return `No completed run has reported ${what} yet.`;
  const scope = record.distinctModels > 1
    ? ` Picked from ${record.candidates} completed runs spanning ${record.distinctModels} models, which are separate experiments and not comparable with each other.`
    : ` Picked from ${record.candidates} completed run${record.candidates === 1 ? '' : 's'}.`;
  return `${what} from a single run: ${record.name}${record.model ? ' (' + record.model + ')' : ''}.${scope}`;
}

// --- Section 2: ThroughputLatencyScatter ---

const AXIS_MODES = {
  tps_p99: { xField: 'throughputRps', yField: 'latencyP99Ms', xLabel: 'Throughput (req/s)', yLabel: 'Latency P99 (ms)' },
  tps_ttft: { xField: 'throughputRps', yField: 'ttftMs', xLabel: 'Throughput (req/s)', yLabel: 'TTFT (ms)' },
  tokps_p99: { xField: 'tokenThroughput', yField: 'latencyP99Ms', xLabel: 'Token Throughput (tok/s)', yLabel: 'Latency P99 (ms)' },
};

const quadrantPlugin = {
  id: 'quadrantLabels',
  afterDraw(chart, _args, options) {
    // Chart.register() installs a plugin GLOBALLY: Chart.js then runs it for
    // every chart instance that does not explicitly disable it, and no other
    // chart in this app passes `plugins.quadrantLabels: false`. Without this
    // guard, visiting the dashboard once painted "high throughput, low
    // latency" into the corners of the leaderboard bars and every compare
    // scatter -- charts whose axes are not throughput and latency at all.
    // Opt-in only: this chart sets `quadrantLabels: { enabled: true }`.
    if (!options?.enabled) return;
    const { ctx, chartArea: { left, right, top, bottom } } = chart;
    const midX = (left + right) / 2;

    ctx.save();
    ctx.font = CHART_TYPOGRAPHY.QUADRANT_LABEL_FONT;
    ctx.fillStyle = palette.overlay0 + '60';
    ctx.textAlign = 'center';

    // Chart.js draws a non-reversed linear y-axis with the MAXIMUM at
    // chartArea.top, and every y series this chart can plot is a latency
    // (AXIS_MODES: latencyP99Ms / ttftMs / latencyP99Ms) where lower is
    // better. The desirable corner is therefore bottom-right -- high
    // throughput, low latency -- and the undesirable one is top-left.
    // A quadrant annotation that contradicts the axis it annotates inverts
    // the reader's judgement of which runs are good, and it does so more
    // forcefully than the tick labels correct it.
    ctx.fillText('High throughput, low latency', (midX + right) / 2, bottom - 8);
    ctx.fillText('Low throughput, high latency', (left + midX) / 2, top + 16);

    ctx.restore();
  },
};

// Chart.js UMD loads via a plain <script> tag while this module is imported
// asynchronously; at module-evaluation time, window.Chart may or may not exist.
// Register lazily from inside the component instead.
function ensureQuadrantPluginRegistered() {
  if (window.Chart && !window._quadrantPluginRegistered) {
    window.Chart.register(quadrantPlugin);
    window._quadrantPluginRegistered = true;
  }
}

function ThroughputLatencyScatter({ completedJobs }) {
  const [axisMode, setAxisMode] = useState('tps_p99');
  const [logScale, setLogScale] = useState(false);

  ensureQuadrantPluginRegistered();

  if (!completedJobs || completedJobs.length === 0) return null;

  const mode = AXIS_MODES[axisMode];
  const points = completedJobs.filter(
    j => j[mode.xField] != null && j[mode.yField] != null,
  );
  if (points.length === 0) return null;

  const modelGroups = {};
  for (const job of points) {
    const m = job.model ?? 'unknown';
    if (!modelGroups[m]) modelGroups[m] = [];
    modelGroups[m].push(job);
  }

  const datasets = Object.entries(modelGroups).map(([model, mjobs]) => ({
    label: model,
    data: mjobs.map(j => ({
      x: j[mode.xField],
      y: j[mode.yField],
      jobName: j.name,
    })),
    backgroundColor: modelColor(model) + 'cc',
    borderColor: modelColor(model),
    borderWidth: 1.5,
    pointRadius: 7,
    pointHoverRadius: 10,
  }));

  const scaleType = logScale ? 'logarithmic' : 'linear';
  const chartOptions = {
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: {
          label: ctx => {
            const pt = ctx.raw;
            const xUnit = mode.xLabel.includes('tok/s') ? 'tok/s' : 'req/s';
            const yUnit = 'ms';
            return [
              `${ctx.dataset.label}${pt.jobName ? ' · ' + pt.jobName : ''}`,
              `${xUnit === 'req/s' ? fmtReqPerSecond(pt.x) : fmtNumber(pt.x, 1)} ${xUnit}, ${fmtMilliseconds(pt.y)} ${yUnit}`,
            ];
          },
        },
      },
      quadrantLabels: { enabled: true },
    },
    scales: {
      x: {
        type: scaleType,
        title: { display: true, text: mode.xLabel, color: palette.overlay1, font: { size: CHART_TYPOGRAPHY.AXIS_LABEL } },
        ticks: { color: palette.muted, font: { size: CHART_TYPOGRAPHY.AXIS_TICK } },
        grid: { color: palette.border + '60' },
      },
      y: {
        type: scaleType,
        title: { display: true, text: mode.yLabel, color: palette.overlay1, font: { size: CHART_TYPOGRAPHY.AXIS_LABEL } },
        ticks: { color: palette.muted, font: { size: CHART_TYPOGRAPHY.AXIS_TICK } },
        grid: { color: palette.border + '60' },
      },
    },
  };

  const models = Object.keys(modelGroups);

  return html`
    <div class="card" style="margin-bottom: var(--space-6)">
      <div class="scatter-header">
        <div style="display:flex;flex-direction:column;gap:2px;min-width:0">
          <div class="card-title" style="margin:0">Performance Scatter</div>
          <div style="font-size: var(--font-size-md);font-weight:600;color:${palette.text};line-height:1.2">Throughput vs Latency</div>
        </div>
        <div class="axis-toggles">
          <button type="button" class="nav-tab${axisMode === 'tps_p99' ? ' active' : ''}" aria-pressed=${axisMode === 'tps_p99'} onclick=${() => setAxisMode('tps_p99')}>TPS / P99</button>
          <button type="button" class="nav-tab${axisMode === 'tps_ttft' ? ' active' : ''}" aria-pressed=${axisMode === 'tps_ttft'} onclick=${() => setAxisMode('tps_ttft')}>TPS / TTFT</button>
          <button type="button" class="nav-tab${axisMode === 'tokps_p99' ? ' active' : ''}" aria-pressed=${axisMode === 'tokps_p99'} onclick=${() => setAxisMode('tokps_p99')}>Tok/s / P99</button>
          <button type="button" class="nav-tab${logScale ? ' active' : ''}" aria-pressed=${logScale} onclick=${() => setLogScale(!logScale)}>Log</button>
        </div>
      </div>
      <${ChartWrapper}
        type="scatter"
        data=${{ datasets }}
        options=${chartOptions}
        height=${280}
      />
      ${models.length > 1 ? html`
        <div style="display:flex;gap:12px;flex-wrap:wrap;margin-top:8px;padding:0 4px">
          ${models.map(m => html`
            <div key=${m} style="display:flex;align-items:center;gap:4px;font-size: var(--font-size-xs);color:${palette.sub}">
              <span style="width:8px;height:8px;border-radius:50%;background:${modelColor(m)};display:inline-block"></span>
              ${m}
            </div>
          `)}
        </div>
      ` : null}
    </div>
  `;
}


/**
 * One live job: name, sweep badge, run, phase, workers, live metric strip,
 * progress. Markup is the former inline "Active Jobs" card; the sweep badge
 * (`childBadge`) and run (`deriveRun`) are the only additions.
 */
function LiveJobCard({ job }) {
  const badge = childBadge(job);
  const run = deriveRun(job);
  const phase = job.phase ?? 'Unknown';
  const pct = Math.round(job.progressPercent ?? 0);
  const color = phaseColor(phase);
  const startTime = job.startTime;
  const workersReady = job.workersReady ?? 0;
  const workersTotal = job.workersTotal ?? 0;
  const showWorkers = workersTotal > 0;
  const errPctValue = job.errorRate != null ? job.errorRate * 100 : null;
  const errColor = errPctValue == null
    ? palette.muted
    : errPctValue >= 5 ? palette.red
    : errPctValue >= 1 ? palette.amber
    : palette.green;
  const liveMetrics = [
    { label: 'TTFT', value: job.ttftMs, fmt: v => fmtMilliseconds(v), unit: 'ms', help: 'Time To First Token (avg) — latency from request send to first streamed token' },
    { label: 'OutTok', value: job.outputTokenThroughputTps, fmt: v => fmtInt(v), unit: 'tok/s', help: 'Output token throughput — tokens generated per second across all in-flight requests' },
    { label: 'P99', value: job.latencyP99Ms, fmt: v => fmtMilliseconds(v), unit: 'ms', help: '99th-percentile end-to-end request latency' },
    { label: 'ITL', value: job.interTokenLatencyMs, fmt: v => fmtMilliseconds(v), unit: 'ms', help: 'Inter-Token Latency — average time between successive output tokens' },
    { label: 'Reqs', value: job.totalRequests, fmt: v => fmtInt(v), unit: '', help: 'Total requests issued so far in this run' },
  ].filter(m => m.value != null);

  const goToJob = () => navigate(buildJobPath(job));
  return html`
    <div
      class="job-card"
      role="button"
      tabindex="0"
      aria-label=${'Open job ' + job.namespace + '/' + job.name}
      onclick=${goToJob}
      onkeydown=${e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goToJob(); } }}
      onfocus=${e => { e.currentTarget.style.outline = '2px solid ' + palette.accent; e.currentTarget.style.outlineOffset = '2px'; }}
      onblur=${e => { e.currentTarget.style.outline = ''; e.currentTarget.style.outlineOffset = ''; }}
      style="cursor:pointer;margin-bottom:var(--space-3)"
    >
      <div style="display:grid;grid-template-columns:1fr auto;gap:8px;align-items:start">
        <div>
          <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
            <div class="job-indicator running"></div>
            <span class="job-name">${job.name}</span>
            ${badge ? html`<span class="meta-pill" title=${'Sweep child: ' + badge} data-testid="dashboard-sweep-child-badge">${badge}</span>` : null}
            <span class="job-badge running">${phase}</span>
            ${job.currentPhase ? html`
              <span class="job-subphase" title="Current benchmark phase">${job.currentPhase}</span>
            ` : null}
            <${NsPill} ns=${job.namespace} onClick=${ns => navigate('/jobs?ns=' + encodeURIComponent(ns))} testId=${'dashboard-active-ns-' + (job.namespace ?? '')} />
            ${job.model && html`<${ModelPill} model=${job.model} testId=${'dashboard-active-model-' + (job.namespace ?? '')} />`}
          </div>
          <div class="text-dim" style="font-size:var(--font-size-sm);margin-top:4px;display:flex;gap:8px;flex-wrap:wrap;align-items:center">
            ${run && run !== job.name ? html`<span title="Run (from labels or the job name)">run <span style="color:${palette.sub}">${run}</span></span>` : null}
            ${startTime ? html`<${RelativeTime} ts=${startTime} mode="elapsed" />` : null}
            ${showWorkers ? html`
              <span title="Workers ready / total">\u00b7
                <span style="color:${workersReady === workersTotal ? palette.green : palette.amber}">${workersReady}/${workersTotal}</span> workers
              </span>
            ` : null}
          </div>
        </div>
        <div style="text-align:right">
          ${job.throughputRps != null ? html`
            <div style="font-size: var(--font-size-xl);font-weight:700;color:${palette.text};line-height:1">${fmtThroughput(job.throughputRps)}</div>
            <div style="font-size: var(--font-size-xs);color:${palette.muted}">req/s</div>
          ` : null}
        </div>
      </div>
      ${liveMetrics.length > 0 || errPctValue != null ? html`
        <div class="live-metric-strip" data-testid="dashboard-active-metrics">
          ${liveMetrics.map(m => html`
            <div class="live-metric" key=${m.label} title=${m.help + (m.unit ? ' (' + m.unit + ')' : '')}>
              <span class="live-metric-label">${m.label}</span>
              <span class="live-metric-value">${m.fmt(m.value)}</span>
              ${m.unit ? html`<span class="live-metric-unit">${m.unit}</span>` : null}
            </div>
          `)}
          ${errPctValue != null ? html`
            <div class="live-metric" title=${'Errored requests as % of total — ' + (errPctValue >= 5 ? 'high error rate, investigate' : errPctValue >= 1 ? 'elevated error rate' : 'within tolerance')}>
              <span class="live-metric-label">Err</span>
              <span class="live-metric-value" style="color:${errColor}">
                ${errPctValue >= 5 ? html`<span aria-label="high">! </span>` : null}${fmtNumber(errPctValue, errPctValue < 1 ? 2 : 1)}%
              </span>
            </div>
          ` : null}
        </div>
      ` : null}
      ${pct > 0 ? html`
        <div class="progress-track" style="margin-top:8px">
          <div class="progress-fill" style=${'width:' + pct + '%;background:' + color} />
        </div>
      ` : null}
    </div>
  `;
}

// --- Main Dashboard ---

/**
 * Build a metrics map from per-job summaries fetched in parallel.
 * Single leaderboard call for throughput ranking, then fetch summaries
 * only for jobs that appear in the leaderboard (completed + have results).
 */
function enrichJobsFromSummaries(jobList, summaryMap) {
  return jobList.map(j => {
    const id = j.jobId ?? j.name;
    const s = summaryMap[id];
    if (!s) return j;
    return {
      ...j,
      throughputRps: j.throughputRps ?? s.throughputRps ?? null,
      latencyP99Ms: j.latencyP99Ms ?? s.latencyP99Ms ?? null,
      ttftMs: j.ttftMs ?? s.ttftMs ?? null,
      tokenThroughput: j.outputTokenThroughputTps ?? s.tokenThroughput ?? null,
    };
  });
}

export function Dashboard() {
  const [localJobs, setLocalJobs] = useState(jobs.value);
  const [localSweeps, setLocalSweeps] = useState(sweeps.value);
  const [clusterError, setClusterError] = useState(false);
  const [summaryMap, setSummaryMap] = useState({});
  // Block the dashboard body behind a spinner until the first /jobs
  // fetch returns. Without this, an empty cluster shows the entire
  // dashboard skeleton in its empty-state form before the first poll
  // resolves, which reads as "no data" rather than "still loading".
  const [firstJobsLoad, setFirstJobsLoad] = useState(jobs.value.length === 0);
  const [jobsError, setJobsError] = useState(null);

  useEffect(() => {
    const ac = new AbortController();
    poll(async () => {
      try {
        const data = await api.listJobs();
        const list = dedupeByNsName(data?.jobs ?? []);
        jobs.value = list;
        setLocalJobs(list);
        setJobsError(null);
      } catch (err) {
        if (firstJobsLoad) setJobsError(err?.message ?? String(err));
        throw err;
      } finally {
        setFirstJobsLoad(false);
      }
    }, 5000, ac.signal, { source: 'jobs' });
    poll(async () => {
      const data = await api.listSweeps();
      const list = dedupeByNsName(data?.sweeps ?? []);
      sweeps.value = list;
      setLocalSweeps(list);
    }, 5000, ac.signal, { source: 'sweeps' });
    poll(async () => {
      try {
        const data = await api.getCluster();
        clusterInfo.value = data;
        setClusterError(false);
      } catch (err) {
        setClusterError(true);
        throw err;
      }
    }, 10000, ac.signal, { source: 'cluster' });
    poll(async () => {
      const data = await api.getScatterData();
      const entries = data?.entries ?? [];
      if (entries.length === 0) return;
      const newEntries = {};
      for (const e of entries) {
        newEntries[e.job_id] = {
          throughputRps: e.request_throughput_avg ?? null,
          latencyP99Ms: e.request_latency_p99 ?? null,
          ttftMs: e.time_to_first_token_avg ?? null,
          tokenThroughput: e.output_token_throughput_avg ?? null,
        };
      }
      setSummaryMap(newEntries);
    }, 30000, ac.signal, { source: 'scatter' });
    return () => ac.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const allJobs = enrichJobsFromSummaries(localJobs, summaryMap);
  const running = allJobs.filter(j => { const p = (j.phase ?? '').toLowerCase(); return p === 'running' || p === 'initializing' || p === 'pending'; });
  const completed = allJobs.filter(j => { const p = (j.phase ?? '').toLowerCase(); return p === 'completed' || p === 'succeeded'; });
  const best = findBest(allJobs, 'throughputRps');
  const bestTtft = findMin(allJobs, 'ttftMs');
  const bestTokenTps = findBest(allJobs, 'tokenThroughput');

  // The lists below are scoped to what the cluster is doing now plus the last
  // 24 h; the record tiles and the scatter above keep the all-time view.
  const now = Date.now();
  const modelFilter = query.value.model ?? '';
  const windowJobs = dashboardJobs(allJobs, now);
  const modelOptions = facetValues(windowJobs, 'model');
  if (modelFilter && !modelOptions.includes(modelFilter)) modelOptions.push(modelFilter);
  const scopedJobs = modelFilter ? windowJobs.filter(j => j.model === modelFilter) : windowJobs;
  const scopedSweeps = modelFilter ? localSweeps.filter(s => s?.model === modelFilter) : localSweeps;
  const live = liveJobs(scopedJobs);
  const finished = finishedJobsWithin(scopedJobs, now);
  // Newest first, then regrouped so each run's points sit together under one
  // header row (groups keep newest-first order via first appearance).
  const runGroups = groupByRun(recentJobs(finished, RECENT_LIMIT), deriveRun);
  const recent = runGroups.flatMap(g => g.items);
  const maxThroughput = recent.reduce((mx, j) => Math.max(mx, j.throughputRps ?? 0), 0) || 1;
  // hashUrl() encodes the query for us; navigate() wants the path without '#'.
  const openModel = (model) => navigate(hashUrl('/jobs', { model, group: 'run' }).slice(1));
  const clearModel = () => setQuery({ model: undefined });

  if (firstJobsLoad) {
    return html`
      <div class="dashboard" data-testid="page-dashboard">
        <${ClusterStatsBanner} />
        <div class="card">
          <${LoadingPanel} label="Loading dashboard…" testid="dashboard-loading" />
        </div>
      </div>
    `;
  }

  if (jobsError) {
    return html`
      <div class="dashboard" data-testid="page-dashboard">
        <${ClusterStatsBanner} />
        <div class="card" style="border-color: var(--error); color: var(--error)" data-testid="dashboard-jobs-error">
          <div style="font-weight:600;margin-bottom:4px">Failed to load jobs</div>
          <div style="font-size:var(--font-size-sm);margin-bottom:8px">${jobsError}</div>
          <div style="font-size:var(--font-size-sm);color:var(--muted)">
            Check that the operator is reachable (try <code>aiperf kube status</code>) and that your kubeconfig context targets the right cluster.
          </div>
        </div>
      </div>
    `;
  }

  const noJobsAtAll = allJobs.length === 0;

  return html`
    <div class="dashboard" data-testid="page-dashboard">
      <${ClusterStatsBanner} />
      ${clusterError && html`<div class="cluster-warning-banner" title="The /cluster endpoint failed. GPU/node counts and topology may not reflect the live cluster.">Cluster endpoint unavailable — GPU/node counts may be stale. Check operator logs with <code>aiperf kube logs operator</code>.</div>`}

      ${noJobsAtAll ? html`
        <div class="empty-state card" style="text-align:center;padding:var(--space-6)" data-testid="dashboard-empty">
          <div style="font-size: var(--font-size-md);font-weight:600;margin-bottom:8px">No benchmarks yet</div>
          <p class="text-dim" style="margin:0 0 12px 0">
            Submit your first benchmark to see throughput, latency, and TTFT here.
          </p>
          <p class="text-dim" style="font-size:var(--font-size-sm);margin:0">
            Start one with <code>aiperf kube run --model &lt;model&gt; --url &lt;endpoint&gt;</code>,
            or scaffold a manifest with <code>aiperf kube init</code>.
          </p>
        </div>
      ` : html`
      <!-- Section 4: Models, running now, finished in the last 24 h -->
      <div class="section-header" style="margin-top:var(--space-6);flex-wrap:wrap;gap:8px">
        <span class="section-title">Models</span>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          <span class="text-dim" style="font-size: var(--font-size-sm)" data-testid="dashboard-window-summary">
            ${live.length} running · ${finished.length} finished in 24 h
          </span>
          ${modelOptions.length > 0 ? html`
            <select
              class="ui-select"
              aria-label="Filter dashboard by model"
              data-testid="dashboard-model-select"
              value=${modelFilter}
              onchange=${e => setQuery({ model: e.target.value })}
            >
              <option value="">All models</option>
              ${modelOptions.map(m => html`<option key=${m} value=${m}>${m}</option>`)}
            </select>
          ` : null}
        </div>
      </div>

      <${ModelCards} jobs=${scopedJobs} sweeps=${scopedSweeps} onOpen=${openModel} now=${now} />

      <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(380px,1fr));gap:var(--space-4);margin-top:var(--space-4);align-items:start">
        <div data-testid="dashboard-running-column">
          <div class="section-header" style="margin-bottom:var(--space-2)">
            <span class="section-title" style="font-size:var(--font-size-sm)">Running now</span>
            <span class="text-dim" style="font-size: var(--font-size-xs)">
              ${live.length} job${live.length !== 1 ? 's' : ''}
            </span>
          </div>
          ${live.length === 0
            ? html`
              <div class="empty-state card" style="padding:var(--space-4)" data-testid="dashboard-running-empty">
                <p class="text-dim" style="margin:0">
                  ${finished.length > 0
                    ? html`No active jobs. ${finished.length} finished in the last 24 h — start another with <code>aiperf kube run</code>.`
                    : modelFilter
                      ? html`No active jobs for this model. <button type="button" class="nav-tab" onclick=${clearModel} style="font-size:var(--font-size-xs);padding:2px 8px">Clear filter</button>`
                      : html`No active jobs. Start a benchmark with <code>aiperf kube run</code>.`}
                </p>
              </div>
            `
            : live.map(job => html`<${LiveJobCard} key=${job.namespace + '/' + job.name} job=${job} />`)}
        </div>

        <div data-testid="dashboard-finished-column">
          <div class="section-header" style="margin-bottom:var(--space-2)">
            <span class="section-title" style="font-size:var(--font-size-sm)">Finished in the last 24 h</span>
            <button type="button" class="nav-tab" onclick=${() => navigate('/jobs')} style="font-size: var(--font-size-xs);padding:4px 10px;">View All →</button>
          </div>
          ${recent.length === 0 ? html`
            <div class="empty-state card" style="padding:var(--space-4)" data-testid="dashboard-finished-empty">
              <p class="text-dim" style="margin:0">
                Nothing finished in the last 24 h${modelFilter ? ' for this model' : ''}. Older runs are on the
                <button type="button" class="nav-tab" onclick=${() => navigate('/jobs')} style="font-size:var(--font-size-xs);padding:2px 8px">Jobs</button> page.
              </p>
            </div>
          ` : html`
            <table class="compare-table" data-testid="dashboard-finished-table">
              <thead>
                <tr>
                  <th>Job</th>
                  <th style="width:96px">Phase</th>
                  <th style="width:160px">Throughput</th>
                  <th style="text-align:right">TTFT</th>
                  <th style="text-align:right">Out tok/s</th>
                  <th style="text-align:right">Finished</th>
                </tr>
              </thead>
              <tbody>
                ${recent.map((job, i) => {
                  const run = deriveRun(job);
                  const newRun = i === 0 || deriveRun(recent[i - 1]) !== run;
                  const group = newRun ? runGroups.find(g => g.run === run) : null;
                  const tpsVal = job.throughputRps ?? 0;
                  const tpsPct = maxThroughput > 0 ? (tpsVal / maxThroughput) * 100 : 0;
                  const mColor = modelColor(job.model);
                  const goToLb = () => navigate(buildJobPath(job));
                  const phase = job.phase ?? 'Unknown';
                  const phaseClr = phaseColor(phase);
                  const endedTs = job.completionTime ?? job.created ?? job.startTime ?? null;
                  const outTokTps = job.outputTokenThroughputTps ?? job.tokenThroughput ?? null;
                  const badge = childBadge(job);

                  return html`
                    ${group ? html`
                      <tr key=${'run:' + run} data-testid=${'dashboard-run-header-' + run}>
                        <td colspan="6" style="padding:8px 8px 4px 8px;font-size:var(--font-size-xs);color:${palette.sub};border-bottom:1px solid ${palette.border}">
                          <span style="font-weight:600;color:${palette.text}">${run}</span>
                          <span class="text-dim"> · ${group.items.length} job${group.items.length === 1 ? '' : 's'}</span>
                          ${group.failed > 0 ? html`<span style="color:${palette.red}"> · ${group.failed} failed</span>` : null}
                          ${job.model ? html`<span class="text-dim" title=${job.model}> · ${shortModel(job.model)}</span>` : null}
                        </td>
                      </tr>
                    ` : null}
                    <tr
                      key=${job.namespace + '/' + job.name}
                      role="button"
                      tabindex="0"
                      aria-label=${'Open job ' + job.namespace + '/' + job.name}
                      onclick=${goToLb}
                      onkeydown=${e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); goToLb(); } }}
                      onfocus=${e => { e.currentTarget.style.outline = '2px solid ' + palette.accent; e.currentTarget.style.outlineOffset = '-2px'; }}
                      onblur=${e => { e.currentTarget.style.outline = ''; e.currentTarget.style.outlineOffset = ''; }}
                      style="cursor:pointer"
                    >
                      <td>
                        <div class="model-cell">
                          <span class="model-color" style="background:${mColor}"></span>
                          <span
                            class="model-name"
                            title=${(job.model ?? job.name) + ' — ' + job.namespace + '/' + job.name}
                            style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:220px;display:inline-block;vertical-align:middle"
                          >${job.name}</span>
                          ${badge ? html`<span class="meta-pill" title=${'Sweep child: ' + badge} style="margin-left:4px">${badge}</span>` : null}
                        </div>
                      </td>
                      <td>
                        <span class="phase-badge" style=${'background: ' + phaseClr + '22; color: ' + phaseClr + '; border-color: ' + phaseClr + '44'}>${phase}</span>
                      </td>
                      <td title=${BAR_SCALE_HINT}>
                        <div class="bar-cell">
                          <div class="inline-bar">
                            <div class="inline-bar-fill" style="width:${tpsPct}%;background:${palette.accent}"></div>
                          </div>
                          <span class="bar-val">${job.throughputRps != null ? fmtThroughput(tpsVal) + ' req/s' : '---'}</span>
                        </div>
                      </td>
                      <td style="text-align:right;font-variant-numeric:tabular-nums">${job.ttftMs != null ? fmtMilliseconds(job.ttftMs) + ' ms' : '---'}</td>
                      <td style="text-align:right;font-variant-numeric:tabular-nums">${outTokTps != null ? fmtInt(outTokTps) : '---'}</td>
                      <td style="text-align:right;font-variant-numeric:tabular-nums" class="text-dim">
                        ${endedTs ? html`<${RelativeTime} ts=${endedTs} suffix="ago" />` : '---'}
                      </td>
                    </tr>
                  `;
                })}
              </tbody>
            </table>
          `}
        </div>
      </div>

      <${ThroughputLatencyScatter} completedJobs=${completed} />

      <!-- Section 3: Metric cards -->
      <div class="metrics-row">
        <${KpiCard} label="Running" value=${running.length} />
        <${KpiCard} label="Completed" value=${completed.length} color=${palette.green} />
        <${KpiCard} label="Peak Throughput" value=${best.value != null ? fmtThroughput(best.value) : '---'} unit=${best.value != null ? 'req/s' : ''} sub=${recordSub(best)} title=${recordTitle(best, 'Highest request throughput')} />
        <${KpiCard} label="Best TTFT" value=${bestTtft.value != null ? fmtMilliseconds(bestTtft.value) : '---'} unit=${bestTtft.value != null ? 'ms' : ''} sub=${recordSub(bestTtft)} title=${recordTitle(bestTtft, 'Lowest time to first token')} />
        <${KpiCard} label="Token Throughput" value=${bestTokenTps.value != null ? fmtInt(bestTokenTps.value) : '---'} unit=${bestTokenTps.value != null ? 'tok/s' : ''} sub=${recordSub(bestTokenTps)} title=${recordTitle(bestTokenTps, 'Highest output token throughput')} />
      </div>
      <div class="text-dim" style="font-size: var(--font-size-xs);margin-top:-8px;margin-bottom:var(--space-4);padding:0 4px">
        <span title="Time To First Token: latency from request send to first streamed token (lower is better)">TTFT</span> = time to first token,
        <span title="Inter-Token Latency: average time between successive output tokens">ITL</span> = inter-token latency,
        <span title="99th-percentile end-to-end request latency (lower is better)">P99</span> = 99th-percentile latency.
      </div>

      `}
    </div>
  `;
}
