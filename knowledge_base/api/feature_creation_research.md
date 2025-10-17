# Feature Creation via Onshape API - Research Notes

## Current Status

We've successfully:
- ✅ Found Part Studios in documents
- ✅ Read existing features
- ✅ Read variables from Part Studios
- ❌ Create new features (getting 400 errors)

## Problem

Our current sketch builder creates JSON like this:

```json
{
  "btType": "BTMFeature-134",
  "feature": {
    "btType": "BTMSketch-151",
    "name": "Sketch",
    "parameters": [...]
  }
}
```

But this causes a 400 Bad Request error from Onshape.

## What We Learned from Real Features

From the display cabinets document, we found that **working** variable assignment features look like:

```json
{
  "btType": "BTMFeature-134",
  "namespace": "",
  "name": "###name = #value",
  "suppressed": false,
  "parameters": [
    {
      "btType": "BTMParameterString-149",
      "value": "side_cabinet_height",
      "nodeId": "MiDrYGR+PzB/FVKig",
      "parameterId": "name",
      "parameterName": "",
      "libraryRelationType": "NONE"
    },
    {
      "btType": "BTMParameterQuantity-147",
      "isInteger": false,
      "value": 0.0,
      "units": "",
      "expression": "67.125 in",
      "nodeId": "MXMNBG8c5Q45Q+VKt",
      "parameterId": "value",
      "parameterName": "",
      "libraryRelationType": "NONE"
    }
  ],
  "featureId": "FWHg1NvqqOzMd0w",
  "nodeId": "M3jfUeySdjq8uMQz5",
  "featureType": "assignVariable",
  "returnAfterSubfeatures": false,
  "subFeatures": [],
  "suppressionState": null,
  "parameterLibraries": []
}
```

### Key Differences:

1. **NO nested "feature" object** - parameters go directly in BTMFeature-134
2. **featureType field** - identifies what kind of feature ("assignVariable", "newSketch", "extrude")
3. **nodeId fields** - mysterious IDs on every parameter
4. **Additional metadata** - namespace, suppressed, returnAfterSubfeatures, etc.
5. **Parameter structure** - more fields than we're providing (nodeId, parameterName, libraryRelationType)

## Next Steps

### Option 1: Study Real Sketches (Recommended)
We need to see actual working sketch and extrude features from a real document:

1. Get features from outdoor kitchen (has tons of working examples)
2. Extract first sketch feature
3. Extract first extrude feature
4. Document exact structure
5. Update our builders to match

### Option 2: Use FeatureScript
Instead of creating JSON directly, we could:
- Write FeatureScript code
- Submit via different API endpoint
- Let Onshape handle the JSON generation

### Option 3: Simpler Operations First
Before creating features, implement:
- ✅ Variable modification (change existing variable values)
- ✅ Part export/import
- ✅ Assembly operations
- ✅ Metadata management

Then tackle feature creation once we understand the format better.

## Questions to Answer

1. What does `nodeId` represent? How is it generated?
2. What's the difference between API v6, v9 endpoints?
3. Can we create features without nodeIds (let Onshape generate)?
4. Is there a simpler feature type to start with?
5. Should we use FeatureScript instead of direct JSON?

## Resources Needed

- [ ] Working sketch feature JSON example
- [ ] Working extrude feature JSON example
- [ ] Onshape API documentation on feature creation
- [ ] FeatureScript documentation
- [ ] Community examples/forum posts

## Alternative Approach: Learn from Onshape's Own Tools

The Onshape web interface creates features. We could:
1. Monitor network traffic while creating a sketch
2. Capture the exact JSON sent
3. Replicate that structure

This would give us the "ground truth" of what Onshape expects.
