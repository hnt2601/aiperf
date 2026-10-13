// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Facet filter controls shared by the Jobs and Sweeps pages: one ``ui-select``
// per facet that has more than one value, removable chips for the facets
// currently applied, and the "Group by" picker. Facet values come from
// lib/grouping.js (labels first, name convention second).

import { html } from 'htm/preact';
import { palette } from '../lib/theme.js';
import { facetValues } from '../lib/grouping.js';

export const FACET_DEFS = [
  { key: 'run', label: 'Run', color: palette.blue },
  { key: 'scenario', label: 'Scenario', color: palette.green },
  { key: 'lifecycle', label: 'Lifecycle', color: palette.amber },
  { key: 'deploy', label: 'Deploy', color: palette.cyan },
];

export const GROUP_LABELS = {
  none: 'None',
  model: 'Model',
  run: 'Run',
  scenario: 'Scenario',
  sweep: 'Sweep',
};

function defsFor(facets) {
  const wanted = facets ?? FACET_DEFS.map((d) => d.key);
  return FACET_DEFS.filter((d) => wanted.includes(d.key));
}

// ``[{key, label, values}]`` for the facets worth a select: more than one
// value across ``items``. A filter value no longer present in the list is
// kept as an option so the select still shows what the URL says.
export function facetSelectOptions(items, facets, filters) {
  const out = [];
  for (const d of defsFor(facets)) {
    const values = facetValues(items, d.key);
    const current = filters?.[d.key];
    if (current && !values.includes(current)) values.push(current);
    if (values.length > 1) out.push({ key: d.key, label: d.label, values });
  }
  return out;
}

export function FacetSelects({ items, facets, filters, onChange, testidPrefix = '' }) {
  return facetSelectOptions(items, facets, filters).map((f) => html`
    <select
      key=${f.key}
      class="ui-select"
      aria-label=${'Filter by ' + f.label.toLowerCase()}
      value=${filters?.[f.key] ?? ''}
      onchange=${(e) => onChange(f.key, e.target.value)}
      data-testid=${testidPrefix + f.key + '-filter-select'}
    >
      <option value="">All ${f.label.toLowerCase()}s</option>
      ${f.values.map((v) => html`<option key=${v} value=${v}>${v}</option>`)}
    </select>
  `);
}

export function FacetChips({ facets, filters, onClear }) {
  return defsFor(facets)
    .filter((d) => filters?.[d.key])
    .map((d) => {
      const value = filters[d.key];
      const activate = () => onClear(d.key);
      return html`
        <span
          key=${d.key}
          class="meta-pill meta-pill--clickable"
          role="button"
          tabindex="0"
          aria-label=${'Remove ' + d.label.toLowerCase() + ' filter ' + value}
          style=${'background:' + d.color + '22;color:' + d.color + ';border-color:' + d.color + '55'}
          title=${d.label + ' filter: ' + value + ' (click to clear)'}
          onclick=${activate}
          onkeydown=${(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); activate(); } }}
          data-testid=${d.key + '-filter-chip'}
        >
          <span class="meta-pill__prefix">${d.key}</span>${value}
          <span style="margin-left:4px;opacity:0.7" aria-hidden="true">×</span>
        </span>
      `;
    });
}

export function GroupBySelect({ value, keys, onChange, testid }) {
  return html`
    <label class="list-facet-bar__groupby">
      <span class="text-dim">Group by</span>
      <select
        class="ui-select"
        aria-label="Group by"
        value=${value}
        onchange=${(e) => onChange(e.target.value)}
        data-testid=${testid}
      >
        ${(keys ?? []).map((k) => html`<option key=${k} value=${k}>${GROUP_LABELS[k] ?? k}</option>`)}
      </select>
    </label>
  `;
}
