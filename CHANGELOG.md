# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Assembly management tools: `create_assembly`, `add_assembly_instance`, `transform_instance`, `create_fastened_mate`, `create_revolute_mate`
- Expanded sketch geometry tools: `create_sketch_circle`, `create_sketch_line`, `create_sketch_arc`
- Part Studio feature tools: `create_fillet`, `create_chamfer`, `create_revolve`, `create_linear_pattern`, `create_circular_pattern`, `create_boolean`
- FeatureScript tools: `eval_featurescript`, `get_bounding_box`
- Export tools: `export_part_studio`, `export_assembly`
- API modules: `AssemblyManager`, `ExportManager`, `FeatureScriptManager`
- Builders: `BooleanBuilder`, `ChamferBuilder`, `FilletBuilder`, `MateConnectorBuilder`, `MateBuilder`, `LinearPatternBuilder`, `CircularPatternBuilder`, `RevolveBuilder`
- Knowledge base example: parametric bracket walkthrough

## [0.1.0] - 2025-02-20

### Added
- Onshape API client with OAuth and API key authentication
- Document management tools: `list_documents`, `get_document`, `create_document`
- Part Studio tools: `list_part_studios`, `create_part_studio`, `get_features`, `add_feature`
- Assembly tools: `list_assemblies`, `get_assembly_definition`, `add_assembly_instance`, `add_mate_connector`, `add_assembly_mate`
- Auto-load `.env` from package directory
- CI pipeline with multi-OS/Python matrix testing
- 80%+ test coverage requirement

[Unreleased]: https://github.com/hedless/onshape-mcp/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/hedless/onshape-mcp/releases/tag/v0.1.0
