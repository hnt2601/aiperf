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
