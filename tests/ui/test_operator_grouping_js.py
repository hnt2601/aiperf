# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the pure grouping/faceting helpers in ``lib/grouping.js``."""

from __future__ import annotations

import json

from tests.ui.node_utils import UI_DIR, requires_node, run_node

GROUPING_PATH = UI_DIR / "lib" / "grouping.js"

JOBS = [
    {
        "name": "gemma4-mvp-sweep-ccu-e5dea4-v00",
        "namespace": "perfledger",
        "phase": "Completed",
        "model": "gemma-4",
        "sweepName": "gemma4-mvp-sweep-ccu-e5dea4",
        "variationIndex": 0,
        "startTime": "2026-10-13T10:35:20Z",
        "throughputRps": 0.18,
    },
    {
        "name": "gemma4-mvp-sweep-ccu-e5dea4-v01",
        "namespace": "perfledger",
        "phase": "Running",
        "model": "gemma-4",
        "sweepName": "gemma4-mvp-sweep-ccu-e5dea4",
        "variationIndex": 1,
        "startTime": "2026-10-13T10:38:06Z",
        "throughputRps": 0.35,
    },
    {
        "name": "gemma4-pilot-1-c4-ab12cd",
        "namespace": "perfledger",
        "phase": "Failed",
        "model": "gemma-4",
        "labels": {
            "perfledger.fptcloud.vn/run": "gemma4-pilot-1",
            "perfledger.fptcloud.vn/scenario": "fixed_seq_ref",
            "perfledger.fptcloud.vn/lifecycle": "gateway",
            "perfledger.fptcloud.vn/deploy": "gemma-4-26b",
        },
        "startTime": "2026-10-13T09:00:00Z",
    },
    {
        "name": "qwen-adhoc",
        "namespace": "team-b",
        "phase": "Completed",
        "model": "qwen3",
        "created": "2026-10-13T11:00:00Z",
        "outputTokenThroughputTps": 4100,
    },
]


def _run(expr: str) -> object:
    script = f"""
        import * as g from {GROUPING_PATH.as_uri()!r};
        const JOBS = {json.dumps(JOBS)};
        console.log(JSON.stringify({expr}));
    """
    return json.loads(run_node(script))


@requires_node
def test_parse_name_decodes_child_point_and_sweep_names() -> None:
    assert _run("g.parseName('gemma4-mvp-sweep-ccu-e5dea4-v03')") == {
        "kind": "child",
        "run": "gemma4-mvp-sweep-ccu",
        "sweep": "gemma4-mvp-sweep-ccu-e5dea4",
        "sweep6": "e5dea4",
        "index": 3,
        "trial": None,
    }
    assert _run("g.parseName('run-x-e5dea4-v03-t2')")["trial"] == 2
    assert _run("g.parseName('gemma4-pilot-1-c16-ab12cd')") == {
        "kind": "point",
        "run": "gemma4-pilot-1",
        "conc": 16,
        "sweep6": "ab12cd",
    }
    assert _run("g.parseName('gemma4-mvp-sweep-ccu-e5dea4')") == {
        "kind": "sweep",
        "run": "gemma4-mvp-sweep-ccu",
        "sweep6": "e5dea4",
    }
    assert _run("g.parseName('qwen-adhoc')") is None
    assert _run("g.parseName(null)") is None


@requires_node
def test_derive_run_prefers_labels_then_name_then_sweep_then_bare_name() -> None:
    assert _run("JOBS.map(g.deriveRun)") == [
        "gemma4-mvp-sweep-ccu",
        "gemma4-mvp-sweep-ccu",
        "gemma4-pilot-1",
        "qwen-adhoc",
    ]
    # sweepName from the API wins over an unparseable name
    assert _run("g.deriveRun({name: 'weird', sweepName: 'my-sweep-abc123'})") == "my-sweep"
    assert _run("g.deriveRun({name: 'weird', sweepName: 'free-form'})") == "free-form"


@requires_node
def test_label_lookup_is_prefix_agnostic_and_accepts_aliases() -> None:
    assert _run("g.deriveScenario(JOBS[2])") == "fixed_seq_ref"
    assert _run("g.deriveScenario({labels: {'x.io/profile': 'agentx-ref'}})") == "agentx-ref"
    assert _run("g.deriveLifecycle(JOBS[2])") == "gateway"
    assert _run("g.deriveDeploy(JOBS[2])") == "gemma-4-26b"
    assert _run("g.deriveScenario(JOBS[0])") is None
    assert _run("g.sweepOf({name: 'a', labels: {'aiperf.nvidia.com/sweep-name': 'sw'}})") == "sw"


@requires_node
def test_sweep_child_detection_uses_api_field_or_name() -> None:
    assert _run("JOBS.map(g.isSweepChild)") == [True, True, False, False]
    assert _run("g.isSweepChild({name: 'run-abcdef-v02'})") is True
    assert _run("g.childBadge(JOBS[1])") == "gemma4-mvp-sweep-ccu-e5dea4·v01"
    assert _run("g.childBadge({name: 'r-abcdef-v02-t1', trialIndex: 1})") == "r-abcdef·v02·t1"
    assert _run("g.childBadge(JOBS[3])") is None


@requires_node
def test_group_by_model_orders_by_latest_start_and_counts_phases() -> None:
    groups = _run("g.groupItems(JOBS, 'model').map(x => [x.key, x.total, x.counts, x.bestThroughput])")
    assert groups == [
        ["qwen3", 1, {"running": 0, "completed": 1, "failed": 0, "other": 0}, 4100],
        ["gemma-4", 3, {"running": 1, "completed": 1, "failed": 1, "other": 0}, 0.35],
    ]


@requires_node
def test_group_by_scenario_puts_unlabeled_items_last() -> None:
    assert _run("g.groupItems(JOBS, 'scenario').map(x => [x.key, x.total])") == [
        ["fixed_seq_ref", 1],
        [None, 3],
    ]


@requires_node
def test_group_none_or_unknown_key_returns_single_group() -> None:
    assert _run("g.groupItems(JOBS, 'none').map(x => [x.key, x.total])") == [[None, 4]]
    assert _run("g.groupItems(JOBS, 'bogus').length") == 1
    assert _run("g.groupItems([], 'model')") == []


@requires_node
def test_collapse_sweep_children_folds_children_in_variation_order() -> None:
    rows = _run(
        "g.collapseSweepChildren([JOBS[1], JOBS[2], JOBS[0], JOBS[3]])"
        ".map(r => r.kind === 'sweep' ? [r.kind, r.sweep, r.items.map(j => j.name), r.counts.running] : [r.kind, r.job.name])"
    )
    assert rows == [
        ["sweep", "gemma4-mvp-sweep-ccu-e5dea4", ["gemma4-mvp-sweep-ccu-e5dea4-v00", "gemma4-mvp-sweep-ccu-e5dea4-v01"], 1],
        ["job", "gemma4-pilot-1-c4-ab12cd"],
        ["job", "qwen-adhoc"],
    ]


@requires_node
def test_facets_and_filters() -> None:
    assert _run("g.facetValues(JOBS, 'run')") == ["gemma4-mvp-sweep-ccu", "gemma4-pilot-1", "qwen-adhoc"]
    assert _run("g.facetValues(JOBS, 'lifecycle')") == ["gateway"]
    assert _run("g.applyFacetFilters(JOBS, {run: 'gemma4-mvp-sweep-ccu'}).length") == 2
    assert _run("g.applyFacetFilters(JOBS, {run: '', scenario: null}).length") == 4
    assert _run("g.applyFacetFilters(JOBS, {scenario: 'fixed_seq_ref', lifecycle: 'gateway'}).map(j => j.name)") == [
        "gemma4-pilot-1-c4-ab12cd"
    ]


@requires_node
def test_default_group_key_is_model_only_when_several_models() -> None:
    assert _run("g.defaultGroupKey(JOBS)") == "model"
    assert _run("g.defaultGroupKey(JOBS.slice(0, 3))") == "none"
    assert _run("g.parseGroupKey('RUN', JOBS)") == "run"
    assert _run("g.parseGroupKey('nope', JOBS)") == "model"


@requires_node
def test_phase_bucket_covers_job_and_sweep_phases() -> None:
    assert _run(
        "['Running','Initializing','Aggregating','Completed','Succeeded','Archived','Failed','PartiallyFailed','Cancelled','Unknown',null].map(g.phaseBucket)"
    ) == [
        "running", "running", "running",
        "completed", "completed", "completed",
        "failed", "failed", "failed",
        "other", "other",
    ]


@requires_node
def test_sweeps_api_snake_case_is_accepted() -> None:
    sweeps = [
        {"name": "gemma4-mvp-sweep-ccu-e5dea4", "phase": "Succeeded", "model": "gemma-4", "started_at": "2026-10-13T10:35:06Z"},
        {"name": "other-sweep-abcdef", "phase": "Running", "model": "qwen3", "started_at": "2026-10-13T12:00:00Z",
         "labels": {"perfledger.fptcloud.vn/run": "qwen-capacity"}},
    ]
    script = f"""
        import * as g from {GROUPING_PATH.as_uri()!r};
        const S = {json.dumps(sweeps)};
        console.log(JSON.stringify([S.map(g.deriveRun), g.groupItems(S, 'run').map(x => [x.key, x.counts.running])]));
    """
    assert json.loads(run_node(script)) == [
        ["gemma4-mvp-sweep-ccu", "qwen-capacity"],
        [["qwen-capacity", 1], ["gemma4-mvp-sweep-ccu", 0]],
    ]
