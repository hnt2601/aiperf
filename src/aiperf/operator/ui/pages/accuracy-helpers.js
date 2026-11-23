// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Pure helpers for the ANALYZE → Accuracy page. No DOM, no Preact: unit-testable under plain node.
//
// The page reads rows from the PerfLedger read-only data route (``perfledger-api/accuracy``). Each row is one accuracy
// or behavior eval run; ``tasks`` carry a normalized ``{task, metric, direction, rate, ci, count, total, ...}`` so the
// page draws accuracy (higher is better) and behavior rates (cheat/deception rate, lower is better) the same way.

export const DIRECTION_LABEL = {
  higher_is_better: 'higher is better',
  lower_is_better: 'lower is better',
  neutral: 'neutral',
};

export const DIRECTION_GLYPH = {
  higher_is_better: '▲',
  lower_is_better: '▼',
  neutral: '◆',
};

// Shown when the API cannot supply its own ``label``. The API label (Vietnamese) is authoritative when present.
export const FALLBACK_LABEL = 'Không phải kết quả InferenceX chính thức · đo trên staging';

const UNPARSED_HIGH = 0.2;

function finite(x) {
  return typeof x === 'number' && Number.isFinite(x);
}

/** 0.6444 → "64.4%"; null / NaN → "—". */
export function fmtRate(x, digits = 1) {
  return finite(x) ? `${(x * 100).toFixed(digits)}%` : '—';
}

/** [0.618, 0.67] → "61.8–67.0%"; anything else → "—". */
export function fmtCi(ci, digits = 1) {
  if (!Array.isArray(ci) || ci.length !== 2 || !finite(ci[0]) || !finite(ci[1])) return '—';
  return `${(ci[0] * 100).toFixed(digits)}–${(ci[1] * 100).toFixed(digits)}%`;
}

/** count/total with thousands separators; "—" when total is unknown. */
export function fmtCount(count, total) {
  if (!finite(total)) return '—';
  const c = finite(count) ? count.toLocaleString('en-US') : '—';
  return `${c}/${total.toLocaleString('en-US')}`;
}

/** {pass: 6, fail: 4} → "pass 6 · fail 4" (largest first, ties by name); empty → "—". */
export function labelsText(labels) {
  const entries = Object.entries(labels ?? {}).filter(([, n]) => finite(n));
  if (!entries.length) return '—';
  entries.sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0]));
  return entries.map(([k, n]) => `${k} ${n}`).join(' · ');
}

/** Bar width in percent, clamped to [0, 100]; non-numbers → 0. */
export function barPercent(rate) {
  if (!finite(rate)) return 0;
  return Math.max(0, Math.min(100, rate * 100));
}

/** Only http(s) URLs may become links; anything else (javascript:, data:, garbage) → null. */
export function safeHttpUrl(value) {
  if (typeof value !== 'string' || !value) return null;
  try {
    const u = new URL(value);
    return u.protocol === 'http:' || u.protocol === 'https:' ? u.href : null;
  } catch {
    return null;
  }
}

/** Filters → "?benchmark=…&kind=…"; empty values are dropped. */
export function buildQuery(filters) {
  const p = new URLSearchParams();
  for (const key of ['benchmark', 'kind', 'model', 'status', 'limit']) {
    const v = filters?.[key];
    if (v !== undefined && v !== null && String(v) !== '') p.set(key, String(v));
  }
  const s = p.toString();
  return s ? `?${s}` : '';
}

/**
 * Rows → [{benchmark, kind, rows}] ordered by the newest run in each group (rows keep the server order, newest first).
 * @param {Array<object>} rows
 */
export function groupByBenchmark(rows) {
  const groups = new Map();
  for (const row of rows ?? []) {
    const key = `${row.benchmark ?? '—'}\u0000${row.kind ?? 'accuracy'}`;
    if (!groups.has(key)) groups.set(key, { benchmark: row.benchmark ?? '—', kind: row.kind ?? 'accuracy', rows: [] });
    groups.get(key).rows.push(row);
  }
  const newest = (g) => g.rows.reduce((m, r) => (String(r.recorded_at ?? '') > m ? String(r.recorded_at ?? '') : m), '');
  return [...groups.values()].sort((a, b) => newest(b).localeCompare(newest(a)) || a.benchmark.localeCompare(b.benchmark));
}

/** Plain-language caveats that must travel with the numbers of one run. */
export function rowNotes(row) {
  const notes = [];
  const flags = row.audit_flags ?? [];
  if (row.kind === 'behavior' && (row.gate?.mode ?? 'report') !== 'block') {
    notes.push('Report only: this behavior metric does not block the gate.');
  }
  if (row.status && row.status !== 'official') {
    notes.push(`Status ${row.status}: not promoted to a baseline.`);
  }
  if (row.pilot) notes.push('Pilot run.');
  if ((row.unparsed_rate ?? 0) > UNPARSED_HIGH || flags.includes('accuracy_unparsed_high')) {
    notes.push('More than 20% of answers did not follow the answer format; scores may read low (accuracy_unparsed_high).');
  }
  if ((row.grader_error_rate ?? 0) > 0) {
    notes.push(`${fmtRate(row.grader_error_rate)} of problems hit a grader error and are excluded from the totals.`);
  }
  if (isUngraded(row)) {
    notes.push(
      'Generation only (_grading: deferred): not graded yet, so there are no scores. They appear once the sandbox grading is ingested as the next attempt.',
    );
  } else if (row.grading?.mode === 'sandbox') {
    const from = row.grading.graded_from ? ` from generation ${row.grading.graded_from}` : '';
    notes.push(`Graded in a no-network sandbox${row.grading.grader ? ` (${row.grading.grader})` : ''}${from}.`);
  }
  if (!isUngraded(row) && row.overall == null && (row.tasks?.length ?? 0) > 1) {
    notes.push('Tasks measure different metrics, so there is no combined figure.');
  }
  return notes;
}

/** True for a generation-only run (``_grading: deferred``): it carries counts, never scores. */
export function isUngraded(row) {
  return row?.grading?.state === 'ungraded';
}

/** Direction → "higher is better"; a missing direction (ungraded run) → "—", never "undefined". */
export function directionText(direction) {
  return DIRECTION_LABEL[direction] ?? (direction ? String(direction) : '—');
}

export const TASK_ROWS_COLLAPSED = 12;

/** Benchmarks such as MMLU-Pro have dozens of tasks: show the first ``limit`` unless expanded. */
export function visibleTasks(tasks, expanded, limit = TASK_ROWS_COLLAPSED) {
  const all = tasks ?? [];
  return expanded || all.length <= limit ? all : all.slice(0, limit);
}

/** Percentage-point delta with an explicit sign: 83.33 → "+83.3 pp", -16.67 → "−16.7 pp", 0 → "0.0 pp"; null → "—". */
export function fmtDelta(pp, digits = 1) {
  if (!finite(pp)) return '—';
  const v = Number(pp.toFixed(digits));
  if (v === 0) return `${(0).toFixed(digits)} pp`;
  return `${v > 0 ? '+' : '−'}${Math.abs(v).toFixed(digits)} pp`;
}

/** McNemar p-value: 0.00195 → "p = 0.002", 0.0000004 → "p < 0.001", 1 → "p = 1.000"; null → "—". */
export function fmtP(p) {
  if (!finite(p)) return '—';
  return p < 0.001 ? 'p < 0.001' : `p = ${p.toFixed(3)}`;
}

/** One paired-comparison row → plain wording. ``better`` is only set by the server when the difference is statistically significant. */
export function readingText(stat) {
  if (stat?.better === 'candidate') return 'Candidate better';
  if (stat?.better === 'baseline') return 'Baseline better';
  return 'No clear difference';
}

const COMPARE_REASONS = {
  grading_deferred: 'One of the two runs is generation only and not graded yet, so there is nothing to compare.',
  benchmark_mismatch: 'The two runs use a different benchmark, n-shots, grader or behavior rules, so they cannot be compared.',
  problem_set_mismatch: 'The two runs do not cover the same problems (less than 95% in common), so they cannot be compared.',
};

/** Reason code from the compare route → sentence for the reader; unknown codes pass through. */
export function compareReasonText(reason) {
  return COMPARE_REASONS[reason] ?? (reason ? String(reason) : '');
}

/** Candidate/baseline point ids → "?candidate=…&baseline=…"; missing either → "" (no request). */
export function buildCompareQuery(candidate, baseline) {
  if (!candidate || !baseline) return '';
  const p = new URLSearchParams();
  p.set('candidate', candidate);
  p.set('baseline', baseline);
  return `?${p.toString()}`;
}

/** Short label for a run in a picker: "Qwen3.8-27B · sweep 3fa2 · attempt 2 · candidate". */
export function runLabel(row) {
  const attempt = String(row?.point_id ?? '').split('/')[1];
  const parts = [row?.model ?? row?.model_prefix ?? '—', `sweep ${row?.sweep_id ?? '—'}`];
  if (attempt) parts.push(`attempt ${attempt}`);
  if (row?.status) parts.push(row.status);
  if (isUngraded(row)) parts.push('not graded');
  return parts.join(' · ');
}

/** Judge object → "model=judge-a, prompt_sha256=ab12"; none → null. */
export function judgeText(judge) {
  if (!judge || typeof judge !== 'object') return null;
  const parts = Object.entries(judge).map(([k, v]) => `${k}=${v}`);
  return parts.length ? parts.join(', ') : null;
}

/** Actionable wording for the failures this page can actually hit. */
export function describeLoadError(raw) {
  const s = String(raw ?? '');
  if (/API 404/.test(s)) {
    return 'Accuracy data route not found — the PerfLedger data route is not deployed on this host (served only behind dashboard-subpath).';
  }
  if (/not JSON/i.test(s)) {
    return 'The server answered with something other than accuracy data — the PerfLedger data route is probably not deployed here.';
  }
  if (/API 401|API 403/.test(s)) return 'Not authorized to read accuracy data — sign in to the dashboard again.';
  if (/API 400/.test(s)) return `The request was rejected: ${s.replace(/^API 400:\s*/, '').slice(0, 160)}`;
  if (/API 502|API 503|API 504/.test(s)) return 'PerfLedger data service is unreachable or cannot read its storage — try again shortly.';
  if (/Failed to fetch|NetworkError|ECONNREFUSED/i.test(s)) return 'Network error reaching the PerfLedger data route.';
  return s;
}
