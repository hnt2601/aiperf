// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Pure helpers for grouping and faceting the Jobs / Sweeps / Dashboard lists.
//
// A flat list stops being navigable once several models each run several
// scenarios at the same time. These helpers derive a small set of facets per
// item — model, run, scenario, lifecycle, deploy, parent sweep — from
// (1) the ``labels`` map the API ships (``aiperf.nvidia.com/*`` plus any
// operator-configured prefixes such as ``perfledger.fptcloud.vn/*``) and
// (2) a name-convention fallback for jobs created without labels, then group
// and collapse the list for display.
//
// Everything here is dependency-free so it can be spliced into bare-node
// test harnesses (see tests/ui/test_operator_grouping_js.py). Both camelCase
// (jobs API) and snake_case (sweeps API) field spellings are accepted.

export const GROUP_KEYS = ['none', 'model', 'run', 'scenario', 'sweep'];

// Label suffixes looked up under every allowed prefix, first match wins.
// ``aiperf.nvidia.com/sweep-name`` is what the operator stamps on sweep
// children; the rest are the PerfLedger conventions.
const LABEL_SUFFIXES = {
  run: ['run'],
  scenario: ['scenario', 'profile'],
  lifecycle: ['lifecycle'],
  deploy: ['deploy', 'deployment'],
  // not ``sweep``: PerfLedger stamps ``…/sweep`` = sweep *id* on every point job.
  sweep: ['sweep-name'],
};

// ``<run>-c<conc>-<sweep6>``: a single PerfLedger point job.
const POINT_RE = /^(?<run>[a-z0-9][a-z0-9-]*?)-c(?<conc>\d+)-(?<sweep6>[0-9a-f]{6})$/;
// ``<run>-<sweep6>-vNN[-tK]``: a child of an AIPerfSweep named ``<run>-<sweep6>``.
const CHILD_RE = /^(?<sweep>(?<run>[a-z0-9][a-z0-9-]*?)-(?<sweep6>[0-9a-f]{6}))-v(?<idx>\d{2})(?:-t(?<trial>\d+))?$/;
// ``<run>-<sweep6>``: an AIPerfSweep created by PerfLedger.
const SWEEP_RE = /^(?<run>[a-z0-9][a-z0-9-]*?)-(?<sweep6>[0-9a-f]{6})$/;

function labelsOf(item) {
  const l = item?.labels;
  return l && typeof l === 'object' ? l : {};
}

// First label whose key ends in ``/<suffix>`` for any suffix of ``facet``.
export function labelValue(item, facet) {
  const suffixes = LABEL_SUFFIXES[facet] ?? [facet];
  const labels = labelsOf(item);
  for (const suffix of suffixes) {
    for (const [k, v] of Object.entries(labels)) {
      const slash = k.lastIndexOf('/');
      if (k.slice(slash + 1) === suffix && v != null && v !== '') return String(v);
    }
  }
  return null;
}

// Decode a PerfLedger-style name. Returns ``null`` for names outside the
// convention so callers fall back to the bare name.
export function parseName(name) {
  const s = String(name ?? '');
  let m = s.match(CHILD_RE);
  if (m) {
    return {
      kind: 'child',
      run: m.groups.run,
      sweep: m.groups.sweep,
      sweep6: m.groups.sweep6,
      index: Number(m.groups.idx),
      trial: m.groups.trial != null ? Number(m.groups.trial) : null,
    };
  }
  m = s.match(POINT_RE);
  if (m) {
    return { kind: 'point', run: m.groups.run, conc: Number(m.groups.conc), sweep6: m.groups.sweep6 };
  }
  m = s.match(SWEEP_RE);
  if (m) {
    return { kind: 'sweep', run: m.groups.run, sweep6: m.groups.sweep6 };
  }
  return null;
}

function field(item, camel, snake) {
  const v = item?.[camel];
  if (v != null && v !== '') return v;
  const w = item?.[snake];
  return w != null && w !== '' ? w : null;
}

// Parent sweep name for a job, or ``null`` for a standalone job.
export function sweepOf(job) {
  const api = field(job, 'sweepName', 'sweep_name');
  if (api) return String(api);
  const label = labelValue(job, 'sweep');
  if (label) return label;
  const parsed = parseName(job?.name);
  return parsed?.kind === 'child' ? parsed.sweep : null;
}

export function isSweepChild(job) {
  return sweepOf(job) != null;
}

// Run = the human intent behind one or more jobs/sweeps. Labels win; then the
// name convention; then the bare name (so every item has a run and ungrouped
// lists still work).
export function deriveRun(item) {
  const label = labelValue(item, 'run');
  if (label) return label;
  const parsed = parseName(item?.name);
  if (parsed?.run) return parsed.run;
  const sweep = sweepOf(item);
  if (sweep) {
    const p = parseName(sweep);
    if (p?.run) return p.run;
    return sweep;
  }
  return String(item?.name ?? '');
}

export function deriveScenario(item) {
  return labelValue(item, 'scenario');
}

export function deriveLifecycle(item) {
  return labelValue(item, 'lifecycle');
}

export function deriveDeploy(item) {
  return labelValue(item, 'deploy');
}

export function deriveModel(item) {
  const m = item?.model;
  return m != null && m !== '' ? String(m) : null;
}

// Value an item contributes to a ``GROUP_KEYS`` bucket. ``null`` means "no
// value" and lands in the trailing "(none)" group.
export function facetOf(item, key) {
  switch (key) {
    case 'model': return deriveModel(item);
    case 'run': return deriveRun(item);
    case 'scenario': return deriveScenario(item);
    case 'lifecycle': return deriveLifecycle(item);
    case 'deploy': return deriveDeploy(item);
    case 'sweep': return sweepOf(item);
    default: return null;
  }
}

// Coarse lifecycle bucket shared by jobs (AIPerfJob phases) and sweeps.
export function phaseBucket(phase) {
  const p = String(phase ?? '').toLowerCase();
  if (['running', 'initializing', 'pending', 'aggregating', 'queued'].includes(p)) return 'running';
  if (['completed', 'succeeded', 'archived'].includes(p)) return 'completed';
  if (['failed', 'error', 'cancelled', 'partiallyfailed'].includes(p)) return 'failed';
  return 'other';
}

function startTs(item) {
  const raw = field(item, 'startTime', 'start_time')
    ?? field(item, 'started_at', 'startedAt')
    ?? field(item, 'created', 'creation_timestamp');
  if (raw == null) return 0;
  const t = Date.parse(raw);
  return Number.isFinite(t) ? t : 0;
}

function finite(v) {
  const n = typeof v === 'number' ? v : (typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);
  return Number.isFinite(n) ? n : null;
}

function throughputOf(item) {
  return finite(field(item, 'outputTokenThroughputTps', 'output_token_throughput_tps'))
    ?? finite(field(item, 'throughputRps', 'throughput_rps'));
}

// Sorted unique values of a facet across ``items`` (nulls dropped).
export function facetValues(items, key) {
  const set = new Set();
  for (const it of items ?? []) {
    const v = facetOf(it, key);
    if (v != null) set.add(v);
  }
  return [...set].sort((a, b) => a.localeCompare(b));
}

// Apply ``{run, scenario, lifecycle, deploy, sweep}`` equality filters; empty
// or missing values are ignored.
export function applyFacetFilters(items, filters) {
  let out = items ?? [];
  for (const key of ['run', 'scenario', 'lifecycle', 'deploy', 'sweep']) {
    const want = filters?.[key];
    if (want == null || want === '') continue;
    out = out.filter(it => facetOf(it, key) === want);
  }
  return out;
}

export function summarize(items) {
  const counts = { running: 0, completed: 0, failed: 0, other: 0 };
  let best = null;
  let latestStart = 0;
  const running = [];
  for (const it of items ?? []) {
    const b = phaseBucket(it?.phase);
    counts[b] += 1;
    if (b === 'running') running.push(it);
    const tp = throughputOf(it);
    if (tp != null && (best == null || tp > best)) best = tp;
    latestStart = Math.max(latestStart, startTs(it));
  }
  return { total: (items ?? []).length, counts, running, bestThroughput: best, latestStart };
}

// Group ``items`` by one of ``GROUP_KEYS``. Groups are ordered by most recent
// start (so what is happening now is on top); items without a value for the
// key collect in a final ``{ key: null }`` group. ``'none'`` returns a single
// unlabeled group so callers can render both shapes with one code path.
export function groupItems(items, key) {
  const list = items ?? [];
  if (!key || key === 'none' || !GROUP_KEYS.includes(key)) {
    return [{ key: null, label: null, items: list, ...summarize(list) }];
  }
  const buckets = new Map();
  const none = [];
  for (const it of list) {
    const v = facetOf(it, key);
    if (v == null) { none.push(it); continue; }
    if (!buckets.has(v)) buckets.set(v, []);
    buckets.get(v).push(it);
  }
  const groups = [...buckets.entries()].map(([k, members]) => ({
    key: k, label: k, items: members, ...summarize(members),
  }));
  groups.sort((a, b) => b.latestStart - a.latestStart || a.key.localeCompare(b.key));
  if (none.length) groups.push({ key: null, label: null, items: none, ...summarize(none) });
  return groups;
}

// Fold sweep children under one row per sweep so a 7-point sweep does not
// occupy 7 rows. Order follows first appearance; standalone jobs pass through
// as ``{ kind: 'job', job }`` and each sweep becomes
// ``{ kind: 'sweep', sweep, items, ...summary }`` with children sorted by
// variation index (then trial).
export function collapseSweepChildren(jobs) {
  const out = [];
  const bySweep = new Map();
  for (const job of jobs ?? []) {
    const sweep = sweepOf(job);
    if (!sweep) { out.push({ kind: 'job', job }); continue; }
    if (!bySweep.has(sweep)) {
      const entry = { kind: 'sweep', sweep, namespace: job?.namespace ?? null, items: [] };
      bySweep.set(sweep, entry);
      out.push(entry);
    }
    bySweep.get(sweep).items.push(job);
  }
  for (const entry of bySweep.values()) {
    entry.items.sort((a, b) => childOrder(a) - childOrder(b));
    Object.assign(entry, summarize(entry.items));
  }
  return out;
}

function childOrder(job) {
  const idx = finite(field(job, 'variationIndex', 'variation_index'));
  const trial = finite(field(job, 'trialIndex', 'trial_index')) ?? 0;
  const parsed = idx == null ? parseName(job?.name) : null;
  const i = idx ?? parsed?.index ?? 0;
  return i * 1000 + trial;
}

// Default grouping when the URL has no ``?group=``: by model as soon as more
// than one model is listed, otherwise flat (the legacy behaviour).
export function defaultGroupKey(items) {
  return facetValues(items, 'model').length > 1 ? 'model' : 'none';
}

// Validate a ``?group=`` query value.
export function parseGroupKey(raw, items) {
  const v = String(raw ?? '').toLowerCase();
  if (GROUP_KEYS.includes(v)) return v;
  return defaultGroupKey(items);
}

// ``<sweep>·v03`` style badge text for a sweep child, ``null`` otherwise.
export function childBadge(job) {
  const sweep = sweepOf(job);
  if (!sweep) return null;
  const idx = finite(field(job, 'variationIndex', 'variation_index')) ?? parseName(job?.name)?.index ?? null;
  const trial = finite(field(job, 'trialIndex', 'trial_index'));
  let s = sweep;
  if (idx != null) s += `·v${String(idx).padStart(2, '0')}`;
  if (trial != null && trial > 0) s += `·t${trial}`;
  return s;
}
