"""Length parsing for tool inputs.

All user-facing length inputs (depth, radius, corners, thickness, etc.) flow
through `parse_length`. It accepts:

- A bare number (int or float): interpreted as millimeters, the industry CAD
  default. This is the "new-forward" convention agreed during the units task;
  earlier starter code silently assumed inches, which bit the dogfood driver
  repeatedly.
- A string with a recognized unit suffix: returned verbatim for Onshape to
  evaluate (e.g. "30 mm", "0.03 m", "1.5 in", "2ft"). Whitespace between the
  number and unit is optional.
- A string with no unit: treated as millimeters.

Returns a `Length` carrying BOTH the Onshape-facing expression string and the
numeric value in meters, because the builder layer needs both: expression
fields (BTMParameterQuantity-147) want the string so Onshape re-evaluates when
variables change, while sketch geometry fields (pntX, xCenter, radius, ...)
need a raw meter float.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Union


# Canonical unit string -> meters per unit. Canonical is what we emit back in
# the expression so it round-trips cleanly through Onshape's parser.
_UNIT_TO_METERS: dict[str, float] = {
    "mm": 0.001,
    "cm": 0.01,
    "m": 1.0,
    "in": 0.0254,
    "ft": 0.3048,
}

# Long-form and alias inputs that get normalized to one of the canonical keys
# above before conversion. Kept lowercase; the parser lowercases the suffix.
_UNIT_ALIASES: dict[str, str] = {
    "mm": "mm",
    "millimeter": "mm",
    "millimeters": "mm",
    "millimetre": "mm",
    "millimetres": "mm",
    "cm": "cm",
    "centimeter": "cm",
    "centimeters": "cm",
    "centimetre": "cm",
    "centimetres": "cm",
    "m": "m",
    "meter": "m",
    "meters": "m",
    "metre": "m",
    "metres": "m",
    "in": "in",
    "inch": "in",
    "inches": "in",
    '"': "in",
    "ft": "ft",
    "foot": "ft",
    "feet": "ft",
    "'": "ft",
}

# Matches `<number>[<optional whitespace><unit>]`. Number allows sign, decimal,
# and exponent. Unit is any non-whitespace suffix that we look up against the
# alias table — unknown suffixes fall through as a ValueError below rather than
# being silently accepted.
_LENGTH_RE = re.compile(
    r"""
    ^\s*
    (?P<num>[+-]?(?:\d+\.\d*|\.\d+|\d+)(?:[eE][+-]?\d+)?)
    \s*
    (?P<unit>\S+)?
    \s*$
    """,
    re.VERBOSE,
)

DEFAULT_UNIT = "mm"


@dataclass(frozen=True)
class Length:
    """A parsed length carrying both the Onshape expression and numeric meters.

    `expression` is suitable for BTMParameterQuantity-147 `expression` fields;
    `meters` is suitable for raw geometry coordinates that Onshape expects in
    SI units (sketch pntX/pntY, circle radius, etc).
    """

    expression: str
    meters: float


def parse_length(value: Union[int, float, str]) -> Length:
    """Parse a length input into an Onshape expression and a meter value.

    Args:
        value: Either a number (int/float), in which case it is treated as
            millimeters, or a string with an optional unit suffix ("30 mm",
            "1.5 in", "0.03 m", "2ft", "10" — "10" becomes 10 mm).

    Returns:
        Length(expression, meters). `expression` is always of the form
        "<number> <canonical-unit>" (e.g. "30.0 mm", "1.5 in").

    Raises:
        TypeError: `value` is not a number or string.
        ValueError: string is unparseable or has an unknown unit.
    """
    if isinstance(value, bool):
        # bool is a subclass of int in Python — disallow so (True, False)
        # doesn't sneak in as a length.
        raise TypeError(f"length cannot be a bool, got {value!r}")

    if isinstance(value, (int, float)):
        num = float(value)
        unit = DEFAULT_UNIT
    elif isinstance(value, str):
        s = value.strip()
        if not s:
            raise ValueError("length string is empty")
        match = _LENGTH_RE.match(s)
        if not match:
            raise ValueError(f"cannot parse length {value!r}")
        num = float(match.group("num"))
        raw_unit = (match.group("unit") or DEFAULT_UNIT).strip().lower()
        if raw_unit not in _UNIT_ALIASES:
            raise ValueError(
                f"unknown length unit {raw_unit!r} in {value!r}; "
                f"supported units: mm, cm, m, in, ft"
            )
        unit = _UNIT_ALIASES[raw_unit]
    else:
        raise TypeError(
            f"length must be a number or string, got {type(value).__name__}"
        )

    meters = num * _UNIT_TO_METERS[unit]
    # Print numbers without trailing zeros where possible — "30 mm" reads
    # cleaner in feature trees than "30.0 mm". Keep precision for non-integer.
    if num == int(num):
        num_str = str(int(num))
    else:
        num_str = repr(num)
    expression = f"{num_str} {unit}"
    return Length(expression=expression, meters=meters)


def parse_length_meters(value: Union[int, float, str]) -> float:
    """Shorthand for `parse_length(value).meters` — for raw geometry fields."""
    return parse_length(value).meters


def parse_length_expression(value: Union[int, float, str]) -> str:
    """Shorthand for `parse_length(value).expression` — for parameter fields."""
    return parse_length(value).expression
