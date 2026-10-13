# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Tests for the saved-views helpers (``lib/saved-views.js``) and the menu
chrome that uses them (``components/saved-views-menu.js``)."""

from __future__ import annotations

import json
from pathlib import Path

from tests.ui.node_utils import UI_DIR, requires_node, run_node

SAVED_VIEWS_PATH = UI_DIR / "lib" / "saved-views.js"
SAVED_VIEWS_MENU_PATH = UI_DIR / "components" / "saved-views-menu.js"
PAGES = (UI_DIR / "pages" / "jobs.js", UI_DIR / "pages" / "sweeps.js")


def _run(expression: str) -> object:
    script = f"""
        import * as sv from {SAVED_VIEWS_PATH.as_uri()!r};
        console.log(JSON.stringify({expression}));
    """
    return json.loads(run_node(script))


@requires_node
def test_query_encoding_is_stable_and_drops_empty_values() -> None:
    assert _run("sv.encodeQuery({ ns: 'perfledger', group: 'run', q: '', sort: null, x: undefined })") == (
        "group=run&ns=perfledger"
    )
    assert _run("sv.encodeQuery({ b: '1', a: 'x y/z', 'c d': 'é' })") == "a=x%20y%2Fz&b=1&c%20d=%C3%A9"
    assert _run("sv.decodeQuery('a=x%20y%2Fz&b=1&c%20d=%C3%A9&flag&=skip&bad=%E0%A4%A')") == {
        "a": "x y/z",
        "b": "1",
        "c d": "é",
        "flag": "",
        "bad": "%E0%A4%A",
    }
    assert _run("sv.decodeQuery('')") == {}
    assert _run("sv.viewHash('/jobs', { group: 'run', ns: 'a b' })") == "#/jobs?group=run&ns=a%20b"
    assert _run("sv.viewHash('sweeps', {})") == "#/sweeps"


@requires_node
def test_views_serialize_one_per_line_and_parse_back_skipping_junk() -> None:
    views = [
        {"name": "  gateway  pilots ", "query": {"lifecycle": "gateway", "group": "run"}},
        {"name": "", "query": {"ns": "ignored"}},
        {"name": "flat", "query": {}},
    ]
    serialized = _run(f"sv.serializeViews({json.dumps(views)})")
    assert serialized == "gateway%20pilots=group=run&lifecycle=gateway\nflat="

    parsed = _run(
        "sv.parseViews('gateway%20pilots=group=run&lifecycle=gateway\\n\\n  \\n=nameless\\nflat=\\nflat=ns=later\\njust-a-name')"
    )
    assert parsed == [
        {"name": "gateway pilots", "query": {"group": "run", "lifecycle": "gateway"}},
        {"name": "flat", "query": {"ns": "later"}},
        {"name": "just-a-name", "query": {}},
    ]
    assert _run("sv.parseViews(null)") == []


@requires_node
def test_upsert_and_remove_are_pure_and_name_aware() -> None:
    out = _run(
        """
        (() => {
          const base = [{ name: 'a', query: { ns: 'x' } }];
          const added = sv.upsertView(base, ' b ', { ns: 'y', q: '', group: 'model' });
          const replaced = sv.upsertView(added, 'a', { phase: 'running' });
          const blank = sv.upsertView(base, '   ', { ns: 'z' });
          const removed = sv.removeView(replaced, 'a ');
          return {
            base, added, replaced, blankIsSame: blank === base, removed,
            missing: sv.removeView(base, 'nope'),
          };
        })()
        """
    )

    assert out["base"] == [{"name": "a", "query": {"ns": "x"}}]
    assert out["added"] == [
        {"name": "a", "query": {"ns": "x"}},
        {"name": "b", "query": {"group": "model", "ns": "y"}},
    ]
    assert out["replaced"] == [
        {"name": "a", "query": {"phase": "running"}},
        {"name": "b", "query": {"group": "model", "ns": "y"}},
    ]
    assert out["blankIsSame"] is True
    assert out["removed"] == [{"name": "b", "query": {"group": "model", "ns": "y"}}]
    assert out["missing"] == out["base"]


@requires_node
def test_storage_round_trip_is_per_page_and_tolerates_broken_storage() -> None:
    out = _run(
        """
        (() => {
          const store = new Map();
          const storage = {
            getItem: (k) => (store.has(k) ? store.get(k) : null),
            setItem: (k, v) => store.set(k, v),
            removeItem: (k) => store.delete(k),
          };
          const views = [{ name: 'v', query: { group: 'run' } }];
          const out = {};
          out.saved = sv.saveViews('jobs', views, storage);
          out.key = [...store.keys()];
          out.jobs = sv.loadViews('jobs', storage);
          out.sweeps = sv.loadViews('sweeps', storage);
          out.cleared = sv.saveViews('jobs', [], storage);
          out.afterClear = [...store.keys()];
          const broken = { getItem() { throw new Error('private'); }, setItem() { throw new Error('quota'); }, removeItem() {} };
          out.brokenLoad = sv.loadViews('jobs', broken);
          out.brokenSave = sv.saveViews('jobs', views, broken);
          out.noStorage = [sv.loadViews('jobs'), sv.saveViews('jobs', views)];
          return out;
        })()
        """
    )

    assert out["saved"] is True
    assert out["key"] == ["aiperf.savedViews.jobs"]
    assert out["jobs"] == [{"name": "v", "query": {"group": "run"}}]
    assert out["sweeps"] == []
    assert out["cleared"] is True
    assert out["afterClear"] == []
    assert out["brokenLoad"] == []
    assert out["brokenSave"] is False
    # Bare node has no localStorage: load is empty, save reports it could not.
    assert out["noStorage"] == [[], False]


def test_saved_views_menu_is_wired_into_both_list_pages_with_cleanup() -> None:
    menu = SAVED_VIEWS_MENU_PATH.read_text(encoding="utf-8")

    assert "import { loadViews, saveViews, upsertView, removeView, viewHash, normalizeViewName } from '../lib/saved-views.js';" in menu
    assert "navigate(viewHash(route.value, view.query).slice(1))" in menu
    assert "upsertView(views, draft, query.value)" in menu
    assert "document.addEventListener('mousedown', onDocMouseDown)" in menu
    assert "document.removeEventListener('mousedown', onDocMouseDown)" in menu
    assert "document.removeEventListener('keydown', onKey)" in menu
    assert 'aria-haspopup="true"' in menu and "aria-expanded=${open}" in menu
    assert "disabled=${!canSave}" in menu
    assert "JSON.stringify" not in menu
    assert "JSON.stringify" not in SAVED_VIEWS_PATH.read_text(encoding="utf-8")

    for page in PAGES:
        src = page.read_text(encoding="utf-8")
        assert "import { SavedViewsMenu } from '../components/saved-views-menu.js';" in src
        assert f'<${{SavedViewsMenu}} page="{page.stem}" />' in src
