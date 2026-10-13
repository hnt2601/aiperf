# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""``labels`` on the unified job view: live CRs, archived sidecar, both-merge.

Live labels come from ``AIPerfJobCR.metadata.labels`` via ``to_info()``;
archived ones from ``<run_dir>/job_labels.json`` written by the create
handler. Both are narrowed to ``AIPERF_OPERATOR_UI_LABEL_PREFIXES`` before
the API serves them.
"""

from __future__ import annotations

from pathlib import Path

import orjson
import pytest

from aiperf.common.results_markers import ready_marker_path
from aiperf.kubernetes.models import AIPerfJobCR, AIPerfJobInfo
from aiperf.operator import job_union as ju
from aiperf.operator.environment import OperatorEnvironment
from aiperf.operator.labels import JOB_LABELS_FILENAME
from aiperf.operator.results_layout import write_latest

_EPOCH = "1714064523"
_RAW = {
    "aiperf.nvidia.com/run": "nightly-7",
    "aiperf.nvidia.com/scenario": "agentx",
    "perfledger.io/lifecycle": "candidate",
    "app.kubernetes.io/managed-by": "argocd",
}
_ALLOWED = {
    "aiperf.nvidia.com/run": "nightly-7",
    "aiperf.nvidia.com/scenario": "agentx",
}


@pytest.fixture(autouse=True)
def _default_prefixes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(OperatorEnvironment.UI, "LABEL_PREFIXES", "aiperf.nvidia.com/")
    ju._pvc_scan_cache.entries.clear()


def _live(name: str, labels: dict[str, str] | None = None) -> AIPerfJobInfo:
    return AIPerfJobInfo(
        name=name,
        namespace="ns",
        phase="Running",
        job_id=name,
        created="2026-04-22T10:00:00Z",
        labels=dict(labels or {}),
    )


def _write_run(
    base: Path,
    name: str,
    *,
    labels: bytes | None,
    summary: bool = True,
) -> Path:
    run = base / "ns" / name / _EPOCH
    run.mkdir(parents=True)
    if summary:
        (run / "profile_export_aiperf.json").write_bytes(
            orjson.dumps(
                {
                    "status": "Succeeded",
                    "start_time": "2026-04-22T10:00:00Z",
                    "end_time": "2026-04-22T10:45:00Z",
                    "request_throughput": {"avg": 1.0, "unit": "requests/sec"},
                }
            )
        )
    else:
        ready_marker_path(run).parent.mkdir(parents=True, exist_ok=True)
        ready_marker_path(run).write_bytes(b"")
    if labels is not None:
        (run / JOB_LABELS_FILENAME).write_bytes(labels)
    write_latest(base, "ns", name, _EPOCH)
    return run


def test_to_info_copies_cr_labels_verbatim() -> None:
    cr = AIPerfJobCR.model_validate(
        {"metadata": {"name": "j", "namespace": "ns", "labels": _RAW}}
    )
    assert cr.to_info().labels == _RAW


def test_to_info_without_labels_is_empty_dict() -> None:
    cr = AIPerfJobCR.model_validate({"metadata": {"name": "j", "namespace": "ns"}})
    assert cr.to_info().labels == {}


def test_labels_serialize_under_plain_key() -> None:
    dumped = _live("j", _ALLOWED).model_dump(by_alias=True)
    assert dumped["labels"] == _ALLOWED


@pytest.mark.asyncio
async def test_list_all_jobs_filters_live_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_list(api, *, all_namespaces=True, namespace=None, **_):
        return [_live("live-1", _RAW)]

    monkeypatch.setattr(ju, "list_aiperf_jobs", fake_list)
    jobs = await ju.list_all_jobs(object(), tmp_path)
    assert [j.name for j in jobs] == ["live-1"]
    assert jobs[0].labels == _ALLOWED


@pytest.mark.asyncio
async def test_list_all_jobs_custom_prefixes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(OperatorEnvironment.UI, "LABEL_PREFIXES", "perfledger.io/")

    async def fake_list(api, *, all_namespaces=True, namespace=None, **_):
        return [_live("live-1", _RAW)]

    monkeypatch.setattr(ju, "list_aiperf_jobs", fake_list)
    jobs = await ju.list_all_jobs(object(), tmp_path)
    assert jobs[0].labels == {"perfledger.io/lifecycle": "candidate"}


@pytest.mark.asyncio
async def test_list_all_jobs_archived_labels_from_sidecar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_list(api, *, all_namespaces=True, namespace=None, **_):
        return []

    monkeypatch.setattr(ju, "list_aiperf_jobs", fake_list)
    _write_run(tmp_path, "arch-1", labels=orjson.dumps(_RAW))
    _write_run(tmp_path, "arch-none", labels=None)
    _write_run(tmp_path, "arch-stub", labels=orjson.dumps(_RAW), summary=False)

    jobs = {j.name: j for j in await ju.list_all_jobs(None, tmp_path)}
    assert jobs["arch-1"].source == "archived"
    assert jobs["arch-1"].labels == _ALLOWED
    assert jobs["arch-none"].labels == {}
    # CSV-only / summary-less runs go through ``archived_stub`` and still
    # carry labels so a failed run can be grouped with its siblings.
    assert jobs["arch-stub"].phase == "Unknown"
    assert jobs["arch-stub"].labels == _ALLOWED


@pytest.mark.asyncio
async def test_list_all_jobs_unreadable_sidecar_never_hides_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    async def fake_list(api, *, all_namespaces=True, namespace=None, **_):
        return []

    monkeypatch.setattr(ju, "list_aiperf_jobs", fake_list)
    _write_run(tmp_path, "arch-bad", labels=b"\xff{broken")

    with caplog.at_level("WARNING", logger="aiperf.operator.labels"):
        jobs = await ju.list_all_jobs(None, tmp_path)
    assert [j.name for j in jobs] == ["arch-bad"]
    assert jobs[0].labels == {}
    assert JOB_LABELS_FILENAME in caplog.text


@pytest.mark.asyncio
async def test_both_sources_prefer_live_then_backfill_from_archive(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_list(api, *, all_namespaces=True, namespace=None, **_):
        return [
            _live("has-live-labels", {"aiperf.nvidia.com/run": "from-cr"}),
            _live("cr-without-labels"),
        ]

    monkeypatch.setattr(ju, "list_aiperf_jobs", fake_list)
    _write_run(
        tmp_path,
        "has-live-labels",
        labels=orjson.dumps({"aiperf.nvidia.com/run": "from-disk"}),
    )
    _write_run(tmp_path, "cr-without-labels", labels=orjson.dumps(_RAW))

    jobs = {j.name: j for j in await ju.list_all_jobs(object(), tmp_path)}
    assert jobs["has-live-labels"].source == "both"
    assert jobs["has-live-labels"].labels == {"aiperf.nvidia.com/run": "from-cr"}
    assert jobs["cr-without-labels"].source == "both"
    assert jobs["cr-without-labels"].labels == _ALLOWED


@pytest.mark.asyncio
async def test_find_any_job_live_and_archived_labels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def fake_find(api, name, namespace):
        return _live(name, _RAW) if name == "live-1" else None

    monkeypatch.setattr(ju, "find_aiperf_job", fake_find)
    _write_run(tmp_path, "arch-1", labels=orjson.dumps(_RAW))

    live = await ju.find_any_job(object(), tmp_path, "ns", "live-1")
    assert live is not None and live.labels == _ALLOWED

    archived = await ju.find_any_job(object(), tmp_path, "ns", "arch-1")
    assert archived is not None
    assert archived.source == "archived"
    assert archived.labels == _ALLOWED

    pinned = await ju.find_any_job(object(), tmp_path, "ns", "arch-1", epoch=_EPOCH)
    assert pinned is not None and pinned.labels == _ALLOWED
