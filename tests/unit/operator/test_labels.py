# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ``aiperf.operator.labels`` and the UI label allow-list setting."""

from __future__ import annotations

import importlib
from pathlib import Path

import orjson
import pytest

from aiperf.operator.labels import (
    DEFAULT_UI_LABEL_PREFIXES,
    JOB_LABELS_FILENAME,
    filter_labels,
    parse_label_prefixes,
    read_job_labels,
)

_LABELS = {
    "aiperf.nvidia.com/run": "nightly-1",
    "aiperf.nvidia.com/scenario": "agentx",
    "perfledger.io/lifecycle": "candidate",
    "app.kubernetes.io/name": "aiperf",
    "team": "perf",
}


class TestFilterLabels:
    def test_default_prefix_keeps_only_aiperf_domain(self) -> None:
        assert filter_labels(_LABELS, DEFAULT_UI_LABEL_PREFIXES) == {
            "aiperf.nvidia.com/run": "nightly-1",
            "aiperf.nvidia.com/scenario": "agentx",
        }

    def test_multiple_prefixes_union(self) -> None:
        out = filter_labels(_LABELS, ("aiperf.nvidia.com/", "perfledger.io/"))
        assert set(out) == {
            "aiperf.nvidia.com/run",
            "aiperf.nvidia.com/scenario",
            "perfledger.io/lifecycle",
        }

    def test_prefix_is_a_prefix_not_a_substring(self) -> None:
        assert (
            filter_labels({"x.aiperf.nvidia.com/run": "1"}, ("aiperf.nvidia.com/",))
            == {}
        )
        assert filter_labels({"aiperf.nvidia.com": "1"}, ("aiperf.nvidia.com/",)) == {}

    @pytest.mark.parametrize("labels", [None, {}])
    def test_none_or_empty_labels(self, labels: dict[str, str] | None) -> None:
        assert filter_labels(labels, DEFAULT_UI_LABEL_PREFIXES) == {}

    def test_no_prefixes_keeps_nothing(self) -> None:
        assert filter_labels(_LABELS, ()) == {}

    def test_drops_non_string_entries_without_raising(self) -> None:
        dirty = {"aiperf.nvidia.com/ok": "1", "aiperf.nvidia.com/bad": 3, 7: "x"}
        assert filter_labels(dirty, DEFAULT_UI_LABEL_PREFIXES) == {  # type: ignore[arg-type]
            "aiperf.nvidia.com/ok": "1"
        }

    def test_returns_new_dict(self) -> None:
        src = {"aiperf.nvidia.com/run": "1"}
        out = filter_labels(src, DEFAULT_UI_LABEL_PREFIXES)
        assert out == src
        assert out is not src


class TestParseLabelPrefixes:
    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("aiperf.nvidia.com/", ("aiperf.nvidia.com/",)),
            ("a/, b/ ,c/", ("a/", "b/", "c/")),
            ("", ()),
            (" , ,", ()),
        ],
    )
    def test_split_and_strip(self, raw: str, expected: tuple[str, ...]) -> None:
        assert parse_label_prefixes(raw) == expected


class TestReadJobLabels:
    def test_missing_file_is_empty(self, tmp_path: Path) -> None:
        assert read_job_labels(tmp_path) == {}

    def test_reads_object(self, tmp_path: Path) -> None:
        (tmp_path / JOB_LABELS_FILENAME).write_bytes(orjson.dumps(_LABELS))
        assert read_job_labels(tmp_path) == _LABELS

    def test_corrupt_file_logs_and_is_empty(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / JOB_LABELS_FILENAME).write_bytes(b"{not json")
        with caplog.at_level("WARNING", logger="aiperf.operator.labels"):
            assert read_job_labels(tmp_path) == {}
        assert "unreadable" in caplog.text

    def test_non_object_document_is_empty(self, tmp_path: Path) -> None:
        (tmp_path / JOB_LABELS_FILENAME).write_bytes(b"[1, 2]")
        assert read_job_labels(tmp_path) == {}

    def test_non_string_values_dropped(self, tmp_path: Path) -> None:
        (tmp_path / JOB_LABELS_FILENAME).write_bytes(
            orjson.dumps({"aiperf.nvidia.com/run": "r", "aiperf.nvidia.com/n": 1})
        )
        assert read_job_labels(tmp_path) == {"aiperf.nvidia.com/run": "r"}


class TestUISettings:
    """``AIPERF_OPERATOR_UI_LABEL_PREFIXES`` on ``OperatorEnvironment.UI``."""

    @pytest.fixture
    def env_module(self, monkeypatch: pytest.MonkeyPatch):
        from aiperf.operator import environment as mod

        yield mod
        monkeypatch.delenv("AIPERF_OPERATOR_UI_LABEL_PREFIXES", raising=False)
        importlib.reload(mod)

    def test_default_matches_helper_constant(
        self, monkeypatch: pytest.MonkeyPatch, env_module
    ) -> None:
        monkeypatch.delenv("AIPERF_OPERATOR_UI_LABEL_PREFIXES", raising=False)
        importlib.reload(env_module)
        assert env_module.OperatorEnvironment.UI.LABEL_PREFIXES == "aiperf.nvidia.com/"
        assert (
            env_module.OperatorEnvironment.UI.label_prefixes
            == DEFAULT_UI_LABEL_PREFIXES
        )

    def test_custom_prefixes_from_env(
        self, monkeypatch: pytest.MonkeyPatch, env_module
    ) -> None:
        monkeypatch.setenv(
            "AIPERF_OPERATOR_UI_LABEL_PREFIXES", "perfledger.io/, aiperf.nvidia.com/"
        )
        importlib.reload(env_module)
        ui = env_module.OperatorEnvironment.UI
        assert ui.label_prefixes == ("perfledger.io/", "aiperf.nvidia.com/")
        assert filter_labels(_LABELS, ui.label_prefixes) == {
            "aiperf.nvidia.com/run": "nightly-1",
            "aiperf.nvidia.com/scenario": "agentx",
            "perfledger.io/lifecycle": "candidate",
        }

    def test_empty_env_serves_no_labels(
        self, monkeypatch: pytest.MonkeyPatch, env_module
    ) -> None:
        monkeypatch.setenv("AIPERF_OPERATOR_UI_LABEL_PREFIXES", "")
        importlib.reload(env_module)
        ui = env_module.OperatorEnvironment.UI
        assert ui.label_prefixes == ()
        assert filter_labels(_LABELS, ui.label_prefixes) == {}
