# Sketch Plane Reference Guide

## Understanding Onshape Sketch Planes: Standard vs. Referenced Geometry

This guide documents how to programmatically create sketches on existing geometry (edges, faces) instead of just standard planes (Front, Top, Right).

## Background: The Cabinet Side Panel Example

### The Carpentry Principle

When building a cabinet, the side panels are typically attached to the **edge of the back panel**, not to a standard plane. This creates proper assembly relationships:

- **Traditional approach**: Sides butt against back panel edges
- **Alternative approach**: Back panel fits into dado grooves in sides
- **Key insight**: The side panel's sketch plane is the **face created by the back panel's edge**

### What Changed in the Side Panel

**Original (Standard Plane)**:
- Sketch plane: Standard "Right" plane (deterministic ID: `JEC`)
- Reference type: `BTMIndividualQuery-138` with only `deterministicIds`
- Simple reference to one of the three standard planes

**Modified (Geometry Reference)**:
- Sketch plane: Face created from back panel's right edge (deterministic ID: `JHO`)
- Reference type: `BTMIndividualQuery-138` with complex `queryString`
- References specific geometry from existing feature

## Technical Breakdown: The Query Format

### The Modified Side Panel Sketch Plane Parameter

```json
{
  "btType": "BTMParameterQueryList-148",
  "queries": [
    {
      "btType": "BTMIndividualQuery-138",
      "queryStatement": null,
      "queryString": "query=qCompressed(1.0,\"%B5$QueryM5S12$disambiguationDataA1M2S12$disambiguationTypeS13$ORIGINAL_DEPENDENCYS9$originalsA1C0M5Sa$entityTypeBa$EntityTypeS4$EDGESb$historyTypeS8$CREATIONSb$operationIdB2$IdA1S11.6$FWXtkjgpR9vOAbK_0wireOpS9$queryTypeSd$SKETCH_ENTITYS e$sketchEntityIdSc.5$AjpZLHQCiR3IrightR4C6S4$FACER6R7R8CbA1S11.9$FVsfqYeclVHClNI_0opThickenRbSa$SWEPT_FACE\",id);",
      "nodeId": "FJzQums7VKAJqNu",
      "deterministicIds": [
        "JHO"
      ]
    }
  ],
  "filter": {
    "btType": "BTOrFilter-167",
    "operand1": {
      "btType": "BTOrFilter-167",
      "operand1": {
        "btType": "BTAndFilter-110",
        "operand1": {
          "btType": "BTGeometryFilter-130",
          "geometryType": "PLANE"
        },
        "operand2": {
          "btType": "BTFlatSheetMetalFilter-3018",
          "allows": "MODEL_ONLY"
        }
      },
      "operand2": {
        "btType": "BTAndFilter-110",
        "operand1": {
          "btType": "BTAndFilter-110",
          "operand1": {
            "btType": "BTSMDefinitionEntityTypeFilter-1651",
            "smDefinitionEntityType": "FACE"
          },
          "operand2": {
            "btType": "BTFlatSheetMetalFilter-3018",
            "allows": "MODEL_AND_FLATTENED"
          }
        },
        "operand2": {
          "btType": "BTGeometryFilter-130",
          "geometryType": "PLANE"
        }
      }
    },
    "operand2": {
      "btType": "BTBodyTypeFilter-112",
      "bodyType": "MATE_CONNECTOR"
    }
  },
  "parameterId": "sketchPlane",
  "parameterName": "",
  "libraryRelationType": "NONE"
}
```

### Decoding the qCompressed Query String

The `queryString` contains a compressed query format that references the geometry. Let me break down what this query is saying:

**Key Components:**

1. **Disambiguation Data**:
   - Type: `ORIGINAL_DEPENDENCY`
   - Ensures we're referencing the original geometry

2. **Entity Type**: `EDGES`
   - We're referencing edge entities from a sketch

3. **History Type**: `CREATION`
   - We want the edge as it was created

4. **Operation ID**: `FWXtkjgpR9vOAbK_0` (with `wireOp`)
   - This is the **back panel sketch feature ID**
   - The `wireOp` suffix indicates we're looking at the wire (edge) operations

5. **Query Type**: `SKETCH_ENTITY`
   - We're referencing a specific sketch entity

6. **Sketch Entity ID**: `AjpZLHQCiR3Iright`
   - This is the **right edge of the back panel rectangle**
   - Corresponds to `rect.1.right` entity ID from our SketchBuilder

7. **Face from Thicken Operation**:
   - After the initial edge reference, there's a second part
   - Entity Type: `FACE`
   - Operation ID: `FVsfqYeclVHClNI_0opThicken`
   - Query Type: `SWEPT_FACE`
   - This references the **face created when the edge was extruded/thickened**

8. **Deterministic ID**: `JHO`
   - The final resolved ID for this specific face
   - Different from standard plane IDs (JCC, JDC, JEC)

### The Reference Chain

```
Back Panel Sketch (FWXtkjgpR9vOAbK_0)
  → Right edge entity (AjpZLHQCiR3Iright)
    → Thicken operation (FVsfqYeclVHClNI_0opThicken)
      → Swept face created from edge
        → Final deterministic ID: JHO
```

## Implementation Implications

### What We Learned

1. **Complex Geometry References Require Query Strings**
   - Standard planes: Just use `deterministicIds: ["JCC"]`
   - Geometry references: Need full `queryString` with qCompressed format

2. **Entity IDs Are Important**
   - Our SketchBuilder generates entity IDs like `rect.1.right`
   - These become `AjpZLHQCiR3Iright` in the actual sketch
   - We need to know the actual entity ID format Onshape uses

3. **Feature IDs Are Required**
   - To reference geometry, we need the feature ID of the source feature
   - Example: Back panel sketch is `FWXtkjgpR9vOAbK_0`

4. **Operation Tracking**
   - When geometry is transformed (extruded, thickened, etc.)
   - We need to reference the resulting face, not the original edge
   - This requires knowing the operation ID

### Challenges for Programmatic Implementation

1. **Entity ID Translation**
   - Our builder uses: `rect.1.right`
   - Onshape uses: `AjpZLHQCiR3Iright`
   - **Problem**: How do we map between these?

2. **Query String Construction**
   - The qCompressed format is complex and likely uses Onshape's internal serialization
   - **Problem**: Can we construct this programmatically, or must we use Onshape's API?

3. **Operation Chain Tracking**
   - When sketch → extrude → thicken, face IDs change
   - **Problem**: How do we track which face to use?

4. **Deterministic ID Discovery**
   - The final ID `JHO` isn't predictable
   - **Problem**: How do we discover this ID programmatically?

## Potential Approaches

### Approach 1: Use Onshape's Evaluation API

Onshape likely has an API endpoint that can:
1. Take a source feature ID and entity ID
2. Evaluate what face/edge it becomes after operations
3. Return the proper query string and deterministic ID

**Pros**: Correct, maintained by Onshape
**Cons**: Need to find and understand this API

### Approach 2: FeatureScript Query Functions

FeatureScript has query functions like:
- `qCreatedBy(featureId, EntityType.EDGE)`
- `qSketchRegion(sketchId)`
- `qEntityFilter(query, EntityType.FACE)`

These might be usable via the `/featurescript` endpoint.

**Pros**: Leverages Onshape's query system
**Cons**: Requires FeatureScript knowledge

### Approach 3: Manual Entity Tracking

Track our own mapping:
1. When creating a sketch, store entity IDs
2. When creating extrude/thicken, request resulting faces
3. Build the query string manually

**Pros**: Full control
**Cons**: Complex, fragile, may not match Onshape's format

### Approach 4: Two-Step Creation

1. Create sketch on standard plane first
2. Use Onshape UI to manually reattach to geometry
3. Read back the result to learn the pattern

**Pros**: Guarantees correct format
**Cons**: Not fully programmatic

## Recommended Next Steps

### 1. Research Onshape's Evaluation API

Look for endpoints like:
- `/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/evaluatequery`
- `/api/v9/partstudios/d/{did}/w/{wid}/e/{eid}/querybyface`

These might allow us to:
- Specify a feature ID and entity type
- Get back the proper query string

### 2. Test FeatureScript Queries

Try using the `/featurescript` endpoint with queries like:
```javascript
qCreatedBy(makeId("FWXtkjgpR9vOAbK_0"), EntityType.EDGE)
```

See if this returns entity information we can use.

### 3. Examine Entity ID Mapping

Create a test sketch and immediately query it back to see:
- How entity IDs are transformed
- Whether there's a consistent mapping pattern
- If we can predict the transformation

### 4. Study More Examples

Create several manual examples of:
- Sketch on extruded face
- Sketch on edge face
- Sketch on swept face

Compare their query strings to find patterns.

## Carpentry Workflow: Side Panel Attachment

### The Ideal Workflow for Cabinet Assembly

1. **Create Back Panel**
   - Sketch on Front plane
   - Define rectangle with variables
   - Extrude/thicken to create panel

2. **Create Side Panel (Ideal Approach)**
   - Identify back panel's right edge
   - Find the face created from that edge after thickening
   - Create sketch on that face
   - This positions side panel flush with back panel edge

3. **Benefits of This Approach**
   - Side panel is automatically positioned
   - Changes to back panel propagate to side panel
   - Maintains proper assembly relationships
   - Reflects real-world carpentry practice

### Alternative Approaches

**Mate/Fastener Assembly**:
- Create parts on standard planes
- Use assembly mates to position
- More flexible but requires assembly modeling

**Offset Sketches**:
- Sketch on standard plane
- Add offset constraints
- Simpler but less robust to changes

**Derived Sketches**:
- Project geometry from back panel
- Sketch relative to projection
- Good for complex relationships

## Conclusion

Referencing existing geometry as sketch planes is significantly more complex than using standard planes. The key challenges are:

1. **Query String Complexity**: The qCompressed format is not easily constructed
2. **Entity ID Mapping**: Understanding how sketch entity IDs transform
3. **Operation Tracking**: Following geometry through feature operations
4. **Deterministic IDs**: Discovering the final IDs programmatically

**For MCP Implementation**, we should:
1. Start with standard plane support (already working)
2. Research Onshape's evaluation/query APIs
3. Implement a higher-level method like `create_sketch_on_face(feature_id, face_selector)`
4. Let Onshape handle the complex query string construction

**For Carpentry-Correct Models**, the workflow should:
1. Allow specifying source feature and entity type
2. Automatically find the resulting face after operations
3. Create the sketch with proper references
4. Maintain parametric relationships

## Example Usage (Proposed API)

```python
# Future API proposal
await create_sketch_on_geometry(
    document_id=doc_id,
    workspace_id=ws_id,
    element_id=elem_id,
    name="side panel",
    source_feature_id="FWXtkjgpR9vOAbK_0",  # back panel sketch
    source_entity="right",  # which edge
    after_operation="thicken",  # which operation created the face
    corner1=[0, 0],
    corner2=[16, 67.125],
    variable_width="side_cabinet_depth",
    variable_height="side_cabinet_height"
)
```

This would internally:
1. Query Onshape to find the face created from the right edge
2. Construct the proper query string
3. Create the sketch with the geometry reference
4. Return the sketch feature ID

---

**Status**: Research and planning phase. Standard plane sketches are working. Geometry-referenced sketches require additional API research and implementation.

**Last Updated**: 2025-10-16
**Source**: Analysis of manually-created side panel in display cabinets project
