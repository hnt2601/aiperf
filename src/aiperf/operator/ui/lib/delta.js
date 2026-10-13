// SPDX-FileCopyrightText: Copyright (c) 2025-2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

/**
 * DELTA - sign-aware percentage-change helpers shared by the multi-job
 * Compare page (``pages/compare.js``, "Δ% vs baseline" column) and the
 * two-epoch Compare-epochs page (``pages/compare-epochs.js``, Delta column).
 *
 * Pure module: no DOM, no imports. ``palette`` is passed in by the caller so
 * the module runs under plain Node in ``tests/ui`` without the theme.
 *
 * Conventions (identical on both pages):
 *   - ``pct = (value - base) / |base| * 100``; ``null`` when either side is
 *     missing, non-finite, or ``base === 0`` (division by zero is not a delta).
 *   - |pct| below ``NEUTRAL_BAND_PCT`` is "neutral" (gray) - run-to-run noise,
 *     not a claim.
 *   - ``better`` is ``'higher'`` or ``'lower'``; green when the sign matches
 *     that direction, red otherwise.
 */

/** Absolute percentage below which a change is shown without colour. */
export const NEUTRAL_BAND_PCT = 1;

/** Percentage change of ``value`` relative to ``base``; ``null`` when undefined. */
export function deltaPct(base, value) {
  if (base == null || value == null) return null;
  const b = Number(base);
  const v = Number(value);
  if (!Number.isFinite(b) || !Number.isFinite(v) || b === 0) return null;
  return ((v - b) / Math.abs(b)) * 100;
}

/** Classify a percentage delta into ``'better'`` | ``'worse'`` | ``'neutral'``.
 *  ``null``/non-finite input yields ``'neutral'`` so the gray colour lands. */
export function deltaClass(pct, better) {
  if (pct == null || !Number.isFinite(pct)) return 'neutral';
  if (Math.abs(pct) < NEUTRAL_BAND_PCT) return 'neutral';
  const improved = better === 'higher' ? pct > 0 : pct < 0;
  return improved ? 'better' : 'worse';
}

/** Colour for a delta class from the theme palette (``green``/``red``/``overlay0``). */
export function deltaColor(klass, palette) {
  if (klass === 'better') return palette.green;
  if (klass === 'worse') return palette.red;
  return palette.overlay0;
}

/** ``'+12.3%'`` / ``'-4.1%'``; ``'—'`` when there is no delta. ``fmt(n, digits)``
 *  defaults to ``toFixed`` so the module stays import-free; pages pass
 *  ``fmtNumber`` for locale-aware output. */
export function fmtDeltaPct(pct, fmt = (n, digits) => n.toFixed(digits)) {
  if (pct == null || !Number.isFinite(pct)) return '—';
  const sign = pct > 0 ? '+' : '';
  return `${sign}${fmt(pct, 1)}%`;
}

/** Direction that scores green for a compare-table metric. */
export function betterDirection(metric, lowerIsBetter) {
  return lowerIsBetter.has(metric) ? 'lower' : 'higher';
}

/** The oldest run among ``keys`` by numeric run ``epoch`` in ``meta[key]``
 *  (the operator's run epoch is a microsecond timestamp). Keys without a
 *  usable epoch sort last; ties keep the caller's order, so with no epochs
 *  at all the first selected key is the baseline. ``null`` for no keys. */
export function oldestKey(keys, meta) {
  if (!keys || keys.length === 0) return null;
  const epochOf = (key) => {
    const raw = meta?.[key]?.epoch;
    const n = Number(raw);
    return Number.isFinite(n) && n > 0 ? n : Number.POSITIVE_INFINITY;
  };
  let best = keys[0];
  let bestEpoch = epochOf(best);
  for (const key of keys.slice(1)) {
    const e = epochOf(key);
    if (e < bestEpoch) {
      best = key;
      bestEpoch = e;
    }
  }
  return best;
}
