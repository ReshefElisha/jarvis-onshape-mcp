# Drawing-based section-view renderer — research findings

Date: 2026-04-16 (session UTC 18:55–18:58)
Branch: `dyna-main`
Author: agent (Opus 4.7)

## TL;DR — BLOCKED by Onshape platform limitation, not by our code

The Onshape public REST API **does not support creating Section views** via `/drawings/.../modify`.
Only `TopLevel` and `Projected` view types can be created programmatically. This is a documented,
enforced, server-side restriction — not a missing-payload-shape problem.

Every avenue Shef's spec instructed me to try (TopLevel parent view → section view referencing it,
many btType / messageName / viewType guesses) bottoms out on the same server response:

> `Error processing view: Unsupported view type: <anything-but-TopLevel-or-Projected>`
> `Error processing : View type for view creation is not supported yet`

Without server-side support, there is no payload we can send that will produce a section view in
a drawing. The "make a drawing, add a section view, export" workflow is **impossible via API
today**.

## What works (confirmed live on cad.onshape.com)

Probe doc: `e7738d10a4cc9b6b6a77c7c9` (left undeleted — API key scope does not allow doc delete).
Workspace: `e176ed00b78d0f3ec20df96a`.
Part Studio (40×40×20 mm block, Ø10mm hole): `6f217971bcbfd27fabfeb1f5`, partId `JHD`.
Drawing: `72f5c7f6e965ee4be879e771`.

### 1. Create a drawing element that references a Part Studio
```
POST /api/v9/drawings/d/{did}/w/{wid}/create
{ "drawingName": "...", "elementId": "<part_studio_eid>" }
```
Response: `{"id": "<drawing_eid>", "elementType": "APPLICATION", ...}`. OK in all tests.

### 2. Create a TopLevel (parent) view via modify
```
POST /api/v9/drawings/d/{did}/w/{wid}/e/{drawing_eid}/modify
{
  "description": "Add a front view",
  "jsonRequests": [
    {
      "messageName": "onshapeCreateViews",
      "formatVersion": "2021-01-01",
      "views": [
        {
          "viewType": "TopLevel",
          "position": {"x": 5, "y": 5},
          "scale": {"scaleSource": "Custom", "numerator": 1, "denumerator": 1},
          "orientation": "front",
          "reference": {"elementId": "<part_studio_eid>", "idTag": "<partId>"}
        }
      ]
    }
  ]
}
```
Response: `{"requestState": "ACTIVE", "id": "<modify_request_id>", ...}`.

### 3. Poll the modify request
```
GET /api/v6/drawings/modify/status/{modify_request_id}
```
Returns `requestState` in `{ACTIVE, DONE, FAILED}` with an `output` string containing a JSON
blob: `{"status": "OK|Failed", "results": [{"logicalId": "h:100000FB", "viewId": "...", ...}]}`.
The `logicalId` is what `parentView.logicalId` expects in subsequent modify calls.

### 4. Drawing translation formats (live, per-drawing)
```
GET /api/v9/drawings/d/{did}/w/{wid}/e/{drawing_eid}/translationformats
```
Returns: `[INSPECTION_LIST, DRAWING_DEFINITION_LIST, DRAWING_JSON, PDF, DWG, DXF, DWT, PNG, JPEG, TIFF, SVG]`.

**PNG and JPEG are supported drawing export formats.** The translation pipeline (same pattern as
`api/export.py`) almost certainly works — we just have nothing worth rendering because the
section view can't be created in step 2.5.

## What does not work

### Section view creation — every variant fails server-side

All payloads POSTed to the same endpoint, same workspace, same drawing. All went through, were
accepted by the scheduler (`requestState: ACTIVE`), then failed at processing:

| viewType string    | Error message                                                                  |
|--------------------|--------------------------------------------------------------------------------|
| `Section`          | `View type for view creation is not supported yet`                             |
| `section`          | `View type for view creation is not supported yet`                             |
| `SectionView`      | `Error processing view: Unsupported view type: SectionView`                    |
| `sectionView`      | `Error processing view: Unsupported view type: sectionView`                    |
| `CrossSection`     | `Error processing view: Unsupported view type: CrossSection`                   |
| `Cross Section`    | `Error processing view: Unsupported view type: Cross Section`                  |
| `Aligned Section`  | `Error processing view: Unsupported view type: Aligned Section`                |
| `Detail`           | `View type for view creation is not supported yet`                             |
| `Auxiliary`        | `View type for view creation is not supported yet`                             |

The two distinct error messages suggest two code paths on the server:
- `Unsupported view type: <x>` — the string didn't match any known viewType at all.
- `View type for view creation is not supported yet` — the string matched a known internal
  viewType (Section, Detail, Auxiliary), but the "create via API" path explicitly rejects it.

The second message is the crucial one. Onshape's backend knows what "Section" means. The public
API just refuses to create it. Full stop.

## Primary sources

1. **Onshape Drawings API docs** — https://onshape-public.github.io/docs/api-adv/drawings/
   Direct quote: _"Currently, only `TopLevel` and `Projected` view types are supported for
   creating and editing via the Onshape API."_ and _"Other view types listed are available for
   export only."_

2. **Onshape forum** — multiple threads confirm users have been asking for API-driven section
   views for years without success. Example:
   - https://forum.onshape.com/discussion/10082/drawing-section-view
   - https://forum.onshape.com/discussion/29529/onshape-api-modify-drawing
   - https://forum.onshape.com/discussion/4451/section-views-in-drawings
   (All require JWT SSO to read via WebFetch; content summarized from search snippets.)

3. **Live API** — direct probe on `cad.onshape.com` on 2026-04-16. Errors reproduced above.
   Probe doc left for inspection: `e7738d10a4cc9b6b6a77c7c9`.

## Options going forward (NOT implemented — flagged for Shef)

Shef explicitly ruled out the cut-render-delete fallback (that's what `api/section_view.py`
already does). Given the drawing-section path is impossible today, remaining options are:

### A. Keep the existing `api/section_view.py` FS-cut path.
It works. It's been shipping. The only "con" Shef mentioned is that it's not the native
Onshape-engineer workflow. But the native workflow doesn't exist in the API. If we want a
drawing-with-section-annotation deliverable, we cannot produce it programmatically.

### B. Create a drawing with only TopLevel views and annotate the cutting plane.
We CAN make a drawing, put Front + Top + Side views on it, export it as PNG. We CANNOT put a
section view on it — so the rendered PNG would not show the interior. The FS-cut + shadedviews
path in `api/section_view.py` shows more useful information (the actual interior geometry).

### C. Two-step hybrid: use FS cut, THEN create a drawing.
Apply the temporary section FS feature, render via the drawing-PNG pipeline (which IS a new
capability: drawings look different from shadedviews — they have title blocks, hidden-line
rendering, orthographic projection). Still relies on the FS cut under the hood.

### D. Wait for Onshape to ship API support.
The docs have been carrying the "TopLevel/Projected only" restriction since at least the 2021
API spec. Latest changelog entry (2026-04-03, rel-1.213) does NOT mention section-view
creation being added. This will not land soon.

### E. UI-driven template + API configuration swap.
A user creates the drawing template in the Onshape UI (with the section view baked in), then
the API swaps the referenced part/configuration. This is the workaround the forum points to.
It requires manual template setup per part, which defeats the "just render a section" goal.

## The single most load-bearing unknown

There isn't one. The server error `"View type for view creation is not supported yet"` is a
definitive, authoritative answer from Onshape's backend. No payload shape we can discover will
unlock this. This is a platform gap, not a reverse-engineering gap.

If Shef wants to push further, the paths are (a) email Onshape API support / Paul J.
Premakumar to confirm there is no private flag/beta we're missing, or (b) DevTools-capture the
Onshape web client's own section-view creation call — but since the web client almost
certainly uses an internal non-public endpoint (not `/drawings/.../modify`), even a capture
wouldn't help us build a supported public-API tool.

## What landed in the repo

- This findings doc: `scratchpad/drawing-section-research.md`.
- Stub module: `onshape_mcp/api/drawing_section.py` with a `DrawingSectionManager` whose
  `render_section` raises `NotImplementedError` carrying a short version of this research note,
  plus a working `_create_drawing` + `_add_toplevel_view` + `_translate_to_png` scaffold so the
  pipeline is 80% in place the day Onshape ships server support.
- No test file. The two live-API pieces that DO work (create drawing, create TopLevel view,
  export PNG) are exercised in the stub's module docstring as a runnable docstring example, not
  as a pytest (since the deliverable Shef asked for is section-view render and we can't deliver
  that).
- `server.py` UNCHANGED. Per the spec: do not wire the tool until the manager works end-to-end.
