"""Physics execution of planned trajectories through the Franka articulation controller.

Control runs in a PhysX post-step callback (SimulationEvent.PHYSICS_POST_STEP), so the command rate equals the
physics rate (120 Hz) in both headless and GUI mode, independent of rendering. Trajectory phases use
mg.TrajectoryFollower with isaacsim.robot_motion.cumotion.CumotionTrajectory and apply joint position (and
velocity feed-forward) targets with Articulation.set_dof_position_targets / set_dof_velocity_targets.
Nothing is teleported: joints are only driven through their PhysX joint drives.
"""

from __future__ import annotations

import numpy as np

import motion_utils as mu


class Executor:
    def __init__(self, art, hand_rp, links_rp, link_names, filter_paths, planner, mc, log=print):
        import isaacsim.robot_motion.experimental.motion_generation as mg
        import warp as wp

        self.mg, self.wp = mg, wp
        self.art, self.hand_rp, self.links_rp = art, hand_rp, links_rp
        self.link_names, self.filter_paths = link_names, filter_paths
        self.planner, self.mc, self.log = planner, mc, log
        self.joint_space = list(art.dof_names)
        self.arm_names = planner.joints
        self.arm_idx = [self.joint_space.index(n) for n in self.arm_names]
        self.finger_idx = [i for i, n in enumerate(self.joint_space) if "finger" in n]
        self.phases, self.k, self.phase_t0, self.t = [], -1, 0.0, 0.0
        self.rows, self.contact_max = [], {}
        self.follower = None
        self.done, self.needs_planning, self._cb = False, False, None
        self.events = []

    # ---------------- phases ----------------
    def add_hold(self, name, q_hold, duration, tcp_target):
        self.phases.append({"name": name, "kind": "hold", "q": np.asarray(q_hold, float), "duration": float(duration), "tcp_target": tcp_target})

    def add_trajectory(self, name, traj, tcp_target):
        d = traj.domain()
        self.phases.append({"name": name, "kind": "traj", "traj": traj, "duration": float(d.upper - d.lower),
                            "q_end": np.asarray(traj.eval(d.upper), float).flatten(), "tcp_target": tcp_target})

    def add_planning_break(self, name):
        self.phases.append({"name": name, "kind": "plan", "duration": 0.0})

    # ---------------- state ----------------
    def _estimated(self):
        mg = self.mg
        js = self.joint_space
        return mg.RobotState(joints=mg.JointState.from_name(robot_joint_space=js, positions=(js, self.art.get_dof_positions()),
                                                            velocities=(js, self.art.get_dof_velocities())))

    def _start_phase(self, k):
        self.k = k
        if k >= len(self.phases):
            self.done = True
            return
        ph = self.phases[k]
        self.phase_t0 = self.t
        self.events.append({"t": self.t, "event": f"start:{ph['name']}"})
        self.log(f"[exec] t={self.t:7.3f}s start phase '{ph['name']}' ({ph['kind']}, {ph['duration']:.3f}s)")
        if ph["kind"] == "plan":
            self.needs_planning = True
        elif ph["kind"] == "traj":
            import isaacsim.robot_motion.cumotion as cm
            ctraj = cm.CumotionTrajectory(trajectory=ph["traj"], robot_joint_space=self.joint_space, cumotion_robot=self.planner.robot)
            self.follower = self.mg.TrajectoryFollower()
            self.follower.set_trajectory(ctraj)
            if not self.follower.reset(self._estimated(), None, self.t):
                raise RuntimeError(f"TrajectoryFollower.reset failed for phase {ph['name']}")

    def resume_after_planning(self):
        self.needs_planning = False
        self._start_phase(self.k + 1)

    # ---------------- physics callback ----------------
    def start(self):
        from isaacsim.core.simulation_manager import SimulationEvent, SimulationManager

        fp = self.mc["execution"]["finger_position_m"]
        self.art.set_dof_position_targets(self.wp.array(np.array([[fp] * len(self.finger_idx)], np.float32)), dof_indices=self.finger_idx)
        self._start_phase(0)
        self._cb = SimulationManager.register_callback(self.on_step, event=SimulationEvent.PHYSICS_POST_STEP)

    def stop(self):
        from isaacsim.core.simulation_manager import SimulationManager
        if self._cb is not None:
            SimulationManager.deregister_callback(self._cb)
            self._cb = None

    def on_step(self, dt, context):
        if self.done or self.needs_planning:
            return
        self.t += dt
        ph = self.phases[self.k]
        tau = self.t - self.phase_t0
        q_meas = self.art.get_dof_positions().numpy()[0].astype(float)
        v_meas = self.art.get_dof_velocities().numpy()[0].astype(float)
        # ---- command for the next step ----
        if ph["kind"] == "hold":
            q_cmd, v_cmd = ph["q"], np.zeros(7)
            self.art.set_dof_position_targets(self.wp.array(q_cmd[None].astype(np.float32)), dof_indices=self.arm_idx)
            if self.mc["execution"]["use_velocity_feedforward"]:
                self.art.set_dof_velocity_targets(self.wp.array(v_cmd[None].astype(np.float32)), dof_indices=self.arm_idx)
        else:
            desired = self.follower.forward(self._estimated(), None, self.t)
            if desired is None or desired.joints is None or desired.joints.positions is None:
                q_cmd, v_cmd = ph["q_end"], np.zeros(7)
                self.art.set_dof_position_targets(self.wp.array(q_cmd[None].astype(np.float32)), dof_indices=self.arm_idx)
            else:
                js = desired.joints
                self.art.set_dof_position_targets(js.positions, dof_indices=js.position_indices)  # as in trajectory_example.py
                pos = js.positions.numpy().reshape(-1)
                idx = [int(i) for i in np.asarray(js.position_indices.numpy() if hasattr(js.position_indices, "numpy") else js.position_indices).reshape(-1)]
                q_cmd = np.array([pos[idx.index(i)] for i in self.arm_idx])
                v_cmd = np.zeros(7)
                if js.velocities is not None and self.mc["execution"]["use_velocity_feedforward"]:
                    self.art.set_dof_velocity_targets(js.velocities, dof_indices=js.velocity_indices)
                    vel = js.velocities.numpy().reshape(-1)
                    vidx = [int(i) for i in np.asarray(js.velocity_indices.numpy() if hasattr(js.velocity_indices, "numpy") else js.velocity_indices).reshape(-1)]
                    v_cmd = np.array([vel[vidx.index(i)] for i in self.arm_idx])
        # ---- record ----
        hp, ho = self.hand_rp.get_world_poses()
        W_tcp = mu.T(mu.quat_to_R(ho.numpy()[0]), hp.numpy()[0]) @ self.planner.hTt
        tgt = ph.get("tcp_target")
        base_p, _ = self.art.get_world_poses()
        try:
            F = np.linalg.norm(np.asarray(self.links_rp.get_contact_force_matrix(dt=dt).numpy()), axis=2)  # (links, filters)
            for li, fi in zip(*np.nonzero(F > 1e-6)):
                key = (self.link_names[li], self.filter_paths[fi])
                self.contact_max[key] = max(self.contact_max.get(key, 0.0), float(F[li, fi]))
            fmax = float(F.max())
        except Exception as exc:
            fmax = float("nan")
            if not any(e["event"].startswith("contact_readback_error") for e in self.events):
                self.events.append({"t": self.t, "event": f"contact_readback_error: {exc}"})
        self.rows.append({"t": self.t, "phase": ph["name"], "q_cmd": np.asarray(q_cmd, float), "v_cmd": np.asarray(v_cmd, float),
                          "q_meas": q_meas[:7], "v_meas": v_meas[:7], "fingers": q_meas[7:], "tcp": W_tcp.copy(),
                          "tcp_target": None if tgt is None else tgt.copy(), "base": base_p.numpy()[0].astype(float), "contact_max_N": fmax})
        # ---- phase transitions (after the full duration; holds verify convergence later) ----
        if tau >= ph["duration"] - 1e-9:
            self._start_phase(self.k + 1)
