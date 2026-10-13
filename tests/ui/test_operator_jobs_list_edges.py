# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Edge-case tests for the operator jobs list page and job-detail links."""

from __future__ import annotations

import json
from pathlib import Path

from tests.ui.node_utils import local_module_js, run_node

UI_ROOT = Path(__file__).resolve().parents[2] / "src" / "aiperf" / "operator" / "ui"
JOBS_PAGE_PATH = UI_ROOT / "pages" / "jobs.js"
JOB_TABLE_PATH = UI_ROOT / "components" / "job-table.js"
ROUTER_PATH = UI_ROOT / "lib" / "router.js"
FACET_FILTERS_PATH = UI_ROOT / "components" / "facet-filters.js"

# lib/grouping.js is import-free, so the real helpers are spliced into the
# page harness instead of being stubbed: the page's facet filters, search and
# default grouping are exercised against the same code the browser runs.
GROUPING_JS = local_module_js("lib/grouping.js")


def _job_table_script(expression: str) -> str:
    return f"""
        import fs from 'node:fs';
        const source = fs.readFileSync({str(JOB_TABLE_PATH)!r}, 'utf8')
          .replace(new RegExp('^import .*;\\n', 'gm'), '')
          .replace('export function JobTable', 'function JobTable');

        function html(strings, ...values) {{
          return {{ __html: true, strings: Array.from(strings), values }};
        }}
        function useState(initial) {{
          return [typeof initial === 'function' ? initial() : initial, () => {{}}];
        }}
        function useMemo(fn) {{ return fn(); }}
        function useEffect() {{}}
        function useRef() {{ return {{ current: null }}; }}
        function phaseColor() {{ return '#89b4fa'; }}
        const palette = {{ surface0: '#313244', blue: '#89b4fa' }};
        function fmtNumber(value, digits) {{ return Number(value).toFixed(digits); }}
        function fmtThroughput(value) {{ return String(value); }}
        function navigate() {{}}
        function NsPill(props) {{ return {{ component: 'NsPill', props }}; }}
        function RelativeTime(props) {{ return {{ component: 'RelativeTime', props }}; }}

        eval(source + '\\nglobalThis.JobTable = JobTable;');

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

        function rowIds(rendered) {{
          return collectValues(rendered)
            .filter((value) => typeof value === 'string'
              && value.startsWith('job-row-')
              && !value.startsWith('job-row-ns-'));
        }}

        {expression}
    """


def _jobs_page_script(
    local_jobs: list[dict[str, object]], query_value: dict[str, str], expression: str
) -> str:
    return f"""
        import fs from 'node:fs';
        const source = fs.readFileSync({str(JOBS_PAGE_PATH)!r}, 'utf8')
          .replace(new RegExp('^import .*;\\n', 'gm'), '')
          .replace('export function Jobs', 'function Jobs');

        function html(strings, ...values) {{
          return {{ __html: true, strings: Array.from(strings), values }};
        }}
        function useState(initial) {{
          return [typeof initial === 'function' ? initial() : initial, () => {{}}];
        }}
        function useEffect() {{}}
        function useMemo(fn) {{ return fn(); }}
        const api = {{ listJobs: async () => ({{ jobs: [] }}) }};
        function poll() {{}}
        const jobs = {{ value: {json.dumps(local_jobs)} }};
        const freshness = {{ value: {{ jobs: null }} }};
        function dedupeByNsName(items) {{ return items; }}
        function buildJobPath(job) {{ return '/detail/' + (job.name ?? job.job_id ?? ''); }}
        function navigate() {{}}
        const query = {{ value: {json.dumps(query_value)} }};
        function setQuery() {{}}
        const palette = {{
          mantle: '#181825', surface0: '#313244', surface1: '#45475a', text: '#cdd6f4',
          overlay0: '#6c7086', teal: '#94e2d5', mauve: '#cba6f7', peach: '#fab387'
        }};
        function JobTable() {{}}
        function FreshnessPill() {{}}
        function StaleBanner() {{}}
        function LoadingPanel() {{}}
        function replaceRoute() {{}}
        function hashUrl() {{ return '#/jobs'; }}
        const route = {{ value: '/jobs' }};
        {GROUPING_JS}
        // GroupedList is a plain render function in the page; the stub keeps
        // group bodies in the tree so tests can see which jobs each holds.
        function GroupedList({{ groups, renderGroup }}) {{ return groups.map(renderGroup); }}
        function JobGroupBody() {{}}
        function useCollapsedGroups() {{ return [() => false, () => {{}}]; }}
        function FacetSelects() {{}}
        function FacetChips() {{}}
        function GroupBySelect() {{}}
        function SavedViewsMenu() {{}}

        eval(source + '\\nglobalThis.Jobs = Jobs;');

        // Jobs rendered inside grouped bodies: [[name, ...], ...] per group.
        function groupBodies(node, out = []) {{
          if (node == null || node === false) return out;
          if (Array.isArray(node)) {{
            for (const item of node) groupBodies(item, out);
            return out;
          }}
          if (typeof node === 'object' && node.__html) {{
            for (let i = 0; i < node.values.length; i++) {{
              if (node.values[i] === JobGroupBody) out.push(node.values[i + 1].map((job) => job.name));
            }}
            for (const value of node.values) groupBodies(value, out);
          }}
          return out;
        }}

        function findJobTableJobs(node) {{
          if (node == null || node === false) return null;
          if (Array.isArray(node)) {{
            for (const item of node) {{
              const found = findJobTableJobs(item);
              if (found) return found;
            }}
            return null;
          }}
          if (typeof node === 'object' && node.__html) {{
            for (let i = 0; i < node.values.length; i++) {{
              if (node.values[i] === JobTable) return node.values[i + 1];
            }}
            for (const value of node.values) {{
              const found = findJobTableJobs(value);
              if (found) return found;
            }}
          }}
          return null;
        }}

        const rendered = Jobs();
        const renderedJobs = findJobTableJobs(rendered) ?? [];
        {expression}
    """


def _router_import_script() -> str:
    return f"""
        import {{ readFileSync }} from 'node:fs';
        let source = readFileSync({str(ROUTER_PATH)!r}, 'utf8');
        source = source.replace(
          "import {{ signal }} from '@preact/signals';",
          "const signal = (value) => ({{ value }});",
        );
        const routerModuleUrl = 'data:text/javascript;base64,' + Buffer.from(source).toString('base64');
        const router = await import(routerModuleUrl);
    """


def test_job_table_sorts_current_and_archived_jobs_by_age_without_phase_bucketing() -> (
    None
):
    jobs = [
        {
            "namespace": "bench",
            "name": "new-archived",
            "phase": "Archived",
            "created": "2026-05-03T00:00:00Z",
        },
        {
            "namespace": "bench",
            "name": "old-running",
            "phase": "Running",
            "created": "2026-05-01T00:00:00Z",
        },
        {
            "namespace": "bench",
            "name": "mid-complete",
            "phase": "Completed",
            "created": "2026-05-02T00:00:00Z",
        },
    ]
    script = _job_table_script(
        f"""
        const rendered = JobTable({{
          jobs: {json.dumps(jobs)},
          sort: {{ key: 'age', dir: -1 }},
          onSortChange: () => {{}},
        }});
        console.log(JSON.stringify(rowIds(rendered)));
        """
    )

    assert json.loads(run_node(script)) == [
        "job-row-bench-new-archived",
        "job-row-bench-mid-complete",
        "job-row-bench-old-running",
    ]


def test_jobs_page_phase_filters_match_expected_status_buckets_case_insensitively() -> (
    None
):
    local_jobs = [
        {"namespace": "ns", "name": "starting", "phase": "Initializing"},
        {"namespace": "ns", "name": "live", "phase": "RUNNING"},
        {"namespace": "ns", "name": "done", "phase": "Succeeded"},
        {"namespace": "ns", "name": "bad", "phase": "Error"},
        {"namespace": "ns", "name": "archived", "phase": "Archived"},
    ]
    script = _jobs_page_script(
        local_jobs,
        {},
        """
        const buckets = {};
        for (const phase of ['running', 'completed', 'failed']) {
          query.value = { phase };
          buckets[phase] = findJobTableJobs(Jobs()).map((job) => job.name);
        }
        query.value = {};
        buckets.all = findJobTableJobs(Jobs()).map((job) => job.name);
        console.log(JSON.stringify(buckets));
        """,
    )

    assert json.loads(run_node(script)) == {
        "running": ["starting", "live"],
        "completed": ["done"],
        "failed": ["bad"],
        "all": ["starting", "live", "done", "bad", "archived"],
    }


def test_jobs_page_search_matches_name_or_namespace_case_insensitively() -> None:
    local_jobs = [
        {"namespace": "Team-A", "name": "load-test", "phase": "Running"},
        {"namespace": "default", "name": "MODEL-SMOKE", "phase": "Completed"},
        {"namespace": "default", "name": "unrelated", "phase": "Failed"},
    ]
    script = _jobs_page_script(
        local_jobs,
        {"q": "team"},
        """
        const byNamespace = renderedJobs.map((job) => job.name);
        query.value = { q: 'model' };
        const byName = findJobTableJobs(Jobs()).map((job) => job.name);
        console.log(JSON.stringify({ byNamespace, byName }));
        """,
    )

    assert json.loads(run_node(script)) == {
        "byNamespace": ["load-test"],
        "byName": ["MODEL-SMOKE"],
    }


def test_jobs_page_namespace_and_model_filters_stack_exactly() -> None:
    local_jobs = [
        {
            "namespace": "prod",
            "name": "llama-prod",
            "phase": "Running",
            "model": "llama",
        },
        {
            "namespace": "prod",
            "name": "mixtral-prod",
            "phase": "Running",
            "model": "mixtral",
        },
        {"namespace": "dev", "name": "llama-dev", "phase": "Running", "model": "llama"},
        {
            "namespace": "production",
            "name": "llama-production",
            "phase": "Running",
            "model": "llama",
        },
    ]
    script = _jobs_page_script(
        local_jobs,
        {"ns": "prod", "model": "llama"},
        """
        console.log(JSON.stringify(renderedJobs.map((job) => job.name)));
        """,
    )

    assert json.loads(run_node(script)) == ["llama-prod"]


def test_build_job_path_encodes_names_and_pins_run_epoch_variants() -> None:
    script = f"""
        global.window = {{
          location: {{ hash: '#/' }},
          addEventListener() {{}},
        }};
        {_router_import_script()}
        const {{ buildJobPath }} = router;
        const paths = {{
          nameOnly: buildJobPath({{ namespace: 'team/a', name: 'bench/job 1' }}),
          jobId: buildJobPath({{ namespace: 'analytics', job_id: 'archive/job' }}),
          nameBeatsJobId: buildJobPath({{ namespace: 'ns', name: 'job-name', job_id: 'job-id' }}),
          runEpoch: buildJobPath({{ namespace: 'ns', name: 'job', runEpoch: '2026-05-18T03:04:05Z' }}),
          snakeRunEpoch: buildJobPath({{ namespace: 'ns', job_id: 'job/id', run_epoch: 'epoch/with slash' }}),
          childRunEpoch: buildJobPath({{ namespace: 'ns', name: 'child', runEpoch: 'parent', childRunEpoch: 42 }}),
        }};
        console.log(JSON.stringify(paths));
    """

    assert json.loads(run_node(script)) == {
        "nameOnly": "/jobs/team%2Fa/bench%2Fjob%201",
        "jobId": "/jobs/analytics/archive%2Fjob",
        "nameBeatsJobId": "/jobs/ns/job-name",
        "runEpoch": "/jobs/ns/job/runs/2026-05-18T03%3A04%3A05Z",
        "snakeRunEpoch": "/jobs/ns/job%2Fid/runs/epoch%2Fwith%20slash",
        "childRunEpoch": "/jobs/ns/child/runs/42",
    }


def test_jobs_page_row_click_delegates_to_build_job_path_for_links() -> None:
    source = JOBS_PAGE_PATH.read_text()
    assert "navigate(buildJobPath(job))" in source
    assert "function handleRowClick(job)" in source
    assert "onRowClick=${handleRowClick}" in source


def test_jobs_page_uses_shared_freshness_source_and_stale_banner() -> None:
    source = (UI_ROOT / "pages" / "jobs.js").read_text(encoding="utf-8")

    assert (
        "import { FreshnessPill, StaleBanner } from '../components/freshness.js';"
        in source
    )
    assert "freshness.value.jobs" in source
    assert "source: 'jobs'" in source
    assert '<${StaleBanner} source=${jobsFreshness} label="Jobs list" />' in source
    assert "<${FreshnessPill} source=${jobsFreshness}" in source


_LABELLED_JOBS = [
    {
        "namespace": "perfledger",
        "name": "gemma4-pilot-1-c4-ab12cd",
        "phase": "Completed",
        "model": "gemma-4",
        "labels": {
            "perfledger.fptcloud.vn/run": "gemma4-pilot-1",
            "perfledger.fptcloud.vn/scenario": "fixed_seq_ref",
            "perfledger.fptcloud.vn/lifecycle": "gateway",
            "perfledger.fptcloud.vn/deploy": "gemma-4-26b",
        },
    },
    {
        "namespace": "perfledger",
        "name": "gemma4-pilot-1-c16-ab12cd",
        "phase": "Running",
        "model": "gemma-4",
        "labels": {
            "perfledger.fptcloud.vn/run": "gemma4-pilot-1",
            "perfledger.fptcloud.vn/scenario": "fixed_seq_ref",
            "perfledger.fptcloud.vn/lifecycle": "internal",
        },
    },
    {
        "namespace": "perfledger",
        "name": "qwen-cap-e5dea4-v00",
        "phase": "Completed",
        "model": "qwen3",
        "sweepName": "qwen-cap-e5dea4",
        "variationIndex": 0,
        "labels": {"perfledger.fptcloud.vn/scenario": "agentx-ref"},
    },
    {"namespace": "team-b", "name": "adhoc", "phase": "Failed", "model": "qwen3"},
]


def test_jobs_page_facet_filters_from_url_stack_with_existing_filters() -> None:
    script = _jobs_page_script(
        _LABELLED_JOBS,
        {"run": "gemma4-pilot-1", "group": "none"},
        """
        const out = { run: renderedJobs.map((job) => job.name) };
        query.value = { run: 'gemma4-pilot-1', lifecycle: 'gateway', group: 'none' };
        out.runAndLifecycle = findJobTableJobs(Jobs()).map((job) => job.name);
        query.value = { scenario: 'agentx-ref', group: 'none' };
        out.scenario = findJobTableJobs(Jobs()).map((job) => job.name);
        query.value = { deploy: 'gemma-4-26b', phase: 'running', group: 'none' };
        out.deployAndPhase = (findJobTableJobs(Jobs()) ?? []).map((job) => job.name);
        query.value = { run: 'nope', group: 'none' };
        out.unknownRun = (findJobTableJobs(Jobs()) ?? []).map((job) => job.name);
        console.log(JSON.stringify(out));
        """,
    )

    assert json.loads(run_node(script)) == {
        "run": ["gemma4-pilot-1-c4-ab12cd", "gemma4-pilot-1-c16-ab12cd"],
        "runAndLifecycle": ["gemma4-pilot-1-c4-ab12cd"],
        "scenario": ["qwen-cap-e5dea4-v00"],
        "deployAndPhase": [],
        "unknownRun": [],
    }


def test_jobs_page_search_matches_run_scenario_and_sweep_name() -> None:
    script = _jobs_page_script(
        _LABELLED_JOBS,
        {"q": "pilot", "group": "none"},
        """
        const out = { run: renderedJobs.map((job) => job.name) };
        query.value = { q: 'AGENTX', group: 'none' };
        out.scenario = findJobTableJobs(Jobs()).map((job) => job.name);
        query.value = { q: 'qwen-cap-e5dea4', group: 'none' };
        out.sweep = findJobTableJobs(Jobs()).map((job) => job.name);
        console.log(JSON.stringify(out));
        """,
    )

    assert json.loads(run_node(script)) == {
        "run": ["gemma4-pilot-1-c4-ab12cd", "gemma4-pilot-1-c16-ab12cd"],
        "scenario": ["qwen-cap-e5dea4-v00"],
        "sweep": ["qwen-cap-e5dea4-v00"],
    }


def test_jobs_page_groups_by_model_by_default_and_flat_when_one_model_or_forced() -> (
    None
):
    script = _jobs_page_script(
        _LABELLED_JOBS,
        {},
        """
        const out = {};
        let tree = Jobs();
        out.defaultFlat = findJobTableJobs(tree) != null;
        out.defaultGroups = groupBodies(tree);
        query.value = { model: 'qwen3' };
        tree = Jobs();
        out.oneModelFlat = findJobTableJobs(tree).map((job) => job.name);
        out.oneModelGroups = groupBodies(tree);
        query.value = { group: 'none' };
        out.forcedFlat = findJobTableJobs(Jobs()).map((job) => job.name).length;
        query.value = { group: 'run' };
        out.byRun = groupBodies(Jobs());
        query.value = { group: 'sweep' };
        out.bySweep = groupBodies(Jobs());
        query.value = { group: 'bogus' };
        out.bogus = groupBodies(Jobs()).length;
        console.log(JSON.stringify(out));
        """,
    )

    assert json.loads(run_node(script)) == {
        "defaultFlat": False,
        # Two models -> grouped; no start times so groups fall back to key order.
        "defaultGroups": [
            ["gemma4-pilot-1-c4-ab12cd", "gemma4-pilot-1-c16-ab12cd"],
            ["qwen-cap-e5dea4-v00", "adhoc"],
        ],
        "oneModelFlat": ["qwen-cap-e5dea4-v00", "adhoc"],
        "oneModelGroups": [],
        "forcedFlat": 4,
        "byRun": [
            ["adhoc"],
            ["gemma4-pilot-1-c4-ab12cd", "gemma4-pilot-1-c16-ab12cd"],
            ["qwen-cap-e5dea4-v00"],
        ],
        "bySweep": [["qwen-cap-e5dea4-v00"], ["gemma4-pilot-1-c4-ab12cd", "gemma4-pilot-1-c16-ab12cd", "adhoc"]],
        "bogus": 2,
    }


def test_jobs_page_wires_facet_group_and_view_controls_to_url_keys() -> None:
    source = JOBS_PAGE_PATH.read_text(encoding="utf-8")
    facets = FACET_FILTERS_PATH.read_text(encoding="utf-8")

    for key in ("run", "scenario", "lifecycle", "deploy"):
        assert f"const {key}Filter = q.{key} ?? '';" in source
    assert "const JOB_FACETS = ['run', 'scenario', 'lifecycle', 'deploy'];" in source
    assert "parseGroupKey(q.group, filtered)" in source
    assert "onChange=${value => setQuery({ group: value })}" in source
    assert 'testid="jobs-group-select"' in source
    assert "keys=${GROUP_KEYS}" in source
    assert "groupKey === 'none' && html`<${JobTable}" in source
    assert "foldSweeps=${groupKey !== 'sweep'}" in source
    assert "storageKey: 'jobs.' + groupKey" in source
    assert '<${SavedViewsMenu} page="jobs" />' in source
    # Facet chips/selects share one component and expose stable test ids.
    assert "data-testid=${d.key + '-filter-chip'}" in facets
    assert "data-testid=${testidPrefix + f.key + '-filter-select'}" in facets
    assert "onkeydown=${(e) => { if (e.key === 'Enter' || e.key === ' ')" in facets
    # "Clear" drops the facet keys too, via a history replace so Back stays one step.
    clear_body = source[source.index("function clearFilters") : source.index("function chipKeyHandler")]
    assert "...FACET_CLEAR" in clear_body
    assert "replaceRoute(hashUrl(route.value" in clear_body
