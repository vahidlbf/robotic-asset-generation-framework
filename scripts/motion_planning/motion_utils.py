"""Shared motion-planning utilities (run inside Isaac Sim's python.sh, after SimulationApp is created).

Planning stack (NVIDIA cuMotion through the maintained Isaac Sim 6.2 robot-motion APIs):
  * world:    mg.WorldBinding + cumotion CumotionWorldInterface populated from the scene's PhysicsCollisionAPI
              prims (explicit list, see collect_obstacle_prims), padded by the ObstacleStrategy safety tolerance
  * goal:     cumotion.CollisionFreeIkSolver (top-down pre-grasp pose, several gripper yaws)
  * path:     cumotion GraphBasedMotionPlanner.plan_to_cspace_target (RRT; robot collision spheres vs. world +
              self-collision spheres from the Franka XRDF)
  * timing:   cumotion CSpaceTrajectoryGenerator with velocity / acceleration / jerk limits
  * checking: every trajectory is re-validated densely with cumotion.RobotWorldInspector (world + self collision)
              and independently with the project's PhysX-hull model (robot_geometry.RobotModel)
"""

from __future__ import annotations

import json
import math
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(ROOT, "scripts", "workstation"))


def load_configs(path="config/motion_planning.json"):
    mc = json.load(open(path if os.path.isabs(path) else os.path.join(ROOT, path)))
    wc = json.load(open(os.path.join(ROOT, mc["workstation_config"])))
    return mc, wc


def enable_motion_extensions(app):
    from isaacsim.core.utils.extensions import enable_extension

    out = {}
    for e in ("isaacsim.robot_motion.experimental.motion_generation", "isaacsim.robot_motion.cumotion"):
        out[e] = bool(enable_extension(e))
    app.update()
    return out


# ---------------------------------------------------------------------------
# Frames
# ---------------------------------------------------------------------------

def quat_to_R(q):
    w, x, y, z = q
    return np.array([[1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)],
                     [2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)],
                     [2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)]])


def R_to_quat(R):
    from scipy.spatial.transform import Rotation
    x, y, z, w = Rotation.from_matrix(R).as_quat()
    q = np.array([w, x, y, z])
    return q if q[0] >= 0 else -q


def T(R=None, p=None):
    M = np.eye(4)
    if R is not None:
        M[:3, :3] = R
    if p is not None:
        M[:3, 3] = p
    return M


def hand_T_tcp(mc):
    a = math.radians(mc["tcp"]["rotation_from_hand_deg_z"])
    Rz = np.array([[math.cos(a), -math.sin(a), 0], [math.sin(a), math.cos(a), 0], [0, 0, 1]])
    return T(Rz, mc["tcp"]["offset_from_hand_m"])


def topdown_R(yaw):
    """Same convention as robot_geometry.topdown_R: TCP z down, finger axis = TCP y."""
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, s, 0.0], [s, -c, 0.0], [0.0, 0.0, -1.0]])


def rot_err_deg(Ra, Rb):
    return float(np.degrees(np.arccos(np.clip((np.trace(Ra.T @ Rb) - 1) / 2, -1, 1))))


# ---------------------------------------------------------------------------
# Scene / world binding
# ---------------------------------------------------------------------------

def collect_obstacle_prims(stage, robot_path):
    """All PhysicsCollisionAPI prims outside the robot.

    mg.SceneQuery().get_prims_in_aabb() is NOT used: it bounds prims with a default-purpose BBoxCache, and this
    project's colliders are authored with purpose=guide (invisible), so it returns only the floor. The explicit
    list gives the same obstacle set the PhysX scene uses."""
    from pxr import Usd, UsdPhysics

    out = []
    for p in Usd.PrimRange(stage.GetPseudoRoot()):
        sp = str(p.GetPath())
        if sp.startswith(robot_path) or p.IsInstanceProxy():
            continue
        if p.HasAPI(UsdPhysics.CollisionAPI):
            out.append(sp)
    return out


def expose_guide_colliders(stage, prims):
    """Session-layer only (never saved): give guide-purpose colliders purpose=default + visibility=invisible so that
    USD bounding boxes (used by mg.SceneQuery and by the OBB obstacle builder) are non-empty. Rendering is unchanged
    (invisible) and PhysX ignores purpose/visibility, so the simulated scene is identical."""
    from pxr import Usd, UsdGeom

    n = 0
    with Usd.EditContext(stage, stage.GetSessionLayer()):
        for sp in prims:
            img = UsdGeom.Imageable(stage.GetPrimAtPath(sp))
            if img and img.ComputePurpose() == UsdGeom.Tokens.guide:
                img.CreatePurposeAttr().Set(UsdGeom.Tokens.default_)
                img.CreateVisibilityAttr().Set(UsdGeom.Tokens.invisible)
                n += 1
    return n


def scene_query_count(robot_path):
    import isaacsim.robot_motion.experimental.motion_generation as mg
    return len(mg.SceneQuery().get_prims_in_aabb(search_box_origin=[0, 0, 0], search_box_minimum=[-10, -10, -10],
                                                 search_box_maximum=[10, 10, 10], tracked_api=mg.TrackableApi.PHYSICS_COLLISION,
                                                 exclude_prim_paths=[robot_path]))


def build_world(robot, robot_path, stage, mc, exclude=()):
    import isaacsim.robot_motion.experimental.motion_generation as mg
    import isaacsim.robot_motion.cumotion as cm

    prims = [p for p in collect_obstacle_prims(stage, robot_path) if not any(p.startswith(e) for e in exclude)]
    from isaacsim.core.experimental.objects import Cone, Cylinder

    tol = mc["collision"]["obstacle_safety_tolerance_m"]
    strategy = mg.ObstacleStrategy()
    strategy.set_default_safety_tolerance(tol)
    # CumotionWorldInterface implements no cylinders/cones (add_cylinders -> NotImplementedError); as in NVIDIA's
    # motion-generation world_binding helper they are represented by their oriented bounding box (conservative).
    for prim_type in (Cylinder, Cone):
        strategy.set_default_configuration(prim_type, mg.ObstacleConfiguration("obb", tol))
    # generic MESH is not implemented by CumotionWorldInterface either; its triangulated-mesh path keeps the real geometry
    from isaacsim.core.experimental.objects import Mesh
    strategy.set_default_configuration(Mesh, mg.ObstacleConfiguration(mg.ObstacleRepresentation.TRIANGULATED_MESH, tol))
    wi = cm.CumotionWorldInterface()
    binding = mg.WorldBinding(world_interface=wi, obstacle_strategy=strategy, tracked_prims=prims,
                              tracked_collision_api=mg.TrackableApi.PHYSICS_COLLISION)
    binding.initialize()
    wi.update_world_to_robot_root_transforms(robot.get_world_poses())
    binding.synchronize_transforms()
    return binding, wi, prims


def base_T_world(wi):
    p, q = wi.get_world_to_robot_base_transform()
    W = T(quat_to_R(q.numpy()), p.numpy())  # world_T_base
    return np.linalg.inv(W), W


# ---------------------------------------------------------------------------
# cuMotion objects
# ---------------------------------------------------------------------------

class Planner:
    def __init__(self, mc, wc, wi):
        import cumotion
        import isaacsim.robot_motion.cumotion as cm

        self.cumotion, self.cm, self.mc, self.wc, self.wi = cumotion, cm, mc, wc, wi
        self.robot = cm.load_cumotion_supported_robot(mc["planner"]["robot_configuration"])
        self.joints = list(self.robot.controlled_joint_names)
        self.tool = mc["planner"]["planning_tool_frame"]
        self.kin = self.robot.kinematics
        self.inspector = cumotion.create_robot_world_inspector(self.robot.robot_description, wi.world_view)
        self.lim = np.array([[self.kin.cspace_coord_limits(i).lower, self.kin.cspace_coord_limits(i).upper] for i in range(len(self.joints))])
        self.vel_lim_robot = np.array([self.kin.cspace_coord_velocity_limit(i) for i in range(len(self.joints))])
        self.hTt = hand_T_tcp(mc)
        self.bTw, self.wTb = base_T_world(wi)

    # --- kinematics in world frame ---
    def hand_world(self, q):
        pose = self.kin.pose(np.asarray(q, float), self.tool)
        M = np.asarray(pose.matrix()) if hasattr(pose, "matrix") else T(np.asarray(pose.rotation.matrix()), np.asarray(pose.translation))
        return self.wTb @ M

    def tcp_world(self, q):
        return self.hand_world(q) @ self.hTt

    # --- world view ---
    def refresh(self):
        self.wi.world_view.update()

    def check_q(self, q):
        q = np.asarray(q, float)
        return {"in_collision": bool(self.inspector.in_collision_with_obstacle(q)),
                "min_distance_m": float(self.inspector.min_distance_to_obstacle(q)),
                "self_collision": bool(self.inspector.in_self_collision(q)),
                "self_pairs": [list(p) for p in self.inspector.frames_in_self_collision(q)][:5],
                "within_limits": bool(np.all(q >= self.lim[:, 0] - 1e-9) and np.all(q <= self.lim[:, 1] + 1e-9))}

    # --- goal: collision-free IK ---
    def solve_goal(self, tcp_targets, seeds):
        """tcp_targets: list of (name, world 4x4). Returns all collision-free solutions with metadata."""
        cu = self.cumotion
        cfg = cu.create_default_collision_free_ik_solver_config(self.robot.robot_description, self.tool, self.wi.world_view)
        solver = cu.create_collision_free_ik_solver(cfg)
        self.refresh()
        sols = []
        for name, W_tcp in tcp_targets:
            W_hand = W_tcp @ np.linalg.inv(self.hTt)
            B = self.bTw @ W_hand
            q_rot = R_to_quat(B[:3, :3])
            tgt = cu.CollisionFreeIkSolver.TaskSpaceTarget(
                cu.CollisionFreeIkSolver.TranslationConstraint.target(B[:3, 3]),
                cu.CollisionFreeIkSolver.OrientationConstraint.target(cu.Rotation3(*q_rot)))
            res = solver.solve(tgt, [np.asarray(s, float) for s in seeds])
            if res.status() != cu.CollisionFreeIkSolver.Results.Status.SUCCESS:
                continue
            for q in res.cspace_positions():
                q = np.asarray(q, float).flatten()
                Wt = self.tcp_world(q)
                sols.append({"target": name, "q": q, "pos_err_m": float(np.linalg.norm(Wt[:3, 3] - W_tcp[:3, 3])),
                             "rot_err_deg": rot_err_deg(Wt[:3, :3], W_tcp[:3, :3]), **self.check_q(q)})
        return sols

    # --- path ---
    def plan_path(self, q_start, q_goal):
        planner = self.cm.GraphBasedMotionPlanner(self.robot, self.wi, tool_frame=self.tool,
                                                  graph_planner_config_filename=self.mc["planner"]["planner_config_file"])
        cfg = planner.get_graph_planner_config()
        try:
            cfg.set_param("seed", self.cumotion.MotionPlannerConfig.ParamValue(int(self.mc["planner"]["planner_seed"])))
        except Exception:
            pass
        self.refresh()
        path = planner.plan_to_cspace_target(np.asarray(q_start, float), np.asarray(q_goal, float))
        if path is None:
            return None
        return np.array([path.get_waypoint_by_index(i) for i in range(path.get_waypoints_count())], float)

    # --- timing ---
    def densify(self, wps, max_step):
        out = [wps[0]]
        for a, b in zip(wps[:-1], wps[1:]):
            n = max(1, int(math.ceil(np.abs(b - a).max() / max_step)))
            for k in range(1, n + 1):
                out.append(a + (b - a) * k / n)
        return np.array(out)

    def time_parameterize(self, wps):
        lim = self.mc["limits"]
        gen = self.cumotion.create_cspace_trajectory_generator(self.kin)
        gen.set_velocity_limits(np.minimum(np.array(lim["max_joint_velocity_rad_s"], float), self.vel_lim_robot))
        gen.set_acceleration_limits(np.array(lim["max_joint_acceleration_rad_s2"], float))
        gen.set_jerk_limits(np.array(lim["max_joint_jerk_rad_s3"], float))
        return gen.generate_trajectory([np.asarray(w, float) for w in wps])

    def sample(self, traj, dt):
        d = traj.domain()
        ts = np.arange(d.lower, d.upper + 1e-9, dt)
        if ts[-1] < d.upper:
            ts = np.append(ts, d.upper)
        Q, V, A = [], [], []
        for t in ts:
            q, v, a, _ = traj.eval_all(float(t))
            Q.append(np.asarray(q).flatten()); V.append(np.asarray(v).flatten()); A.append(np.asarray(a).flatten())
        return ts - d.lower, np.array(Q), np.array(V), np.array(A)


def validate_trajectory(planner, traj, hull_model, hull_boxes, mc, opening, skip_pairs=()):
    """Dense validation of a time-parameterised trajectory (independent of the planner's own edge checks)."""
    cc = mc["collision"]
    t, Q, V, A = planner.sample(traj, cc["trajectory_check_dt_s"])
    lim = mc["limits"]
    planner.refresh()
    insp = [planner.check_q(q) for q in Q]
    hull = []
    for i in range(0, len(Q), cc["hull_check_every_n_samples"]):
        r = hull_model.clearance(Q[i], opening, hull_boxes, None, skip=set(skip_pairs))
        hull.append((float(t[i]), r["min_m"], r["part"], r["box"]))
    r = hull_model.clearance(Q[-1], opening, hull_boxes, None, skip=set(skip_pairs))
    hull.append((float(t[-1]), r["min_m"], r["part"], r["box"]))
    vmax = np.abs(V).max(axis=0)
    amax = np.abs(A).max(axis=0)
    res = {
        "duration_s": float(t[-1]), "samples": len(t),
        "within_position_limits": all(c["within_limits"] for c in insp),
        "max_velocity_rad_s": vmax.tolist(), "velocity_within_limits": bool(np.all(vmax <= np.array(lim["max_joint_velocity_rad_s"]) + 1e-6)),
        "max_acceleration_rad_s2": amax.tolist(),
        "acceleration_within_limits": bool(np.all(amax <= np.array(lim["max_joint_acceleration_rad_s2"]) + 1e-6)),
        "max_joint_step_between_samples_rad": float(np.abs(np.diff(Q, axis=0)).max()) if len(Q) > 1 else 0.0,
        "inspector_world_collision_samples": int(sum(c["in_collision"] for c in insp)),
        "inspector_self_collision_samples": int(sum(c["self_collision"] for c in insp)),
        "inspector_min_distance_m": float(min(c["min_distance_m"] for c in insp)),
        "hull_min_clearance_m": float(min(h[1] for h in hull)), "hull_closest": min(hull, key=lambda h: h[1])[2:],
        "hull_samples": len(hull),
    }
    res["collision_free"] = (res["inspector_world_collision_samples"] == 0 and res["inspector_self_collision_samples"] == 0
                             and res["inspector_min_distance_m"] >= cc["min_inspector_distance_m"]
                             and res["hull_min_clearance_m"] >= cc["min_hull_clearance_m"])
    res["valid"] = res["collision_free"] and res["within_position_limits"] and res["velocity_within_limits"] and res["acceleration_within_limits"]
    return res, (t, Q, V, A)


def plan_validated(planner, q_start, q_goal, hull_model, hull_boxes, mc, opening, skip_pairs=(), log=print):
    """RRT path -> time parameterisation -> dense validation. If the spline leaves the checked corridor,
    densify the RRT polyline and re-time (bounded rounds). Returns (trajectory, waypoints, report) or (None, None, report)."""
    pc = mc["planner"]
    report = {"attempts": []}
    for attempt in range(pc["max_planning_attempts"]):
        wps = planner.plan_path(q_start, q_goal)
        if wps is None:
            report["attempts"].append({"attempt": attempt, "path_found": False})
            log(f"  attempt {attempt}: no path found")
            continue
        raw = wps.copy()
        for rnd in range(pc["max_densify_rounds"] + 1):
            traj = planner.time_parameterize(wps)
            val, samples = validate_trajectory(planner, traj, hull_model, hull_boxes, mc, opening, skip_pairs)
            report["attempts"].append({"attempt": attempt, "path_found": True, "rrt_waypoints": len(raw),
                                       "densify_round": rnd, "timed_waypoints": len(wps), **{k: v for k, v in val.items()}})
            log(f"  attempt {attempt} round {rnd}: {len(raw)} RRT wps -> {len(wps)} timed wps, duration {val['duration_s']:.2f}s, "
                f"valid={val['valid']} (inspector min {val['inspector_min_distance_m']:.3f} m, hull min {val['hull_min_clearance_m']:.3f} m)")
            if val["valid"]:
                report["selected"] = report["attempts"][-1]
                return traj, wps, raw, samples, report
            wps = planner.densify(wps, pc["densify_max_joint_step_rad"] / (2 ** rnd))
    return None, None, None, None, report


def hull_obstacles(stage, wc):
    """Project collision proxies: USD static colliders (layout_validation.usd_static_boxes) + dynamic objects."""
    import layout_geometry as lg
    import layout_validation

    return layout_validation.usd_static_boxes(stage, wc) + lg.tabletop_object_boxes(wc)
