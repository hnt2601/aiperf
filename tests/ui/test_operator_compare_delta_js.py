# SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Node-based tests for the operator UI's shared delta helpers
(``src/aiperf/operator/ui/lib/delta.js``) used by the multi-job Compare page's
"Δ% vs baseline" column and by the Compare-epochs Delta column.

Same cheap layer as ``tests/ui/test_dashboard_js.py``: ``node --check`` on the
touched ES modules plus a Node-executed behavioural script against the pure
``delta.js`` module. No DOM, no browser; skips when ``node`` is not on PATH.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_UI = _REPO_ROOT / "src" / "aiperf" / "operator" / "ui"
_DELTA_JS = _UI / "lib" / "delta.js"
_MODULES = [
    _DELTA_JS,
    _UI / "pages" / "compare.js",
    _UI / "pages" / "compare-epochs.js",
]
_NODE_TIMEOUT_SECONDS = 60
_NODE_REASON = "node not on PATH"


def _node_binary() -> str | None:
    return shutil.which("node")


_SCRIPT = """
import { deltaPct, deltaClass, deltaColor, fmtDeltaPct, betterDirection, oldestKey, NEUTRAL_BAND_PCT } from './lib/delta.js';
const out = {};
out.band = NEUTRAL_BAND_PCT;
out.pct = deltaPct(4157.69, 4072.17);
out.pctNull = [deltaPct(0, 5), deltaPct(null, 5), deltaPct(5, undefined), deltaPct('x', 1)];
out.pctAbsBase = deltaPct(-10, -5);
out.cls = [deltaClass(-2.06, 'higher'), deltaClass(-2.06, 'lower'), deltaClass(0.9, 'higher'), deltaClass(null, 'higher'), deltaClass(NaN, 'lower')];
const pal = { green: 'G', red: 'R', overlay0: 'O' };
out.color = [deltaColor('better', pal), deltaColor('worse', pal), deltaColor('neutral', pal)];
out.fmt = [fmtDeltaPct(-2.0569), fmtDeltaPct(12.345), fmtDeltaPct(null), fmtDeltaPct(3.14159, (n, d) => n.toFixed(d) + '!')];
const lower = new Set(['inter_token_latency']);
out.dir = [betterDirection('inter_token_latency', lower), betterDirection('output_token_throughput', lower)];
const meta = { 'ns/new': { epoch: '1792000000000000' }, 'ns/old': { epoch: '1791790834885188' }, 'ns/none': {} };
out.oldest = [oldestKey(['ns/new', 'ns/old', 'ns/none'], meta), oldestKey(['ns/none', 'ns/new'], meta), oldestKey(['a', 'b'], {}), oldestKey([], meta), oldestKey(['a'], null)];
console.log(JSON.stringify(out));
"""


def _sandbox(tmp_path: Path) -> Path:
    sandbox = tmp_path / "operator-ui"
    (sandbox / "lib").mkdir(parents=True)
    (sandbox / "pages").mkdir()
    (sandbox / "package.json").write_text('{"type": "module"}\n')
    shutil.copy(_DELTA_JS, sandbox / "lib" / "delta.js")
    for mod in _MODULES[1:]:
        shutil.copy(mod, sandbox / "pages" / mod.name)
    return sandbox


@pytest.mark.skipif(_node_binary() is None, reason=_NODE_REASON)
class TestOperatorCompareDeltaJs:
    def test_modules_parse(self, tmp_path: Path) -> None:
        sandbox = _sandbox(tmp_path)
        for rel in ("lib/delta.js", "pages/compare.js", "pages/compare-epochs.js"):
            proc = subprocess.run(
                [_node_binary(), "--check", rel],
                capture_output=True,
                timeout=_NODE_TIMEOUT_SECONDS,
                text=True,
                cwd=sandbox,
            )
            assert proc.returncode == 0, f"{rel} failed `node --check`:\n{proc.stderr}"

    def test_delta_helpers_behaviour(self, tmp_path: Path) -> None:
        sandbox = _sandbox(tmp_path)
        script = sandbox / "delta.test.mjs"
        script.write_text(_SCRIPT)
        proc = subprocess.run(
            [_node_binary(), str(script)],
            capture_output=True,
            timeout=_NODE_TIMEOUT_SECONDS,
            text=True,
            cwd=sandbox,
        )
        assert proc.returncode == 0, (
            f"node delta test failed\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
        out = json.loads(proc.stdout)
        assert out["band"] == 1
        assert out["pct"] == pytest.approx(-2.0569, abs=1e-3)
        assert out["pctNull"] == [None, None, None, None]
        assert out["pctAbsBase"] == 50
        assert out["cls"] == ["worse", "better", "neutral", "neutral", "neutral"]
        assert out["color"] == ["G", "R", "O"]
        assert out["fmt"] == ["-2.1%", "+12.3%", "\u2014", "+3.1!%"]
        assert out["dir"] == ["lower", "higher"]
        assert out["oldest"] == ["ns/old", "ns/new", "a", None, "a"]

    def test_compare_pages_import_shared_helpers(self) -> None:
        """Both pages must take sign/colour rules from the one module."""
        compare = (_UI / "pages" / "compare.js").read_text()
        epochs = (_UI / "pages" / "compare-epochs.js").read_text()
        assert "from '../lib/delta.js'" in compare
        assert "from '../lib/delta.js'" in epochs
        assert (
            "function deltaClass(" not in epochs
            and "function deltaColor(" not in epochs
        )
        for testid in (
            "compare-baseline-select",
            "compare-delta-toggle",
            "compare-delta-cell",
            "compare-baseline-mark",
        ):
            assert f'data-testid="{testid}"' in compare, testid
