# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the pure helpers and static markup of ``components/model-cards.js``.

The module imports preact for its components, so the harness strips the
imports, stubs ``html``/``useState``/``NsPill``/``palette``, and loads
``lib/grouping.js`` for real through its file URI.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from tests.ui.node_utils import (
    FORMAT_JS,
    UI_DIR,
    requires_node,
    run_node,
)

MODEL_CARDS_PATH = UI_DIR / "components" / "model-cards.js"
GROUPING_PATH = UI_DIR / "lib" / "grouping.js"
DASHBOARD_PATH = UI_DIR / "pages" / "dashboard.js"

NOW = "2026-10-13T12:00:00Z"
NOW_MS = int(datetime(2026, 10, 13, 12, tzinfo=timezone.utc).timestamp() * 1000)

JOBS = [
    # gemma-4: one sweep child running, one finished 2 h ago, one failed 30 h ago (outside window)
    {
        "name": "gemma4-mvp-sweep-ccu-e5dea4-v01",
        "namespace": "perfledger",
        "phase": "Running",
        "model": "gemma-4",
        "sweepName": "gemma4-mvp-sweep-ccu-e5dea4",
        "variationIndex": 1,
        "startTime": "2026-10-13T11:40:00Z",
        "outputTokenThroughputTps": 3200,
    },
    {
        "name": "gemma4-mvp-sweep-ccu-e5dea4-v00",
        "namespace": "perfledger",
        "phase": "Completed",
        "model": "gemma-4",
        "sweepName": "gemma4-mvp-sweep-ccu-e5dea4",
        "variationIndex": 0,
        "startTime": "2026-10-13T09:30:00Z",
        "completionTime": "2026-10-13T10:00:00Z",
        "outputTokenThroughputTps": 2900,
    },
    {
        "name": "gemma4-pilot-1-c4-ab12cd",
        "namespace": "perfledger",
        "phase": "Failed",
        "model": "gemma-4",
        "startTime": "2026-10-12T05:00:00Z",
        "completionTime": "2026-10-12T06:00:00Z",
    },
    # qwen3: one queued, one failed 1 h ago in another namespace
    {
        "name": "qwen-adhoc",
        "namespace": "team-b",
        "phase": "Pending",
        "model": "qwen3",
        "created": "2026-10-13T11:55:00Z",
    },
    {
        "name": "qwen-nightly-c8-ffeedd",
        "namespace": "team-c",
        "phase": "Error",
        "model": "qwen3",
        "created": "2026-10-13T10:30:00Z",
        "completionTime": "2026-10-13T11:00:00Z",
        "throughputRps": 1.5,
    },
    # llama: nothing in the window, nothing running -> idle
    {
        "name": "llama-old",
        "namespace": "perfledger",
        "phase": "Completed",
        "model": "llama-3",
        "completionTime": "2026-10-10T11:00:00Z",
        "throughputRps": 9.0,
    },
    # no model: never a card
    {"name": "modelless", "namespace": "perfledger", "phase": "Running", "created": "2026-10-13T11:59:00Z"},
]

SWEEPS = [
    {
        "name": "gemma4-mvp-sweep-ccu-e5dea4",
        "namespace": "perfledger",
        "phase": "Running",
        "model": "gemma-4",
        "total_variations": 7,
        "completed_runs": 1,
        "failed_runs": 0,
        "started_at": "2026-10-13T09:30:00Z",
    },
    {
        "name": "gemma4-done-aaaaaa",
        "namespace": "perfledger",
        "phase": "Succeeded",
        "model": "gemma-4",
        "total_variations": 3,
        "completed_runs": 3,
    },
    # running sweep whose children have not been created yet
    {
        "name": "mistral-cap-bbbbbb",
        "namespace": "team-d",
        "phase": "Running",
        "model": "mistral-7b",
        "total_variations": 4,
        "completed_runs": 0,
        "started_at": "2026-10-13T11:58:00Z",
    },
]


def _module_js() -> str:
    source = MODEL_CARDS_PATH.read_text(encoding="utf-8")
    source = re.sub(r"^import .*;\n", "", source, flags=re.MULTILINE)
    source = re.sub(r"^export (function|const|let) ", r"\1 ", source, flags=re.MULTILINE)
    return source


def _run(expr: str) -> object:
    script = f"""
        import {{ groupItems, phaseBucket, deriveRun }} from {GROUPING_PATH.as_uri()!r};
        const palette = new Proxy({{}}, {{ get: () => '#000000' }});
        const rendered = [];
        function html(strings, ...values) {{ return {{ strings, values }}; }}
        function useState(v) {{ return [v, () => {{}}]; }}
        function NsPill() {{ return null; }}
        {FORMAT_JS}
        {_module_js()}
        const JOBS = {json.dumps(JOBS)};
        const SWEEPS = {json.dumps(SWEEPS)};
        const NOW = {NOW_MS};
        console.log(JSON.stringify({expr}));
    """
    return json.loads(run_node(script))


@requires_node
def test_now_constant_matches_fixture() -> None:
    assert _run(f"Date.parse({NOW!r})") == NOW_MS


@requires_node
def test_model_cards_count_running_queued_and_24h_outcomes_per_model() -> None:
    cards = _run(
        "modelCardsData(JOBS, SWEEPS, NOW).map(c => [c.model, c.namespaces, c.running, c.queued, c.completed24h, c.failed24h, c.idle])"
    )
    by_model = {c[0]: c[1:] for c in cards}
    # gemma-4: the 30 h-old failure is outside the window
    assert by_model["gemma-4"] == [["perfledger"], 1, 0, 1, 0, False]
    # qwen3: Pending counts as queued, Error as failed; namespaces are merged and sorted
    assert by_model["qwen3"] == [["team-b", "team-c"], 0, 1, 0, 1, False]
    # llama-3: nothing running, nothing in 24 h -> idle
    assert by_model["llama-3"] == [["perfledger"], 0, 0, 0, 0, True]
    # a job without a model never gets a card
    assert None not in by_model and "" not in by_model


@requires_node
def test_model_cards_are_sorted_by_latest_start_then_name() -> None:
    assert _run("modelCardsData(JOBS, SWEEPS, NOW).map(c => c.model)") == [
        "mistral-7b",  # sweep started 11:58 (no child jobs yet)
        "qwen3",       # created 11:55
        "gemma-4",     # started 11:40
        "llama-3",     # no start timestamp at all
    ]
    assert _run("modelCardsData(JOBS, SWEEPS, NOW).map(c => c.latestStart > 0)") == [True, True, True, False]


@requires_node
def test_only_running_sweeps_are_attached_with_progress() -> None:
    cards = _run("Object.fromEntries(modelCardsData(JOBS, SWEEPS, NOW).map(c => [c.model, c.sweeps]))")
    assert cards["gemma-4"] == [
        {
            "name": "gemma4-mvp-sweep-ccu-e5dea4",
            "namespace": "perfledger",
            "completed": 1,
            "failed": 0,
            "total": 7,
            "phase": "Running",
        }
    ]
    assert cards["qwen3"] == []
    # A running sweep with no children yet still earns a (non-idle) card.
    assert cards["mistral-7b"] == [
        {"name": "mistral-cap-bbbbbb", "namespace": "team-d", "completed": 0, "failed": 0, "total": 4, "phase": "Running"}
    ]
    assert _run("modelCardsData(JOBS, SWEEPS, NOW).find(c => c.model === 'mistral-7b').namespaces") == ["team-d"]


@requires_node
def test_sweeps_accept_camel_case_too() -> None:
    sweeps = [{"name": "s-abcdef", "phase": "Running", "model": "gemma-4", "totalVariations": 5, "completedRuns": 2}]
    assert _run(f"modelCardsData(JOBS, {json.dumps(sweeps)}, NOW).find(c => c.model === 'gemma-4').sweeps[0].total") == 5
    assert _run(f"modelCardsData(JOBS, {json.dumps(sweeps)}, NOW).find(c => c.model === 'gemma-4').sweeps[0].completed") == 2


@requires_node
def test_best_throughput_comes_from_grouping_summary() -> None:
    best = _run("Object.fromEntries(modelCardsData(JOBS, SWEEPS, NOW).map(c => [c.model, c.bestThroughput]))")
    assert best == {"gemma-4": 3200, "qwen3": 1.5, "llama-3": 9.0, "mistral-7b": None}


@requires_node
def test_split_idle_cards_hides_models_with_no_recent_activity() -> None:
    assert _run("(() => { const s = splitIdleCards(modelCardsData(JOBS, SWEEPS, NOW)); return [s.active.map(c => c.model), s.idle.map(c => c.model)]; })()") == [
        ["mistral-7b", "qwen3", "gemma-4"],
        ["llama-3"],
    ]
    assert _run("splitIdleCards([])") == {"active": [], "idle": []}
    assert _run("splitIdleCards(null)") == {"active": [], "idle": []}


@requires_node
def test_window_cutoff_is_exactly_24h_and_uses_completion_time_first() -> None:
    edge = {"name": "edge", "phase": "Completed", "model": "m", "created": "2026-10-13T11:00:00Z", "completionTime": "2026-10-12T12:00:00Z"}
    assert _run(f"finishedWithin({json.dumps(edge)}, NOW)") is True
    assert _run(f"finishedWithin({json.dumps(edge)}, NOW + 1)") is False
    # completionTime wins over created even when created is inside the window
    assert _run(f"finishedWithin({json.dumps(edge)}, NOW + 60_000)") is False
    # running jobs are never "finished", whatever their timestamps say
    assert _run("finishedWithin({phase: 'Running', completionTime: '2026-10-13T11:00:00Z'}, NOW)") is False
    # a terminal job without any timestamp is not shown (it cannot be placed in time)
    assert _run("finishedWithin({phase: 'Completed'}, NOW)") is False
    assert _run("DASHBOARD_WINDOW_MS") == 24 * 3600 * 1000


@requires_node
def test_dashboard_jobs_keeps_live_jobs_and_24h_finishes_only() -> None:
    assert _run("dashboardJobs(JOBS, NOW).map(j => j.name)") == [
        "gemma4-mvp-sweep-ccu-e5dea4-v01",
        "gemma4-mvp-sweep-ccu-e5dea4-v00",
        "qwen-adhoc",
        "qwen-nightly-c8-ffeedd",
        "modelless",
    ]
    assert _run("liveJobs(JOBS).map(j => j.name)") == [
        "gemma4-mvp-sweep-ccu-e5dea4-v01",
        "qwen-adhoc",
        "modelless",
    ]
    assert _run("finishedJobsWithin(JOBS, NOW).map(j => j.name)") == [
        "gemma4-mvp-sweep-ccu-e5dea4-v00",
        "qwen-nightly-c8-ffeedd",
    ]
    assert _run("dashboardJobs(null, NOW)") == []
    assert _run("dashboardJobs([null, undefined], NOW)") == []


@requires_node
def test_group_by_run_preserves_first_appearance_and_counts_failures() -> None:
    assert _run("groupByRun(finishedJobsWithin(JOBS, NOW).concat([JOBS[2]]), deriveRun).map(g => [g.run, g.items.map(j => j.name), g.failed])") == [
        ["gemma4-mvp-sweep-ccu", ["gemma4-mvp-sweep-ccu-e5dea4-v00"], 0],
        ["qwen-nightly", ["qwen-nightly-c8-ffeedd"], 1],
        ["gemma4-pilot-1", ["gemma4-pilot-1-c4-ab12cd"], 1],
    ]
    assert _run("groupByRun([], deriveRun)") == []


# Walk a rendered htm tree (stubbed as {strings, values}) and collect every
# data-testid, literal or interpolated. The stub does not invoke nested
# components, so a `<${ModelCard} card=${c} />` child is expanded by calling
# ModelCard on the `card` prop that follows it.
_WALK_TESTIDS_JS = """
  const walk = (node, ids) => {
    if (node == null) return ids;
    if (Array.isArray(node)) { node.forEach(n => walk(n, ids)); return ids; }
    if (typeof node !== 'object') return ids;
    if (node.strings) {
      node.strings.forEach((s, i) => {
        if (/data-testid=$/.test(s) && typeof node.values[i] === 'string') ids.push(node.values[i]);
        for (const lit of s.match(/data-testid="([^"]+)"/g) ?? []) ids.push(lit.slice(13, -1));
        if (/ card=$/.test(s) && node.values[0] === ModelCard) walk(ModelCard({ card: node.values[i] }), ids);
      });
      node.values.forEach(v => walk(v, ids));
    }
    return ids;
  };
"""


@requires_node
def test_model_cards_component_renders_one_card_per_active_model() -> None:
    ids = _run(f"(() => {{ {_WALK_TESTIDS_JS} return walk(ModelCards({{ jobs: JOBS, sweeps: SWEEPS, now: NOW }}), []); }})()")
    assert "model-cards" in ids
    assert "model-card-gemma-4" in ids
    assert "model-card-qwen3" in ids
    assert "model-card-mistral-7b" in ids
    assert "model-card-llama-3" not in ids  # idle, hidden by default
    assert "model-cards-idle-toggle" in ids
    assert "model-card-sweeps-gemma-4" in ids
    assert "model-card-sweeps-qwen3" not in ids  # no running sweep
    assert "model-card-failed-qwen3" in ids


@requires_node
def test_model_card_click_and_keyboard_call_on_open_with_the_full_model_name() -> None:
    expr = """
      (() => {
        const opened = [];
        const card = modelCardsData(JOBS, SWEEPS, NOW).find(c => c.model === 'gemma-4');
        const tree = ModelCard({ card, onOpen: (m) => opened.push(m) });
        const attrs = {};
        tree.strings.forEach((s, i) => {
          const m = s.match(/(onclick|onkeydown|aria-label|title)=$/);
          if (m) attrs[m[1]] = tree.values[i];
        });
        attrs.onclick();
        let prevented = 0;
        attrs.onkeydown({ key: 'Enter', preventDefault: () => { prevented += 1; } });
        attrs.onkeydown({ key: ' ', preventDefault: () => { prevented += 1; } });
        attrs.onkeydown({ key: 'a', preventDefault: () => { prevented += 1; } });
        return { opened, prevented, label: attrs['aria-label'], title: attrs.title };
      })()
    """
    assert _run(expr) == {
        "opened": ["gemma-4", "gemma-4", "gemma-4"],
        "prevented": 2,
        "label": "Open jobs for model gemma-4",
        "title": "gemma-4",
    }


@requires_node
def test_model_cards_component_returns_null_without_models() -> None:
    assert _run("ModelCards({ jobs: [], sweeps: [], now: NOW })") is None
    assert _run("ModelCards({ jobs: [JOBS[6]], sweeps: [], now: NOW })") is None


def test_model_card_markup_is_keyboard_accessible_and_links_to_jobs_by_model() -> None:
    source = MODEL_CARDS_PATH.read_text(encoding="utf-8")
    assert 'role="button"' in source
    assert 'tabindex="0"' in source
    assert "e.key === 'Enter' || e.key === ' '" in source
    assert "data-testid=${'model-card-' + card.model}" in source
    assert 'role="progressbar"' in source
    assert "aria-valuenow=${s.completed}" in source
    assert "aria-valuemax=${s.total || 1}" in source
    assert "palette.red" in source  # failed 24 h turns red
    # No navigation inside the component: the page decides where a card goes.
    assert "navigate(" not in source


def test_dashboard_wires_model_cards_filter_and_columns() -> None:
    source = DASHBOARD_PATH.read_text(encoding="utf-8")
    assert "from '../components/model-cards.js'" in source
    assert "<${ModelCards} jobs=${scopedJobs} sweeps=${scopedSweeps} onOpen=${openModel} now=${now} />" in source
    # Cards open the Jobs page scoped to the model and grouped by run.
    assert "hashUrl('/jobs', { model, group: 'run' })" in source
    # Quick filter lives in the URL under `model`.
    assert 'data-testid="dashboard-model-select"' in source
    assert "setQuery({ model: e.target.value })" in source
    assert "query.value.model" in source
    # Two columns, both scoped to the 24 h window.
    assert 'data-testid="dashboard-running-column"' in source
    assert 'data-testid="dashboard-finished-column"' in source
    assert "const finished = finishedJobsWithin(scopedJobs, now);" in source
    assert "const live = liveJobs(scopedJobs);" in source
    # Finished rows are grouped by run with a header row.
    assert "groupByRun(recentJobs(finished, RECENT_LIMIT), deriveRun)" in source
    assert "dashboard-run-header-" in source
    # Sweeps are polled alongside jobs with a named source.
    assert "api.listSweeps()" in source
    assert "{ source: 'sweeps' }" in source
    # The old flat "Active Jobs" block and the bottom "Recent Jobs" table are gone.
    assert '<span class="section-title">Active Jobs</span>' not in source
    assert '<div class="section-title">Recent Jobs</div>' not in source
    assert "running.map(job =>" not in source
