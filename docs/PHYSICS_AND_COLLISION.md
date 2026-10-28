# Physics and collision

Physics coefficients are illustrative simulation parameters, not measured material properties.

## Scene

`/World/PhysicsScene`: gravity 9.81 m/s² along −Z, 120 steps/s, TGS solver, CPU dynamics (`gpu_dynamics: false`, MBP
broadphase), CCD off. Friction and restitution combine mode `average` on every material. This is authored by
`build_scene.py` for base materials and by `compose_scene.py` for instance materials.

## Visual vs. collision geometry

The render mesh (`Visual`, from Blender) is never used as a collider. Colliders are separate, simpler prims under
`Collision/` with `purpose = guide`, so they are invisible in renders and the viewport.

| Asset | Collision representation | Notes |
|---|---|---|
| table | 1 box top slab + 1 box per leg | static |
| bins | bottom + 4 wall boxes, open top | static; labels are visual only |
| glass crate | bottom + 4 walls + separators | static, open top |
| crate platform | kick plinth, body, top plate boxes | static |
| glass / PET bottle | body cylinder + shoulder convex hull + neck (+ cap) cylinders | dynamic; **solid** (not hollow) |
| paper cup | base cylinder + 16 tilted 2 mm wall boxes | dynamic; hollow, open top |
| library `primitive` | one Cube or Cylinder | solid; a tube becomes a solid cylinder |
| library `convex_hull` | convex mesh of the visual vertices (`MeshCollisionAPI.approximation = convexHull`) | solid |
| library `ring_segments` | N boxes, a regular N-gon inscribed in the outer circle with inner faces at the bore radius | keeps the bore open; N must be a multiple of 4 |
| library `container_walls` (crate, tray) | `Floor` box + 4 separate convex wall slabs (inner face = the tapered inner wall, outer edge at the rim) | static; open top (`open_top` check); no lid; interior corners are sharp (visual corners are rounded, up to ~6 mm difference); hand holes are visual only (walls solid); floor box covers the whole bottom, including the area under the recessed stacking foot |
| library `fitting_sections` (brass adapters) | per zone a ring of convex sector prisms: 6 for a hex section, 12 circumscribed sectors for round zones; inner faces tangent to the zone's largest bore radius | dynamic; bore open along the whole axis (`bore_open` check); threads, grooves and chamfers are not in the colliders; a zone uses its largest radius, e.g. a thread zone at the major diameter; 42 (Type A) / 54 (Type B) convex pieces |
| library `none` (labels) | no colliders, no rigid body | visual only, fixed to a mount point of its support |

## Static vs. dynamic

- **Static:** colliders without `RigidBodyAPI` (table, bins, crate, platform, ground, and static library assets).
- **Dynamic:** `RigidBodyAPI` on the asset root, exactly one per asset, with no nested rigid bodies.
- **Instance override:** `physics:rigidBodyEnabled = false` in the scene layer makes one instance static without
  changing the asset. The four crate bottles in the base scene and `"static": true` library instances use it.
- **Robot:** an articulation from the official asset. The scene only adds the home joint state, equal drive targets
  and a filtered pair between `panda_link0` and the tabletop collider (mounting contact).

## Contact offset (thin static floors)

`collision.contact_offset_m` (0.02 m for the crate and the tray) writes `PhysxCollisionAPI.contactOffset` on the
asset's colliders. Without it, a 6 cm test cube dropped 0.15 m above the crate rim (2.53 m/s at impact, 21 mm per
8.3 ms step) did not generate a contact at 16 mm separation and sank 5.7 mm into the 16 mm floor for one step before
resting correctly. The base bins' drop test happened to hit a better step phase. With the 2 cm offset the contact
exists before impact; the measured lowest point is 0.0159998 m against a floor top of 0.016 m. The rest offset is
unchanged, so resting parts touch the floor (measured gap 0.000 mm). CCD remains off in the scene.

## Rest poses of lying parts

`pose: lying` lays an asset's axis along x (after `spin_deg` about the axis) and tilts it about the horizontal so the
lower convex hull edge of its collider points under the centre of mass is horizontal (`asset_lib.rest_orientation`).
The Type A adapter rests on a hex flat with its axis horizontal. Type B rests on its spigot end and the socket edge,
12.1° tilted. In the 3 s PhysX run the seven fittings rotated at most 0.033° from these poses.

## Mass and inertia

`mass_properties(tris, mass)` integrates the closed visual triangle mesh, which must be watertight with outward
normals. It assumes uniform density, scales to the given mass, and returns the COM and inertia about the COM. The
assets author `physics:mass`, `physics:centerOfMass` and `physics:diagonalInertia` with
`principalAxes = identity`. That is valid because every asset is symmetric about Z: the off-diagonal ratio is
recorded, e.g. 7e-17 for the glass bottle.

- **Workstation objects:** the mass comes from the config and the implied density is reported. The paper cup's
  implied ~420 kg/m³ is low because its 1 mm visual wall is thicker than real cup board.
- **Library assets:** the mass is `mass_kg` or `density_kg_m3` × mesh volume. The mesh is the tessellated solid,
  e.g. a 48-gon is 0.29 % smaller than a true circle. `validation.density_range_kg_m3` makes generation fail when a
  `mass_kg` implies an implausible density. The brass adapters (45 g and 75 g from the task) imply 8197 and
  8483 kg/m³ against a band of 8000–8800; the geometry was adjusted until both fell inside it.
- **Turned parts with helical threads:** they are not exactly symmetric. The COM lies within 0.2 mm of the axis
  (measured ≤ 5.1 µm), and the off-diagonal inertia is below 1 % of the diagonal (measured ≤ 3.9e-4). That justifies
  `principalAxes = identity`.

Mass comes from the visual mesh, not the colliders. For hollow objects with solid colliders (the bottles), the
collision shape and the mass distribution therefore differ.

## Physical materials

Per asset, a `UsdPhysics.MaterialAPI` material is bound to all of its colliders with the `physics` purpose. The
workstation materials are in `config/waste_sorting_environment.json` → `physics.materials` (`table`, `glass`,
`pet`, `paper`, `bin`, `floor`). Library assets either name one of these or define their own inline (`test_spacer`:
`steel`, 0.6 / 0.5 / 0.1).

## Known limitations

- **No deformation:** PET crushing and paper-cup deformation are not modelled; all bodies are rigid.
- **Solid bottles:** the bottle colliders are solid, so liquids and the bottles' interiors are not represented.
- **Discrete collision checks:** CCD is off. Small, fast objects could tunnel. The settle tests drop objects only
  1.5 mm (`objects.clearance`).
- **Box approximation of round parts:** compound boxes approximate round walls, e.g. a 12-segment ring is a 12-gon
  outside. Fitting sectors circumscribe the zone radius: their vertices lie 3.5 % outside it, and the rolling
  resistance comes from the 12-gon flats.
- **Brass friction:** 0.35 / 0.30 static/dynamic, restitution 0.08, averaged with the tray plastic (0.40 / 0.35 /
  0.05). These are illustrative values, not measurements.
- **Self-collision:** the official Franka asset has PhysX self-collision disabled; the motion experiment checks
  self-collision with cuMotion's spheres.
- **Test-only settings:** sleeping is disabled and contact reporting is enabled only in the test session layers;
  the saved scenes keep PhysX defaults.
