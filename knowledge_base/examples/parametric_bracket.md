# Example: Parametric Mounting Bracket

## Design Intent

Create a fully parametric L-shaped mounting bracket with:
- Adjustable dimensions
- Mounting holes with standard spacing
- Lightening pockets
- Corner fillets for strength
- All features driven by variables

## Design Requirements

### Dimensions
- Base plate: 100mm × 100mm
- Vertical plate: 100mm × 75mm
- Thickness: 5mm throughout
- Mounting holes: M6 clearance (Ø6.5mm)

### Features
- 4 mounting holes in base plate
- 2 mounting holes in vertical plate
- Weight reduction pockets
- R5mm corner fillets

### Manufacturing
- Material: Aluminum 6061
- Process: CNC machining or waterjet cutting + bending
- Finish: Anodized

## Variable Table

```python
# Main dimensions
base_length = 100 mm           # Base plate length
base_width = 100 mm            # Base plate width
vertical_height = 75 mm        # Vertical plate height
plate_thickness = 5 mm         # Uniform thickness

# Mounting holes
hole_diameter = 6.5 mm         # M6 clearance hole
hole_edge_distance = 10 mm     # Distance from edge to hole center
hole_spacing = 80 mm           # Center-to-center spacing

# Pockets (weight reduction)
pocket_size = 30 mm            # Pocket width/length
pocket_depth = 3 mm            # Pocket depth (leave 2mm wall)
pocket_fillet = 5 mm           # Pocket corner radius

# Finishing
corner_fillet = 5 mm           # External corner fillets
edge_chamfer = 0.5 mm          # Deburring chamfer
```

## Feature Sequence

### 1. Create Variables

```python
# Discovery phase
docs = await search_documents(query="bracket project")
doc_id = docs[0].id
summary = await get_document_summary(doc_id)
ws_id = summary['workspaces'][0].id
elem_id = await find_part_studios(doc_id, ws_id)[0].id

# Set all variables
await set_variable(doc_id, ws_id, elem_id, "base_length", "100 mm", "Base plate length")
await set_variable(doc_id, ws_id, elem_id, "base_width", "100 mm", "Base plate width")
await set_variable(doc_id, ws_id, elem_id, "vertical_height", "75 mm", "Vertical plate height")
await set_variable(doc_id, ws_id, elem_id, "plate_thickness", "5 mm", "Uniform thickness")
await set_variable(doc_id, ws_id, elem_id, "hole_diameter", "6.5 mm", "M6 clearance hole")
await set_variable(doc_id, ws_id, elem_id, "hole_edge_distance", "10 mm", "Hole edge margin")
await set_variable(doc_id, ws_id, elem_id, "corner_fillet", "5 mm", "Corner fillet radius")
```

### 2. Create Base Plate Profile

```python
# Sketch on Front plane
await create_sketch_rectangle(
    documentId=doc_id,
    workspaceId=ws_id,
    elementId=elem_id,
    name="Base Plate Profile",
    plane="Front",
    corner1=[0, 0],
    corner2=[100, 100],  # Will be driven by variables
    variableWidth="base_width",
    variableHeight="base_length"
)

# Feature ID returned: base_profile_sketch
```

### 3. Create L-Profile Sketch

```python
# For this, we need a more complex sketch with both base and vertical
# This would be a custom sketch with connected lines forming an L

# Pseudo-code (not yet implemented in MCP):
create_sketch_custom(
    name="L-Bracket Profile",
    plane="Right",
    entities=[
        # Base plate portion
        line(start=[0, 0], end=["#base_length", 0]),
        # Vertical portion
        line(start=["#base_length", 0], end=["#base_length", "#vertical_height"]),
        # Top edge
        line(start=["#base_length", "#vertical_height"],
             end=["#base_length - #plate_thickness", "#vertical_height"]),
        # Step down
        line(start=["#base_length - #plate_thickness", "#vertical_height"],
             end=["#base_length - #plate_thickness", "#plate_thickness"]),
        # Bottom inside edge
        line(start=["#base_length - #plate_thickness", "#plate_thickness"],
             end=[0, "#plate_thickness"]),
        # Close profile
        line(start=[0, "#plate_thickness"], end=[0, 0])
    ]
)
```

### 4. Extrude L-Profile

```python
await create_extrude(
    documentId=doc_id,
    workspaceId=ws_id,
    elementId=elem_id,
    name="Bracket Body",
    sketchFeatureId="l_profile_sketch",
    depth=100,  # base_width
    variableDepth="base_width",
    operationType="NEW"
)
```

### 5. Create Mounting Hole Pattern (Base Plate)

```python
# Create single hole sketch
create_sketch_circle(
    name="Base Mounting Hole",
    plane="Top",  # Top face of base plate
    center=["#hole_edge_distance", "#hole_edge_distance"],
    radius="#hole_diameter / 2",
    variableRadius="hole_diameter"
)

# Extrude cut through
await create_extrude(
    name="Base Hole Cut",
    sketchFeatureId="base_hole_sketch",
    depth=5,  # Through plate_thickness
    variableDepth="plate_thickness",
    operationType="REMOVE"
)

# Pattern the hole (4 holes in corners)
# This would require a pattern feature (not yet in MCP)
create_linear_pattern(
    feature="base_hole_cut",
    direction1="X",
    spacing1="#base_length - 2 * #hole_edge_distance",
    count1=2,
    direction2="Y",
    spacing2="#base_width - 2 * #hole_edge_distance",
    count2=2
)
```

### 6. Create Weight Reduction Pockets

```python
# Central pocket in base plate
create_sketch_rectangle(
    name="Center Pocket",
    plane="Top",
    center=["#base_length / 2", "#base_width / 2"],  # Center of base
    width="#pocket_size",
    height="#pocket_size",
    variableWidth="pocket_size",
    variableHeight="pocket_size"
)

await create_extrude(
    name="Pocket Cut",
    sketchFeatureId="pocket_sketch",
    depth=3,  # pocket_depth
    variableDepth="pocket_depth",
    operationType="REMOVE"
)

# Add pocket fillet (requires fillet feature - not yet in MCP)
create_fillet(
    name="Pocket Fillets",
    edges="pocket_edges",
    radius="#pocket_fillet",
    variableRadius="pocket_fillet"
)
```

### 7. Add Corner Fillets

```python
# This requires fillet feature implementation
create_fillet(
    name="External Corner Fillets",
    edges="all_external_edges",
    radius="#corner_fillet",
    variableRadius="corner_fillet"
)
```

### 8. Add Edge Chamfers (Deburring)

```python
# Small chamfer for sharp edge removal
create_chamfer(
    name="Deburring Chamfer",
    edges="all_edges",
    distance="#edge_chamfer",
    variableDistance="edge_chamfer"
)
```

## Design Validation

### Modify and Test

```python
# Test 1: Change base size
await set_variable(doc_id, ws_id, elem_id, "base_length", "150 mm")
await set_variable(doc_id, ws_id, elem_id, "base_width", "150 mm")
# ✅ All features should update automatically

# Test 2: Change thickness
await set_variable(doc_id, ws_id, elem_id, "plate_thickness", "3 mm")
# ✅ Profile, holes, pockets should all adjust

# Test 3: Change hole spacing
await set_variable(doc_id, ws_id, elem_id, "hole_edge_distance", "15 mm")
# ✅ Hole pattern should reposition
```

## Manufacturing Notes

### CNC Machining
- Material: 6061 aluminum plate
- Stock size: 100mm × 100mm × 5mm
- Operations:
  1. Face milling (both sides)
  2. Contour milling (L-shape profile)
  3. Drilling (mounting holes Ø6.5mm)
  4. Pocket milling (weight reduction)
  5. Fillet milling (R5 ball end mill)
  6. Deburring

### Alternative: Sheet Metal + Bending
- Material: 5mm aluminum sheet
- Cut flat pattern with tabs
- Bend to 90° at bend line
- Drill holes after bending

### Post-Processing
- Deburr all edges
- Anodize (Type II or Type III)
- Color: Clear, black, or blue

## Design Variations

### Heavy Duty Version
```python
await set_variable(doc_id, ws_id, elem_id, "plate_thickness", "8 mm")
await set_variable(doc_id, ws_id, elem_id, "corner_fillet", "8 mm")
# Remove weight reduction pockets
```

### Compact Version
```python
await set_variable(doc_id, ws_id, elem_id, "base_length", "75 mm")
await set_variable(doc_id, ws_id, elem_id, "base_width", "75 mm")
await set_variable(doc_id, ws_id, elem_id, "vertical_height", "50 mm")
```

### Different Mounting Pattern
```python
await set_variable(doc_id, ws_id, elem_id, "hole_diameter", "8.5 mm")  # M8
await set_variable(doc_id, ws_id, elem_id, "hole_spacing", "100 mm")  # Wider spacing
```

## Key Takeaways

1. **Fully Parametric**: Every dimension is a variable
2. **Design Intent**: Variable names explain purpose
3. **Logical Sequence**: Features build logically
4. **Manufacturable**: Considers real machining processes
5. **Testable**: Easy to validate by changing variables
6. **Reusable**: Can create variations quickly

## Current Limitations

The following features are planned but not yet implemented in the MCP server:
- Custom sketch creation (beyond rectangles)
- Pattern features (linear, circular)
- Fillet features
- Chamfer features
- More complex sketch geometry

Once these are added, this complete bracket can be created programmatically!
