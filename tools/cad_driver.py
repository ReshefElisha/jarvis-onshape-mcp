"""Iterative CAD test driver — "pytest for CAD parts".

Each `CadTest` declares a brief (natural-language description of the target
part) and a series of `Step`s. Each step is either:

  - a Build step: call an MCP tool with args. Returns the structured result
    dict from the tool. On non-OK status, the test FAILS and the driver
    prints a diagnostic snapshot (feature tree, render image path).

  - an Assert step: a predicate over the current Part Studio state
    (obtained via describe_part_studio). Predicates get the structured
    result dict and return either None (pass) or a failure string.

  - an Inspect step: always passes, but emits a render of the current
    state to disk for later eyeballing / Gemini critique.

The driver creates a throwaway document, runs every step in order, writes
a per-step snapshot (render + text) to disk, and reports PASS/FAIL at the
end. Failures halt the test.

This is the pattern I'll use to drive CAD like I drive code: mutate,
verify, move on OR fix.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time

from loguru import logger
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

from dotenv import load_dotenv

# Look for .env in parent dir (project root) first, then the repo.
load_dotenv(REPO.parent.parent / ".env")
load_dotenv(REPO / ".env")

from onshape_mcp import server as S  # noqa: E402
from onshape_mcp.api.client import OnshapeClient, OnshapeCredentials  # noqa: E402
from onshape_mcp.api.describe import DescribeManager  # noqa: E402
from onshape_mcp.api.documents import DocumentManager  # noqa: E402
from onshape_mcp.api.partstudio import PartStudioManager  # noqa: E402
from onshape_mcp.api.rendering import get_image  # noqa: E402



# --- Step kinds --------------------------------------------------------------


StepFn = Callable[["DriverContext"], Awaitable[Optional[str]]]


@dataclass
class Step:
    name: str
    fn: StepFn
    halt_on_failure: bool = True


def build(name: str, tool: str, args_fn: Callable[["DriverContext"], Dict[str, Any]]) -> Step:
    """Build step: call an MCP tool with args derived from context."""

    async def _do(ctx: "DriverContext") -> Optional[str]:
        args = args_fn(ctx)
        args = {**ctx.common, **args}
        result = await ctx.call_tool(tool, args)
        first_text = next(
            (b.text for b in result if getattr(b, "type", None) == "text"), None
        )
        if first_text is None:
            return f"{tool} returned no text"
        try:
            parsed = json.loads(first_text)
        except json.JSONDecodeError:
            # Some tools return prose; stash and continue.
            ctx.last_prose = first_text
            return None
        ctx.last_result = parsed
        if isinstance(parsed, dict) and "ok" in parsed and not parsed["ok"]:
            return f"{tool} returned ok=false: {parsed.get('error_message') or parsed}"
        # Save features referenced by name in later steps.
        feature_id = parsed.get("feature_id") if isinstance(parsed, dict) else None
        if feature_id:
            ctx.feature_ids[args.get("name", tool)] = feature_id
        return None

    return Step(name=name, fn=_do)


def assert_state(name: str, predicate: Callable[[Dict[str, Any]], Optional[str]]) -> Step:
    """Assertion step: describe the PS, run predicate over the raw snapshot."""

    async def _do(ctx: "DriverContext") -> Optional[str]:
        snap = await ctx.describe()
        err = predicate(snap)
        if err:
            return f"assertion failed: {err}"
        return None

    return Step(name=name, fn=_do)


def inspect(name: str) -> Step:
    """Inspect step: render + save per-step snapshot. Always passes.

    Historical note: this used to route renders through a Gemini visual
    critic. Per Shef's feedback the critic is deferred — it was a good
    idea but not enough to ship, and text checks cover correctness cheaply
    (see scratchpad/text-vs-render-calibration.md). The hook can be added
    back later; for now inspect just saves snapshot artifacts.
    """

    async def _do(ctx: "DriverContext") -> Optional[str]:
        snap = await ctx.describe()
        _save_snapshot(ctx, name, snap)
        return None

    return Step(name=name, fn=_do, halt_on_failure=False)


# --- Driver -----------------------------------------------------------------


@dataclass
class DriverContext:
    client: OnshapeClient
    did: str
    wid: str
    eid: str
    out_dir: Path
    describe_mgr: DescribeManager
    brief: str = ""
    common: Dict[str, str] = field(default_factory=dict)
    feature_ids: Dict[str, str] = field(default_factory=dict)
    step_ix: int = 0
    last_result: Any = None
    last_prose: str = ""
    _snapshot_cache: Optional[Dict[str, Any]] = None
    _snapshot_at_step: int = -1

    async def call_tool(self, name: str, args: Dict[str, Any]) -> list:
        self._snapshot_cache = None  # state changed; invalidate cache
        return await S.call_tool(name, args)

    async def describe(self) -> Dict[str, Any]:
        if self._snapshot_cache and self._snapshot_at_step == self.step_ix:
            return self._snapshot_cache
        snap = await self.describe_mgr.describe_part_studio(
            self.did, self.wid, self.eid, views=["iso", "top"], render_width=1000, render_height=700
        )
        self._snapshot_cache = {
            "text": snap.structured_text,
            "views": snap.views,
            "raw": snap.raw,
        }
        self._snapshot_at_step = self.step_ix
        return self._snapshot_cache


def _save_snapshot(
    ctx: DriverContext, label: str, snap: Dict[str, Any], extra_text: str = ""
) -> None:
    ctx.out_dir.mkdir(parents=True, exist_ok=True)
    safe = label.replace(" ", "_").replace("/", "-")
    txt_path = ctx.out_dir / f"{ctx.step_ix:02d}_{safe}.txt"
    txt_path.write_text(snap["text"] + extra_text)
    for v in snap["views"]:
        png_path = ctx.out_dir / f"{ctx.step_ix:02d}_{safe}_{v.view}.png"
        png_path.write_bytes(get_image(v.image_id))


# --- Test case + runner ------------------------------------------------------


@dataclass
class CadTest:
    name: str
    brief: str
    steps: List[Step]
    keep_doc: bool = True  # keep Onshape doc for post-mortem; delete if False


@dataclass
class StepResult:
    step: str
    ok: bool
    error: Optional[str] = None
    duration_s: float = 0.0


@dataclass
class TestReport:
    test: CadTest
    document_id: str
    document_url: str
    steps: List[StepResult]
    out_dir: Path

    @property
    def ok(self) -> bool:
        return all(s.ok for s in self.steps)

    def summary(self) -> str:
        lines = [
            f"=== {self.test.name} === {'PASS' if self.ok else 'FAIL'}",
            f"    doc: {self.document_url}",
            f"    out: {self.out_dir}",
        ]
        for s in self.steps:
            mark = "✓" if s.ok else "✗"
            err = f"  [{s.error}]" if s.error else ""
            lines.append(f"    {mark} [{s.duration_s:5.2f}s] {s.step}{err}")
        return "\n".join(lines)


async def run_cad_test(test: CadTest, out_root: Path) -> TestReport:
    ak = os.getenv("ONSHAPE_API_KEY") or os.getenv("ONSHAPE_ACCESS_KEY", "")
    sk = os.getenv("ONSHAPE_API_SECRET") or os.getenv("ONSHAPE_SECRET_KEY", "")
    if not ak or not sk:
        raise RuntimeError(
            "Onshape credentials not found. Set ONSHAPE_API_KEY/ONSHAPE_API_SECRET."
        )
    creds = OnshapeCredentials(access_key=ak, secret_key=sk)
    ts = int(time.time())
    out_dir = out_root / f"{test.name}-{ts}"
    results: List[StepResult] = []

    async with OnshapeClient(creds) as client:
        dm = DocumentManager(client)
        doc = await dm.create_document(f"dyna-cad-test {test.name} {ts}")
        did = doc.id
        workspaces = await dm.get_workspaces(did)
        wid = next((w.id for w in workspaces if w.is_main), workspaces[0].id)
        psm = PartStudioManager(client)
        ps = await psm.create_part_studio(did, wid, f"{test.name} ps")
        eid = ps["id"] if isinstance(ps, dict) else ps.id
        url = f"https://cad.onshape.com/documents/{did}/w/{wid}/e/{eid}"

        ctx = DriverContext(
            client=client, did=did, wid=wid, eid=eid, out_dir=out_dir,
            describe_mgr=DescribeManager(client),
            brief=test.brief,
            common={"documentId": did, "workspaceId": wid, "elementId": eid},
        )
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "brief.txt").write_text(test.brief)

        for i, step in enumerate(test.steps):
            ctx.step_ix = i
            t0 = time.time()
            try:
                err = await step.fn(ctx)
            except Exception as e:
                err = f"exception: {type(e).__name__}: {e}"
            dur = time.time() - t0
            results.append(StepResult(step=step.name, ok=(err is None), error=err, duration_s=dur))
            if err and step.halt_on_failure:
                # Save a final diagnostic snapshot on failure.
                try:
                    snap = await ctx.describe()
                    _save_snapshot(ctx, f"FAIL_{step.name}", snap)
                except Exception:
                    pass
                break

        if not test.keep_doc:
            try:
                await dm.delete_document(did)
            except Exception:
                pass

    return TestReport(
        test=test, document_id=did, document_url=url, steps=results, out_dir=out_dir
    )


async def run_many(tests: List[CadTest], out_root: Path) -> List[TestReport]:
    reports: List[TestReport] = []
    for t in tests:
        r = await run_cad_test(t, out_root)
        print(r.summary())
        print()
        reports.append(r)
    return reports
