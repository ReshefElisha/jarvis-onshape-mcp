"""FeatureScript notice extraction + body re-evaluation.

When `write_featurescript_feature` lands a feature that fails at REGEN, the
top-level response only carries `featureState: {featureStatus: "ERROR"}` and
`getFeatureStatus` only adds `{statusEnum: "REGEN_ERROR"}` -- both opaque.
The parser/runtime notice that names the actual failing call (e.g.
`Function opThisDoesNotExist with 3 argument(s) not found`) is reachable
only by re-evaluating the BODY of the user's `defineFeature(function(...) {
...BODY... })` via `/featurescript`. The eval endpoint streams its `notices[]`
on the response.

Probed live 2026-04-17 with BAD_FUNC and BAD_HELIX fixtures; only the
inline-body re-eval surfaced the real diagnostic. See
`scratchpad/fs-failure-evidence.md` for the full channel comparison.

This module:
  - `extract_fs_body(source)`  : pull the body out of a defineFeature wrapper
  - `format_notice(notice)`    : render one BTNotice-227 as a single line
  - `format_notices(notices)`  : render a list, drop INFO when nosier than ERROR
  - `fetch_body_notices(...)`  : POST the body to /featurescript and return notices
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from loguru import logger

from .client import OnshapeClient


def extract_fs_body(source: str) -> Optional[str]:
    """Pull the body of `defineFeature(function(...) precondition {...} { BODY })`.

    Returns the inner BODY (curly-brace contents stripped). Returns None if
    the source isn't a recognizable defineFeature shape -- callers should
    skip enrichment in that case.

    Heuristic, not a full parser: counts balanced braces/parens on raw
    characters. Comments containing `{` `}` and string literals containing
    them will fool it. Good enough for the ~95% case where the user's FS is
    a clean defineFeature.
    """
    df = re.search(r"defineFeature\s*\(\s*function\s*\(", source)
    if not df:
        return None

    # Skip the function signature: balance the opening "(" we already passed.
    pos = df.end()
    depth = 1
    while pos < len(source) and depth > 0:
        ch = source[pos]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        pos += 1
    if depth != 0:
        return None

    # Optional `precondition { ... }` block.
    while pos < len(source) and source[pos].isspace():
        pos += 1
    if source[pos:pos + len("precondition")] == "precondition":
        pos += len("precondition")
        while pos < len(source) and source[pos] != "{":
            pos += 1
        if pos >= len(source):
            return None
        pos += 1  # past opening "{"
        depth = 1
        while pos < len(source) and depth > 0:
            ch = source[pos]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
            pos += 1
        if depth != 0:
            return None

    # Now the body: skip whitespace, expect "{".
    while pos < len(source) and source[pos].isspace():
        pos += 1
    if pos >= len(source) or source[pos] != "{":
        return None
    body_start = pos + 1
    pos = body_start
    depth = 1
    while pos < len(source) and depth > 0:
        ch = source[pos]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
        pos += 1
    if depth != 0:
        return None
    return source[body_start:pos - 1]


def format_notice(notice: Dict[str, Any]) -> str:
    """Render one BTNotice-227 as a single line: `[LEVEL] L<line>:C<col>  <message>`.

    Falls back through several field names because Onshape's notice shape
    varies by error class: parser notices put the message in `message`;
    expression-evaluation notices put a structured identifier in
    `expressionErrorInfo.errorMessageIdentifier` and the actual symbol in
    `messageArguments[].value.value`.
    """
    if not isinstance(notice, dict):
        return ""

    level = (
        notice.get("level")
        or notice.get("severity")
        or notice.get("type")
        or "?"
    )
    msg = notice.get("message") or notice.get("text") or ""
    if not msg:
        err_info = notice.get("expressionErrorInfo") or {}
        ident = err_info.get("errorMessageIdentifier") or ""
        args = err_info.get("messageArguments") or []
        arg_vals: List[str] = []
        for a in args:
            if not isinstance(a, dict):
                continue
            v = a.get("value")
            # BTValueAndUse-4696: { use, value: BTFSValueString-... }
            if isinstance(v, dict):
                arg_vals.append(str(v.get("value", "")))
            elif v is not None:
                arg_vals.append(str(v))
        arg_vals = [v for v in arg_vals if v]
        if ident:
            msg = f"{ident}: {', '.join(arg_vals)}" if arg_vals else ident

    loc = ""
    st = notice.get("stackTrace") or []
    if st and isinstance(st[0], dict):
        line = st[0].get("line", 0) or 0
        col = st[0].get("column", 0) or 0
        # Onshape sometimes returns 0/0 when location info is unavailable
        # (whole-script errors). Skip the location prefix in that case.
        if line or col:
            loc = f" L{line}:C{col}"

    return f"[{level}]{loc} {msg}".strip()


def format_notices(
    notices: Optional[List[Dict[str, Any]]],
    *,
    max_count: int = 5,
) -> str:
    """Render a notices list to one notice per line. Dedupe, and drop INFO if
    any ERROR / WARNING is present (INFOs are usually "Variable e set but not
    used" noise from the catch wrapper, not the real issue).
    """
    if not notices:
        return ""

    rendered: List[str] = []
    seen: set[str] = set()
    has_real = any(
        isinstance(n, dict)
        and (n.get("level") or n.get("severity") or "") in ("ERROR", "WARNING")
        for n in notices
    )

    for n in notices:
        if not isinstance(n, dict):
            continue
        level = (n.get("level") or n.get("severity") or "").upper()
        if has_real and level == "INFO":
            continue
        line = format_notice(n)
        if not line or line in seen:
            continue
        seen.add(line)
        rendered.append(line)
        if len(rendered) >= max_count:
            break

    return "\n".join(rendered)


async def fetch_body_notices(
    client: OnshapeClient,
    document_id: str,
    workspace_id: str,
    part_studio_element_id: str,
    fs_body: str,
) -> List[Dict[str, Any]]:
    """Wrap `fs_body` as `function(context, queries) { <body> }` and POST it
    to /featurescript. Return the response's `notices[]` (possibly empty).

    Best-effort: any error returns []. The enrichment path must never raise
    a new error on top of the original feature failure.
    """
    if not fs_body or not fs_body.strip():
        return []

    # Wrap the body. The eval endpoint requires a `function(...)` toplevel.
    # We rebind `id` to a fresh `newId()` and `definition` to an empty map so
    # references to either keep working without the caller having to
    # parameterize them.
    wrapped = (
        "function(context is Context, queries) {\n"
        "    var id = newId();\n"
        "    var definition = {};\n"
        f"{fs_body}\n"
        "    return undefined;\n"
        "}"
    )
    path = (
        f"/api/v8/partstudios/d/{document_id}/w/{workspace_id}"
        f"/e/{part_studio_element_id}/featurescript"
    )
    try:
        resp = await client.post(path, data={"script": wrapped})
    except Exception as e:  # noqa: BLE001
        logger.debug(f"fs body re-eval call failed: {e}")
        return []

    notices = resp.get("notices") if isinstance(resp, dict) else None
    return notices if isinstance(notices, list) else []
