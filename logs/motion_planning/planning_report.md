# Motion planning experiment: Franka home → PET pre-grasp → home

- **Classification: FULL SUCCESS**
- Mode: headless; physics 120 Hz (PhysX, CPU); obstacle collider prims: 63
- GPU memory peak: 2374 / 12282 MiB; wall time 64.0 s (execution 20.6 s)

## Framework

- framework: NVIDIA cuMotion via isaacsim.robot_motion.cumotion (maintained Isaac Sim 6.2 robot-motion stack, mg substrate)
- goal_solver: cumotion.CollisionFreeIkSolver
- path_planner: isaacsim.robot_motion.cumotion.GraphBasedMotionPlanner.plan_to_cspace_target (RRT, collision-aware)
- time_parameterization: cumotion.CSpaceTrajectoryGenerator (cubic-spline, velocity/acceleration/jerk limited; not collision-aware -> validated densely)
- executor: isaacsim.robot_motion.experimental.motion_generation.TrajectoryFollower -> Articulation.set_dof_position_targets / set_dof_velocity_targets
- Why: cuMotion is NVIDIA's maintained motion-generation backend in Isaac Sim 6.2 (`isaacsim.robot_motion.cumotion` on the `experimental.motion_generation` substrate). Its graph planner checks the robot's collision spheres against the scene obstacles and its self-collision spheres. The previous Lula stack lives in the deprecated `motion_generation` extension and is used here only for the independent hull cross-check. cuRobo is not installed. RMPflow (also cuMotion) is a reactive controller, not a global planner, so it was not used.
- World: all PhysicsCollisionAPI prims outside the robot (explicit list; `mg.SceneQuery` misses colliders with purpose=guide), native cube/cylinder/mesh obstacles + 0.02 m safety tolerance.

## Pre-flight checks

- Frames: cuMotion `panda_hand` FK vs. physics hand link: 0.000 mm / 0.0175°; derived TCP vs. project TCP (Lula `right_gripper`): 0.000 mm / 0.0198°
- Obstacle world vs. independent hull model on 400 random configurations: positive control 0/0 detected, negative control 0/325 flagged
- Home verified at start: max |q − home| = 0.0052°

## Target

- PET bottom (physics) [-0.12, 0.1, 0.7501] (config [-0.12, 0.1, 0.7515], Δ 1.42 mm, tilt 0.000°); `/World/Targets` PET frame present: False → derived from bottle pose + config
- Grasp point (cap) [-0.12, 0.1, 0.9621]; **pre-grasp TCP [-0.12, 0.1, 1.0821]**, top-down, 120 mm above the grasp point; fingertips 109 mm above the cap
- Selected goal (yaw0): q = [-34.4, 6.6, -52.24, -113.2, 5.85, 117.17, 45.92]°, IK error 0.164 mm / 0.071°, inspector distance 0.088 m, hull clearance 0.109 m, gripper↔PET 0.109 m

## Planned trajectories

| Segment | RRT waypoints | Timed waypoints | Duration (s) | Max |qd| (rad/s) | Max |qdd| (rad/s²) | Inspector min dist (m) | Hull min clearance (m) | Collision samples (world/self) | Valid |
|---|---|---|---|---|---|---|---|---|---|
| outbound | 2 | 2 | 2.659 | 0.600 | 0.902 | 0.0878 | 0.0998 | 0/0 | True |
| return | 2 | 2 | 2.645 | 0.600 | 0.906 | 0.0861 | 0.0983 | 0/0 | True |

## Execution (PhysX, articulation joint drives)

| Phase | Duration (s) | Max tracking err (rad) | RMS tracking err (rad) | Max |qd| (rad/s) | Max |qdd| (rad/s², finite diff) | Final TCP err (mm / °) |
|---|---|---|---|---|---|---|
| settle_home | 0.500 | 0.0010 | 0.00036 | 0.005 | 0.03 | 0.71 / 0.094 |
| outbound | 2.667 | 0.0466 | 0.00613 | 0.595 | 4.45 | 2.00 / 0.159 |
| hold_target | 1.000 | 0.0074 | 0.00280 | 0.069 | 0.17 | 5.06 / 0.450 |
| return | 2.650 | 0.0394 | 0.00443 | 0.611 | 6.28 | 0.81 / 0.108 |
| hold_home | 1.000 | 0.0011 | 0.00052 | 0.006 | 0.01 | 0.77 / 0.105 |

- **Target**: TCP error (mean of the last 0.1 s of the hold) 5.062 mm / 0.4513° (limits 10.0 mm / 5.0°) → reached: **True**
- **Home**: joint error 0.0613°, TCP error 0.766 mm → returned: **True**
- Joint limits respected: True (min margin 40.9°); base drift 0.00e+00 m; finger max deviation 0.003 mm; PET displacement 0.0827 mm

## Collision checking

- PhysX contact reports (all links × 63 colliders, every step): readback OK True, unintended contacts: 0 
- Executed joint states (938 steps) re-checked with cuMotion: world-collision steps 0, self-collision steps 0, min distance to padded obstacles 0.0853 m
- Independent hull model (157 steps): min clearance 0.0970 m (['panda_leftfinger', 'object/plastic_bottle']); min gripper↔PET clearance 0.097 m
- PhysX articulation self-collision enabled in the official asset: False
- Not available / not done: continuous (swept) collision checking — all checks are discrete in time.

## Checks

| Check | Result |
|---|---|
| collision_aware_outbound_plan | PASS |
| collision_aware_return_plan | PASS |
| outbound_executed | PASS |
| target_reached_within_tolerance | PASS |
| return_executed | PASS |
| returned_home_within_tolerance | PASS |
| joint_limits_respected | PASS |
| tracking_error_within_limit | PASS |
| no_unintended_collisions | PASS |
| fixed_base | PASS |
| gripper_held_open | PASS |
| pet_bottle_not_disturbed | PASS |
| workstation_scene_unmodified | PASS |
| initial_home_verified | PASS |
| workstation_regression | PASS (validate_scene exit 0 (94/94 static checks passed), run_physics_test exit 0 (39/39 dynamic checks passed), GUI self-test PASS, files unchanged yes) |

## Files

- `logs/motion_planning/validation_results.json`
- `logs/motion_planning/collision_report.json`
- `logs/motion_planning/joint_trajectory.csv`
- `logs/motion_planning/executed_joint_states.csv`
- `logs/motion_planning/tcp_trajectory.csv`
- `logs/motion_planning/execution.log`
