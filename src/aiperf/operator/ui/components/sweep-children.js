// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Inline children of one sweep on the Sweeps list page. Loads
// ``/api/v1/sweeps/<ns>/<name>/children`` when mounted (i.e. when the row is
// expanded). The manifest rows there are not AIPerfJobInfo — they carry the
// variation index/label, trial and run epoch but no phase — so they render in
// a compact table; a job-shaped payload (an operator that returns live job
// summaries) goes through the regular ``JobTable`` instead.

import { html } from 'htm/preact';
import { useEffect, useState } from 'preact/hooks';
import { api } from '../lib/api.js';
import { buildJobPath, navigate } from '../lib/router.js';
import { phaseColor } from '../lib/theme.js';
import { JobTable } from './job-table.js';
import { LoadingPanel } from './spinner.js';

export function isJobShaped(items) {
  const list = items ?? [];
  return list.length > 0 && list.every((c) => c && typeof c === 'object' && typeof c.phase === 'string');
}

function pick(c, camel, snake) {
  const v = c?.[camel];
  if (v != null && v !== '') return v;
  const w = c?.[snake];
  return w != null && w !== '' ? w : null;
}

export function childVariation(c) {
  const label = pick(c, 'variationLabel', 'variation_label');
  if (label) return String(label);
  const idx = pick(c, 'variationIndex', 'variation_index');
  return idx != null ? 'v' + String(idx).padStart(2, '0') : '---';
}

export function childTrial(c) {
  const t = pick(c, 'trialIndex', 'trial_index');
  return t != null ? String(t) : '---';
}

export function childEpoch(c) {
  return pick(c, 'childRunEpoch', 'child_run_epoch');
}

// Children in variation order (then trial) regardless of manifest order.
export function sortChildren(children) {
  const num = (v) => { const n = Number(v); return Number.isFinite(n) ? n : 0; };
  return [...(children ?? [])].sort((a, b) =>
    num(pick(a, 'variationIndex', 'variation_index')) - num(pick(b, 'variationIndex', 'variation_index'))
    || num(pick(a, 'trialIndex', 'trial_index')) - num(pick(b, 'trialIndex', 'trial_index')));
}

export function describeChildrenError(raw) {
  const s = String(raw ?? '');
  if (/API 404/.test(s)) return 'children manifest not found — this sweep has no persisted epoch yet';
  if (/API 401|API 403/.test(s)) return 'no permission to read sweep children';
  if (/API 503|API 502|API 504/.test(s)) return 'operator unreachable';
  if (/Failed to fetch|NetworkError|ECONNREFUSED/i.test(s)) return 'network error reaching operator API';
  return s;
}

function childPath(c) {
  return buildJobPath({ ...c, childRunEpoch: childEpoch(c) });
}

function PhaseCell({ phase }) {
  if (!phase) return html`<span class="text-dim" title="Phase is not part of the children manifest; open the job for its status">—</span>`;
  const color = phaseColor(phase);
  return html`
    <span class="phase-badge" style=${'background: ' + color + '22; color: ' + color + '; border-color: ' + color + '44'}>
      ${phase}
    </span>
  `;
}

function ChildrenTable({ children, namespace, name, phaseOf }) {
  function openChild(c) {
    navigate(childPath(c));
  }
  return html`
    <table class="job-table sweep-children__table" data-testid=${'sweep-children-table-' + namespace + '-' + name}>
      <thead>
        <tr>
          <th class="job-table-th">Name</th>
          <th class="job-table-th">Variation</th>
          <th class="job-table-th">Trial</th>
          <th class="job-table-th">Phase</th>
          <th class="job-table-th">Run epoch</th>
          <th class="job-table-th"></th>
        </tr>
      </thead>
      <tbody>
        ${sortChildren(children).map((c) => {
          const path = childPath(c);
          return html`
            <tr
              key=${(c.namespace ?? namespace) + '/' + c.name + '/' + (childEpoch(c) ?? '')}
              class="job-table-row"
              role="row"
              tabindex="0"
              style="cursor: pointer"
              onkeydown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); openChild(c); } }}
              onclick=${() => openChild(c)}
              data-testid=${'sweep-child-row-' + (c.namespace ?? namespace) + '-' + (c.name ?? '')}
            >
              <td class="job-table-td job-table-name">${c.name}</td>
              <td class="job-table-td">${childVariation(c)}</td>
              <td class="job-table-td">${childTrial(c)}</td>
              <td class="job-table-td"><${PhaseCell} phase=${phaseOf ? phaseOf(c.namespace ?? namespace, c.name) : null} /></td>
              <td class="job-table-td text-dim">${childEpoch(c) ?? '---'}</td>
              <td class="job-table-td">
                <a
                  href=${'#' + path}
                  title=${'Open job ' + (c.name ?? '')}
                  onclick=${(e) => { e.stopPropagation(); e.preventDefault(); openChild(c); }}
                >open ↗</a>
              </td>
            </tr>
          `;
        })}
      </tbody>
    </table>
  `;
}

/**
 * @param {object} props
 * @param {string} props.namespace
 * @param {string} props.name
 * @param {Function} [props.phaseOf] - ``(ns, jobName) => phase|null`` from the
 *   jobs list already in memory, so manifest rows can still show a phase.
 */
export function SweepChildren({ namespace, name, phaseOf }) {
  const [state, setState] = useState({ status: 'loading', children: [], error: null });

  useEffect(() => {
    let cancelled = false;
    setState({ status: 'loading', children: [], error: null });
    api.getSweepChildren(namespace, name)
      .then((d) => {
        if (cancelled) return;
        setState({ status: 'ready', children: d?.children ?? [], error: null });
      })
      .catch((err) => {
        if (cancelled) return;
        setState({ status: 'error', children: [], error: describeChildrenError(err?.message ?? err) });
      });
    return () => { cancelled = true; };
  }, [namespace, name]);

  const testid = 'sweep-children-' + namespace + '-' + name;
  if (state.status === 'loading') {
    return html`<div class="sweep-children" data-testid=${testid}>
      <${LoadingPanel} label="Loading children…" inline=${true} size="sm" testid=${testid + '-loading'} />
    </div>`;
  }
  if (state.status === 'error') {
    return html`<div class="sweep-children sweep-children--error" data-testid=${testid}>
      <span data-testid=${testid + '-error'}>Failed to load children: ${state.error}</span>
    </div>`;
  }
  if (state.children.length === 0) {
    return html`<div class="sweep-children text-dim" data-testid=${testid}>
      <span data-testid=${testid + '-empty'}>No children recorded for this sweep yet.</span>
    </div>`;
  }
  return html`
    <div class="sweep-children" data-testid=${testid}>
      ${isJobShaped(state.children)
        ? html`<${JobTable} jobs=${state.children} onRowClick=${(j) => navigate(buildJobPath(j))} />`
        : ChildrenTable({ children: state.children, namespace, name, phaseOf })}
    </div>
  `;
}
