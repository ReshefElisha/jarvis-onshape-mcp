"""Unit tests for the entity-filter helpers in api/entities.py.

The list_entities API itself is covered end-to-end by tests/real/test_entities_real.py
(live Onshape). These tests pin the predicate helpers so filter behavior can't
silently regress without mocking a full bodydetails response.
"""

from onshape_mcp.api.entities import (
    _classify_face,
    _face_passes_filters,
    _edge_passes_filters,
    _vertex_passes_filters,
    _in_range,
    _parse_fs_frame_map,
)


def _face(
    *,
    face_id="JHW",
    type_="PLANE",
    origin=(0.0, 0.0, 0.010),  # meters
    outward_axis="+Z",
    normal_axis="+Z",
    radius=None,
):
    return {
        "id": face_id,
        "type": type_,
        "origin": list(origin),
        "normal": [0.0, 0.0, 1.0],
        "normal_axis": normal_axis,
        "outward_axis": outward_axis,
        "radius": radius,
    }


def _edge(
    *,
    edge_id="JHE",
    type_="LINE",
    midpoint=(0.005, 0.0, 0.010),
    length=0.010,
    radius=None,
):
    return {
        "id": edge_id,
        "type": type_,
        "midpoint": list(midpoint),
        "length": length,
        "radius": radius,
    }


class TestInRange:
    def test_no_range_means_always_pass(self):
        assert _in_range(None, None) is True
        assert _in_range(5.0, None) is True

    def test_value_none_with_range_fails(self):
        assert _in_range(None, [0, 10]) is False

    def test_inclusive_boundaries(self):
        assert _in_range(0.0, [0, 10]) is True
        assert _in_range(10.0, [0, 10]) is True
        assert _in_range(10.0001, [0, 10]) is False


class TestFaceFilters:
    def test_no_filters_keeps_everything(self):
        assert _face_passes_filters(
            _face(),
            geometry_type=None, outward_axis=None, at_z_mm=None, at_z_tol_mm=0.5,
            radius_range_mm=None,
        )

    def test_geometry_type_case_insensitive_match(self):
        face = _face(type_="PLANE")
        assert _face_passes_filters(
            face, geometry_type="PLANE", outward_axis=None, at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )
        # Different type drops it
        assert not _face_passes_filters(
            face, geometry_type="CYLINDER", outward_axis=None, at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )

    def test_outward_axis_match(self):
        face = _face(outward_axis="+Z")
        assert _face_passes_filters(
            face, geometry_type=None, outward_axis="+Z", at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )
        assert not _face_passes_filters(
            face, geometry_type=None, outward_axis="-Z", at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )

    def test_outward_axis_falls_back_to_normal_axis(self):
        """When FS outward probe missed a face, normal_axis is the fallback."""
        face = _face(outward_axis=None, normal_axis="+Y")
        assert _face_passes_filters(
            face, geometry_type=None, outward_axis="+Y", at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )
        assert not _face_passes_filters(
            face, geometry_type=None, outward_axis="-Y", at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )

    def test_at_z_mm_within_tolerance(self):
        """Face origin z=0.010 m = 10 mm; keep when at_z=10, drop when at_z=12."""
        face = _face(origin=(0, 0, 0.010))
        assert _face_passes_filters(
            face, geometry_type=None, outward_axis=None, at_z_mm=10.0,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )
        assert not _face_passes_filters(
            face, geometry_type=None, outward_axis=None, at_z_mm=12.0,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )

    def test_at_z_mm_with_missing_origin_drops(self):
        face = _face()
        face["origin"] = None
        assert not _face_passes_filters(
            face, geometry_type=None, outward_axis=None, at_z_mm=0.0,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )

    def test_radius_range_keeps_cylinder(self):
        """Face radius 0.005 m = 5 mm."""
        face = _face(type_="CYLINDER", radius=0.005)
        assert _face_passes_filters(
            face, geometry_type=None, outward_axis=None, at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=[4.0, 6.0],
        )
        assert not _face_passes_filters(
            face, geometry_type=None, outward_axis=None, at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=[10.0, 20.0],
        )

    def test_radius_range_drops_plane_without_radius(self):
        face = _face(type_="PLANE", radius=None)
        assert not _face_passes_filters(
            face, geometry_type=None, outward_axis=None, at_z_mm=None,
            at_z_tol_mm=0.5, radius_range_mm=[0.0, 100.0],
        )

    def test_filters_combine(self):
        """All filters must pass for the face to keep."""
        face = _face(type_="PLANE", outward_axis="+Z", origin=(0, 0, 0.006))
        assert _face_passes_filters(
            face, geometry_type="PLANE", outward_axis="+Z", at_z_mm=6.0,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )
        # Flip one: wrong type
        assert not _face_passes_filters(
            face, geometry_type="CYLINDER", outward_axis="+Z", at_z_mm=6.0,
            at_z_tol_mm=0.5, radius_range_mm=None,
        )


class TestEdgeFilters:
    def test_no_filters(self):
        assert _edge_passes_filters(
            _edge(),
            geometry_type=None, at_z_mm=None, at_z_tol_mm=0.5,
            radius_range_mm=None, length_range_mm=None,
        )

    def test_geometry_type_match(self):
        e = _edge(type_="LINE")
        assert _edge_passes_filters(
            e, geometry_type="LINE", at_z_mm=None, at_z_tol_mm=0.5,
            radius_range_mm=None, length_range_mm=None,
        )
        assert not _edge_passes_filters(
            e, geometry_type="CIRCLE", at_z_mm=None, at_z_tol_mm=0.5,
            radius_range_mm=None, length_range_mm=None,
        )

    def test_length_range_mm(self):
        """Edge length 0.010 m = 10 mm."""
        e = _edge(length=0.010)
        assert _edge_passes_filters(
            e, geometry_type=None, at_z_mm=None, at_z_tol_mm=0.5,
            radius_range_mm=None, length_range_mm=[5.0, 20.0],
        )
        assert not _edge_passes_filters(
            e, geometry_type=None, at_z_mm=None, at_z_tol_mm=0.5,
            radius_range_mm=None, length_range_mm=[50.0, 100.0],
        )

    def test_at_z_uses_midpoint(self):
        """Edge midpoint z=0.010 m = 10 mm."""
        e = _edge(midpoint=(0, 0, 0.010))
        assert _edge_passes_filters(
            e, geometry_type=None, at_z_mm=10.0, at_z_tol_mm=0.5,
            radius_range_mm=None, length_range_mm=None,
        )
        assert not _edge_passes_filters(
            e, geometry_type=None, at_z_mm=12.0, at_z_tol_mm=0.5,
            radius_range_mm=None, length_range_mm=None,
        )

    def test_radius_range_for_arc(self):
        e = _edge(type_="ARC", radius=0.003, length=None)
        assert _edge_passes_filters(
            e, geometry_type=None, at_z_mm=None, at_z_tol_mm=0.5,
            radius_range_mm=[2.0, 5.0], length_range_mm=None,
        )


class TestFaceFrames:
    """Verify sketch-axis + outward-normal surfacing from the FS probe."""

    @staticmethod
    def _planar_face(face_id="JHW"):
        """A minimal BTExportModelFace payload for a planar face."""
        return {
            "id": face_id,
            "surface": {
                "type": "plane",
                "origin": {"x": 0.0, "y": 0.0, "z": 0.006},
                "normal": {"x": 0.0, "y": 0.0, "z": 1.0},
            },
        }

    def test_parse_fs_frame_map_unpacks_flat_9_array(self):
        """FS returns each face's frame as a 9-element flat array."""
        # Construct the response shape Onshape actually produces: list of
        # entries with key+value, each value a BTFSValueArray wrapping 9
        # numeric BTFSValueWithUnits entries.
        fs_resp = {
            "result": {
                "value": [
                    {
                        "key": {"value": "JHW"},
                        "value": {
                            "value": [
                                # normal = (0, 0, 1)
                                {"value": 0.0}, {"value": 0.0}, {"value": 1.0},
                                # x = (1, 0, 0)
                                {"value": 1.0}, {"value": 0.0}, {"value": 0.0},
                                # y = (0, 1, 0)
                                {"value": 0.0}, {"value": 1.0}, {"value": 0.0},
                            ]
                        },
                    }
                ],
            }
        }
        frames = _parse_fs_frame_map(fs_resp)
        assert list(frames.keys()) == ["JHW"]
        assert frames["JHW"]["normal"] == [0.0, 0.0, 1.0]
        assert frames["JHW"]["x"] == [1.0, 0.0, 0.0]
        assert frames["JHW"]["y"] == [0.0, 1.0, 0.0]

    def test_parse_fs_frame_map_skips_malformed_entries(self):
        """A bad face (wrong array length) shouldn't block the rest."""
        fs_resp = {
            "result": {
                "value": [
                    # good
                    {
                        "key": {"value": "JA"},
                        "value": {
                            "value": [{"value": float(i)} for i in range(9)]
                        },
                    },
                    # bad: only 6 comps instead of 9
                    {
                        "key": {"value": "JB"},
                        "value": {
                            "value": [{"value": 0.0}] * 6
                        },
                    },
                ],
            }
        }
        frames = _parse_fs_frame_map(fs_resp)
        assert "JA" in frames and "JB" not in frames

    def test_classify_face_surfaces_sketch_axes_on_planar(self):
        """A +Z outward face with world-aligned U/V writes sketch-x/sketch-y labels."""
        face = self._planar_face()
        frames = {
            "JHW": {
                "normal": [0.0, 0.0, 1.0],   # +Z outward
                "x": [1.0, 0.0, 0.0],        # U = world +X
                "y": [0.0, 1.0, 0.0],        # V = world +Y
            }
        }
        classified = _classify_face(face, face_frames=frames)
        assert classified["outward_axis"] == "+Z"
        assert classified["sketch_x_axis"] == "+X"
        assert classified["sketch_y_axis"] == "+Y"
        assert classified["sketch_x_world"] == [1.0, 0.0, 0.0]
        assert classified["sketch_y_world"] == [0.0, 1.0, 0.0]
        # Description carries the sketch-axis hint so Claude can read it.
        assert "sketch-x=+X" in classified["description"]
        assert "sketch-y=+Y" in classified["description"]

    def test_classify_face_vertical_side_face_sketch_axes(self):
        """A face facing world +Y has sketch-x=+X, sketch-y=+Z (typical)."""
        face = {
            "id": "JY1",
            "surface": {
                "type": "plane",
                "origin": {"x": 0.010, "y": 0.030, "z": 0.003},
                "normal": {"x": 0.0, "y": 1.0, "z": 0.0},
            },
        }
        frames = {
            "JY1": {
                "normal": [0.0, 1.0, 0.0],
                "x": [1.0, 0.0, 0.0],
                "y": [0.0, 0.0, 1.0],
            }
        }
        classified = _classify_face(face, face_frames=frames)
        assert classified["outward_axis"] == "+Y"
        assert classified["sketch_x_axis"] == "+X"
        assert classified["sketch_y_axis"] == "+Z"
        assert "sketch-x=+X sketch-y=+Z" in classified["description"]

    def test_classify_face_without_frames_leaves_sketch_axes_none(self):
        """Missing FS frames -> no lying about sketch-axis direction."""
        classified = _classify_face(self._planar_face(), face_frames=None)
        assert classified["sketch_x_axis"] is None
        assert classified["sketch_y_axis"] is None
        assert classified["sketch_x_world"] is None
        assert classified["sketch_y_world"] is None

    def test_classify_cylinder_face_has_no_sketch_axes(self):
        """Non-planar faces never get sketch_x/y surfaced even if FS reports them."""
        cyl = {
            "id": "JCYL",
            "surface": {
                "type": "cylinder",
                "origin": {"x": 0.020, "y": 0.015, "z": 0.006},
                "axis": {"x": 0.0, "y": 0.0, "z": 1.0},
                "radius": 0.005,
            },
        }
        # FS might still return a frame for a cylinder (tangent-plane at
        # parameter (0.5, 0.5)); we suppress it since the notion doesn't
        # make sense for a curved face.
        frames = {
            "JCYL": {
                "normal": [1.0, 0.0, 0.0],
                "x": [0.0, 1.0, 0.0],
                "y": [0.0, 0.0, 1.0],
            }
        }
        classified = _classify_face(cyl, face_frames=frames)
        assert classified["sketch_x_world"] is None
        assert classified["sketch_y_world"] is None
        # But outward_normal still bubbles up.
        assert classified["outward_normal"] == [1.0, 0.0, 0.0]

    def test_classify_face_off_axis_sketch_frame_not_labeled(self):
        """If sketch x/y land 45° off an axis, the label is None — don't fake it."""
        face = self._planar_face()
        # A plane tilted 30° about Z: its U/V are 30° from world X/Y.
        import math
        c, s = math.cos(math.radians(30)), math.sin(math.radians(30))
        frames = {
            "JHW": {
                "normal": [0.0, 0.0, 1.0],
                "x": [c, s, 0.0],     # 30° off +X
                "y": [-s, c, 0.0],    # 30° off +Y
            }
        }
        classified = _classify_face(face, face_frames=frames)
        assert classified["sketch_x_axis"] is None
        assert classified["sketch_y_axis"] is None
        # Raw vectors are still carried so a caller doing vector math gets them.
        assert classified["sketch_x_world"] == [c, s, 0.0]
        # Description doesn't include a sketch-x line (can't label cleanly).
        assert "sketch-x=" not in classified["description"]


class TestVertexFilters:
    def test_no_filters(self):
        assert _vertex_passes_filters(
            {"id": "V", "point": [0, 0, 0.010]},
            at_z_mm=None, at_z_tol_mm=0.5,
        )

    def test_at_z(self):
        v = {"id": "V", "point": [0, 0, 0.010]}
        assert _vertex_passes_filters(v, at_z_mm=10.0, at_z_tol_mm=0.5)
        assert not _vertex_passes_filters(v, at_z_mm=15.0, at_z_tol_mm=0.5)

    def test_at_z_missing_point(self):
        v = {"id": "V", "point": None}
        assert not _vertex_passes_filters(v, at_z_mm=0.0, at_z_tol_mm=0.5)
