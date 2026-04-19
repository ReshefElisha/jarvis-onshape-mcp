"""OCR + grouping for engineering-drawing dimension callouts.

Why this exists: Claude can see the drawing PNG attached to its prompt, but
small numeric callouts (10-20 px tall after multi-image downsampling) are
unreliable to read. The agent under-builds at 4× wrong scale on hard-tier
NIST drawings because the "800 mm overall" callout looks like noise.

Tesseract is decent at picking up tokens that contain digits when run with
PSM 11 (sparse text). We OCR once, group spatially-adjacent tokens into
callouts, and return a structured list. The agent maps numbers to features
using its own vision + the position info.

Known limitations:
- Ø (diameter prefix) is often misread as "9" (e.g. "Ø50" → "950")
- Some special characters (×, ⊥, ⌖) drop entirely
- Confidence is per-token; very low confidence (< 30) is filtered out

Even with these issues, getting "R3, 80, 40, 36, M8, 30.0°" reliably is a
big win over having to read 12-px text from a 1568px-wide image.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import List, Optional

from PIL import Image


@dataclass
class Callout:
    text: str
    x: int            # bbox x in source pixels
    y: int            # bbox y in source pixels
    width: int
    height: int
    confidence: float  # 0..100 from tesseract
    kind: str          # heuristic class: length / radius / diameter / count / thread / angle / scale / other


_DIM_PATTERNS = [
    (re.compile(r'^[ØΦϕ⌀]\d+(\.\d+)?$'), 'diameter'),
    (re.compile(r'^R\d+(\.\d+)?$'), 'radius'),
    (re.compile(r'^\d+X\b'), 'count'),
    (re.compile(r'^M\d+(X\d+(\.\d+)?)?$'), 'thread'),
    (re.compile(r'^\d+(\.\d+)?°$'), 'angle'),
    (re.compile(r'^1:\d+$'), 'scale'),
    (re.compile(r'^\(?\d+(\.\d+)?\)?$'), 'length'),
]


def _classify(text: str) -> str:
    cleaned = text.strip().rstrip('.,;')
    for pat, kind in _DIM_PATTERNS:
        if pat.match(cleaned):
            return kind
    return 'other'


def extract_callouts(image_path: str, min_confidence: int = 30,
                     group_y_tol: int = 12, group_x_gap: int = 25) -> List[Callout]:
    """Run OCR on a drawing PNG, group adjacent tokens, classify each group.

    Returns a list of Callout objects. Caller can filter on `kind` for
    just the dimensions (length / radius / diameter / etc.).
    """
    import pytesseract
    img = Image.open(image_path)
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT,
                                     config="--psm 11")

    raw_tokens = []
    for i, t in enumerate(data['text']):
        t = t.strip()
        try:
            conf = float(data['conf'][i])
        except (TypeError, ValueError):
            conf = -1.0
        if t and conf >= min_confidence:
            raw_tokens.append({
                "text": t,
                "x": int(data['left'][i]),
                "y": int(data['top'][i]),
                "w": int(data['width'][i]),
                "h": int(data['height'][i]),
                "conf": conf,
            })

    raw_tokens.sort(key=lambda t: (t['y'] // 20, t['x']))

    groups: list[list[dict]] = []
    for t in raw_tokens:
        placed = False
        for g in groups:
            last = g[-1]
            if abs(t['y'] - last['y']) < group_y_tol \
               and abs(t['x'] - (last['x'] + last['w'])) < group_x_gap:
                g.append(t)
                placed = True
                break
        if not placed:
            groups.append([t])

    callouts: list[Callout] = []
    for g in groups:
        text = " ".join(tok['text'] for tok in g)
        if not re.search(r'\d', text):
            continue
        first_kind = _classify(g[0]['text'])
        # Use the first token's classification; multi-token combines like
        # "4X R12" inherit "count" from the first.
        kind = first_kind
        x_min = min(tok['x'] for tok in g)
        y_min = min(tok['y'] for tok in g)
        x_max = max(tok['x'] + tok['w'] for tok in g)
        y_max = max(tok['y'] + tok['h'] for tok in g)
        avg_conf = sum(tok['conf'] for tok in g) / len(g)
        callouts.append(Callout(
            text=text,
            x=x_min, y=y_min,
            width=x_max - x_min, height=y_max - y_min,
            confidence=avg_conf,
            kind=kind,
        ))
    return callouts


def callouts_to_dict(callouts: List[Callout]) -> dict:
    return {
        "callouts": [asdict(c) for c in callouts],
        "by_kind": {
            kind: [c.text for c in callouts if c.kind == kind]
            for kind in ("length", "radius", "diameter", "thread", "angle", "count", "scale")
        },
    }
