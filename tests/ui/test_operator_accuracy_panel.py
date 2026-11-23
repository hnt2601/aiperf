# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the operator UI ANALYZE → Accuracy page (pure helpers under node + static wiring checks)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from tests.ui.node_utils import run_node

_UI_ROOT = Path(__file__).resolve().parents[2] / "src" / "aiperf" / "operator" / "ui"
_HELPERS = (_UI_ROOT / "pages" / "accuracy-helpers.js").as_uri()
_PAGE = _UI_ROOT / "pages" / "accuracy.js"


def _node(body: str) -> Any:
    script = f"""
        const h = await import({_HELPERS!r});
        console.log(JSON.stringify((() => {{ {body} }})()));
    """
    return json.loads(run_node(script))


def test_formatters_handle_missing_and_out_of_range_values() -> None:
    out = _node(
        """
        return {
          rate: [h.fmtRate(0.6444), h.fmtRate(null), h.fmtRate(NaN), h.fmtRate(0.3, 0)],
          ci: [h.fmtCi([0.618, 0.67]), h.fmtCi(null), h.fmtCi([0.1]), h.fmtCi([NaN, 1])],
          count: [h.fmtCount(850, 1319), h.fmtCount(null, 10), h.fmtCount(3, null)],
          labels: [h.labelsText({pass: 6, fail: 4, timeout: 4}), h.labelsText({}), h.labelsText(null)],
          bar: [h.barPercent(0.5), h.barPercent(1.5), h.barPercent(-1), h.barPercent(null)],
        };
        """
    )
    assert out == {
        "rate": ["64.4%", "—", "—", "30%"],
        "ci": ["61.8–67.0%", "—", "—", "—"],
        "count": ["850/1,319", "—/10", "—"],
        "labels": ["pass 6 · fail 4 · timeout 4", "—", "—"],
        "bar": [50, 100, 0, 0],
    }


def test_only_http_urls_become_links() -> None:
    out = _node(
        """
        return ['javascript:alert(1)', 'data:text/html,x', 'ftp://h/x', 'not a url', '', null, 42,
                'https://h.example/p?a=1#/jobs/x'].map(h.safeHttpUrl);
        """
    )
    assert out == [None, None, None, None, None, None, None, "https://h.example/p?a=1#/jobs/x"]


def test_build_query_drops_empty_filters_and_encodes_values() -> None:
    out = _node(
        """
        return [
          h.buildQuery({benchmark: 'gsm8k', kind: '', model: 'qwen 3', limit: 5}),
          h.buildQuery({}), h.buildQuery(null), h.buildQuery({status: 'candidate', junk: 'x'}),
        ];
        """
    )
    assert out == ["?benchmark=gsm8k&model=qwen+3&limit=5", "", "", "?status=candidate"]


def test_group_by_benchmark_orders_groups_by_newest_run_and_keeps_row_order() -> None:
    out = _node(
        """
        const rows = [
          {point_id: 'a', benchmark: 'impossible_lcb', kind: 'behavior', recorded_at: '2026-11-20T09:00:00Z'},
          {point_id: 'b', benchmark: 'gsm8k', kind: 'accuracy', recorded_at: '2026-11-17T03:00:00Z'},
          {point_id: 'c', benchmark: 'impossible_lcb', kind: 'behavior', recorded_at: '2026-11-18T03:00:00Z'},
          {point_id: 'd', benchmark: 'gsm8k', kind: 'accuracy', recorded_at: '2026-11-21T03:00:00Z'},
        ];
        return [h.groupByBenchmark(rows).map((g) => [g.benchmark, g.rows.map((r) => r.point_id)]), h.groupByBenchmark(null)];
        """
    )
    assert out == [[["gsm8k", ["b", "d"]], ["impossible_lcb", ["a", "c"]]], []]


def test_row_notes_carry_the_caveats_that_must_travel_with_the_numbers() -> None:
    out = _node(
        """
        const behavior = {
          kind: 'behavior', status: 'candidate', pilot: true, gate: {mode: 'report'}, audit_flags: [],
          unparsed_rate: 0.3, grader_error_rate: 0.05, overall: null, tasks: [{}, {}],
        };
        const clean = {kind: 'accuracy', status: 'official', gate: {mode: 'block'}, audit_flags: [],
                       unparsed_rate: 0.01, grader_error_rate: 0, overall: {}, tasks: [{}]};
        return [h.rowNotes(behavior), h.rowNotes(clean), h.rowNotes({audit_flags: ['accuracy_unparsed_high']})];
        """
    )
    behavior, clean, flagged = out
    joined = " | ".join(behavior)
    assert "Report only" in joined and "not promoted" in joined and "Pilot run" in joined
    assert "More than 20%" in joined and "5.0% of problems hit a grader error" in joined
    assert "different metrics" in joined
    assert clean == []
    assert any("accuracy_unparsed_high" in n for n in flagged)


def test_describe_load_error_is_actionable_for_a_missing_route() -> None:
    out = _node(
        """
        return ['API 404: x', 'API 200: response is not JSON', 'API 401: x', 'API 400: kind phải là một trong',
                'API 502: boom', 'TypeError: Failed to fetch', 'weird'].map(h.describeLoadError);
        """
    )
    assert "not deployed" in out[0] and "not deployed" in out[1]
    assert "sign in" in out[2] and out[3].startswith("The request was rejected: kind")
    assert "unreachable" in out[4] and "Network error" in out[5] and out[6] == "weird"


def test_judge_text() -> None:
    out = _node("return [h.judgeText({model: 'judge-a', prompt_sha256: 'ab12'}), h.judgeText(null), h.judgeText({})];")
    assert out == ["model=judge-a, prompt_sha256=ab12", None, None]


def test_generation_only_and_sandbox_graded_runs_say_so() -> None:
    out = _node(
        """
        const ungraded = {kind: 'behavior', status: 'candidate', gate: {mode: 'report'}, audit_flags: ['accuracy_ungraded'],
                          grading: {mode: 'deferred', state: 'ungraded'}, overall: null, tasks: [{}, {}]};
        const sandbox = {kind: 'behavior', status: 'candidate', gate: {mode: 'report'}, audit_flags: [], overall: null,
                         grading: {mode: 'sandbox', state: 'graded', grader: 'perfledger-sandbox', graded_from: 'sw/1/pk'}, tasks: [{}, {}]};
        const inline = {kind: 'accuracy', status: 'official', gate: {mode: 'block'}, audit_flags: [],
                        grading: {mode: 'inline', state: 'graded'}, overall: {}, tasks: [{}]};
        return {
          flags: [h.isUngraded(ungraded), h.isUngraded(sandbox), h.isUngraded(inline), h.isUngraded({}), h.isUngraded(null)],
          ungraded: h.rowNotes(ungraded), sandbox: h.rowNotes(sandbox), inline: h.rowNotes(inline),
        };
        """
    )
    assert out["flags"] == [True, False, False, False, False]
    joined = " | ".join(out["ungraded"])
    assert "not graded yet" in joined and "no scores" in joined
    assert "different metrics" not in joined  # an ungraded run has no metrics to disagree about
    sandbox = " | ".join(out["sandbox"])
    assert "no-network sandbox (perfledger-sandbox) from generation sw/1/pk" in sandbox
    assert "different metrics" in sandbox  # graded, several tasks, no combined figure
    assert out["inline"] == []


def test_ungraded_task_rows_never_print_undefined() -> None:
    out = _node("return [h.directionText(undefined), h.directionText(null), h.directionText('lower_is_better'), h.directionText('x')];")
    assert out == ["—", "—", "lower is better", "x"]


def test_many_task_benchmarks_collapse_after_a_dozen_rows() -> None:
    out = _node(
        """
        const tasks = Array.from({length: 57}, (_, i) => ({task: 't' + i}));
        return [h.visibleTasks(tasks, false).length, h.visibleTasks(tasks, true).length, h.visibleTasks(tasks.slice(0, 12), false).length,
                h.visibleTasks(null, false), h.TASK_ROWS_COLLAPSED];
        """
    )
    assert out == [12, 57, 12, [], 12]


def test_paired_formatters_and_reading() -> None:
    out = _node(
        """
        return {
          delta: [h.fmtDelta(83.33), h.fmtDelta(-16.67), h.fmtDelta(0), h.fmtDelta(-0.04), h.fmtDelta(null), h.fmtDelta(NaN)],
          p: [h.fmtP(0.00195), h.fmtP(0.0000004), h.fmtP(1), h.fmtP(0.5), h.fmtP(null)],
          reading: [h.readingText({better: 'candidate'}), h.readingText({better: 'baseline'}), h.readingText({better: null}), h.readingText(null)],
        };
        """
    )
    assert out == {
        "delta": ["+83.3 pp", "−16.7 pp", "0.0 pp", "0.0 pp", "—", "—"],
        "p": ["p = 0.002", "p < 0.001", "p = 1.000", "p = 0.500", "—"],
        "reading": ["Candidate better", "Baseline better", "No clear difference", "No clear difference"],
    }


def test_compare_query_reasons_and_run_labels() -> None:
    out = _node(
        """
        return {
          query: [h.buildCompareQuery('sw/2/pk', 'sw/1/pk'), h.buildCompareQuery('', 'b'), h.buildCompareQuery('a', null)],
          reasons: ['grading_deferred', 'benchmark_mismatch', 'problem_set_mismatch', 'weird', null].map(h.compareReasonText),
          labels: [h.runLabel({model: 'Qwen3.8-27B', sweep_id: '3fa2', point_id: '3fa2/2/pk', status: 'candidate'}),
                   h.runLabel({model_prefix: 'q', point_id: 'x', grading: {state: 'ungraded'}}), h.runLabel(null)],
        };
        """
    )
    assert out["query"] == ["?candidate=sw%2F2%2Fpk&baseline=sw%2F1%2Fpk", "", ""]
    r = out["reasons"]
    assert "generation only" in r[0] and "different benchmark" in r[1] and "same problems" in r[2]
    assert r[3] == "weird" and r[4] == ""
    assert out["labels"] == [
        "Qwen3.8-27B · sweep 3fa2 · attempt 2 · candidate",
        "q · sweep — · not graded",
        "— · sweep —",
    ]


# --------------------------------------------------------------------- static wiring
def _read(rel: str) -> str:
    return (_UI_ROOT / rel).read_text(encoding="utf-8")


def test_accuracy_is_wired_into_analyze_menu_route_palette_and_breadcrumb() -> None:
    nav = _read("components/top-nav.js")
    group = re.search(r"label: 'ANALYZE',\s*items: \[(.*?)\]", nav, re.S)
    assert group and "{ path: '/accuracy', label: 'Accuracy' }" in group.group(1)
    app = _read("app.js")
    assert "import { Accuracy } from './pages/accuracy.js';" in app
    assert re.search(r"currentRoute === '/accuracy'\)\s*\{\s*page = html`<\$\{Accuracy\} />`;", app)
    assert "{ label: 'Accuracy', path: '/accuracy' }" in _read("components/command-palette.js")
    assert "'/accuracy': 'Accuracy'" in _read("components/breadcrumb.js")


def test_accuracy_page_resolves_its_data_route_under_the_serving_prefix_and_never_injects_html() -> None:
    src = _PAGE.read_text(encoding="utf-8")
    assert "new URL('perfledger-api/accuracy', document.baseURI).pathname" in src
    # lib/base-path.js is absent in 0.13.0 (f3a76e5); a static import of it would break the whole SPA on that base.
    assert "base-path.js" not in re.sub(r"//.*", "", src)
    # A root-absolute URL would drop a reverse-proxy prefix (same rule as test_operator_base_path).
    assert not re.search(r"['\"`]/(api|dashboard|perfledger-api)/", src)
    assert "innerHTML" not in src and "dangerouslySetInnerHTML" not in src
    assert "const ac = new AbortController();" in src and "ac.abort()" in src  # fetch is cancelled on unmount
    assert "safeHttpUrl(row.dashboard_url)" in src and 'rel="noopener noreferrer"' in src
    assert "FALLBACK_LABEL" in src  # the "not an official InferenceX result" label is always on screen
    # The paired-comparison route lives under the same serving prefix; the page is its only caller and sends ids URL-encoded.
    assert "new URL('perfledger-api/accuracy/compare', document.baseURI).pathname" in src
    assert "buildCompareQuery(candidate, baseline)" in src and "export function ComparePanel" in src
    assert src.count("new AbortController()") == 2 and src.count("ac.abort()") == 2  # list and compare are both cancelled
