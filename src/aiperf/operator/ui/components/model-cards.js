// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Per-model summary cards for the dashboard.
//
// The dashboard answers "what is the cluster doing right now, and what did it
// finish today?". One card per model folds every job and sweep of that model
// into a handful of counts over a 24 h window. The helpers above the
// components are pure (``now`` is injected) so
// tests/ui/test_operator_model_cards_js.py can evaluate them in bare node with
// the preact imports stripped and ``lib/grouping.js`` loaded for real.

import { html } from 'htm/preact';
import { useState } from 'preact/hooks';
import { groupItems, phaseBucket } from '../lib/grouping.js';
import { NsPill } from './pills.js';
import { palette } from '../lib/theme.js';
import { fmtNumber } from '../lib/format.js';

/** Window the dashboard shows: running jobs plus anything that ended in the last 24 h. */
export const DASHBOARD_WINDOW_MS = 24 * 60 * 60 * 1000;

const QUEUED_PHASES = new Set(['pending', 'queued', 'initializing']);

export const shortModel = (m) => (m ? String(m).split('/').pop() : null);

function parseTs(raw) {
  if (raw == null || raw === '') return 0;
  const t = typeof raw === 'number' ? raw : Date.parse(raw);
  return Number.isFinite(t) ? t : 0;
}

function field(item, camel, snake) {
  const v = item?.[camel];
  if (v != null && v !== '') return v;
  const w = item?.[snake];
  return w != null && w !== '' ? w : null;
}

/** Wall-clock ms at which a job ended (falls back to start / creation). */
export function jobEndTs(job) {
  return parseTs(field(job, 'completionTime', 'completion_time'))
    || parseTs(field(job, 'startTime', 'start_time'))
    || parseTs(field(job, 'created', 'creation_timestamp'));
}

export function isLiveJob(job) {
  return phaseBucket(job?.phase) === 'running';
}

export function isQueuedJob(job) {
  return QUEUED_PHASES.has(String(job?.phase ?? '').toLowerCase());
}

/** Terminal (completed or failed) and ended inside ``windowMs`` of ``now``. */
export function finishedWithin(job, now, windowMs = DASHBOARD_WINDOW_MS) {
  const b = phaseBucket(job?.phase);
  if (b !== 'completed' && b !== 'failed') return false;
  const end = jobEndTs(job);
  return end > 0 && end >= now - windowMs && end <= now + 60_000;
}

/** Jobs the dashboard shows at all: live, or finished inside the window. */
export function dashboardJobs(jobs, now, windowMs = DASHBOARD_WINDOW_MS) {
  return (jobs ?? []).filter(j => j && (isLiveJob(j) || finishedWithin(j, now, windowMs)));
}

export function liveJobs(jobs) {
  return (jobs ?? []).filter(j => j && isLiveJob(j));
}

export function finishedJobsWithin(jobs, now, windowMs = DASHBOARD_WINDOW_MS) {
  return (jobs ?? []).filter(j => j && finishedWithin(j, now, windowMs));
}

function sweepProgress(sweep) {
  const total = Number(field(sweep, 'totalVariations', 'total_variations')) || 0;
  const completed = Number(field(sweep, 'completedRuns', 'completed_runs')) || 0;
  const failed = Number(field(sweep, 'failedRuns', 'failed_runs')) || 0;
  return {
    name: String(sweep?.name ?? ''),
    namespace: sweep?.namespace ?? null,
    completed,
    failed,
    total,
    phase: sweep?.phase ?? null,
  };
}

/**
 * One summary per model, newest activity first.
 *
 * @param {object[]} jobs    jobs API items (camelCase)
 * @param {object[]} sweeps  sweeps API items (snake_case), may be empty
 * @param {number}   now     wall-clock ms (injected so tests are deterministic)
 * @param {number}   windowMs
 * @returns {{model, namespaces, running, queued, completed24h, failed24h,
 *            sweeps: {name, completed, total, phase}[], bestThroughput,
 *            latestStart, idle}[]}
 */
export function modelCardsData(jobs, sweeps, now = Date.now(), windowMs = DASHBOARD_WINDOW_MS) {
  const runningSweeps = new Map();
  for (const s of sweeps ?? []) {
    const model = s?.model;
    if (!model || phaseBucket(s?.phase) !== 'running') continue;
    if (!runningSweeps.has(model)) runningSweeps.set(model, []);
    runningSweeps.get(model).push(sweepProgress(s));
  }

  const cards = [];
  for (const g of groupItems(jobs ?? [], 'model')) {
    if (g.key == null) continue;
    let running = 0;
    let queued = 0;
    let completed24h = 0;
    let failed24h = 0;
    const namespaces = new Set();
    for (const j of g.items) {
      if (j?.namespace) namespaces.add(String(j.namespace));
      if (isQueuedJob(j)) queued += 1;
      else if (isLiveJob(j)) running += 1;
      else if (finishedWithin(j, now, windowMs)) {
        if (phaseBucket(j.phase) === 'failed') failed24h += 1;
        else completed24h += 1;
      }
    }
    const modelSweeps = runningSweeps.get(g.key) ?? [];
    for (const s of modelSweeps) {
      if (s.namespace) namespaces.add(String(s.namespace));
    }
    const idle = running + queued + modelSweeps.length === 0 && completed24h + failed24h === 0;
    cards.push({
      model: g.key,
      namespaces: [...namespaces].sort(),
      running,
      queued,
      completed24h,
      failed24h,
      sweeps: modelSweeps,
      bestThroughput: g.bestThroughput,
      latestStart: g.latestStart,
      idle,
    });
  }
  // A sweep can be running before its first child job exists; give it a card.
  for (const [model, modelSweeps] of runningSweeps) {
    if (cards.some(c => c.model === model)) continue;
    cards.push({
      model,
      namespaces: [...new Set(modelSweeps.map(s => s.namespace).filter(Boolean))].sort(),
      running: 0,
      queued: 0,
      completed24h: 0,
      failed24h: 0,
      sweeps: modelSweeps,
      bestThroughput: null,
      latestStart: Math.max(0, ...(sweeps ?? [])
        .filter(s => s?.model === model)
        .map(s => parseTs(field(s, 'started_at', 'startedAt')))),
      idle: false,
    });
  }
  cards.sort((a, b) => b.latestStart - a.latestStart || a.model.localeCompare(b.model));
  return cards;
}

/** Split cards into the ones worth showing and the idle remainder. */
export function splitIdleCards(cards) {
  const active = [];
  const idle = [];
  for (const c of cards ?? []) (c.idle ? idle : active).push(c);
  return { active, idle };
}

/**
 * Group jobs by run (``deriveRun``) preserving first-appearance order, with a
 * ``failed`` count per group for the run header.
 */
export function groupByRun(jobs, deriveRunFn) {
  const out = [];
  const byRun = new Map();
  for (const job of jobs ?? []) {
    const run = deriveRunFn(job);
    if (!byRun.has(run)) {
      const entry = { run, items: [], failed: 0 };
      byRun.set(run, entry);
      out.push(entry);
    }
    const entry = byRun.get(run);
    entry.items.push(job);
    if (phaseBucket(job?.phase) === 'failed') entry.failed += 1;
  }
  return out;
}

function fmtThroughputShort(v) {
  if (v == null) return null;
  return v >= 100 ? fmtNumber(v, 0) : fmtNumber(v, 1);
}

export function ModelCard({ card, onOpen }) {
  const open = () => { if (typeof onOpen === 'function') onOpen(card.model); };
  const live = card.running + card.queued;
  const failedColor = card.failed24h > 0 ? palette.red : palette.muted;
  const name = shortModel(card.model);
  return html`
    <div
      class="card"
      role="button"
      tabindex="0"
      data-testid=${'model-card-' + card.model}
      aria-label=${'Open jobs for model ' + card.model}
      title=${card.model}
      onclick=${open}
      onkeydown=${e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); open(); } }}
      onfocus=${e => { e.currentTarget.style.outline = '2px solid ' + palette.accent; e.currentTarget.style.outlineOffset = '2px'; }}
      onblur=${e => { e.currentTarget.style.outline = ''; e.currentTarget.style.outlineOffset = ''; }}
      style=${'cursor:pointer;flex:0 0 auto;width:260px;min-width:220px;margin:0;padding:12px 14px;display:flex;flex-direction:column;gap:8px;' + (live > 0 ? 'border-color:' + palette.blue + '66;' : '')}
    >
      <div style="display:flex;align-items:center;gap:6px;min-width:0">
        ${live > 0 ? html`<div class="job-indicator running" aria-hidden="true"></div>` : null}
        <span class="job-name" style="font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0">${name}</span>
      </div>
      <div style="display:flex;gap:4px;flex-wrap:wrap;min-height:18px">
        ${card.namespaces.map(ns => html`<${NsPill} key=${ns} ns=${ns} testId=${'model-card-ns-' + card.model + '-' + ns} />`)}
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 10px;font-size:var(--font-size-sm);font-variant-numeric:tabular-nums">
        <span title="Jobs running right now"><span style=${'color:' + (card.running > 0 ? palette.blue : palette.muted) + ';font-weight:600'}>${card.running}</span> <span class="text-dim">running</span></span>
        <span title="Jobs pending or initializing"><span style=${'color:' + (card.queued > 0 ? palette.amber : palette.muted) + ';font-weight:600'}>${card.queued}</span> <span class="text-dim">queued</span></span>
        <span title="Jobs completed in the last 24 h"><span style=${'color:' + (card.completed24h > 0 ? palette.green : palette.muted) + ';font-weight:600'}>${card.completed24h}</span> <span class="text-dim">done 24h</span></span>
        <span title="Jobs failed in the last 24 h" data-testid=${'model-card-failed-' + card.model}><span style=${'color:' + failedColor + ';font-weight:600'}>${card.failed24h}</span> <span class="text-dim">failed 24h</span></span>
      </div>
      ${card.sweeps.length > 0 ? html`
        <div style="display:flex;flex-direction:column;gap:4px" data-testid=${'model-card-sweeps-' + card.model}>
          ${card.sweeps.map(s => {
            const pct = s.total > 0 ? Math.min(100, Math.round((s.completed / s.total) * 100)) : 0;
            return html`
              <div key=${s.name} title=${'Sweep ' + s.name + ': ' + s.completed + ' of ' + s.total + ' variations complete'}>
                <div style="display:flex;justify-content:space-between;gap:6px;font-size:var(--font-size-xs)">
                  <span class="text-dim" style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0">${s.name}</span>
                  <span style="font-variant-numeric:tabular-nums;flex:0 0 auto">${s.completed}/${s.total}</span>
                </div>
                <div class="progress-track" role="progressbar" aria-label=${'Sweep ' + s.name + ' progress'} aria-valuenow=${s.completed} aria-valuemin="0" aria-valuemax=${s.total || 1} style="margin-top:2px">
                  <div class="progress-fill" style=${'width:' + pct + '%;background:' + palette.blue}></div>
                </div>
              </div>
            `;
          })}
        </div>
      ` : null}
      ${card.bestThroughput != null ? html`
        <div class="text-dim" style="font-size:var(--font-size-xs)" title="Highest output token throughput (or req/s when tok/s is unknown) reported by any job of this model">
          best <span style=${'color:' + palette.text + ';font-variant-numeric:tabular-nums'}>${fmtThroughputShort(card.bestThroughput)}</span>
        </div>
      ` : null}
    </div>
  `;
}

/**
 * Horizontally scrolling row of per-model cards.
 *
 * Props:
 *   jobs:   jobs API items
 *   sweeps: sweeps API items (optional)
 *   onOpen: (model:string) => void
 *   now:    wall-clock ms (optional, for tests)
 */
export function ModelCards({ jobs, sweeps, onOpen, now }) {
  const [showIdle, setShowIdle] = useState(false);
  const cards = modelCardsData(jobs, sweeps, now ?? Date.now());
  const { active, idle } = splitIdleCards(cards);
  if (cards.length === 0) return null;
  const visible = showIdle ? cards : active;
  return html`
    <div data-testid="model-cards">
      ${visible.length > 0 ? html`
        <div style="display:flex;gap:12px;overflow-x:auto;padding:2px 2px 8px 2px;scroll-snap-type:x proximity">
          ${visible.map(c => html`<${ModelCard} key=${c.model} card=${c} onOpen=${onOpen} />`)}
        </div>
      ` : html`
        <div class="empty-state card" style="padding:var(--space-4)" data-testid="model-cards-idle">
          <p class="text-dim" style="margin:0">Nothing ran in the last 24 h. ${idle.length} model${idle.length === 1 ? '' : 's'} on record.</p>
        </div>
      `}
      ${idle.length > 0 ? html`
        <button
          type="button"
          class="nav-tab"
          aria-pressed=${showIdle}
          data-testid="model-cards-idle-toggle"
          onclick=${() => setShowIdle(!showIdle)}
          style="font-size:var(--font-size-xs);padding:4px 10px;margin-top:4px"
        >${showIdle ? 'Hide' : 'Show'} ${idle.length} idle model${idle.length === 1 ? '' : 's'}</button>
      ` : null}
    </div>
  `;
}
