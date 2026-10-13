// SPDX-FileCopyrightText: Copyright (c) 2026 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
// SPDX-License-Identifier: Apache-2.0

// "Views" dropdown for the Jobs and Sweeps lists: save the current query
// string under a name, apply a saved one, delete it. State lives in
// lib/saved-views.js; this file is only the menu chrome.

import { html } from 'htm/preact';
import { useEffect, useRef, useState } from 'preact/hooks';
import { loadViews, saveViews, upsertView, removeView, viewHash, normalizeViewName } from '../lib/saved-views.js';
import { navigate, query, route } from '../lib/router.js';

export function SavedViewsMenu({ page }) {
  const [open, setOpen] = useState(false);
  const [views, setViews] = useState(() => loadViews(page));
  const [draft, setDraft] = useState('');
  const rootRef = useRef(null);

  // Click-outside / Escape close the menu; listeners only exist while open.
  useEffect(() => {
    if (!open) return undefined;
    function onDocMouseDown(e) {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    }
    function onKey(e) {
      if (e.key === 'Escape') setOpen(false);
    }
    document.addEventListener('mousedown', onDocMouseDown);
    document.addEventListener('keydown', onKey);
    return () => {
      document.removeEventListener('mousedown', onDocMouseDown);
      document.removeEventListener('keydown', onKey);
    };
  }, [open]);

  function persist(next) {
    setViews(next);
    saveViews(page, next);
  }

  function saveCurrent() {
    const next = upsertView(views, draft, query.value);
    if (next === views) return;
    persist(next);
    setDraft('');
  }

  function apply(view) {
    navigate(viewHash(route.value, view.query).slice(1));
    setOpen(false);
  }

  const canSave = normalizeViewName(draft).length > 0;

  return html`
    <div ref=${rootRef} class="saved-views" data-testid=${'saved-views-' + page}>
      <button
        type="button"
        class="filter-tab"
        aria-haspopup="true"
        aria-expanded=${open}
        title="Saved views for this page"
        onclick=${() => setOpen((v) => !v)}
        data-testid=${'saved-views-toggle-' + page}
      >
        Views${views.length > 0 ? html`<span class="filter-tab-count">${views.length}</span>` : null}
        <span aria-hidden="true" style="opacity:0.7">${open ? '▲' : '▼'}</span>
      </button>
      ${open && html`
        <div class="saved-views__panel" role="group" aria-label="Saved views" data-testid=${'saved-views-panel-' + page}>
          ${views.length === 0
            ? html`<div class="text-dim saved-views__empty">No saved views yet. Set filters, then save them under a name.</div>`
            : views.map((v) => html`
              <div key=${v.name} class="saved-views__row">
                <button
                  type="button"
                  class="saved-views__apply"
                  title=${'Apply view ' + v.name}
                  onclick=${() => apply(v)}
                  data-testid=${'saved-view-apply-' + v.name}
                >${v.name}</button>
                <button
                  type="button"
                  class="saved-views__delete"
                  aria-label=${'Delete view ' + v.name}
                  title=${'Delete view ' + v.name}
                  onclick=${() => persist(removeView(views, v.name))}
                  data-testid=${'saved-view-delete-' + v.name}
                >×</button>
              </div>
            `)}
          <form
            class="saved-views__save"
            onsubmit=${(e) => { e.preventDefault(); saveCurrent(); }}
          >
            <input
              type="text"
              class="saved-views__input"
              placeholder="Name this view…"
              aria-label="Name for the current view"
              value=${draft}
              oninput=${(e) => setDraft(e.target.value)}
              data-testid=${'saved-views-name-' + page}
            />
            <button
              type="submit"
              class="saved-views__save-btn"
              disabled=${!canSave}
              title="Save the current filters, grouping and sort"
              data-testid=${'saved-views-save-' + page}
            >Save</button>
          </form>
        </div>
      `}
    </div>
  `;
}
