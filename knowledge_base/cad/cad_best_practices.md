# CAD Best Practices for Onshape

## Parametric Design Principles

### 1. Design Intent

**Capture the "Why"**
- Document why dimensions exist
- Use variable names that explain purpose
- Add descriptions to variables
- Comment complex feature sequences

**Example:**
```python
# ✅ Good - Clear intent
set_variable("mounting_hole_spacing", "50 mm", "Standard VESA mount pattern")
set_variable("clearance_gap", "0.5 mm", "Manufacturing tolerance")

# ❌ Bad - No clear intent
set_variable("dim1", "50 mm")
set_variable("dim2", "0.5 mm")
```

### 2. Fully Define Sketches

**Always Constrain Sketches Completely**
- Use geometric constraints (parallel, perpendicular, tangent)
- Add dimensional constraints
- Lock to reference geometry
- Avoid over-constraining

**Common Constraints:**
- Horizontal/Vertical
- Parallel/Perpendicular
- Equal length/radius
- Symmetric
- Concentric
- Tangent
- Midpoint

### 3. Use Variables for Everything

**Make Designs Adjustable**
```
✅ Variable-driven: Changes propagate automatically
❌ Hard-coded: Must manually update each dimension
```

**Variable Naming:**
- Use descriptive names: `bracket_width` not `width1`
- Group related variables: `hole_diameter`, `hole_spacing`, `hole_count`
- Include units in name if helpful: `thread_depth_mm`

## Feature Organization

### 1. Logical Feature Order

**Recommended Sequence:**
1. **Reference Geometry** - Planes, axes, points
2. **Base Features** - Main body profiles and extrudes
3. **Primary Features** - Major cuts, bosses, ribs
4. **Secondary Features** - Holes, slots, pockets
5. **Finishing Features** - Fillets, chamfers
6. **Patterns** - Linear and circular patterns

**Why This Matters:**
- Features build on previous features
- Changing base features affects downstream
- Logical order is easier to modify later

### 2. Feature Naming

**Name Everything Descriptively:**
```
✅ "Mounting Holes - M6"
✅ "Base Plate - 100x100"
✅ "Corner Fillets - R3"
✅ "Clearance Pocket"

❌ "Sketch 1"
❌ "Extrude 2"
❌ "Hole 3"
```

### 3. Feature Grouping

**Use Feature Folders/Groups:**
- Group related features
- Organize by functional area
- Make complex models navigable
- Hide/show groups for performance

**Example:**
```
Mounting Features/
├── Mounting Holes
├── Boss Posts
└── Clearance Cuts

Body Features/
├── Main Extrude
├── Ribs
└── Stiffeners

Finishing/
├── Edge Fillets
└── Corner Chamfers
```

## Reference Geometry Best Practices

### 1. Use Reference Planes

**When to Create Reference Planes:**
- Angled features
- Offset patterns
- Complex assembly relationships
- Mirror operations

**Benefits:**
- More robust than referencing faces
- Faces may disappear with design changes
- Planes persist through modifications

### 2. Construction Geometry

**Use Construction Lines:**
- Layout sketches
- Define relationships
- Create reference points
- Aid in constraints

### 3. Origin and Coordinate System

**Plan Your Origin:**
- Center for symmetric parts
- Corner for rectangular parts
- Mounting point for assemblies
- Consistent across related parts

## Sketch Best Practices

### 1. Sketch Complexity

**Keep Sketches Simple:**
- One sketch per logical profile
- Split complex shapes across multiple sketches
- Use separate sketches for separate features

**Example:**
```
✅ Separate sketches:
   - Base profile sketch
   - Hole pattern sketch
   - Cutout sketch

❌ One huge sketch:
   - Everything in one sketch (hard to modify)
```

### 2. Sketch Relations

**Use Smart Relations:**
- Symmetric about centerline
- Equal spacing
- Colinear lines
- Tangent arcs

### 3. Fully Constrained

**Blue vs Black:**
- Blue = Under-constrained (will move)
- Black = Fully constrained (locked in place)
- Always aim for fully constrained (black)

## Extrude Best Practices

### 1. Extrude Types

**NEW**: Creates new body
- Use for: First feature, separate components
- Creates: Independent solid

**ADD**: Adds material
- Use for: Bosses, ribs, mounting features
- Creates: Union with existing body

**REMOVE**: Removes material
- Use for: Cuts, pockets, holes
- Creates: Subtraction from body

**INTERSECT**: Keeps only intersection
- Use for: Complex trimming operations
- Creates: Intersection of bodies

### 2. End Conditions

**Blind**: Fixed depth
- Most common
- Use with variables for flexibility

**Through All**: Cuts through everything
- For holes through entire part
- Robust to thickness changes

**Up To Face**: Stops at a face
- For mating features
- Reference-based depth

### 3. Draft Angles

**Add Draft for Molding/Casting:**
```python
create_extrude(
    ...,
    draft_angle="2 deg",  # Typical for plastic molding
    draft_variable="draft_angle"
)
```

## Variable Best Practices

### 1. Variable Organization

**Group Related Variables:**
```
# Dimensions
overall_length = 100 mm
overall_width = 50 mm
overall_height = 25 mm

# Features
hole_diameter = 6 mm
hole_spacing = 50 mm
hole_count = 4

# Materials
wall_thickness = 2 mm
rib_thickness = 1.5 mm
```

### 2. Dependent Variables

**Create Relationships:**
```
# Base variables
outer_width = 100 mm
wall_thickness = 2 mm

# Derived variables
inner_width = #outer_width - (2 * #wall_thickness)
```

### 3. Variable Descriptions

**Always Add Descriptions:**
```python
set_variable("clearance", "0.5 mm", "Manufacturing tolerance for sliding fit")
set_variable("fillet_radius", "3 mm", "Standard corner fillet per company spec")
```

## Pattern Best Practices

### 1. Linear Patterns

**Use for:**
- Repeated holes
- Ribs
- Mounting bosses
- Any linear repetition

**Variables:**
```
pattern_spacing = 50 mm
pattern_count = 4
```

### 2. Circular Patterns

**Use for:**
- Bolt circles
- Radial ribs
- Gear teeth
- Symmetric features

**Variables:**
```
bolt_circle_diameter = 100 mm
bolt_count = 6
```

## Fillet and Chamfer Best Practices

### 1. Fillet Strategy

**Small to Large:**
- Apply small fillets first
- Then larger fillets
- Prevents geometry failures

**Group by Size:**
```
corner_fillet = 3 mm (all corners)
edge_fillet = 1 mm (all edges)
blend_fillet = 5 mm (blend surfaces)
```

### 2. Chamfer Usage

**When to Use Chamfers:**
- Assembly clearance
- Sharp edge removal
- Aesthetic breaks
- Deburring specification

**Standard Sizes:**
```
deburr_chamfer = 0.5 mm
assembly_chamfer = 1 mm
aesthetic_chamfer = 2 mm
```

## Design for Manufacturing (DFM)

### 1. Material Considerations

**Minimum Wall Thickness:**
- Plastic molding: 1-3 mm
- Sheet metal: Material thickness
- 3D printing: 1-2 mm
- Machining: Tool dependent

### 2. Draft Angles

**Molding Requirements:**
- Internal walls: 1-3 degrees
- External walls: 0.5-2 degrees
- Deep pockets: More draft needed

### 3. Hole Standards

**Standard Sizes:**
- Metric: M3, M4, M5, M6, M8, M10
- Imperial: #4-40, #6-32, #8-32, 1/4-20, 1/4-28
- Clearance: Diameter + 0.5mm to 1mm

### 4. Bend Radius (Sheet Metal)

**Minimum Bend Radius:**
- Soft materials: 0.5× thickness
- Hard materials: 2× thickness
- Standard: 1× thickness

### 5. 3D Printing

**Key Guidelines:**
- Support angles < 45°
- Wall thickness ≥ 1mm
- Avoid large flat surfaces on bed
- Consider print orientation

## Performance Optimization

### 1. Feature Count

**Minimize Features:**
- Combine when possible
- Use patterns instead of individual features
- Simplify complex curves

### 2. Suppression

**Suppress When Not Needed:**
- Temporarily hide features
- Speed up rebuilds
- Manage complexity

### 3. External References

**Minimize External References:**
- Too many = slow rebuilds
- Can break with changes
- Document critical references

## Assembly Best Practices

### 1. Top-Down Design

**In-Context Design:**
- Layout sketch in assembly
- Reference for part sizes
- Maintains design intent

### 2. Mate Types

**Common Mates:**
- Fastened: Fixed together
- Revolute: Rotating joint
- Slider: Linear motion
- Cylindrical: Rotation + slide
- Planar: Constrained to plane

### 3. Interference Detection

**Always Check:**
- Before finalizing design
- After modifications
- Before manufacturing

## Documentation Best Practices

### 1. Comments

**Add Comments:**
```
// This feature creates clearance for cable routing
// Dimension based on maximum cable diameter + 5mm
```

### 2. Variable Descriptions

**Explain Purpose:**
- Why this value?
- How determined?
- What constrains it?

### 3. Design Notes

**Document:**
- Design decisions
- Tradeoffs made
- Future considerations
- Testing results

## Common Mistakes to Avoid

### ❌ Don't:
1. Hard-code dimensions (use variables!)
2. Over-constrain sketches
3. Create fragile references
4. Ignore feature order
5. Skip naming features
6. Forget design intent
7. Ignore manufacturing constraints
8. Create overly complex single features
9. Use poor variable names
10. Skip documentation

### ✅ Do:
1. Use variables everywhere
2. Fully define sketches properly
3. Use reference planes
4. Logical feature sequence
5. Descriptive naming
6. Document design intent
7. Consider manufacturing
8. Break complexity into steps
9. Clear, descriptive names
10. Add comments and descriptions

## Quick Checklist

Before finalizing any design:

- [ ] All sketches fully constrained?
- [ ] All dimensions are variables?
- [ ] Features named descriptively?
- [ ] Logical feature order?
- [ ] Design intent documented?
- [ ] Manufacturing feasibility checked?
- [ ] Standard sizes used where applicable?
- [ ] Parametric behavior tested?
- [ ] No external reference issues?
- [ ] Performance acceptable?

## Resources

- Onshape Learning Center
- Professional CAD standards (ASME, ISO)
- Manufacturing guidelines
- Material specifications
- Industry best practices
