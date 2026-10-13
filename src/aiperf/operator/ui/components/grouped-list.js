// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Collapsible grouped sections for the Jobs and Sweeps lists.
//
// ``GroupedList`` is a plain render function (no hooks) so a page can call it
// directly and keep every row inside the page's own render tree; the
// collapsed state it needs comes from ``useCollapsedGroups`` which the page
// owns. ``JobGroupBody`` folds sweep children under one expandable row per
// sweep and hands standalone jobs to the regular ``JobTable``.

import { html } from 'htm/preact';
import { useState } from 'preact/hooks';
import { phaseColor } from '../lib/theme.js';
import { fmtInt, fmtReqPerSecond } from '../lib/format.js';
import { navigate } from '../lib/router.js';
import { collapseSweepChildren } from '../lib/grouping.js';
import { JobTable } from './job-table.js';
import { RelativeTime } from './time.js';

// One localStorage entry per (page.facet, group key) holding ``'1'`` while the
// group is collapsed. Absent = expanded, so a fresh browser shows everything.
export const COLLAPSED_STORAGE_PREFIX = 'aiperf-ui-v1.grouped-list.collapsed.';

export const FACET_LABELS = {
  model: 'model',
  run: 'run',
  scenario: 'scenario',
  lifecycle: 'lifecycle',
  deploy: 'deploy',
  sweep: 'sweep',
};

// Items without a value for the facet collect under ``key: null``; give that
// bucket a stable id that cannot collide with a real value.
const NONE_ID = '\u0000none';

export function groupId(groupKey) {
  return groupKey == null ? NONE_ID : String(groupKey);
}

export function collapsedStorageKey(storageKey, groupKey) {
  return COLLAPSED_STORAGE_PREFIX + String(storageKey ?? '') + '.' + groupId(groupKey);
}

export function readCollapsed(storageKey, groupKey) {
  try {
    if (typeof localStorage === 'undefined') return false;
    return localStorage.getItem(collapsedStorageKey(storageKey, groupKey)) === '1';
  } catch {
    return false;
  }
}

export function writeCollapsed(storageKey, groupKey, collapsed) {
  try {
    if (typeof localStorage === 'undefined') return;
    const k = collapsedStorageKey(storageKey, groupKey);
    if (collapsed) localStorage.setItem(k, '1');
    else localStorage.removeItem(k);
  } catch { /* quota / private mode — the toggle still works for this session */ }
}

// Page-level hook: ``[isCollapsed(groupKey), toggle(groupKey)]``. Storage is
// consulted on every read so groups that appear after mount (polling) pick up
// their remembered state too; session toggles override storage.
export function useCollapsedGroups(storageKey) {
  const [overrides, setOverrides] = useState(() => new Map());
  const id = (groupKey) => String(storageKey ?? '') + '\u0000' + groupId(groupKey);
  function isCollapsed(groupKey) {
    const k = id(groupKey);
    return overrides.has(k) ? overrides.get(k) : readCollapsed(storageKey, groupKey);
  }
  function toggle(groupKey) {
    const next = !isCollapsed(groupKey);
    writeCollapsed(storageKey, groupKey, next);
    setOverrides((prev) => {
      const m = new Map(prev);
      m.set(id(groupKey), next);
      return m;
    });
  }
  return [isCollapsed, toggle];
}

// Heading text for a group: its value, or ``(no <facet>)`` for the trailing
// unlabeled bucket.
export function groupHeading(group, facet) {
  if (group?.key == null) {
    const label = FACET_LABELS[facet] ?? facet;
    return label && facet !== 'none' ? `(no ${label})` : 'All';
  }
  return String(group.label ?? group.key);
}

function finite(v) {
  const n = typeof v === 'number' ? v : (typeof v === 'string' && v.trim() !== '' ? Number(v) : NaN);
  return Number.isFinite(n) ? n : null;
}

// Best throughput across ``items`` with its unit. Token throughput wins when
// any item reports it (that is the number operators compare); otherwise the
// request rate. Null when nothing is measured yet.
export function throughputSummary(items) {
  let tok = null;
  let req = null;
  for (const it of items ?? []) {
    const t = finite(it?.outputTokenThroughputTps ?? it?.output_token_throughput_tps);
    if (t != null && (tok == null || t > tok)) tok = t;
    const r = finite(it?.throughputRps ?? it?.throughput_rps);
    if (r != null && (req == null || r > req)) req = r;
  }
  if (tok != null) return { value: tok, unit: 'tok/s', text: fmtInt(tok) + ' tok/s' };
  if (req != null) return { value: req, unit: 'req/s', text: fmtReqPerSecond(req) + ' req/s' };
  return null;
}

// The one running item of a group, or null when zero or several are running
// (several would need a table, not a header hint).
export function singleRunning(group) {
  const running = group?.running ?? [];
  return running.length === 1 ? running[0] : null;
}

// Progress label for a running item; null when the API reports none.
export function progressText(item) {
  const pct = finite(item?.progressPercent ?? item?.progress_percent);
  if (pct == null) return null;
  const shown = pct >= 100 ? 100 : Math.max(0, Math.min(99, Math.round(pct)));
  return shown + '%';
}

function slug(s) {
  return String(s ?? '').replace(/[^A-Za-z0-9_-]+/g, '-');
}

// Hook-free, so callers invoke these directly and the chips stay in the
// caller's render tree (which is what the node harnesses inspect).
function CountChips({ counts }) {
  const specs = [['running', 'Running'], ['completed', 'Completed'], ['failed', 'Failed']];
  return specs
    .filter(([k]) => (counts?.[k] ?? 0) > 0)
    .map(([k, phase]) => {
      const color = phaseColor(phase);
      return html`
        <span
          key=${k}
          class="phase-badge grouped-list__chip"
          style=${'background:' + color + '22;color:' + color + ';border-color:' + color + '44'}
          data-testid=${'group-count-' + k}
        >${counts[k]} ${k}</span>
      `;
    });
}

function SummaryHints({ summary, items }) {
  const one = singleRunning(summary);
  const tp = throughputSummary(items);
  const latest = summary?.latestStart ?? 0;
  return html`
    ${one && html`
      <span class="grouped-list__meta grouped-list__meta--running" title=${'Running: ' + (one.name ?? '')}>
        <span aria-hidden="true">▶</span> ${one.name}${progressText(one) ? ' · ' + progressText(one) : ''}
      </span>
    `}
    ${tp && html`<span class="grouped-list__meta" title="Best throughput in this group">best ${tp.text}</span>`}
    ${latest > 0 && html`<span class="grouped-list__meta">started <${RelativeTime} ts=${latest} suffix="ago" /></span>`}
  `;
}

/**
 * Render one collapsible section per group. Plain function: call it as
 * ``${GroupedList({...})}`` from a page that owns ``useCollapsedGroups``.
 *
 * @param {object} props
 * @param {Array} props.groups      - output of ``groupItems`` (lib/grouping.js)
 * @param {Function} props.renderGroup - ``(group) => vnode`` for an open body
 * @param {Function} props.isCollapsed - ``(groupKey) => boolean``
 * @param {Function} props.onToggle    - ``(groupKey) => void``
 * @param {string} props.facet       - group key, for the ``(no <facet>)`` label
 * @param {string} props.storageKey  - namespaces the DOM ids
 * @param {string} [props.itemNoun]  - ``job`` / ``sweep`` for the total label
 * @param {string} [props.testidPrefix]
 */
export function GroupedList({ groups, renderGroup, isCollapsed, onToggle, facet, storageKey, itemNoun = 'item', testidPrefix = 'group' }) {
  return html`
    <div class="grouped-list" data-testid=${testidPrefix + '-list'}>
      ${(groups ?? []).map((g) => {
        const id = groupId(g.key);
        const open = !isCollapsed(g.key);
        const heading = groupHeading(g, facet);
        const bodyId = 'grouped-' + slug(storageKey) + '-' + slug(id);
        const total = g.total ?? (g.items ?? []).length;
        return html`
          <section
            key=${id}
            class=${'card grouped-list__group' + (open ? '' : ' grouped-list__group--collapsed')}
            data-testid=${testidPrefix + '-' + (g.key == null ? 'none' : g.key)}
          >
            <button
              type="button"
              class="grouped-list__header"
              aria-expanded=${open}
              aria-controls=${bodyId}
              title=${(open ? 'Collapse ' : 'Expand ') + heading}
              onclick=${() => onToggle(g.key)}
              data-testid=${testidPrefix + '-toggle-' + (g.key == null ? 'none' : g.key)}
            >
              <span class="grouped-list__caret" aria-hidden="true">${open ? '▾' : '▸'}</span>
              <span class="grouped-list__title">${heading}</span>
              <span class="grouped-list__total">${total} ${itemNoun}${total === 1 ? '' : 's'}</span>
              ${CountChips({ counts: g.counts })}
              ${SummaryHints({ summary: g, items: g.items })}
            </button>
            ${open && html`<div id=${bodyId} class="grouped-list__body">${renderGroup(g)}</div>`}
          </section>
        `;
      })}
    </div>
  `;
}

// One folded sweep inside a job group: a row that expands to its children.
export function SweepFoldRow({ entry, sort, onSortChange, onRowClick, onNamespaceClick }) {
  const [open, setOpen] = useState(false);
  const ns = entry?.namespace ?? '';
  const name = entry?.sweep ?? '';
  const items = entry?.items ?? [];
  const detail = `/sweeps/${encodeURIComponent(ns)}/${encodeURIComponent(name)}`;
  const bodyId = 'fold-body-' + slug(ns) + '-' + slug(name);
  return html`
    <div class="grouped-list__sweep" data-testid=${'sweep-fold-' + ns + '-' + name}>
      <div class="grouped-list__sweep-row">
        <button
          type="button"
          class="grouped-list__sweep-toggle"
          aria-expanded=${open}
          aria-controls=${bodyId}
          title=${(open ? 'Hide' : 'Show') + ' the ' + items.length + ' children of sweep ' + name}
          onclick=${() => setOpen((v) => !v)}
          data-testid=${'sweep-fold-toggle-' + ns + '-' + name}
        >
          <span class="grouped-list__caret" aria-hidden="true">${open ? '▾' : '▸'}</span>
          <span class="meta-pill__prefix">sweep</span>
          <span class="grouped-list__sweep-name">${name}</span>
          <span class="grouped-list__total">· ${items.length} ${items.length === 1 ? 'child' : 'children'}</span>
        </button>
        ${CountChips({ counts: entry?.counts })}
        ${SummaryHints({ summary: entry, items })}
        <a
          class="grouped-list__sweep-link"
          href=${'#' + detail}
          title=${'Open sweep ' + name}
          onclick=${(e) => { e.preventDefault(); navigate(detail); }}
        >open sweep ↗</a>
      </div>
      ${open && html`
        <div id=${bodyId} class="grouped-list__sweep-children">
          <${JobTable}
            jobs=${items}
            sort=${sort}
            onSortChange=${onSortChange}
            onRowClick=${onRowClick}
            onNamespaceClick=${onNamespaceClick}
          />
        </div>
      `}
    </div>
  `;
}

// Body of one job group: folded sweeps first, then the standalone jobs in a
// regular ``JobTable``. With ``foldSweeps=false`` (grouping by sweep already
// separates children) every job goes straight into the table.
export function JobGroupBody({ items, foldSweeps = true, sort, onSortChange, onRowClick, onNamespaceClick }) {
  const entries = foldSweeps ? collapseSweepChildren(items) : [];
  const standalone = foldSweeps ? entries.filter((e) => e.kind === 'job').map((e) => e.job) : (items ?? []);
  const folded = entries.filter((e) => e.kind === 'sweep');
  return html`
    <div class="grouped-list__jobs">
      ${folded.map((entry) => html`
        <${SweepFoldRow}
          key=${(entry.namespace ?? '') + '/' + entry.sweep}
          entry=${entry}
          sort=${sort}
          onSortChange=${onSortChange}
          onRowClick=${onRowClick}
          onNamespaceClick=${onNamespaceClick}
        />
      `)}
      ${standalone.length > 0 && html`
        <${JobTable}
          jobs=${standalone}
          sort=${sort}
          onSortChange=${onSortChange}
          onRowClick=${onRowClick}
          onNamespaceClick=${onNamespaceClick}
        />
      `}
    </div>
  `;
}
