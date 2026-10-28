"""Franka Panda kinematic + collision model for layout evaluation (run inside Isaac Sim's python.sh).

* IK / FK: Lula kinematics (isaacsim.robot_motion.motion_generation) with NVIDIA's Franka description,
  base pose from the config. TCP = Lula frame `right_gripper` (config gripper.tcp_frame).
* Collision geometry: the robot's own PhysX colliders from the official USD asset. Every link has one
  convex-hull collider; its hull vertices plus face centroids are expressed in the link frame and placed at
  the Lula FK link poses. Fingers are placed from the hand frame and the requested opening.
* Clearance: signed point-to-box distance against the static scene boxes (layout_geometry.OBB). This is an
  endpoint (configuration) check, not a swept/continuous check; between hull vertices on a large flat
  face, a box edge can intrude by up to the face sampling distance (hull face centroids reduce this).

Nothing here moves the simulated robot.
"""

from __future__ import annotations

import math
import os

import numpy as np

LINKS = ["panda_link0", "panda_link1", "panda_link2", "panda_link3", "panda_link4", "panda_link5",
         "panda_link6", "panda_link7", "panda_hand", "panda_leftfinger", "panda_rightfinger"]


def quat_wxyz_from_R(R):
    from scipy.spatial.transform import Rotation
    x, y, z, w = Rotation.from_matrix(R).as_quat()
    return [float(w), float(x), float(y), float(z)]


def topdown_R(yaw):
    """TCP pointing down (Rx(pi)) then rotated by yaw about world Z. Columns: x_tcp, y_tcp (finger axis), z_tcp."""
    c, s = math.cos(yaw), math.sin(yaw)
    return np.array([[c, s, 0.0], [s, -c, 0.0], [0.0, 0.0, -1.0]])


class RobotModel:
    def __init__(self, cfg, stage, simulation_app):
        from isaacsim.core.utils.extensions import enable_extension, get_extension_path_from_name
        from pxr import Usd, UsdGeom, UsdPhysics

        self.cfg, self.g = cfg, cfg["gripper"]
        rc = cfg["robot"]
        enable_extension(rc["ik"]["extension"])
        simulation_app.update()
        from isaacsim.robot_motion.motion_generation import LulaKinematicsSolver

        ext = get_extension_path_from_name(rc["ik"]["extension"])
        self.solver = LulaKinematicsSolver(robot_description_path=os.path.join(ext, rc["ik"]["robot_description"]),
                                           urdf_path=os.path.join(ext, rc["ik"]["urdf"]))
        yaw = math.radians(rc["base_yaw_deg"])
        self.base_pos = np.array(rc["base_position"], float)
        self.base_quat = np.array([math.cos(yaw / 2), 0, 0, math.sin(yaw / 2)])
        self.solver.set_robot_base_pose(self.base_pos, self.base_quat)
        self.joint_names = list(self.solver.get_joint_names())
        self.frames = set(self.solver.get_all_frame_names())
        self.tcp = self.g["tcp_frame"]
        self.home = np.radians([rc["home_joint_positions_deg"][n] for n in self.joint_names])

        # joint limits from the robot USD (degrees -> rad)
        rpath = rc["mount_prim"] + "/" + rc["prim_name"]
        robot = stage.GetPrimAtPath(rpath)
        lim = {}
        for p in Usd.PrimRange(robot, Usd.TraverseInstanceProxies()):
            if p.IsA(UsdPhysics.RevoluteJoint) and p.GetName() in self.joint_names:
                j = UsdPhysics.RevoluteJoint(p)
                lim[p.GetName()] = (math.radians(j.GetLowerLimitAttr().Get()), math.radians(j.GetUpperLimitAttr().Get()))
        self.lower = np.array([lim[n][0] for n in self.joint_names])
        self.upper = np.array([lim[n][1] for n in self.joint_names])

        # collider points in link frames (USD authored pose)
        from scipy.spatial import ConvexHull

        self.link_pts, self.link_usd_world = {}, {}
        links = {p.GetName(): p for p in Usd.PrimRange(robot, Usd.TraverseInstanceProxies()) if p.HasAPI(UsdPhysics.RigidBodyAPI)}
        for name in LINKS:
            lp = links[name]
            lw = UsdGeom.Xformable(lp).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            self.link_usd_world[name] = np.array(lw).T  # column-vector convention
            pts = []
            for cprim in Usd.PrimRange(lp, Usd.TraverseInstanceProxies()):
                if not cprim.HasAPI(UsdPhysics.CollisionAPI) or not cprim.IsA(UsdGeom.Mesh):
                    continue
                cw = UsdGeom.Xformable(cprim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
                rel = np.array(cw * lw.GetInverse()).T
                P = np.array(UsdGeom.Mesh(cprim).GetPointsAttr().Get(), float)
                P = (rel[:3, :3] @ P.T).T + rel[:3, 3]
                hull = ConvexHull(P)
                V = P[hull.vertices]
                C = P[hull.simplices].mean(axis=1)
                pts.append(np.vstack([V, C]))
            self.link_pts[name] = np.vstack(pts)
        # finger poses relative to the hand at the authored (closed) opening
        hw = self.link_usd_world["panda_hand"]
        self.finger_rel = {f: np.linalg.inv(hw) @ self.link_usd_world[f] for f in ("panda_leftfinger", "panda_rightfinger")}

    # ---------------- kinematics ----------------
    def fk(self, q, frame=None):
        p, R = self.solver.compute_forward_kinematics(frame or self.tcp, np.asarray(q, float))
        return np.array(p, float), np.array(R, float)

    def link_poses(self, q, opening):
        T = {}
        for n in LINKS[:9]:
            p, R = self.fk(q, n)
            M = np.eye(4)
            M[:3, :3], M[:3, 3] = R, p
            T[n] = M
        for f, sign in (("panda_leftfinger", 1.0), ("panda_rightfinger", -1.0)):
            M = T["panda_hand"] @ self.finger_rel[f]
            M[:3, 3] += T["panda_hand"][:3, 1] * sign * opening / 2  # prismatic along hand +/-Y
            T[f] = M
        return T

    def fk_consistency(self):
        """Lula FK at q = 0 vs. the USD-authored (zero-pose) link frames."""
        q0 = np.zeros(len(self.joint_names))
        out = {}
        for n in LINKS[:9]:
            p, R = self.fk(q0, n)
            W = self.link_usd_world[n]
            out[n] = {"pos_err_m": float(np.linalg.norm(p - W[:3, 3])),
                      "rot_err_deg": float(np.degrees(np.arccos(np.clip((np.trace(R.T @ W[:3, :3]) - 1) / 2, -1, 1))))}
        return out

    def jacobian(self, q, eps=1e-5):
        p0, R0 = self.fk(q)
        J = np.zeros((6, len(q)))
        for i in range(len(q)):
            dq = np.array(q, float)
            dq[i] += eps
            p1, R1 = self.fk(dq)
            dR = R1 @ R0.T
            w = np.array([dR[2, 1] - dR[1, 2], dR[0, 2] - dR[2, 0], dR[1, 0] - dR[0, 1]]) / 2
            J[:3, i], J[3:, i] = (p1 - p0) / eps, w / eps
        return J

    def quality(self, q):
        J = self.jacobian(q)
        sv = np.linalg.svd(J, compute_uv=False)
        rng_ = self.upper - self.lower
        margin = np.minimum(q - self.lower, self.upper - q)
        return {"manipulability": float(np.sqrt(max(np.linalg.det(J @ J.T), 0.0))), "min_singular_value": float(sv.min()),
                "condition_number": float(sv.max() / max(sv.min(), 1e-12)),
                "min_joint_margin_rad": float(margin.min()), "min_joint_margin_frac": float((margin / rng_).min()),
                "joint_with_min_margin": self.joint_names[int(np.argmin(margin / rng_))],
                "within_limits": bool(np.all(q >= self.lower - 1e-6) and np.all(q <= self.upper + 1e-6))}

    def ik(self, pos, R, warm=None, seeds=4, rng=None):
        rc = self.cfg["robot"]["ik"]
        rng = rng or np.random.default_rng(0)
        starts = ([warm] if warm is not None else []) + [self.home] + [
            np.clip(self.home + rng.normal(0, 0.6, len(self.home)), self.lower, self.upper) for _ in range(seeds)]
        sols = []
        q_wxyz = quat_wxyz_from_R(R)
        for s in starts:
            q, ok = self.solver.compute_inverse_kinematics(self.tcp, np.asarray(pos, float), np.array(q_wxyz), warm_start=s,
                                                           position_tolerance=rc["position_tolerance_m"],
                                                           orientation_tolerance=rc["orientation_tolerance_rad"])
            if ok:
                q = np.asarray(q, float)
                p, Rq = self.fk(q)
                err_p = float(np.linalg.norm(p - pos))
                err_r = float(np.degrees(np.arccos(np.clip((np.trace(Rq.T @ R) - 1) / 2, -1, 1))))
                sols.append((q, err_p, err_r))
        return sols

    # ---------------- collision ----------------
    def robot_points(self, q, opening):
        T = self.link_poses(q, opening)
        return {n: (T[n][:3, :3] @ self.link_pts[n].T).T + T[n][:3, 3] for n in LINKS}

    def clearance(self, q, opening, boxes, carried=None, skip=()):
        """Minimum signed distance robot(+carried object) -> boxes. skip: set of (part, box_name) pairs."""
        pts = self.robot_points(q, opening)
        if carried is not None:
            pts["carried_object"] = carried
        best = {"min_m": np.inf, "part": None, "box": None, "per_part": {}}
        for part, P in pts.items():
            pm = np.inf
            for b in boxes:
                if (part, b.name) in skip or (part, b.group) in skip or ("*", b.name) in skip or (part, "*") in skip:
                    continue
                d = float(b.signed_distance(P).min())
                if d < pm:
                    pm = d
                if d < best["min_m"]:
                    best.update(min_m=d, part=part, box=b.name)
            best["per_part"][part] = pm
        return best


def carried_points(cfg, key, tcp_pos, R_tcp):
    """Sampled collision proxy of the carried object (rings on its outer profile), placed under the TCP."""
    o = cfg["objects"][key]
    g = o["grasp"]
    H = o["height"]
    if key == "paper_cup":
        prof = [(o["bottom_diameter"] / 2 + (o["top_diameter"] - o["bottom_diameter"]) / 2 * z / H, z) for z in np.linspace(0, H, 12)]
    else:
        R, zb, zs = o["body_diameter"] / 2, o["body_top_z"], o["shoulder_top_z"]
        rn = (o.get("lip_diameter") or o.get("cap_diameter") or o["neck_diameter"]) / 2
        prof = [(R, z) for z in np.linspace(0, zb, 8)] + [(R + (rn - R) * u, zb + (zs - zb) * u) for u in np.linspace(0, 1, 5)]
        prof += [(rn, z) for z in np.linspace(zs, H, 4)]
    ang = np.linspace(0, 2 * np.pi, 16, endpoint=False)
    P = np.array([[r * math.cos(a), r * math.sin(a), z] for r, z in prof for a in ang] + [[0, 0, 0], [0, 0, H]])
    finger_axis = R_tcp[:, 1]
    bottom_centre = np.asarray(tcp_pos) - np.array([0, 0, g["tcp_height_from_bottom"]]) + finger_axis * g["tcp_offset_along_finger_axis_m"]
    return P + bottom_centre, bottom_centre
