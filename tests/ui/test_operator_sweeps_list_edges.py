# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Edge-case tests for the operator UI sweeps list page."""

from __future__ import annotations

import json
from pathlib import Path

from tests.ui.node_utils import local_module_js, run_node

_SWEEPS_PAGE_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "aiperf"
    / "operator"
    / "ui"
    / "pages"
    / "sweeps.js"
)

# lib/grouping.js is import-free; splice the real helpers so facet filters,
# label badges and grouping run against the browser's code, not a stub.
_GROUPING_JS = local_module_js("lib/grouping.js")


def _node_script(expression: str) -> str:
    return f"""
        import fs from 'node:fs';
        const source = fs.readFileSync({str(_SWEEPS_PAGE_PATH)!r}, 'utf8')
          .replace(new RegExp('^import .*;\\n', 'gm'), '')
          .replace('export function Sweeps', 'function Sweeps');

        function html(strings, ...values) {{
          return {{ __html: true, strings: Array.from(strings), values }};
        }}
        function useMemo(fn) {{ return fn(); }}
        function useEffect() {{}}
        const stateSetters = [];
        let stateIndex = 0;
        function useState(initial) {{
          stateIndex += 1;
          let value = typeof initial === 'function' ? initial() : initial;
          if (globalThis.__forceSweepsLoaded && stateIndex === 2) value = false;
          stateSetters.push((next) => {{ value = next; }});
          return [value, stateSetters[stateSetters.length - 1]];
        }}

        const api = {{ listSweeps: async () => {{ throw new Error('not called'); }} }};
        function poll() {{}}
        const sweeps = {{ value: [] }};
        const freshness = {{ value: {{ sweeps: null }} }};
        function dedupeByNsName(rows) {{ return rows; }}
        const navigations = [];
        function navigate(path) {{ navigations.push(path); }}
        const queryUpdates = [];
        const query = {{ value: {{}} }};
        function setQuery(update) {{
          queryUpdates.push(update);
          query.value = Object.fromEntries(
            Object.entries({{ ...query.value, ...update }}).filter(([, value]) => value !== undefined)
          );
        }}
        const palette = {{
          blue: '#89b4fa', green: '#a6e3a1', mantle: '#181825', overlay0: '#6c7086',
          red: '#f38ba8', surface0: '#313244', surface1: '#45475a', teal: '#94e2d5',
          text: '#cdd6f4', yellow: '#f9e2af',
        }};
        function phaseColor() {{ return '#89b4fa'; }}
        function NsPill(props) {{ return {{ component: 'NsPill', props }}; }}
        function ModelPill(props) {{ return {{ component: 'ModelPill', props }}; }}
        function RelativeTime(props) {{ return {{ component: 'RelativeTime', props }}; }}
        function FreshnessPill(props) {{ return {{ component: 'FreshnessPill', props }}; }}
        function StaleBanner(props) {{ return {{ component: 'StaleBanner', props }}; }}
        function LoadingPanel(props) {{ return {{ component: 'LoadingPanel', props }}; }}
        const jobs = {{ value: [] }};
        function replaceRoute() {{}}
        function hashUrl() {{ return '#/sweeps'; }}
        const route = {{ value: '/sweeps' }};
        {_GROUPING_JS}
        // GroupedList is a plain render function in the page; the stub keeps
        // every group's rows in the tree so rowIds() sees them in group order.
        function GroupedList({{ groups, renderGroup }}) {{ return groups.map(renderGroup); }}
        function useCollapsedGroups() {{ return [() => false, () => {{}}]; }}
        function FacetSelects(props) {{ return {{ component: 'FacetSelects', props }}; }}
        function FacetChips(props) {{ return {{ component: 'FacetChips', props }}; }}
        function GroupBySelect(props) {{ return {{ component: 'GroupBySelect', props }}; }}
        function SavedViewsMenu(props) {{ return {{ component: 'SavedViewsMenu', props }}; }}
        function SweepChildren(props) {{ return {{ component: 'SweepChildren', props }}; }}

        eval(source + '\\nglobalThis.Sweeps = Sweeps;');

        function renderSweeps({{ rows = [], q = {{}}, forceLoaded = true }} = {{}}) {{
          sweeps.value = rows;
          query.value = q;
          queryUpdates.length = 0;
          navigations.length = 0;
          stateSetters.length = 0;
          stateIndex = 0;
          globalThis.__forceSweepsLoaded = forceLoaded;
          return Sweeps();
        }}

        function collectValues(node, out = []) {{
          if (node == null || node === false) return out;
          if (Array.isArray(node)) {{
            for (const item of node) collectValues(item, out);
            return out;
          }}
          if (typeof node === 'object' && node.__html) {{
            for (const value of node.values) collectValues(value, out);
            return out;
          }}
          out.push(node);
          return out;
        }}

        function flattenText(node) {{
          if (node == null || node === false) return '';
          if (Array.isArray(node)) return node.map(flattenText).join('');
          if (typeof node === 'object' && node.__html) {{
            let text = '';
            for (let i = 0; i < node.strings.length; i++) {{
              text += node.strings[i];
              if (i < node.values.length) text += flattenText(node.values[i]);
            }}
            return text;
          }}
          if (typeof node === 'function') return `[Function ${{node.name}}]`;
          if (typeof node === 'object') return JSON.stringify(node);
          return String(node);
        }}

        function rowIds(rendered) {{
          return collectValues(rendered)
            .filter((value) => typeof value === 'string' && value.startsWith('sweep-row-'))
            .filter((value) => !value.startsWith('sweep-row-ns-') && !value.startsWith('sweep-row-model-')
              && !value.startsWith('sweep-row-expand-'));
        }}

        function testIds(rendered, prefix) {{
          return collectValues(rendered)
            .filter((value) => typeof value === 'string' && value.startsWith(prefix));
        }}

        function components(rendered, name) {{
          return collectValues(rendered)
            .filter((value) => value && typeof value === 'object' && value.component === name);
        }}

        {expression}
    """


def test_all_sweeps_default_age_sort_places_new_live_and_archived_rows_first() -> None:
    rows = [
        {
            "namespace": "bench",
            "name": "old-live",
            "phase": "Running",
            "age_seconds": 600,
        },
        {
            "namespace": "bench",
            "name": "new-archived",
            "phase": "Archived",
            "age_seconds": 5,
        },
        {
            "namespace": "bench",
            "name": "mid-complete",
            "phase": "Succeeded",
            "age_seconds": 60,
        },
    ]
    script = _node_script(
        f"""
        const rendered = renderSweeps({{ rows: {json.dumps(rows)} }});
        console.log(JSON.stringify(rowIds(rendered)));
        """
    )

    assert json.loads(run_node(script)) == [
        "sweep-row-bench-new-archived",
        "sweep-row-bench-mid-complete",
        "sweep-row-bench-old-live",
    ]


def test_phase_filters_include_expected_terminal_and_live_sweep_phases() -> None:
    rows = [
        {"namespace": "bench", "name": "run", "phase": "Running"},
        {"namespace": "bench", "name": "agg", "phase": "Aggregating"},
        {"namespace": "bench", "name": "ok", "phase": "Succeeded"},
        {"namespace": "bench", "name": "partial", "phase": "PartiallyFailed"},
        {"namespace": "bench", "name": "cancel", "phase": "Cancelled"},
        {"namespace": "bench", "name": "arch", "phase": "Archived"},
    ]
    script = _node_script(
        f"""
        const rows = {json.dumps(rows)};
        const out = {{
          running: rowIds(renderSweeps({{ rows, q: {{ phase: 'running', sort: 'name:asc' }} }})),
          completed: rowIds(renderSweeps({{ rows, q: {{ phase: 'completed', sort: 'name:asc' }} }})),
          failed: rowIds(renderSweeps({{ rows, q: {{ phase: 'failed', sort: 'name:asc' }} }})),
        }};
        console.log(JSON.stringify(out));
        """
    )

    assert json.loads(run_node(script)) == {
        "running": ["sweep-row-bench-agg", "sweep-row-bench-run"],
        "completed": ["sweep-row-bench-ok"],
        "failed": ["sweep-row-bench-cancel", "sweep-row-bench-partial"],
    }


def test_namespace_filter_is_exact_and_clear_chip_preserves_other_filters() -> None:
    rows = [
        {"namespace": "bench", "name": "keep", "phase": "Running"},
        {"namespace": "bench-prod", "name": "drop", "phase": "Running"},
    ]
    script = _node_script(
        f"""
        const rendered = renderSweeps({{
          rows: {json.dumps(rows)},
          q: {{ ns: 'bench', sort: 'name:asc' }},
        }});
        console.log(JSON.stringify(rowIds(rendered)));
        """
    )

    assert json.loads(run_node(script)) == ["sweep-row-bench-keep"]

    source = _SWEEPS_PAGE_PATH.read_text()
    assert "onclick=${() => setQuery({ ns: undefined })}" in source
    assert "onkeydown=${chipKeyHandler(() => setQuery({ ns: undefined }))}" in source
    assert "setQuery({ q: undefined, ns: undefined, phase: undefined })" in source


def test_model_text_filter_matches_sweep_model_names() -> None:
    rows = [
        {
            "namespace": "bench",
            "name": "alpha",
            "phase": "Running",
            "model": "llama-3.1-70b",
        },
        {
            "namespace": "bench",
            "name": "bravo",
            "phase": "Running",
            "model": "mixtral-8x7b",
        },
    ]
    script = _node_script(
        f"""
        const rendered = renderSweeps({{
          rows: {json.dumps(rows)},
          q: {{ q: 'llama', sort: 'name:asc' }},
        }});
        console.log(JSON.stringify(rowIds(rendered)));
        """
    )

    assert json.loads(run_node(script)) == ["sweep-row-bench-alpha"]


def test_detail_links_url_encode_namespace_and_sweep_name() -> None:
    rows = [
        {"namespace": "team ns", "name": "sweep/with spaces", "phase": "Running"},
    ]
    script = _node_script(
        f"""
        const rendered = renderSweeps({{ rows: {json.dumps(rows)} }});
        const links = collectValues(rendered).filter((value) =>
          typeof value === 'string' && value.startsWith('#/sweeps/')
        );
        console.log(JSON.stringify(links));
        """
    )

    assert json.loads(run_node(script)) == ["#/sweeps/team%20ns/sweep%2Fwith%20spaces"]


def test_empty_states_distinguish_no_data_from_filtered_no_matches() -> None:
    rows = [{"namespace": "bench", "name": "existing", "phase": "Running"}]
    script = _node_script(
        f"""
        const realEmpty = flattenText(renderSweeps({{ rows: [] }}));
        const filteredEmpty = flattenText(renderSweeps({{
          rows: {json.dumps(rows)},
          q: {{ phase: 'completed' }},
        }}));
        console.log(JSON.stringify({{ realEmpty, filteredEmpty }}));
        """
    )

    out = json.loads(run_node(script))
    assert "No sweeps yet." in out["realEmpty"]
    assert "Create one with" in out["realEmpty"]
    assert "No sweeps match these filters." in out["filteredEmpty"]
    assert "Clear filters" in out["filteredEmpty"]


def test_sweeps_page_uses_shared_freshness_source_and_stale_banner() -> None:
    source = _SWEEPS_PAGE_PATH.read_text(encoding="utf-8")

    assert (
        "import { FreshnessPill, StaleBanner } from '../components/freshness.js';"
        in source
    )
    assert "freshness.value.sweeps" in source
    assert "source: 'sweeps'" in source
    assert '<${StaleBanner} source=${sweepsFreshness} label="Sweeps list" />' in source
    assert "<${FreshnessPill} source=${sweepsFreshness}" in source


_LABELLED_SWEEPS = [
    {
        "namespace": "perfledger",
        "name": "gemma4-cap-e5dea4",
        "phase": "Running",
        "model": "gemma-4",
        "age_seconds": 30,
        "labels": {
            "perfledger.fptcloud.vn/run": "gemma4-cap",
            "perfledger.fptcloud.vn/scenario": "agentx-ref",
            "perfledger.fptcloud.vn/lifecycle": "gateway",
        },
    },
    {
        "namespace": "perfledger",
        "name": "gemma4-pilot-ab12cd",
        "phase": "Succeeded",
        "model": "gemma-4",
        "age_seconds": 600,
        "labels": {
            "perfledger.fptcloud.vn/run": "gemma4-pilot",
            "perfledger.fptcloud.vn/scenario": "fixed_seq_ref",
            "perfledger.fptcloud.vn/lifecycle": "internal",
            "perfledger.fptcloud.vn/pilot": "true",
        },
    },
    {
        "namespace": "team-b",
        "name": "qwen-cap-123abc",
        "phase": "Failed",
        "model": "qwen3",
        "age_seconds": 120,
        "labels": {"perfledger.fptcloud.vn/scenario": "agentx-ref"},
    },
]


def test_facet_filters_and_search_use_labels_and_name_convention() -> None:
    script = _node_script(
        f"""
        const rows = {json.dumps(_LABELLED_SWEEPS)};
        const out = {{
          run: rowIds(renderSweeps({{ rows, q: {{ run: 'gemma4-cap', group: 'none' }} }})),
          scenario: rowIds(renderSweeps({{ rows, q: {{ scenario: 'agentx-ref', group: 'none', sort: 'name:asc' }} }})),
          lifecycleAndPhase: rowIds(renderSweeps({{ rows, q: {{ lifecycle: 'internal', phase: 'completed', group: 'none' }} }})),
          searchRun: rowIds(renderSweeps({{ rows, q: {{ q: 'qwen-cap', group: 'none' }} }})),
          searchScenario: rowIds(renderSweeps({{ rows, q: {{ q: 'FIXED_SEQ', group: 'none' }} }})),
        }};
        console.log(JSON.stringify(out));
        """
    )

    assert json.loads(run_node(script)) == {
        "run": ["sweep-row-perfledger-gemma4-cap-e5dea4"],
        "scenario": ["sweep-row-perfledger-gemma4-cap-e5dea4", "sweep-row-team-b-qwen-cap-123abc"],
        "lifecycleAndPhase": ["sweep-row-perfledger-gemma4-pilot-ab12cd"],
        "searchRun": ["sweep-row-team-b-qwen-cap-123abc"],
        "searchScenario": ["sweep-row-perfledger-gemma4-pilot-ab12cd"],
    }


def test_grouping_defaults_to_model_and_keeps_sort_order_inside_each_group() -> None:
    script = _node_script(
        f"""
        const rows = {json.dumps(_LABELLED_SWEEPS)};
        const out = {{
          byModel: rowIds(renderSweeps({{ rows }})),
          byRun: rowIds(renderSweeps({{ rows, q: {{ group: 'run' }} }})),
          byScenarioNameAsc: rowIds(renderSweeps({{ rows, q: {{ group: 'scenario', sort: 'name:asc' }} }})),
          sweepKeyFallsBackToFlat: rowIds(renderSweeps({{ rows, q: {{ group: 'sweep' }} }})),
          flat: rowIds(renderSweeps({{ rows, q: {{ group: 'none' }} }})),
          groupSelectWired: flattenText(renderSweeps({{ rows }})).includes('sweeps-group-select'),
        }};
        console.log(JSON.stringify(out));
        """
    )

    out = json.loads(run_node(script))
    # No started_at on these rows, so groups order by key; rows inside a group
    # keep the page sort (default: newest first).
    assert out["byModel"] == [
        "sweep-row-perfledger-gemma4-cap-e5dea4",
        "sweep-row-perfledger-gemma4-pilot-ab12cd",
        "sweep-row-team-b-qwen-cap-123abc",
    ]
    assert out["byRun"] == [
        "sweep-row-perfledger-gemma4-cap-e5dea4",
        "sweep-row-perfledger-gemma4-pilot-ab12cd",
        "sweep-row-team-b-qwen-cap-123abc",
    ]
    assert out["byScenarioNameAsc"] == [
        "sweep-row-perfledger-gemma4-cap-e5dea4",
        "sweep-row-team-b-qwen-cap-123abc",
        "sweep-row-perfledger-gemma4-pilot-ab12cd",
    ]
    assert out["sweepKeyFallsBackToFlat"] == out["flat"]
    assert out["flat"] == [
        "sweep-row-perfledger-gemma4-cap-e5dea4",
        "sweep-row-team-b-qwen-cap-123abc",
        "sweep-row-perfledger-gemma4-pilot-ab12cd",
    ]
    assert out["groupSelectWired"] is True


def test_rows_expose_expand_controls_and_label_badges_without_inventing_trials() -> None:
    script = _node_script(
        f"""
        const rows = {json.dumps(_LABELLED_SWEEPS)};
        const rendered = renderSweeps({{ rows, q: {{ group: 'none', sort: 'name:asc' }} }});
        const out = {{
          expand: testIds(rendered, 'sweep-row-expand-'),
          badges: testIds(rendered, 'sweep-badge-'),
          children: components(rendered, 'SweepChildren').length,
          text: flattenText(rendered),
        }};
        console.log(JSON.stringify(out));
        """
    )

    out = json.loads(run_node(script))
    assert out["expand"] == [
        "sweep-row-expand-gemma4-cap-e5dea4",
        "sweep-row-expand-gemma4-pilot-ab12cd",
        "sweep-row-expand-qwen-cap-123abc",
    ]
    assert out["badges"] == [
        "sweep-badge-lifecycle-gemma4-cap-e5dea4",
        "sweep-badge-lifecycle-gemma4-pilot-ab12cd",
        "sweep-badge-pilot-gemma4-pilot-ab12cd",
    ]
    # Nothing is expanded until the user asks, and no trial count is shown
    # because the list payload does not carry one.
    assert out["children"] == 0
    assert "trials" not in out["text"]

    source = _SWEEPS_PAGE_PATH.read_text(encoding="utf-8")
    assert "data-testid=${'sweep-row-expand-' + (s.name ?? '')}" in source
    assert "aria-expanded=${isOpen}" in source
    assert "onclick=${(e) => { e.stopPropagation(); onToggleExpand(s); }}" in source
    assert "<${SweepChildren} namespace=${s.namespace} name=${s.name} phaseOf=${phaseOf} />" in source
    assert 'testid="sweeps-group-select"' in source
    assert "const SWEEP_GROUP_KEYS = ['none', 'model', 'run', 'scenario'];" in source
    assert '<${SavedViewsMenu} page="sweeps" />' in source
