# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
