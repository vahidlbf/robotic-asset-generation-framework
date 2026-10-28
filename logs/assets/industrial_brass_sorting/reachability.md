# Reachability (geometric): `industrial_brass_sorting`

- Lula IK + endpoint clearance (robot collider hulls vs. collider OBBs); no trajectories, no grasp physics; not evidence of executable pick-and-place
- Poses: 16; IK solved: 16; feasible (limits + clearance): 9; infeasible: ['FittingA_0:grasp', 'FittingA_1:grasp', 'FittingA_2:grasp', 'FittingA_3:grasp', 'FittingB_0:grasp', 'FittingB_1:grasp', 'FittingB_2:grasp']
- Minimum robot clearance -0.0041 m (required 0.02 m); minimum joint margin 0.030 of range

| Target | Pose | TCP (m) | IK | Joint margin | Manipulability | Links + hand clearance (m) | Finger clearance (m) | Fingers to support floor (m) | Feasible |
|---|---|---|---|---|---|---|---|---|---|
| FittingA_0 | pre_grasp | [0.42412, -0.20888, 0.86725] | yes | 0.073 | 0.016 | 0.0515 (panda_hand - InputTray/WallPosY) | 0.0378 |  | yes |
| FittingA_0 | grasp | [0.42412, -0.20888, 0.77034] | yes | 0.105 | 0.014 | 0.0104 (panda_hand - FittingB_0/Zone4_07) | 0.0072 | 0.0030 | **no** |
| FittingA_1 | pre_grasp | [0.48104, -0.16573, 0.86725] | yes | 0.030 | 0.012 | 0.0512 (panda_hand - InputTray/WallPosY) | 0.0511 |  | yes |
| FittingA_1 | grasp | [0.48104, -0.16573, 0.77031] | yes | 0.055 | 0.009 | 0.0101 (panda_hand - InputTray/WallPosX) | 0.0080 | 0.0030 | **no** |
| FittingA_2 | pre_grasp | [0.51527, -0.22668, 0.86725] | yes | 0.096 | 0.018 | 0.0512 (panda_hand - InputTray/WallPosX) | 0.0357 |  | yes |
| FittingA_2 | grasp | [0.51527, -0.22668, 0.77031] | yes | 0.115 | 0.017 | -0.0041 (panda_hand - InputTray/WallPosX) | 0.0080 | 0.0030 | **no** |
| FittingA_3 | pre_grasp | [0.31993, -0.14745, 0.86725] | yes | 0.036 | 0.012 | 0.0511 (panda_hand - InputTray/WallPosY) | 0.0332 |  | yes |
| FittingA_3 | grasp | [0.31993, -0.14745, 0.77032] | yes | 0.063 | 0.009 | -0.0026 (panda_hand - InputTray/WallPosY) | 0.0080 | 0.0030 | **no** |
| FittingB_0 | pre_grasp | [0.38438, -0.27506, 0.8712] | yes | 0.108 | 0.027 | 0.0552 (panda_hand - InputTray/WallNegX) | 0.0421 |  | yes |
| FittingB_0 | grasp | [0.38438, -0.27506, 0.7712] | yes | 0.203 | 0.043 | 0.0108 (panda_hand - FittingB_1/Zone4_08) | -0.0005 | 0.0039 | **no** |
| FittingB_1 | pre_grasp | [0.3247, -0.24732, 0.8712] | yes | 0.132 | 0.024 | 0.0552 (panda_hand - InputTray/WallNegX) | 0.0275 |  | yes |
| FittingB_1 | grasp | [0.3247, -0.24732, 0.7712] | yes | 0.150 | 0.024 | -0.0028 (panda_hand - InputTray/WallNegX) | 0.0036 | 0.0039 | **no** |
| FittingB_2 | pre_grasp | [0.46211, -0.30744, 0.87118] | yes | 0.124 | 0.034 | 0.0552 (panda_hand - InputTray/WallNegY) | 0.0089 |  | yes |
| FittingB_2 | grasp | [0.46211, -0.30744, 0.77781] | yes | 0.142 | 0.033 | -0.0036 (panda_hand - InputTray/WallNegY) | 0.0155 | -0.0037 | **no** |
| sorting_bin_A | pre_drop | [-0.03, -0.2, 1.12] | yes | 0.264 | 0.084 | 0.1297 (panda_link1 - FittingA_3/Zone1_04) | 0.1377 |  | yes |
| sorting_bin_B | pre_drop | [-0.03, 0.2, 1.12] | yes | 0.287 | 0.061 | 0.1296 (panda_link1 - FittingA_3/Zone1_04) | 0.1377 |  | yes |

Criteria: within joint limits; links + hand >= 0.02 m (gripper.min_robot_clearance_m) from the table, containers and other parts; fingers >= 5 mm from everything except the grasped part; at the grasp the fingers clear the support floor (the TCP is raised above the part's centre of mass when the finger hulls would touch it). Obstacles are the collider pieces themselves (boxes as OBBs, tapered walls and fitting sectors as convex prisms; outside distances are lower bounds).
