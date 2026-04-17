"""Tests for parse_length (the tool-input unit parser)."""

import math

import pytest

from onshape_mcp.builders._units import (
    Angle,
    Length,
    parse_angle,
    parse_angle_radians,
    parse_length,
    parse_length_meters,
    parse_length_expression,
)


class TestBareNumbers:
    def test_int_is_mm_default(self):
        result = parse_length(30)
        assert isinstance(result, Length)
        assert result.expression == "30 mm"
        assert math.isclose(result.meters, 0.030)

    def test_float_is_mm_default(self):
        result = parse_length(1.5)
        assert result.expression == "1.5 mm"
        assert math.isclose(result.meters, 0.0015)

    def test_zero(self):
        result = parse_length(0)
        assert result.expression == "0 mm"
        assert result.meters == 0.0

    def test_negative(self):
        result = parse_length(-5.0)
        # -5.0 collapses to -5 by the int-check; use -5.5 for a stable float case.
        assert result.expression == "-5 mm"
        assert math.isclose(result.meters, -0.005)

    def test_negative_non_integer(self):
        result = parse_length(-2.5)
        assert result.expression == "-2.5 mm"
        assert math.isclose(result.meters, -0.0025)

    def test_bool_rejected(self):
        with pytest.raises(TypeError):
            parse_length(True)

    def test_list_rejected(self):
        with pytest.raises(TypeError):
            parse_length([30])


class TestStringWithUnit:
    @pytest.mark.parametrize(
        "value,expected_expr,expected_m",
        [
            ("30 mm", "30 mm", 0.030),
            ("30mm", "30 mm", 0.030),
            ("  30.0 mm  ", "30 mm", 0.030),  # 30.0 simplifies to "30 mm"
            ("0.5 cm", "0.5 cm", 0.005),
            ("0.03 m", "0.03 m", 0.03),
            ("1.5 in", "1.5 in", 1.5 * 0.0254),
            ("2ft", "2 ft", 2 * 0.3048),
            ("2 foot", "2 ft", 2 * 0.3048),
            ("10 inches", "10 in", 10 * 0.0254),
            ("3 millimeters", "3 mm", 0.003),
            ("4 METERS", "4 m", 4.0),  # case-insensitive unit
        ],
    )
    def test_parses_canonical_round_trip(self, value, expected_expr, expected_m):
        result = parse_length(value)
        assert result.expression == expected_expr
        assert math.isclose(result.meters, expected_m, rel_tol=1e-9)

    def test_string_without_unit_defaults_to_mm(self):
        result = parse_length("42")
        assert result.expression == "42 mm"
        assert math.isclose(result.meters, 0.042)

    def test_scientific_notation(self):
        result = parse_length("1e-3 m")
        assert math.isclose(result.meters, 0.001)

    def test_leading_dot(self):
        result = parse_length(".5 in")
        assert math.isclose(result.meters, 0.5 * 0.0254)


class TestErrors:
    def test_empty_string(self):
        with pytest.raises(ValueError, match="empty"):
            parse_length("")

    def test_unparseable_garbage(self):
        with pytest.raises(ValueError):
            parse_length("banana")

    def test_unknown_unit(self):
        with pytest.raises(ValueError, match="unknown length unit"):
            parse_length("5 furlongs")

    def test_partial_number(self):
        with pytest.raises(ValueError):
            parse_length("1.2.3 mm")


class TestShorthands:
    def test_meters_shorthand(self):
        assert math.isclose(parse_length_meters(10), 0.010)
        assert math.isclose(parse_length_meters("2 in"), 2 * 0.0254)

    def test_expression_shorthand(self):
        assert parse_length_expression(10) == "10 mm"
        assert parse_length_expression("1.5 in") == "1.5 in"


# --- Angles ---------------------------------------------------------------


class TestAngleBareNumbers:
    def test_int_is_degrees(self):
        a = parse_angle(45)
        assert isinstance(a, Angle)
        assert a.expression == "45 deg"
        assert math.isclose(a.radians, math.pi / 4)

    def test_float_is_degrees(self):
        a = parse_angle(90.0)
        assert a.expression == "90 deg"
        assert math.isclose(a.radians, math.pi / 2)

    def test_zero(self):
        a = parse_angle(0)
        assert a.expression == "0 deg"
        assert a.radians == 0.0

    def test_negative(self):
        a = parse_angle(-30)
        assert a.expression == "-30 deg"
        assert math.isclose(a.radians, -math.pi / 6)

    def test_non_integer(self):
        a = parse_angle(22.5)
        assert a.expression == "22.5 deg"
        assert math.isclose(a.radians, math.radians(22.5))

    def test_bool_rejected(self):
        with pytest.raises(TypeError):
            parse_angle(True)

    def test_list_rejected(self):
        with pytest.raises(TypeError):
            parse_angle([45])


class TestAngleStrings:
    @pytest.mark.parametrize(
        "value,expected_expr,expected_rad",
        [
            ("45 deg", "45 deg", math.pi / 4),
            ("45deg", "45 deg", math.pi / 4),
            ("90 degrees", "90 deg", math.pi / 2),
            ("180 DEG", "180 deg", math.pi),
            ("1.5 rad", "1.5 rad", 1.5),
            ("1.5rad", "1.5 rad", 1.5),
            ("3.14159 radians", "3.14159 rad", 3.14159),
            ("-45 deg", "-45 deg", -math.pi / 4),
        ],
    )
    def test_parses_canonical_round_trip(self, value, expected_expr, expected_rad):
        a = parse_angle(value)
        assert a.expression == expected_expr
        assert math.isclose(a.radians, expected_rad, rel_tol=1e-9)

    def test_string_without_unit_defaults_to_degrees(self):
        # Bare "90" should be DEGREES, never radians, to match the bare-number rule.
        a = parse_angle("90")
        assert a.expression == "90 deg"
        assert math.isclose(a.radians, math.pi / 2)


class TestAngleErrors:
    def test_empty_string(self):
        with pytest.raises(ValueError, match="empty"):
            parse_angle("")

    def test_unparseable_garbage(self):
        with pytest.raises(ValueError):
            parse_angle("banana")

    def test_unknown_unit(self):
        with pytest.raises(ValueError, match="unknown angle unit"):
            parse_angle("5 turns")


class TestAngleShorthand:
    def test_radians_shorthand(self):
        assert math.isclose(parse_angle_radians(180), math.pi)
        assert math.isclose(parse_angle_radians("1.5 rad"), 1.5)
