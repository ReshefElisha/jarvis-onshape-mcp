# Next Steps: Implementing Geometry-Referenced Sketches

## Overview

This document outlines the concrete steps needed to implement the ability to create sketches on faces/edges from existing features, enabling carpentry-correct cabinet modeling.

## Current Status

### ✅ What Works
- Creating sketches on standard planes (Front, Top, Right)
- Linking dimensions to variables
- Creating extrudes with variable depth
- Proper BTMSketch-151 format with constraints

### ❌ What Doesn't Work Yet
- Creating sketches on faces created by other features
- Referencing specific edges from existing sketches
- Generating qCompressed query strings
- Tracking geometry through feature operations

## Research Tasks

### Task 1: Find Onshape's Query Evaluation API

**Goal**: Discover if Onshape provides an API endpoint that can generate query strings for us.

**Potential Endpoints to Test**:
1. `/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/evaluatequery`
2. `/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/querygeometry`
3. `/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/bodydetails`
4. `/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/namedviews`

**Test Approach**:
```python
# Try querying for a specific face
response = await client.post(
    f"/api/v9/partstudios/d/{doc_id}/w/{ws_id}/e/{elem_id}/evaluatequery",
    data={
        "query": {
            "featureId": "FWXtkjgpR9vOAbK_0",  # back panel sketch
            "entityType": "EDGE",
            "entityId": "right"
        }
    }
)
```

**Expected Result**: API returns query string and/or deterministic ID

**Action Items**:
- [ ] Search Onshape API documentation for query-related endpoints
- [ ] Use Context7 to search `/websites/onshape-public_github_io` for "query" endpoints
- [ ] Test endpoints with display cabinet project
- [ ] Document findings

### Task 2: Understand Entity ID Mapping

**Goal**: Figure out how our entity IDs (`rect.1.right`) map to Onshape's internal IDs (`AjpZLHQCiR3Iright`).

**Test Approach**:
```python
# Create a simple sketch
sketch = create_sketch_rectangle(...)

# Immediately query it back
features = await get_features(...)

# Find our sketch and examine entity IDs
for feature in features:
    if feature['featureId'] == sketch.featureId:
        for entity in feature['entities']:
            print(f"Our ID: {entity['entityId']}")
            print(f"Onshape ID: {entity.get('nodeId')}")
```

**Questions to Answer**:
1. Is there a consistent transformation pattern?
2. Does Onshape generate IDs from our IDs or independently?
3. Can we predict Onshape's IDs?
4. Do we need to query back to get the real IDs?

**Action Items**:
- [ ] Create test sketch with known entity IDs
- [ ] Query back the sketch definition
- [ ] Compare our IDs vs Onshape's IDs
- [ ] Look for transformation patterns
- [ ] Document the mapping logic

### Task 3: Test FeatureScript Query Construction

**Goal**: Determine if we can use FeatureScript queries via the `/featurescript` endpoint.

**Test Approach**:
```python
# Try using FeatureScript to query for an edge
script = """
function(context is Context, queries is map) {
    var backPanelId = makeId("FWXtkjgpR9vOAbK_0");
    var rightEdge = qCreatedBy(backPanelId, EntityType.EDGE);
    return evaluateQuery(context, rightEdge);
}
"""

response = await client.post(
    f"/api/v9/partstudios/d/{doc_id}/w/{ws_id}/e/{elem_id}/featurescript",
    data={
        "script": script,
        "queries": {}
    }
)
```

**Expected Result**: Returns information about the edge entities

**Action Items**:
- [ ] Review FeatureScript query functions documentation
- [ ] Test basic queries via `/featurescript` endpoint
- [ ] Try filtering for specific entity types
- [ ] See if results include query strings or IDs we can use
- [ ] Document FeatureScript approach

### Task 4: Analyze More Examples

**Goal**: Create additional manual examples to find patterns in query strings.

**Examples to Create**:
1. Sketch on extruded face (simple extrude, no thicken)
2. Sketch on specific face of a box (top vs side)
3. Sketch on curved surface (cylinder face)
4. Sketch on face from boolean operation

**For Each Example**:
```python
# 1. Create feature manually in Onshape
# 2. Create sketch on geometry manually
# 3. Query back the sketch definition
# 4. Extract and analyze the query string
# 5. Compare with other examples
```

**Action Items**:
- [ ] Create test document with various geometry types
- [ ] Manually create sketches on each type
- [ ] Extract and document each query string
- [ ] Look for common patterns
- [ ] Identify variables vs constants in query strings

## Implementation Tasks

### Task 5: Create Query String Builder (If Needed)

**Goal**: If we can't use Onshape's API to generate queries, build our own.

**Approach**:
```python
class GeometryQueryBuilder:
    """Builds Onshape query strings for referencing geometry."""

    def __init__(self):
        self.query_parts = []

    def reference_sketch_edge(
        self,
        feature_id: str,
        entity_id: str
    ) -> 'GeometryQueryBuilder':
        """Add reference to a sketch edge."""
        # Build the SKETCH_ENTITY part of query
        pass

    def after_operation(
        self,
        operation_type: str,  # "extrude", "thicken", etc.
        operation_id: str
    ) -> 'GeometryQueryBuilder':
        """Add reference to operation result."""
        # Build the operation part of query
        pass

    def build(self) -> str:
        """Generate the final qCompressed query string."""
        # Assemble all parts into proper format
        pass
```

**Action Items**:
- [ ] Only if API approach fails
- [ ] Study query string structure in detail
- [ ] Implement builder for common patterns
- [ ] Test against known working examples
- [ ] Document limitations

### Task 6: Implement High-Level API Method

**Goal**: Create `create_sketch_on_geometry()` method in PartStudioManager.

**Proposed Signature**:
```python
async def create_sketch_on_geometry(
    self,
    document_id: str,
    workspace_id: str,
    element_id: str,
    name: str,
    source_feature_id: str,
    source_entity: str,  # "left", "right", "top", "bottom"
    sketch_definition: Dict[str, Any],  # From SketchBuilder
    after_operation: Optional[str] = None  # "extrude", "thicken", etc.
) -> Dict[str, Any]:
    """Create a sketch on a face/edge from an existing feature."""
```

**Implementation Steps**:
1. Query Onshape to find the target face
2. Get deterministic ID for the face
3. Generate query string (via API or builder)
4. Modify sketch_definition to use geometry reference
5. Create the sketch feature
6. Return result

**Action Items**:
- [ ] Define method signature
- [ ] Implement face/edge resolution
- [ ] Integrate with SketchBuilder
- [ ] Add error handling
- [ ] Write unit tests
- [ ] Document usage

### Task 7: Update SketchBuilder

**Goal**: Modify SketchBuilder to support geometry-referenced planes.

**Changes Needed**:
```python
class SketchBuilder:
    def __init__(
        self,
        name: str = "Sketch",
        plane: Optional[SketchPlane] = None,  # Now optional
        plane_id: Optional[str] = None,
        geometry_reference: Optional[Dict[str, Any]] = None  # NEW
    ):
        """Initialize sketch builder.

        Args:
            plane: Standard plane (for simple cases)
            plane_id: Deterministic ID for standard plane
            geometry_reference: Complex reference with query string
        """
```

**Action Items**:
- [ ] Add geometry_reference support
- [ ] Update build() method to handle complex queries
- [ ] Maintain backward compatibility
- [ ] Add validation
- [ ] Update tests

### Task 8: Add MCP Tool

**Goal**: Expose geometry-referenced sketches via MCP.

**New Tool**:
```json
{
  "name": "create_sketch_on_face",
  "description": "Create a rectangular sketch on a face from an existing feature",
  "inputSchema": {
    "type": "object",
    "properties": {
      "documentId": {"type": "string"},
      "workspaceId": {"type": "string"},
      "elementId": {"type": "string"},
      "name": {"type": "string"},
      "sourceFeatureId": {
        "type": "string",
        "description": "Feature ID containing the target face/edge"
      },
      "sourceEntity": {
        "type": "string",
        "description": "Which entity (left, right, top, bottom, front, back)"
      },
      "corner1": {"type": "array"},
      "corner2": {"type": "array"},
      "variableWidth": {"type": "string"},
      "variableHeight": {"type": "string"}
    },
    "required": ["documentId", "workspaceId", "elementId", "sourceFeatureId", "sourceEntity", "corner1", "corner2"]
  }
}
```

**Action Items**:
- [ ] Define MCP tool schema
- [ ] Implement handler in server.py
- [ ] Add error handling and validation
- [ ] Write integration tests
- [ ] Update QUICK_START.md with examples
- [ ] Document in DOCUMENT_DISCOVERY.md

## Testing Plan

### Unit Tests

**Test Coverage Needed**:
1. Query string construction (if building manually)
2. Entity ID mapping
3. SketchBuilder with geometry references
4. PartStudioManager.create_sketch_on_geometry()
5. MCP tool handler

**Test Files**:
- `tests/api/test_partstudio.py` - Add geometry reference tests
- `tests/builders/test_sketch.py` - Add geometry reference tests
- `tests/integration/test_cabinet_assembly.py` - NEW (end-to-end test)

### Integration Tests

**Scenario 1: Simple Side Panel**
```python
async def test_side_panel_on_back_edge():
    # Create back panel
    back = await create_sketch_rectangle(plane="Front", ...)
    back_extrude = await create_extrude(back.id, ...)

    # Create side panel on back's edge
    side = await create_sketch_on_geometry(
        source_feature_id=back.id,
        source_entity="right",
        ...
    )

    # Verify sketch was created
    # Verify it references the correct face
```

**Scenario 2: Full Cabinet**
```python
async def test_complete_cabinet_assembly():
    # Build entire cabinet using geometry references
    # Verify all panels are properly positioned
    # Verify parametric relationships work
```

### Manual Testing

**Test Cases**:
1. Create side panel on back panel edge
2. Modify back panel width → verify side panel updates
3. Change wall thickness → verify all panels adjust
4. Add shelf using same technique

## Success Criteria

### Minimum Viable Implementation
- [ ] Can create sketch on face from extruded edge
- [ ] Works for simple cabinet side panel case
- [ ] Parametric relationships maintained
- [ ] Basic error handling

### Full Implementation
- [ ] Works for all edge/face combinations
- [ ] Handles complex operation chains (extrude + thicken + boolean)
- [ ] Comprehensive error handling
- [ ] Full test coverage
- [ ] Complete documentation

### Production Ready
- [ ] Tested with multiple real projects
- [ ] Performance optimized
- [ ] User-friendly error messages
- [ ] Examples and tutorials
- [ ] CI/CD integration

## Timeline Estimate

**Phase 1: Research** (1-2 weeks)
- Tasks 1-4: API research, pattern finding

**Phase 2: Proof of Concept** (1 week)
- Task 6: Basic implementation for one use case

**Phase 3: Full Implementation** (2-3 weeks)
- Tasks 5-8: Complete feature set

**Phase 4: Testing & Documentation** (1 week)
- All testing and documentation tasks

**Total Estimate**: 5-7 weeks for production-ready feature

## Resources Needed

### Documentation
- Onshape API reference for query endpoints
- FeatureScript documentation for query functions
- Existing examples from community

### Tools
- Test Onshape document with various geometry
- API testing tools (curl, Postman, or Python scripts)
- Debugger for analyzing query strings

### Knowledge
- Onshape's query language syntax
- FeatureScript basics (if using that approach)
- CAD modeling principles (carpentry knowledge)

## Risk Mitigation

### Risk 1: No Public Query API
**Mitigation**: Build query strings manually using discovered patterns

### Risk 2: Query Format Too Complex
**Mitigation**: Start with simple cases (extrude only), expand gradually

### Risk 3: Deterministic IDs Not Predictable
**Mitigation**: Query back after creation to get actual IDs

### Risk 4: Performance Issues
**Mitigation**: Implement caching, batch operations where possible

## Conclusion

Implementing geometry-referenced sketches is a multi-phase project requiring:
1. Thorough API research
2. Pattern discovery through examples
3. Careful implementation with good abstractions
4. Comprehensive testing

The payoff is enabling truly carpentry-correct CAD models where assembly relationships are built into the parametric structure.

---

**Status**: Research phase - Tasks 1-4 should be tackled first
**Priority**: High - This is the key missing feature for real woodworking projects
**Complexity**: Medium-High - Depends on API availability

**Next Immediate Action**: Start with Task 1 (Find Onshape's Query Evaluation API)
