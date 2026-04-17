# Onshape MCP Server

## Project Conventions

- **PRs target `develop`**, never `main`. `main` is only for releases.
- Tests: `pytest` (all tests must pass). Coverage: `pytest --cov`.
- Style: `ruff check` and `ruff format --check`.

## Assembly Workflow (5-Step Methodology)

When building assemblies, follow this order:

1. **Ground a reference part** — First instance is grounded by default. All positions are relative to this part.
2. **Get face IDs** — Use `get_body_details` on the Part Studio. Face IDs are reusable across all instances of the same part.
3. **Create mates in batches** — Do 3-5 at a time, verify between batches with `get_assembly_features` (all OK?) and `get_assembly_positions` (positions correct?).
4. **Verify positions relative to the reference part** — Always compute `instance_pos - reference_pos` since the reference may not be at origin.
5. **Test motion mates** — Create slider/revolute mates without limits first. Verify direction and animation before adding limits.

See `knowledge_base/assembly_workflow_guide.md` for the full guide and `examples/cabinet_assembly.md` for a worked example.

## Critical Assembly Gotchas

- **Instance order = direction**: For slider/revolute/cylindrical mates, the first instance moves relative to the second. Swap the order to reverse the direction.
- **Limits can break the solver**: API-set limits trigger a full re-solve that may flip parts. Create mates without limits first, add limits in the Onshape UI.
- **Fixed instances can't be moved**: `transform_instance` and `set_instance_position` fail on grounded parts (API 400 error).
- **Absolute positions need reference offset**: If the reference part is at (100, 200, 300), a part at relative (5, 10, 0) needs absolute (105, 210, 300).
- **MC offsets are in local coords**: Flipping the Z-axis changes all axes (right-hand rule), which changes how X/Y offsets map to world space.

## Key File Paths

- `onshape_mcp/server.py` — MCP server with all tool definitions
- `onshape_mcp/builders/mate.py` — MateConnectorBuilder, MateBuilder
- `onshape_mcp/api/assemblies.py` — Assembly API operations
- `knowledge_base/assembly_workflow_guide.md` — Full assembly methodology
- `knowledge_base/cad/cad_best_practices.md` — CAD design principles
- `examples/cabinet_assembly.md` — Complete cabinet assembly walkthrough
