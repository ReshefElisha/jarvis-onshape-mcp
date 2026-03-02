"""Unit tests for face coordinate system query."""

import pytest
from unittest.mock import AsyncMock

from onshape_mcp.analysis.face_cs import (
    extract_mc_coordinate_system,
    query_face_coordinate_system,
)


class TestExtractMCCoordinateSystem:
    """Test the extract_mc_coordinate_system function."""

    def test_extracts_from_direct_matedCS(self):
        assembly_data = {
            "rootAssembly": {
                "features": [
                    {
                        "featureId": "mc123",
                        "matedCS": {
                            "origin": [0.0254, 0.0508, 0.0762],
                            "xAxis": [1, 0, 0],
                            "yAxis": [0, 1, 0],
                            "zAxis": [0, 0, 1],
                        },
                    }
                ]
            }
        }
        cs = extract_mc_coordinate_system(assembly_data, "mc123")
        assert cs is not None
        assert cs.z_axis == (0.0, 0.0, 1.0)
        assert cs.x_axis == (1.0, 0.0, 0.0)
        assert cs.y_axis == (0.0, 1.0, 0.0)
        assert abs(cs.origin_inches[0] - 1.0) < 1e-6
        assert abs(cs.origin_inches[1] - 2.0) < 1e-6
        assert abs(cs.origin_inches[2] - 3.0) < 1e-6
        assert cs.origin_meters == (0.0254, 0.0508, 0.0762)

    def test_extracts_from_featureData_matedCS(self):
        assembly_data = {
            "rootAssembly": {
                "features": [
                    {
                        "featureId": "mc456",
                        "featureData": {
                            "matedCS": {
                                "origin": [0.1, 0.2, 0.3],
                                "xAxis": [0, 1, 0],
                                "yAxis": [0, 0, 1],
                                "zAxis": [1, 0, 0],
                            }
                        },
                    }
                ]
            }
        }
        cs = extract_mc_coordinate_system(assembly_data, "mc456")
        assert cs is not None
        assert cs.z_axis == (1.0, 0.0, 0.0)

    def test_extracts_from_featureData_mateConnectorCS(self):
        """Assembly definition uses mateConnectorCS instead of matedCS."""
        assembly_data = {
            "rootAssembly": {
                "features": [
                    {
                        "id": "mc_live",
                        "featureData": {
                            "mateConnectorCS": {
                                "origin": [0.009525, 0.0, 0.381],
                                "xAxis": [1, 0, 0],
                                "yAxis": [0, 0, -1],
                                "zAxis": [0, 1, 0],
                            }
                        },
                    }
                ]
            }
        }
        cs = extract_mc_coordinate_system(assembly_data, "mc_live")
        assert cs is not None
        assert cs.z_axis == (0.0, 1.0, 0.0)
        assert abs(cs.origin_inches[2] - 15.0) < 0.01

    def test_extracts_from_mateConnectors_list(self):
        assembly_data = {
            "rootAssembly": {
                "features": [],
                "mateConnectors": [
                    {
                        "featureId": "mc789",
                        "matedCS": {
                            "origin": [0.0, 0.0, 0.0],
                            "xAxis": [1, 0, 0],
                            "yAxis": [0, 0, -1],
                            "zAxis": [0, 1, 0],
                        },
                    }
                ],
            }
        }
        cs = extract_mc_coordinate_system(assembly_data, "mc789")
        assert cs is not None
        assert cs.z_axis == (0.0, 1.0, 0.0)

    def test_returns_none_for_missing_feature(self):
        assembly_data = {"rootAssembly": {"features": []}}
        cs = extract_mc_coordinate_system(assembly_data, "nonexistent")
        assert cs is None

    def test_returns_none_for_empty_assembly(self):
        assembly_data = {"rootAssembly": {}}
        cs = extract_mc_coordinate_system(assembly_data, "anything")
        assert cs is None

    def test_returns_none_when_feature_has_no_matedCS(self):
        assembly_data = {
            "rootAssembly": {
                "features": [
                    {"featureId": "mc_no_cs", "name": "test"}
                ]
            }
        }
        cs = extract_mc_coordinate_system(assembly_data, "mc_no_cs")
        assert cs is None

    def test_matches_by_id_field(self):
        """Some API responses use 'id' instead of 'featureId'."""
        assembly_data = {
            "rootAssembly": {
                "features": [
                    {
                        "id": "mc_alt",
                        "matedCS": {
                            "origin": [0, 0, 0],
                            "xAxis": [1, 0, 0],
                            "yAxis": [0, 1, 0],
                            "zAxis": [0, 0, 1],
                        },
                    }
                ]
            }
        }
        cs = extract_mc_coordinate_system(assembly_data, "mc_alt")
        assert cs is not None

    def test_skips_non_matching_features(self):
        assembly_data = {
            "rootAssembly": {
                "features": [
                    {
                        "featureId": "other_mc",
                        "matedCS": {
                            "origin": [0, 0, 0],
                            "xAxis": [1, 0, 0],
                            "yAxis": [0, 1, 0],
                            "zAxis": [0, 0, -1],
                        },
                    },
                    {
                        "featureId": "target_mc",
                        "matedCS": {
                            "origin": [0, 0, 0],
                            "xAxis": [1, 0, 0],
                            "yAxis": [0, 1, 0],
                            "zAxis": [0, 0, 1],
                        },
                    },
                ]
            }
        }
        cs = extract_mc_coordinate_system(assembly_data, "target_mc")
        assert cs is not None
        assert cs.z_axis == (0.0, 0.0, 1.0)


class TestQueryFaceCoordinateSystem:
    """Test the async query_face_coordinate_system function."""

    @pytest.mark.asyncio
    async def test_creates_reads_deletes(self):
        manager = AsyncMock()
        manager.add_feature.return_value = {
            "feature": {"featureId": "temp_mc_id"}
        }
        manager.get_assembly_definition.return_value = {
            "rootAssembly": {
                "features": [
                    {
                        "featureId": "temp_mc_id",
                        "matedCS": {
                            "origin": [0.0254, 0.0, 0.0],
                            "xAxis": [1, 0, 0],
                            "yAxis": [0, 1, 0],
                            "zAxis": [0, 0, 1],
                        },
                    }
                ]
            }
        }
        manager.delete_feature.return_value = {}

        cs = await query_face_coordinate_system(
            assembly_manager=manager,
            document_id="doc1",
            workspace_id="ws1",
            element_id="elem1",
            instance_id="inst1",
            face_id="JHG",
        )

        assert cs.z_axis == (0.0, 0.0, 1.0)
        assert abs(cs.origin_inches[0] - 1.0) < 1e-6

        # Verify all 3 API calls were made
        manager.add_feature.assert_called_once()
        manager.get_assembly_definition.assert_called_once()
        manager.delete_feature.assert_called_once_with("doc1", "ws1", "elem1", "temp_mc_id")

    @pytest.mark.asyncio
    async def test_passes_correct_params_to_get_assembly(self):
        manager = AsyncMock()
        manager.add_feature.return_value = {
            "feature": {"featureId": "temp_id"}
        }
        manager.get_assembly_definition.return_value = {
            "rootAssembly": {
                "features": [
                    {
                        "featureId": "temp_id",
                        "matedCS": {
                            "origin": [0, 0, 0],
                            "xAxis": [1, 0, 0],
                            "yAxis": [0, 1, 0],
                            "zAxis": [0, 0, 1],
                        },
                    }
                ]
            }
        }
        manager.delete_feature.return_value = {}

        await query_face_coordinate_system(
            manager, "d", "w", "e", "i", "face"
        )

        call_args = manager.get_assembly_definition.call_args
        assert call_args[1]["params"]["includeMateFeatures"] is True
        assert call_args[1]["params"]["includeMateConnectors"] is True

    @pytest.mark.asyncio
    async def test_cleanup_on_extraction_failure(self):
        manager = AsyncMock()
        manager.add_feature.return_value = {
            "feature": {"featureId": "temp_mc"}
        }
        # Return data that doesn't contain the MC's coordinate system
        manager.get_assembly_definition.return_value = {
            "rootAssembly": {"features": []}
        }
        manager.delete_feature.return_value = {}

        with pytest.raises(RuntimeError, match="Could not find resolved coordinate system"):
            await query_face_coordinate_system(
                manager, "d", "w", "e", "i", "face"
            )

        # Verify cleanup still happened
        manager.delete_feature.assert_called_once_with("d", "w", "e", "temp_mc")

    @pytest.mark.asyncio
    async def test_cleanup_on_api_error(self):
        manager = AsyncMock()
        manager.add_feature.return_value = {
            "feature": {"featureId": "temp_mc"}
        }
        manager.get_assembly_definition.side_effect = Exception("API error")
        manager.delete_feature.return_value = {}

        with pytest.raises(Exception, match="API error"):
            await query_face_coordinate_system(
                manager, "d", "w", "e", "i", "face"
            )

        # Verify cleanup still happened despite the error
        manager.delete_feature.assert_called_once_with("d", "w", "e", "temp_mc")

    @pytest.mark.asyncio
    async def test_raises_when_add_feature_returns_no_id(self):
        manager = AsyncMock()
        manager.add_feature.return_value = {"feature": {}}

        with pytest.raises(RuntimeError, match="Failed to create temporary mate connector"):
            await query_face_coordinate_system(
                manager, "d", "w", "e", "i", "face"
            )

    @pytest.mark.asyncio
    async def test_delete_failure_is_logged_not_raised(self):
        manager = AsyncMock()
        manager.add_feature.return_value = {
            "feature": {"featureId": "temp_mc"}
        }
        manager.get_assembly_definition.return_value = {
            "rootAssembly": {
                "features": [
                    {
                        "featureId": "temp_mc",
                        "matedCS": {
                            "origin": [0, 0, 0],
                            "xAxis": [1, 0, 0],
                            "yAxis": [0, 1, 0],
                            "zAxis": [0, 0, 1],
                        },
                    }
                ]
            }
        }
        manager.delete_feature.side_effect = Exception("Delete failed")

        # Should NOT raise - delete failure is logged as warning
        cs = await query_face_coordinate_system(
            manager, "d", "w", "e", "i", "face"
        )
        assert cs is not None
        assert cs.z_axis == (0.0, 0.0, 1.0)
