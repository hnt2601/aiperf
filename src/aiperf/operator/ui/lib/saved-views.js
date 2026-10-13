// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// Saved list views: a name plus the query-string state of the Jobs or Sweeps
// page (filters, grouping, sort). Persisted per page under
// ``aiperf.savedViews.<page>`` as one ``name=k=v&k2=v2`` line per view, which
// keeps the module dependency-free and the stored payload human-readable.
//
// Pure helpers take and return plain data so they run in bare node; only
// ``loadViews`` / ``saveViews`` touch Web Storage, and both swallow storage
// failures (private mode, quota) so the page keeps working without them.

export const SAVED_VIEWS_PREFIX = 'aiperf.savedViews.';

export function savedViewsStorageKey(page) {
  return SAVED_VIEWS_PREFIX + String(page ?? '');
}

// ``{a: '1', b: ''} -> 'a=1'`` with keys sorted so equal views serialize equal.
export function encodeQuery(query) {
  const parts = [];
  for (const k of Object.keys(query ?? {}).sort()) {
    const v = query[k];
    if (v === undefined || v === null || v === '') continue;
    parts.push(encodeURIComponent(k) + '=' + encodeURIComponent(String(v)));
  }
  return parts.join('&');
}

function safeDecode(s) {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

export function decodeQuery(encoded) {
  const out = {};
  for (const pair of String(encoded ?? '').split('&')) {
    if (!pair) continue;
    const eq = pair.indexOf('=');
    const k = safeDecode(eq === -1 ? pair : pair.slice(0, eq));
    if (!k) continue;
    out[k] = eq === -1 ? '' : safeDecode(pair.slice(eq + 1));
  }
  return out;
}

export function normalizeViewName(name) {
  return String(name ?? '').trim().replace(/\s+/g, ' ');
}

export function serializeViews(views) {
  return (views ?? [])
    .filter((v) => v && normalizeViewName(v.name))
    .map((v) => encodeURIComponent(normalizeViewName(v.name)) + '=' + encodeQuery(v.query))
    .join('\n');
}

// Inverse of ``serializeViews``. Malformed lines are skipped and a repeated
// name keeps its last definition, so a hand-edited payload degrades gracefully.
export function parseViews(raw) {
  const byName = new Map();
  for (const line of String(raw ?? '').split('\n')) {
    const trimmed = line.trim();
    if (!trimmed) continue;
    const eq = trimmed.indexOf('=');
    const name = normalizeViewName(safeDecode(eq === -1 ? trimmed : trimmed.slice(0, eq)));
    if (!name) continue;
    byName.set(name, { name, query: decodeQuery(eq === -1 ? '' : trimmed.slice(eq + 1)) });
  }
  return [...byName.values()];
}

// Add or replace a view. Returns the same array when the name is blank so a
// caller can detect a no-op by identity.
export function upsertView(views, name, query) {
  const clean = normalizeViewName(name);
  if (!clean) return views;
  const entry = { name: clean, query: decodeQuery(encodeQuery(query)) };
  const list = views ?? [];
  const idx = list.findIndex((v) => v.name === clean);
  if (idx === -1) return [...list, entry];
  return list.map((v, i) => (i === idx ? entry : v));
}

export function removeView(views, name) {
  const clean = normalizeViewName(name);
  return (views ?? []).filter((v) => v.name !== clean);
}

// ``'#/jobs?group=run&ns=x'`` for ``navigate``/``href``.
export function viewHash(path, query) {
  const encoded = encodeQuery(query);
  const base = String(path ?? '/').startsWith('/') ? path : '/' + path;
  return '#' + base + (encoded ? '?' + encoded : '');
}

function storageOrNull(storage) {
  if (storage) return storage;
  try {
    return typeof localStorage === 'undefined' ? null : localStorage;
  } catch {
    return null;
  }
}

export function loadViews(page, storage) {
  const store = storageOrNull(storage);
  if (!store) return [];
  try {
    return parseViews(store.getItem(savedViewsStorageKey(page)) ?? '');
  } catch {
    return [];
  }
}

export function saveViews(page, views, storage) {
  const store = storageOrNull(storage);
  if (!store) return false;
  try {
    const payload = serializeViews(views);
    if (payload) store.setItem(savedViewsStorageKey(page), payload);
    else store.removeItem(savedViewsStorageKey(page));
    return true;
  } catch {
    return false;
  }
}
