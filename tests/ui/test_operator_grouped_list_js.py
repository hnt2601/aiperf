# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the grouped-list components shared by the Jobs and Sweeps pages.

Covers ``components/grouped-list.js`` (collapsible groups, folded sweep rows),
``components/facet-filters.js`` (facet selects/chips, group-by picker) and
``components/sweep-children.js`` (inline children of a sweep). The modules
import preact/htm, so each harness strips the imports, stubs the framework
bits, and splices the real import-free helpers (``lib/grouping.js``,
``lib/format.js``) so the pure logic is exercised as the browser runs it.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.ui.node_utils import FORMAT_JS, local_module_js, requires_node, run_node

UI_ROOT = Path(__file__).resolve().parents[2] / "src" / "aiperf" / "operator" / "ui"
GROUPED_LIST_PATH = UI_ROOT / "components" / "grouped-list.js"
FACET_FILTERS_PATH = UI_ROOT / "components" / "facet-filters.js"
SWEEP_CHILDREN_PATH = UI_ROOT / "components" / "sweep-children.js"
STYLE_CSS_PATH = UI_ROOT / "style.css"

GROUPING_JS = local_module_js("lib/grouping.js")

_HARNESS_COMMON = """
    function html(strings, ...values) {
      return { __html: true, strings: Array.from(strings), values };
    }
    const stateLog = [];
    // ``let`` so a test can swap the hook stubs (e.g. force "open" state).
    let useState = function (initial) {
      const value = typeof initial === 'function' ? initial() : initial;
      stateLog.push(value);
      return [value, () => {}];
    };
    let useEffect = function () {};
    function useRef() { return { current: null }; }
    function phaseColor(phase) { return '#' + String(phase ?? 'none').toLowerCase(); }
    const palette = { blue: '#00f', green: '#0f0', amber: '#fa0', cyan: '#0ff' };
    function navigate() {}
    function buildJobPath(job) { return '/jobs/' + job.namespace + '/' + job.name; }
    function JobTable(props) { return { component: 'JobTable', props }; }
    function RelativeTime(props) { return { component: 'RelativeTime', props }; }
    function LoadingPanel(props) { return { component: 'LoadingPanel', props }; }
    const api = { getSweepChildren: async () => ({ children: [] }) };

    function collectValues(node, out = []) {
      if (node == null || node === false) return out;
      if (Array.isArray(node)) {
        for (const item of node) collectValues(item, out);
        return out;
      }
      if (typeof node === 'object' && node.__html) {
        for (const value of node.values) collectValues(value, out);
        return out;
      }
      out.push(node);
      return out;
    }
    function flattenText(node) {
      if (node == null || node === false) return '';
      if (Array.isArray(node)) return node.map(flattenText).join('');
      if (typeof node === 'object' && node.__html) {
        let text = '';
        for (let i = 0; i < node.strings.length; i++) {
          text += node.strings[i];
          if (i < node.values.length) text += flattenText(node.values[i]);
        }
        return text;
      }
      if (typeof node === 'function') return '[Function ' + node.name + ']';
      if (typeof node === 'object') return JSON.stringify(node);
      return String(node);
    }
    // Props handed to a component vnode: the values right after the function.
    function propsAfter(node, fn, out = []) {
      if (node == null || node === false) return out;
      if (Array.isArray(node)) { for (const item of node) propsAfter(item, fn, out); return out; }
      if (typeof node === 'object' && node.__html) {
        for (let i = 0; i < node.values.length; i++) {
          if (node.values[i] === fn) out.push(node.values.slice(i + 1, i + 6));
        }
        for (const value of node.values) propsAfter(value, fn, out);
      }
      return out;
    }
    function strings(node, prefix) {
      return collectValues(node).filter((v) => typeof v === 'string' && v.startsWith(prefix));
    }
"""


def _top_level_names(path: Path) -> list[str]:
    """Functions and constants the module declares, exported or not."""
    src = path.read_text(encoding="utf-8")
    return [
        a or b
        for a, b in re.findall(
            r"^(?:export )?function (\w+)|^(?:export )?const (\w+)", src, re.MULTILINE
        )
    ]


def _module_script(path: Path, extra: str, expression: str) -> str:
    # Direct eval in a strict module keeps declarations local, so hoist the
    # module's names onto globalThis the way the other page harnesses do.
    hoist = "Object.assign(globalThis, { " + ", ".join(_top_level_names(path)) + " });"
    return f"""
        import fs from 'node:fs';
        const source = fs.readFileSync({str(path)!r}, 'utf8')
          .replace(new RegExp('^import .*;\\n', 'gm'), '')
          .replace(new RegExp('^export ', 'gm'), '');
        {_HARNESS_COMMON}
        {FORMAT_JS}
        {GROUPING_JS}
        {extra}
        eval(source + {hoist!r});
        {expression}
    """


JOBS = [
    {
        "name": "gemma4-cap-e5dea4-v00",
        "namespace": "perfledger",
        "phase": "Completed",
        "model": "gemma-4",
        "sweepName": "gemma4-cap-e5dea4",
        "variationIndex": 0,
        "startTime": "2026-10-13T10:35:20Z",
        "throughputRps": 0.18,
    },
    {
        "name": "gemma4-cap-e5dea4-v01",
        "namespace": "perfledger",
        "phase": "Running",
        "model": "gemma-4",
        "sweepName": "gemma4-cap-e5dea4",
        "variationIndex": 1,
        "startTime": "2026-10-13T10:38:06Z",
        "throughputRps": "0.35",
        "progressPercent": 99.7,
    },
    {
        "name": "gemma4-pilot-1-c4-ab12cd",
        "namespace": "perfledger",
        "phase": "Failed",
        "model": "gemma-4",
        "startTime": "2026-10-13T09:00:00Z",
    },
    {
        "name": "qwen-adhoc",
        "namespace": "team-b",
        "phase": "Completed",
        "model": "qwen3",
        "created": "2026-10-13T11:00:00Z",
        "outputTokenThroughputTps": 4100.4,
        "throughputRps": 9,
    },
]


def _grouped(expression: str, extra: str = "") -> object:
    script = _module_script(
        GROUPED_LIST_PATH,
        f"const JOBS = {json.dumps(JOBS)};\n{extra}",
        expression,
    )
    return json.loads(run_node(script))


@requires_node
def test_collapsed_state_round_trips_through_storage_and_survives_failures() -> None:
    out = _grouped(
        """
        const store = new Map();
        globalThis.localStorage = {
          getItem: (k) => (store.has(k) ? store.get(k) : null),
          setItem: (k, v) => store.set(k, v),
          removeItem: (k) => store.delete(k),
        };
        const out = {};
        out.key = collapsedStorageKey('jobs.model', 'gemma-4');
        out.noneKey = collapsedStorageKey('jobs.model', null);
        out.before = readCollapsed('jobs.model', 'gemma-4');
        writeCollapsed('jobs.model', 'gemma-4', true);
        out.after = readCollapsed('jobs.model', 'gemma-4');
        out.stored = store.get(out.key);
        out.otherFacet = readCollapsed('jobs.run', 'gemma-4');
        writeCollapsed('jobs.model', 'gemma-4', false);
        out.cleared = readCollapsed('jobs.model', 'gemma-4');
        out.removed = store.has(out.key);
        globalThis.localStorage = { getItem() { throw new Error('private mode'); }, setItem() { throw new Error('quota'); }, removeItem() { throw new Error('quota'); } };
        out.readThrows = readCollapsed('jobs.model', 'x');
        writeCollapsed('jobs.model', 'x', true);
        out.writeThrows = 'survived';
        console.log(JSON.stringify(out));
        """
    )

    assert out == {
        "key": "aiperf-ui-v1.grouped-list.collapsed.jobs.model.gemma-4",
        "noneKey": "aiperf-ui-v1.grouped-list.collapsed.jobs.model.\u0000none",
        "before": False,
        "after": True,
        "stored": "1",
        "otherFacet": False,
        "cleared": False,
        "removed": False,
        "readThrows": False,
        "writeThrows": "survived",
    }


@requires_node
def test_group_heading_and_summary_helpers() -> None:
    out = _grouped(
        """
        const groups = groupItems(JOBS, 'model');
        const none = groupItems(JOBS, 'scenario').find((g) => g.key == null);
        console.log(JSON.stringify({
          headings: [groupHeading(groups[0], 'model'), groupHeading(none, 'scenario'), groupHeading({ key: null }, 'none'), groupHeading({ key: 'x', label: 'y' }, 'run')],
          tokens: throughputSummary(JOBS),
          requests: throughputSummary(JOBS.slice(0, 3)),
          nothing: throughputSummary([{ name: 'a' }, { throughputRps: 'abc' }]),
          single: singleRunning(groups.find((g) => g.key === 'gemma-4'))?.name ?? null,
          noneRunning: singleRunning(groups.find((g) => g.key === 'qwen3')),
          several: singleRunning({ running: [JOBS[1], JOBS[1]] }),
          progress: [progressText(JOBS[1]), progressText({ progressPercent: 100 }), progressText({ progress_percent: -3 }), progressText({})],
        }));
        """
    )

    assert out["headings"] == ["qwen3", "(no scenario)", "All", "y"]
    assert out["tokens"] == {"value": 4100.4, "unit": "tok/s", "text": "4,100 tok/s"}
    assert out["requests"] == {"value": 0.35, "unit": "req/s", "text": "0.35 req/s"}
    assert out["nothing"] is None
    assert out["single"] == "gemma4-cap-e5dea4-v01"
    assert out["noneRunning"] is None
    assert out["several"] is None
    # 99.7% must not round up to the one value a reader acts on.
    assert out["progress"] == ["99%", "100%", "0%", None]


@requires_node
def test_grouped_list_renders_accessible_headers_and_skips_collapsed_bodies() -> None:
    out = _grouped(
        """
        const groups = groupItems(JOBS, 'model');
        const collapsed = new Set(['qwen3']);
        const toggled = [];
        const rendered = GroupedList({
          groups,
          facet: 'model',
          storageKey: 'jobs.model',
          itemNoun: 'job',
          testidPrefix: 'jobs-group',
          isCollapsed: (k) => collapsed.has(k),
          onToggle: (k) => toggled.push(k),
          renderGroup: (g) => ({ body: g.key, n: g.items.length }),
        });
        const text = flattenText(rendered);
        const bodies = collectValues(rendered).filter((v) => v && typeof v === 'object' && 'body' in v);
        console.log(JSON.stringify({
          testids: strings(rendered, 'jobs-group-'),
          counts: strings(rendered, 'group-count-'),
          bodies,
          hasButton: text.includes('<button') && text.includes('type="button"'),
          text,
        }));
        """
    )

    assert out["testids"] == [
        "jobs-group-list",
        "jobs-group-qwen3",
        "jobs-group-toggle-qwen3",
        "jobs-group-gemma-4",
        "jobs-group-toggle-gemma-4",
    ]
    assert out["counts"] == ["group-count-completed", "group-count-running", "group-count-completed", "group-count-failed"]
    # The collapsed qwen3 group renders no body; gemma-4 renders its 3 jobs.
    assert out["bodies"] == [{"body": "gemma-4", "n": 3}]
    assert out["hasButton"]
    assert "aria-expanded=" in out["text"]
    assert "1 job" in out["text"] and "3 jobs" in out["text"]
    assert "best 4,100 tok/s" in out["text"]
    assert "gemma4-cap-e5dea4-v01 · 99%" in out["text"]
    assert "(no model)" not in out["text"]


@requires_node
def test_job_group_body_folds_sweep_children_and_keeps_standalone_jobs_in_table() -> None:
    out = _grouped(
        """
        const folded = JobGroupBody({ items: JOBS, foldSweeps: true, sort: { key: 'age', dir: -1 } });
        const flat = JobGroupBody({ items: JOBS, foldSweeps: false });
        const foldRows = propsAfter(folded, SweepFoldRow);
        console.log(JSON.stringify({
          foldedSweeps: foldRows.map((p) => [p[0], p[1].sweep, p[1].items.map((j) => j.name), p[1].counts]),
          foldedStandalone: propsAfter(folded, JobTable).map((p) => p[0].map((j) => j.name)),
          flatTable: propsAfter(flat, JobTable).map((p) => p[0].map((j) => j.name)),
          flatFolds: propsAfter(flat, SweepFoldRow).length,
        }));
        """
    )

    assert out["foldedSweeps"] == [
        [
            "perfledger/gemma4-cap-e5dea4",
            "gemma4-cap-e5dea4",
            ["gemma4-cap-e5dea4-v00", "gemma4-cap-e5dea4-v01"],
            {"running": 1, "completed": 1, "failed": 0, "other": 0},
        ]
    ]
    assert out["foldedStandalone"] == [["gemma4-pilot-1-c4-ab12cd", "qwen-adhoc"]]
    assert out["flatTable"] == [[j["name"] for j in JOBS]]
    assert out["flatFolds"] == 0


@requires_node
def test_sweep_fold_row_links_to_the_sweep_and_only_renders_children_when_open() -> None:
    out = _grouped(
        """
        const entry = collapseSweepChildren(JOBS).find((e) => e.kind === 'sweep');
        stateLog.length = 0;
        const closed = SweepFoldRow({ entry, sort: { key: 'age', dir: -1 } });
        const closedText = flattenText(closed);
        // Re-run with the useState stub reporting "open".
        useState = () => [true, () => {}];
        const open = SweepFoldRow({ entry });
        console.log(JSON.stringify({
          closedTables: propsAfter(closed, JobTable).length,
          openTables: propsAfter(open, JobTable).map((p) => p[0].map((j) => j.name)),
          link: strings(closed, '#/sweeps/'),
          testids: strings(closed, 'sweep-fold-'),
          closedText,
        }));
        """
    )

    assert out["closedTables"] == 0
    assert out["openTables"] == [["gemma4-cap-e5dea4-v00", "gemma4-cap-e5dea4-v01"]]
    assert out["link"] == ["#/sweeps/perfledger/gemma4-cap-e5dea4"]
    assert out["testids"] == [
        "sweep-fold-perfledger-gemma4-cap-e5dea4",
        "sweep-fold-toggle-perfledger-gemma4-cap-e5dea4",
    ]
    assert "2 children" in out["closedText"]
    assert "aria-expanded=" in out["closedText"]


def _facets(expression: str) -> object:
    script = _module_script(
        FACET_FILTERS_PATH,
        f"const JOBS = {json.dumps(JOBS)};",
        expression,
    )
    return json.loads(run_node(script))


@requires_node
def test_facet_selects_only_appear_for_multi_valued_facets_and_keep_stale_url_values() -> (
    None
):
    out = _facets(
        """
        const items = [
          { name: 'a', labels: { 'x/run': 'r1', 'x/scenario': 's1', 'x/lifecycle': 'gateway' } },
          { name: 'b', labels: { 'x/run': 'r2', 'x/scenario': 's1', 'x/lifecycle': 'internal' } },
        ];
        console.log(JSON.stringify({
          all: facetSelectOptions(items, ['run', 'scenario', 'lifecycle', 'deploy'], {}),
          subset: facetSelectOptions(items, ['scenario', 'lifecycle'], {}).map((f) => f.key),
          stale: facetSelectOptions(items, ['scenario'], { scenario: 'gone' }),
          rendered: strings(FacetSelects({ items, facets: ['run', 'lifecycle'], filters: { run: 'r1' }, onChange() {}, testidPrefix: 'jobs-' }), 'jobs-'),
          chips: strings(FacetChips({ facets: ['run', 'scenario', 'lifecycle', 'deploy'], filters: { run: 'r1', deploy: 'd1', scenario: '' }, onClear() {} }), ''),
          chipText: flattenText(FacetChips({ facets: ['lifecycle'], filters: { lifecycle: 'gateway' }, onClear() {} })),
          groupBy: flattenText(GroupBySelect({ value: 'run', keys: ['none', 'model', 'run'], onChange() {}, testid: 'jobs-group-select' })),
        }));
        """
    )

    assert out["all"] == [
        {"key": "run", "label": "Run", "values": ["r1", "r2"]},
        {"key": "lifecycle", "label": "Lifecycle", "values": ["gateway", "internal"]},
    ]
    assert out["subset"] == ["lifecycle"]
    # A filter the current list no longer has stays selectable so the URL is
    # still represented (and clearable) in the UI.
    assert out["stale"] == [{"key": "scenario", "label": "Scenario", "values": ["s1", "gone"]}]
    assert out["rendered"] == ["jobs-run-filter-select", "jobs-lifecycle-filter-select"]
    assert [c for c in out["chips"] if c.endswith("-filter-chip")] == ["run-filter-chip", "deploy-filter-chip"]
    assert 'role="button"' in out["chipText"] and 'tabindex="0"' in out["chipText"]
    assert "Remove lifecycle filter gateway" in out["chipText"]
    assert "jobs-group-select" in out["groupBy"] and "Group by" in out["groupBy"]
    assert out["groupBy"].count("<option") == 3


def _children(expression: str) -> object:
    return json.loads(run_node(_module_script(SWEEP_CHILDREN_PATH, "", expression)))


@requires_node
def test_sweep_children_helpers_order_manifest_rows_and_detect_job_shaped_payloads() -> None:
    out = _children(
        """
        const manifest = [
          { namespace: 'ns', name: 'sw-v01-t1', variationIndex: 1, variationLabel: 'conc=16', trialIndex: 1, childRunEpoch: '1760000000' },
          { namespace: 'ns', name: 'sw-v00', variation_index: 0, child_run_epoch: '1759999999' },
          { namespace: 'ns', name: 'sw-v01', variationIndex: 1, variationLabel: 'conc=16', trialIndex: 0, childRunEpoch: '1760000001' },
        ];
        const phases = { 'ns/sw-v00': 'Completed' };
        const table = ChildrenTable({ children: manifest, namespace: 'ns', name: 'sw', phaseOf: (n, j) => phases[n + '/' + j] ?? null });
        console.log(JSON.stringify({
          order: sortChildren(manifest).map((c) => c.name),
          variation: manifest.map(childVariation),
          trial: manifest.map(childTrial),
          jobShaped: [isJobShaped(manifest), isJobShaped([{ name: 'a', phase: 'Running' }]), isJobShaped([])],
          rows: strings(table, 'sweep-child-row-'),
          links: strings(table, '#/jobs/'),
          errors: ['API 404: nope', 'Failed to fetch', 'boom'].map(describeChildrenError),
          text: flattenText(table),
        }));
        """
    )

    assert out["order"] == ["sw-v00", "sw-v01", "sw-v01-t1"]
    assert out["variation"] == ["conc=16", "v00", "conc=16"]
    assert out["trial"] == ["1", "---", "0"]
    assert out["jobShaped"] == [False, True, False]
    assert out["rows"] == ["sweep-child-row-ns-sw-v00", "sweep-child-row-ns-sw-v01", "sweep-child-row-ns-sw-v01-t1"]
    assert out["links"] == ["#/jobs/ns/sw-v00", "#/jobs/ns/sw-v01", "#/jobs/ns/sw-v01-t1"]
    assert out["errors"][0].startswith("children manifest not found")
    assert out["errors"][1].startswith("network error")
    assert out["errors"][2] == "boom"
    assert 'role="row"' in out["text"] and 'tabindex="0"' in out["text"]
    assert "Completed" in out["text"]


@requires_node
def test_sweep_children_component_has_loading_error_and_empty_states() -> None:
    out = _children(
        """
        const states = {};
        useState = () => [states.current, () => {}];
        const sweepChildrenCalls = [];
        useEffect = (fn) => { sweepChildrenCalls.push(fn); };
        states.current = { status: 'loading', children: [], error: null };
        const loading = flattenText(SweepChildren({ namespace: 'ns', name: 'sw' }));
        states.current = { status: 'error', children: [], error: 'operator unreachable' };
        const error = flattenText(SweepChildren({ namespace: 'ns', name: 'sw' }));
        states.current = { status: 'ready', children: [], error: null };
        const empty = flattenText(SweepChildren({ namespace: 'ns', name: 'sw' }));
        states.current = { status: 'ready', children: [{ name: 'c', namespace: 'ns', phase: 'Running' }], error: null };
        const jobShaped = propsAfter(SweepChildren({ namespace: 'ns', name: 'sw' }), JobTable).length;
        states.current = { status: 'ready', children: [{ name: 'c', namespace: 'ns', variationIndex: 0 }], error: null };
        const manifest = strings(SweepChildren({ namespace: 'ns', name: 'sw' }), 'sweep-children-table-');
        console.log(JSON.stringify({ loading, error, empty, jobShaped, manifest, effects: sweepChildrenCalls.length }));
        """
    )

    assert "sweep-children-ns-sw-loading" in out["loading"]
    assert "Failed to load children: operator unreachable" in out["error"]
    assert "sweep-children-ns-sw-error" in out["error"]
    assert "No children recorded for this sweep yet." in out["empty"]
    assert out["jobShaped"] == 1
    assert out["manifest"] == ["sweep-children-table-ns-sw"]
    assert out["effects"] == 5


def test_grouped_list_markup_has_css_rules_and_accessible_controls() -> None:
    css = STYLE_CSS_PATH.read_text(encoding="utf-8")
    grouped = GROUPED_LIST_PATH.read_text(encoding="utf-8")
    facets = FACET_FILTERS_PATH.read_text(encoding="utf-8")
    children = SWEEP_CHILDREN_PATH.read_text(encoding="utf-8")

    assert "/* ===== grouped lists (jobs/sweeps) ===== */" in css
    for cls in (
        "grouped-list__header",
        "grouped-list__group--collapsed",
        "grouped-list__sweep-toggle",
        "grouped-list__sweep-children",
        "list-facet-bar",
        "list-facet-bar__groupby",
        "sweep-expand",
        "sweep-children-cell",
        "sweep-badge",
        "saved-views__panel",
    ):
        assert f".{cls}" in css, cls
    for cls in ("grouped-list__header", "grouped-list__group--collapsed", "grouped-list__sweep-toggle"):
        assert cls in grouped, cls
    assert "list-facet-bar__groupby" in facets
    assert "sweep-children__table" in children

    # Headers and fold toggles are real buttons with expanded state.
    assert grouped.count('type="button"') == 2
    assert grouped.count("aria-expanded=${open}") == 2
    assert "innerHTML" not in grouped + facets + children
    # Imports stay single-line so the page harnesses can strip them.
    for src in (grouped, facets, children):
        for line in src.splitlines():
            if line.startswith("import "):
                assert line.rstrip().endswith(";"), line
