"""2D renderer for BTMSketch-151 features.

Onshape's /shadedviews endpoint renders solids but not sketches. To give
callers (and the LLM's vision path) a visual of a sketch's geometry and
constraints, we plot it ourselves: walk the entity list, project sketch-local
(x, y) mm into pixel space, and draw each line / arc / circle / point with
PIL. Constraints are overlaid as badges (FIX red squares, dimension labels
near the referenced entity, H/V tags on horizontal/vertical lines).

Pairs with `inspect_sketch` — same entity id conventions, same coordinate
system.
"""

from __future__ import annotations

import io
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from PIL import Image, ImageDraw, ImageFont


# Visual config. Tuned for 800-1200 px renders; small enough that a 4-bar
# linkage reads cleanly, large enough that a 50-entity sketch doesn't
# collide labels too badly.
_BG = (255, 255, 255)
_GRID = (235, 235, 235)
_AXIS = (180, 180, 180)
_LINE = (30, 80, 180)
_CONSTRUCTION = (150, 170, 210)
_ARC = (180, 80, 30)
_POINT = (30, 30, 30)
_LABEL = (60, 60, 60)
_FIX_MARK = (200, 40, 40)
_DIM_LABEL = (30, 130, 60)
_HV_LABEL = (140, 100, 30)


@dataclass
class _Transform:
    """Maps sketch-mm (x, y) to pixel (u, v). Y is flipped (screen-down)."""
    scale: float  # px per mm
    x_min: float  # world mm
    y_min: float  # world mm
    x_max: float
    y_max: float
    pad: int      # pixel padding
    height: int   # image pixel height

    def to_px(self, x_mm: float, y_mm: float) -> Tuple[float, float]:
        u = self.pad + (x_mm - self.x_min) * self.scale
        v = self.height - self.pad - (y_mm - self.y_min) * self.scale
        return u, v


def _collect_points(entities: List[Dict[str, Any]]) -> List[Tuple[float, float]]:
    """Pull every point the bounding box needs to contain."""
    pts: List[Tuple[float, float]] = []
    for e in entities:
        kind = e.get("kind")
        if kind == "line":
            pts.append(tuple(e["start_mm"]))
            pts.append(tuple(e["end_mm"]))
        elif kind == "arc":
            pts.append(tuple(e["start_mm"]))
            pts.append(tuple(e["end_mm"]))
            cx, cy = e["center_mm"]
            r = e["radius_mm"]
            # Arcs don't necessarily reach the bounding cardinal points, but
            # adding the center-expanded bbox keeps the drawn curve visible.
            pts.extend([(cx - r, cy - r), (cx + r, cy + r)])
        elif kind == "circle":
            cx, cy = e["center_mm"]
            r = e["radius_mm"]
            pts.extend([(cx - r, cy - r), (cx + r, cy + r)])
        elif kind == "point":
            pts.append(tuple(e["point_mm"]))
    return pts


def _compute_transform(
    entities: List[Dict[str, Any]],
    width: int,
    height: int,
    pad: int,
) -> _Transform:
    pts = _collect_points(entities)
    if not pts:
        # Empty sketch — arbitrary 100 mm frame around origin.
        pts = [(-50.0, -50.0), (50.0, 50.0)]
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x_min, x_max = min(xs), max(xs)
    y_min, y_max = min(ys), max(ys)

    # Always include the origin so axis crosses are visible for sketches
    # that sit off-origin.
    x_min = min(x_min, 0.0)
    y_min = min(y_min, 0.0)
    x_max = max(x_max, 0.0)
    y_max = max(y_max, 0.0)

    # Inflate degenerate dimensions so the renderer doesn't divide by zero.
    dx = max(x_max - x_min, 1e-6)
    dy = max(y_max - y_min, 1e-6)
    margin = 0.08 * max(dx, dy)
    x_min -= margin; x_max += margin
    y_min -= margin; y_max += margin
    dx, dy = x_max - x_min, y_max - y_min

    scale = min(
        (width - 2 * pad) / dx,
        (height - 2 * pad) / dy,
    )
    return _Transform(
        scale=scale, x_min=x_min, y_min=y_min,
        x_max=x_max, y_max=y_max, pad=pad, height=height,
    )


def _load_font(size: int) -> ImageFont.ImageFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(candidate, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def _nice_grid_step(span_mm: float, target_divisions: int = 10) -> float:
    """Round grid spacing to 1 / 2 / 5 / 10 / ... mm."""
    raw = span_mm / max(target_divisions, 1)
    if raw <= 0:
        return 10.0
    magnitude = 10 ** math.floor(math.log10(raw))
    for m in (1.0, 2.0, 5.0, 10.0):
        if m * magnitude >= raw:
            return m * magnitude
    return 10.0 * magnitude


def _draw_grid(draw: ImageDraw.ImageDraw, t: _Transform, width: int, height: int) -> None:
    step = _nice_grid_step(max(t.x_max - t.x_min, t.y_max - t.y_min))
    # Start grid at the largest multiple of step <= x_min.
    x0 = math.floor(t.x_min / step) * step
    y0 = math.floor(t.y_min / step) * step
    x = x0
    while x <= t.x_max:
        u, _ = t.to_px(x, t.y_min)
        _, v_top = t.to_px(x, t.y_max)
        draw.line([(u, t.pad), (u, height - t.pad)], fill=_GRID, width=1)
        x += step
    y = y0
    while y <= t.y_max:
        _, v = t.to_px(t.x_min, y)
        draw.line([(t.pad, v), (width - t.pad, v)], fill=_GRID, width=1)
        y += step
    # Axes through origin, if origin is in frame (post-inflation it is).
    u0, _ = t.to_px(0.0, 0.0)
    _, v0 = t.to_px(0.0, 0.0)
    draw.line([(u0, t.pad), (u0, height - t.pad)], fill=_AXIS, width=1)
    draw.line([(t.pad, v0), (width - t.pad, v0)], fill=_AXIS, width=1)


def _draw_line(
    draw: ImageDraw.ImageDraw,
    t: _Transform,
    entity: Dict[str, Any],
    color: Tuple[int, int, int],
    width_px: int,
) -> Tuple[float, float, Tuple[float, float]]:
    """Draw the line. Return (mid_u, mid_v, perpendicular_unit_px)."""
    sx, sy = entity["start_mm"]
    ex, ey = entity["end_mm"]
    u1, v1 = t.to_px(sx, sy)
    u2, v2 = t.to_px(ex, ey)
    if entity.get("isConstruction"):
        _draw_dashed(draw, u1, v1, u2, v2, color, dash=6)
    else:
        draw.line([(u1, v1), (u2, v2)], fill=color, width=width_px)
    dx, dy = u2 - u1, v2 - v1
    length = math.hypot(dx, dy) or 1.0
    # Perpendicular unit vector (rotate 90° CCW in screen coords).
    perp = (-dy / length, dx / length)
    return (u1 + u2) / 2, (v1 + v2) / 2, perp


def _draw_dashed(
    draw: ImageDraw.ImageDraw,
    x1: float, y1: float, x2: float, y2: float,
    color: Tuple[int, int, int], dash: int = 6,
) -> None:
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length == 0:
        return
    ux, uy = dx / length, dy / length
    covered = 0.0
    on = True
    while covered < length:
        step = min(dash, length - covered)
        sx = x1 + ux * covered
        sy = y1 + uy * covered
        ex = x1 + ux * (covered + step)
        ey = y1 + uy * (covered + step)
        if on:
            draw.line([(sx, sy), (ex, ey)], fill=color, width=2)
        covered += step
        on = not on


def _draw_arc(
    draw: ImageDraw.ImageDraw,
    t: _Transform,
    entity: Dict[str, Any],
    color: Tuple[int, int, int],
) -> Tuple[float, float]:
    cx, cy = entity["center_mm"]
    r = entity["radius_mm"]
    uc, vc = t.to_px(cx, cy)
    r_px = r * t.scale
    bbox = (uc - r_px, vc - r_px, uc + r_px, vc + r_px)
    # For PIL.arc, angles are measured from +X axis, CCW becomes CW on screen
    # because screen Y is flipped. To place the arc correctly between its
    # start and end *world* points we compute those angles directly.
    sx, sy = entity["start_mm"]
    ex, ey = entity["end_mm"]
    a_start_world = math.degrees(math.atan2(sy - cy, sx - cx))
    a_end_world = math.degrees(math.atan2(ey - cy, ex - cx))
    # Screen Y is flipped: negate.
    a_start = -a_start_world
    a_end = -a_end_world
    # PIL.arc draws the shorter CCW sweep from start to end — normalize so
    # we always go start -> end going CCW on screen.
    if a_end < a_start:
        a_end += 360.0
    draw.arc(bbox, start=a_start, end=a_end, fill=color, width=2)
    # Midpoint in mm (for labels).
    a_mid_world = math.radians((a_start_world + (a_end_world if a_end_world > a_start_world else a_end_world + 360)) / 2)
    return t.to_px(cx + r * math.cos(a_mid_world), cy + r * math.sin(a_mid_world))


def _draw_circle(
    draw: ImageDraw.ImageDraw,
    t: _Transform,
    entity: Dict[str, Any],
    color: Tuple[int, int, int],
) -> Tuple[float, float]:
    cx, cy = entity["center_mm"]
    r = entity["radius_mm"]
    uc, vc = t.to_px(cx, cy)
    r_px = r * t.scale
    draw.ellipse((uc - r_px, vc - r_px, uc + r_px, vc + r_px), outline=color, width=2)
    # Small cross at center.
    draw.line([(uc - 3, vc), (uc + 3, vc)], fill=color, width=1)
    draw.line([(uc, vc - 3), (uc, vc + 3)], fill=color, width=1)
    return uc + r_px * 0.7, vc - r_px * 0.7


def _resolve_ref_point(
    ref: Optional[str],
    entity_index: Dict[str, Dict[str, Any]],
) -> Optional[Tuple[float, float]]:
    """Look up the world-mm coord of a constraint's `localFirst`/`localSecond`.

    Handles bare entity ids and `<id>.start` / `.end` / `.center` sub-points.
    Returns None if the ref can't be resolved (missing entity, unknown suffix).
    """
    if not ref or not isinstance(ref, str):
        return None
    base, _, suffix = ref.partition(".")
    e = entity_index.get(base)
    if not e:
        return None
    kind = e.get("kind")
    if not suffix:
        if kind == "line":
            sx, sy = e["start_mm"]
            ex, ey = e["end_mm"]
            return (sx + ex) / 2, (sy + ey) / 2
        if kind in ("arc", "circle"):
            return tuple(e["center_mm"])
        if kind == "point":
            return tuple(e["point_mm"])
        return None
    if suffix == "start" and "start_mm" in e:
        return tuple(e["start_mm"])
    if suffix == "end" and "end_mm" in e:
        return tuple(e["end_mm"])
    if suffix == "center" and "center_mm" in e:
        return tuple(e["center_mm"])
    return None


def _draw_constraint_badges(
    draw: ImageDraw.ImageDraw,
    t: _Transform,
    constraints: List[Dict[str, Any]],
    entity_index: Dict[str, Dict[str, Any]],
    font: ImageFont.ImageFont,
    line_mid: Optional[Dict[str, Tuple[float, float]]] = None,
    line_perp: Optional[Dict[str, Tuple[float, float]]] = None,
) -> None:
    """Overlay constraint markers on the geometry.

    `line_mid` / `line_perp` (keyed by entity id) let dimension and H/V
    labels sit on the opposite side of the line from its id label, so they
    don't overlap. Pass None to fall back to midpoint placement.
    """
    line_mid = line_mid or {}
    line_perp = line_perp or {}

    def _line_opposite_label(eid: str) -> Optional[Tuple[float, float]]:
        if eid not in line_mid:
            return None
        mu, mv = line_mid[eid]
        perp = line_perp.get(eid, (0, 1))
        return (mu - perp[0] * 10 - 4, mv - perp[1] * 10 + 2)

    for c in constraints:
        ctype = c.get("constraintType")
        lf = c.get("localFirst")
        ls = c.get("localSecond")
        if ctype == "FIX":
            pt = _resolve_ref_point(lf, entity_index)
            if pt is None:
                continue
            u, v = t.to_px(*pt)
            draw.rectangle((u - 4, v - 4, u + 4, v + 4), outline=_FIX_MARK, width=2)
        elif ctype in ("HORIZONTAL", "VERTICAL"):
            tag = "H" if ctype == "HORIZONTAL" else "V"
            pos = _line_opposite_label(lf) if isinstance(lf, str) else None
            if pos is None:
                pt = _resolve_ref_point(lf, entity_index)
                if pt is None:
                    continue
                u, v = t.to_px(*pt)
                pos = (u + 4, v - 12)
            draw.text(pos, tag, fill=_HV_LABEL, font=font)
        elif ctype in ("LENGTH", "DIAMETER", "RADIUS"):
            length_expr = c.get("length")
            if length_expr is None or not isinstance(lf, str):
                continue
            pos = _line_opposite_label(lf)
            if pos is None:
                pt = _resolve_ref_point(lf, entity_index)
                if pt is None:
                    continue
                u, v = t.to_px(*pt)
                pos = (u + 6, v + 4)
            label = f"{length_expr}"
            draw.text(pos, label, fill=_DIM_LABEL, font=font)
        elif ctype == "DISTANCE":
            p1 = _resolve_ref_point(lf, entity_index)
            p2 = _resolve_ref_point(ls, entity_index)
            length_expr = c.get("length")
            if p1 is None or p2 is None or length_expr is None:
                continue
            u1, v1 = t.to_px(*p1)
            u2, v2 = t.to_px(*p2)
            # Dashed dimension line + label at midpoint.
            _draw_dashed(draw, u1, v1, u2, v2, _DIM_LABEL, dash=5)
            mu, mv = (u1 + u2) / 2, (v1 + v2) / 2
            dir_tag = c.get("direction") or ""
            suffix = f" [{dir_tag}]" if dir_tag and dir_tag != "MINIMUM" else ""
            draw.text((mu + 4, mv - 12), f"{length_expr}{suffix}", fill=_DIM_LABEL, font=font)
        elif ctype == "ANGLE":
            p1 = _resolve_ref_point(lf, entity_index)
            angle_expr = c.get("angle")
            if p1 is None or angle_expr is None:
                continue
            u, v = t.to_px(*p1)
            draw.text((u + 6, v + 4), f"angle={angle_expr}", fill=_DIM_LABEL, font=font)
        # COINCIDENT / TANGENT / PARALLEL / PERPENDICULAR / EQUAL / POINT_ON /
        # MIDPOINT / CONCENTRIC: no badge — they're implicit in the drawn
        # geometry (overlapping endpoints, shared tangent, etc.) and adding
        # markers clutters more than it helps.


def render_sketch_png(
    entities: List[Dict[str, Any]],
    constraints: List[Dict[str, Any]],
    *,
    width: int = 1000,
    height: int = 800,
    title: Optional[str] = None,
    show_labels: bool = True,
    show_constraints: bool = True,
) -> bytes:
    """Render a sketch's entities + constraints to a PNG.

    `entities` and `constraints` are the shapes returned by `inspect_sketch`
    (see `sketch_inspect.py`). Each entity has a `kind`, id, and coordinate
    fields in mm. Returns raw PNG bytes.
    """
    pad = 40
    img = Image.new("RGB", (width, height), _BG)
    draw = ImageDraw.Draw(img)

    t = _compute_transform(entities, width, height, pad)
    _draw_grid(draw, t, width, height)

    font_small = _load_font(12)
    font_mid = _load_font(14)

    entity_index: Dict[str, Dict[str, Any]] = {
        e["id"]: e for e in entities if e.get("id")
    }

    # line_perp[eid] = unit perp vector in screen space. Used to push the
    # entity label one way and the dimension badge the other so they don't
    # overlap on the midpoint.
    line_perp: Dict[str, Tuple[float, float]] = {}
    line_mid: Dict[str, Tuple[float, float]] = {}

    for e in entities:
        kind = e.get("kind")
        label_anchor: Optional[Tuple[float, float]] = None
        if kind == "line":
            color = _CONSTRUCTION if e.get("isConstruction") else _LINE
            mu, mv, perp = _draw_line(draw, t, e, color, width_px=2)
            label_anchor = (mu, mv)
            eid = e.get("id")
            if eid:
                line_perp[eid] = perp
                line_mid[eid] = (mu, mv)
        elif kind == "arc":
            label_anchor = _draw_arc(draw, t, e, _ARC)
        elif kind == "circle":
            label_anchor = _draw_circle(draw, t, e, _ARC)
        elif kind == "point":
            px, py = e["point_mm"]
            u, v = t.to_px(px, py)
            draw.ellipse((u - 3, v - 3, u + 3, v + 3), fill=_POINT)
            label_anchor = (u + 5, v - 10)
        if show_labels and label_anchor is not None and e.get("id"):
            # For lines, push the id label one perp direction from midpoint;
            # dimension badges will sit on the opposite side.
            if e.get("kind") == "line":
                perp = line_perp[e["id"]]
                lx = label_anchor[0] + perp[0] * 12 - 4
                ly = label_anchor[1] + perp[1] * 12 - 6
            else:
                lx = label_anchor[0] + 4
                ly = label_anchor[1] + 4
            draw.text((lx, ly), e["id"], fill=_LABEL, font=font_small)

    if show_constraints:
        _draw_constraint_badges(
            draw, t, constraints, entity_index, font_small,
            line_mid=line_mid, line_perp=line_perp,
        )

    # Title / legend in the top-left corner.
    header_lines = []
    if title:
        header_lines.append(title)
    header_lines.append(
        f"{len(entities)} entities, {len(constraints)} constraints   "
        f"scale={t.scale:.2f} px/mm"
    )
    for i, line in enumerate(header_lines):
        draw.text((pad, 8 + i * 16), line, fill=_LABEL, font=font_mid)

    # Axis labels in the bottom-right corner.
    draw.text(
        (width - pad - 60, height - pad - 14),
        f"x: {t.x_min:.0f}..{t.x_max:.0f} mm",
        fill=_LABEL, font=font_small,
    )
    draw.text(
        (width - pad - 60, height - pad),
        f"y: {t.y_min:.0f}..{t.y_max:.0f} mm",
        fill=_LABEL, font=font_small,
    )

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()
