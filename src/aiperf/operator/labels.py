# SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Kubernetes label projection for the operator dashboard API.

The dashboard groups jobs and sweeps by the labels their CRs carry
(run, scenario, lifecycle, ...). Only labels under an allow-listed key
prefix are served, so unrelated cluster labels (``app.kubernetes.io/*``,
tenant tags, ...) never leak into the UI payload. The allow-list is
``AIPERF_OPERATOR_UI_LABEL_PREFIXES``; see
:class:`aiperf.operator.environment._OperatorUISettings`.

Live CRs expose ``metadata.labels`` directly. Archived (PVC-only) runs
have no CR left, so the create handler persists the CR labels next to
``job_spec.json`` as ``job_labels.json`` and :func:`read_job_labels`
reads them back. This module is import-light on purpose: it is pulled in
by ``aiperf.operator.environment`` and must not import it back.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from pathlib import Path

import orjson

logger = logging.getLogger("aiperf.operator.labels")

DEFAULT_UI_LABEL_PREFIXES: tuple[str, ...] = ("aiperf.nvidia.com/",)
"""Label key prefixes served by default (the operator's own label domain)."""

JOB_LABELS_FILENAME = "job_labels.json"
"""Per-run sidecar holding the AIPerfJob CR's ``metadata.labels``."""


def parse_label_prefixes(raw: str) -> tuple[str, ...]:
    """Split a comma-separated prefix list, dropping blanks and whitespace."""
    return tuple(p for p in (part.strip() for part in raw.split(",")) if p)


def filter_labels(
    labels: Mapping[str, str] | None,
    prefixes: Sequence[str],
) -> dict[str, str]:
    """Keep only labels whose key starts with one of ``prefixes``.

    ``None`` or an empty mapping yields ``{}``; an empty ``prefixes`` keeps
    nothing. Non-string keys or values are dropped rather than coerced so an
    odd on-disk document cannot fail the whole listing.
    """
    if not labels or not prefixes:
        return {}
    return {
        key: value
        for key, value in labels.items()
        if isinstance(key, str)
        and isinstance(value, str)
        and key.startswith(tuple(prefixes))
    }


def read_job_labels(run_dir: Path) -> dict[str, str]:
    """Return the labels persisted at ``<run_dir>/job_labels.json``.

    Missing file means the run predates label persistence (or had no
    labels) and yields ``{}``. An unreadable or malformed file is logged and
    also yields ``{}``: labels are a grouping aid and must never hide a run.
    """
    path = run_dir / JOB_LABELS_FILENAME
    try:
        doc = orjson.loads(path.read_bytes())
    except FileNotFoundError:
        return {}
    except (OSError, orjson.JSONDecodeError) as e:
        logger.warning(f"{JOB_LABELS_FILENAME} unreadable at {path}: {e}")
        return {}
    if not isinstance(doc, dict):
        logger.warning(f"{JOB_LABELS_FILENAME} at {path} is not an object; ignoring")
        return {}
    return {k: v for k, v in doc.items() if isinstance(k, str) and isinstance(v, str)}
