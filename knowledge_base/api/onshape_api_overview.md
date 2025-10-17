# Onshape REST API Overview

## API Structure

### Base URL
```
https://cad.onshape.com/api/v6
```

### Authentication
All API requests require Basic Authentication using Access Key and Secret Key:
```
Authorization: Basic base64(access_key:secret_key)
```

## Document Hierarchy

```
Document (did)
├── Workspace (wid) / Version (vid) / Microversion (mid)
│   ├── Part Studio (eid)
│   │   ├── Features
│   │   ├── Parts
│   │   └── Variables
│   ├── Assembly (eid)
│   │   ├── Instances
│   │   └── Mates
│   └── Drawing (eid)
```

### Document IDs
- **Document ID (did)**: Unique identifier for the document
- **Workspace ID (wid)**: Current working version
- **Element ID (eid)**: Specific Part Studio, Assembly, or Drawing

## Key API Endpoints

### Documents
- `GET /api/v6/documents` - List documents
- `GET /api/v6/documents/{did}` - Get document info
- `GET /api/v5/globaltreenodes/search` - Search documents
- `GET /api/v6/documents/d/{did}/workspaces` - List workspaces
- `GET /api/v6/documents/d/{did}/w/{wid}/elements` - List elements

### Part Studios
- `GET /api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/features` - Get features
- `POST /api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/features` - Add feature
- `POST /api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/features/featureid/{fid}` - Update feature
- `DELETE /api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/features/featureid/{fid}` - Delete feature

### Variables
- `GET /api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/variables` - Get variables
- `POST /api/v6/partstudios/d/{did}/w/{wid}/e/{eid}/variables` - Set variable

### Parts
- `GET /api/v6/parts/d/{did}/w/{wid}/e/{eid}` - Get parts in Part Studio
- `GET /api/v6/parts/d/{did}/w/{wid}/e/{eid}/partid/{pid}` - Get specific part

## Feature JSON Structure

All features use the BTMFeature structure:

```json
{
  "btType": "BTMFeature-134",
  "feature": {
    "btType": "BTMSketch-151",  // Feature-specific type
    "name": "Feature Name",
    "parameters": [
      // Feature-specific parameters
    ]
  }
}
```

### Common Feature Types
- `BTMSketch-151` - Sketch
- `BTMExtrude-11` - Extrude
- `BTMRevolve-12` - Revolve
- `BTMFillet-25` - Fillet
- `BTMChamfer-27` - Chamfer
- `BTMHole-8` - Hole
- `BTMPattern-42` - Pattern (linear, circular)

## Parameter Types

### BTMParameterQueryList-148
References sketch entities, faces, edges:
```json
{
  "btType": "BTMParameterQueryList-148",
  "parameterId": "entities",
  "queries": [{
    "btType": "BTMIndividualQuery-138",
    "deterministicIds": ["JHD"]  // Plane ID
  }]
}
```

### BTMParameterQuantity-147
Dimensions with units:
```json
{
  "btType": "BTMParameterQuantity-147",
  "parameterId": "depth",
  "expression": "10 mm",  // or "#variable_name"
  "value": 10,
  "isInteger": false
}
```

### BTMParameterEnum-145
Enumerated options:
```json
{
  "btType": "BTMParameterEnum-145",
  "parameterId": "operationType",
  "value": "NEW"  // NEW, ADD, REMOVE, INTERSECT
}
```

### BTMParameterBoolean-144
True/false values:
```json
{
  "btType": "BTMParameterBoolean-144",
  "parameterId": "oppositeDirection",
  "value": false
}
```

## Variables and Expressions

### Variable Syntax
```
#variable_name
```

### Expression Examples
```
10 mm               // Literal with units
#width              // Variable reference
#width + 5 mm       // Arithmetic
#width * 2          // Multiplication
sqrt(#width)        // Functions
```

### Supported Units
- Length: mm, cm, m, in, ft
- Angle: deg, rad
- Mass: kg, g, lbm

## Common Patterns

### 1. Create Parametric Sketch
```json
{
  "btType": "BTMFeature-134",
  "feature": {
    "btType": "BTMSketch-151",
    "name": "Base Sketch",
    "parameters": [{
      "btType": "BTMParameterQueryList-148",
      "parameterId": "sketchPlane",
      "queries": [{
        "btType": "BTMIndividualQuery-138",
        "deterministicIds": ["JHD"]  // Front plane
      }]
    }],
    "entities": [
      // Sketch geometry
    ],
    "constraints": [{
      "type": "horizontal",
      "expression": "#width",
      "value": 100
    }]
  }
}
```

### 2. Create Extrude
```json
{
  "btType": "BTMFeature-134",
  "feature": {
    "btType": "BTMFeature-134",
    "featureType": "extrude",
    "name": "Extrude 1",
    "parameters": [
      {
        "btType": "BTMParameterQueryList-148",
        "parameterId": "entities",
        "queries": [{
          "btType": "BTMIndividualQuery-138",
          "queryStatement": "query=qSketchRegion('sketch_feature_id')"
        }]
      },
      {
        "btType": "BTMParameterEnum-145",
        "parameterId": "operationType",
        "value": "NEW"
      },
      {
        "btType": "BTMParameterQuantity-147",
        "parameterId": "depth",
        "expression": "#depth",
        "value": 10,
        "isInteger": false
      }
    ]
  }
}
```

## Best Practices

### 1. Always Use Variables
Use variable expressions instead of hardcoded values for flexibility:
```json
"expression": "#height"  // ✅ Good
"expression": "50 mm"    // ❌ Avoid
```

### 2. Descriptive Naming
```json
"name": "Base Plate Sketch"  // ✅ Good
"name": "Sketch 1"           // ❌ Avoid
```

### 3. Logical Feature Order
Create features in a logical sequence:
1. Reference geometry (planes, axes)
2. Base features (sketches, extrudes)
3. Modifications (fillets, chamfers, holes)
4. Patterns

### 4. Error Handling
Always handle API errors:
- 401: Authentication failed
- 404: Resource not found
- 409: Conflict (e.g., feature rebuild failed)
- 500: Server error

### 5. Rate Limiting
Be mindful of API rate limits:
- Use batch operations when possible
- Implement exponential backoff on failures
- Cache results when appropriate

## Standard Plane IDs

- Front: "JHD"
- Top: "JHC"
- Right: "JHB"

## Query Types

### qSketchRegion
Reference sketch regions:
```
query=qSketchRegion('sketch_feature_id')
```

### qCreatedBy
Reference entities created by a feature:
```
query=qCreatedBy('feature_id', EntityType.FACE)
```

### qCapEntity
Reference cap faces (end faces of extrudes):
```
query=qCapEntity('extrude_id', CapType.START)
```

## Resources

- [Official API Docs](https://onshape-public.github.io/docs/)
- [Developer Portal](https://dev-portal.onshape.com/)
- [FeatureScript Docs](https://cad.onshape.com/FsDoc/)
- [API Forum](https://forum.onshape.com/)
