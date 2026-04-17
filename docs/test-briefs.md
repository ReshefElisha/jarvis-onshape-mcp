# Test briefs

A menu of natural-language prompts to stress-test the MCP end-to-end. Each is
chosen to exercise a specific muscle group.

## Warmup (single part, 30–50 turns)

**Mounting plate.**
"Build a 60×40×8 mm mounting plate with 4 M4 through-holes at the corners, 6 mm inset from each edge."

**L-bracket.**
"A right-angle L-bracket: two 40×40×4 mm walls joined along one edge, 3 mm inside fillet at the crease, 4 mm bolt holes 6 mm from each end."

## Medium (sketch-on-face + FS)

**USB-C pass-through enclosure bottom.**
"A 70×40×15 mm enclosure bottom shell, 1.5 mm wall thickness, open on top. USB-C port cutout (9 mm wide × 3.5 mm tall, R=0.5 mm corners) centered on one short wall 2 mm up from the floor. Inner corner fillets R=1.5 mm, outer corners R=3 mm. PCB rail ledges on both long walls: 1 mm wide × 1 mm deep at 2 mm from floor."

**Motor pillow block.**
"Motor pillow block: 60×40×8 mm base flange with four M4 corner holes, ø30×20 mm cylindrical housing centered on top, ø22×8 mm blind bearing bore, ø8 mm through shaft."

## Parametric

**NEMA stepper bracket family.**
"A stepper-motor mounting bracket with variables for NEMA 17/23/34 interchangeability: `motor_flange_w`, `bolt_spacing`, `shaft_d`, `bolt_d`. Build a plate of `motor_flange_w + 20 mm` square, 10 mm thick, with a central through-hole for `shaft_d`, 4 motor-bolt clearance holes on a `bolt_spacing` square pattern, and 4 M5 mounting holes on an outer `motor_flange_w + 15 mm` pattern. Then reparametrize for NEMA 23 values."

## Hard (FS paradigm, assemblies)

**Worm gearbox housing.**
"A horizontal gearbox housing: 50×40×30 mm body. Two parallel ø19 mm bores along the long axis (for 608-2RS bearings), 20 mm between centers, both centered vertically. A perpendicular ø8 mm bore through the top face for the worm shaft, aligned with the centerline between the parallel bores. Four M3 corner mounting holes on the bottom face."

**Cable gland with threads + knurl + hex.**
"A cable gland body: ø20 × 25 mm cylinder with a ø10 through-hole. External M18×1.0 thread on the top 10 mm. A 24-tooth knurl on the middle 5 mm. Six wrench-flat surfaces at the bottom end forming a 13 mm across-flats hex. 1 mm × 1.5 mm washer groove at the thread base."

**4-bar parallelogram linkage (assembly).**
"A 4-bar linkage for tool-orientation maintenance: ground bar 80 mm, input crank 30 mm, coupler 80 mm, output crank 30 mm. Each link is 10 mm wide × 4 mm thick with ø4 mm pivot holes at each end. Make each link its own Part Studio, then assemble with 4 revolute mates so input-crank rotation is mirrored by the output crank while the coupler stays parallel to the ground bar. Verify the assembly has exactly 1 degree of freedom."

## Tips when dogfooding

- After each feature, ask Claude to call `describe_part_studio` so you can see the structured+visual state.
- If Claude wastes turns on a silent `INFO: nothing was cut`, check the `changes:` block — `volume_delta_mm3: 0.0` is the tell.
- FS failures are now surfaced with the parser notice text. Read `error_message` on any `REGEN_ERROR`.
- Paste the doc URL back to Claude if you want it to resume work on an existing document.
