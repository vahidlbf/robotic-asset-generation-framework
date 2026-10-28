"""GUI-side helpers that keep viewport edits consistent with the PhysX rigid bodies.

Root cause addressed: each dynamic object is a rigid body on its asset root
(/World/Objects/<Name>), with the render mesh (Visual/...) and colliders (Collision/...) as children.
A viewport click selects the deepest prim (the render mesh), so dragging it only offsets the *visual*
relative to its body; the body (and its invisible colliders) stays on the table and the object looks
suspended after Play.

RigidBodyGuard watches transform edits on descendants of the watched rigid bodies. When a descendant
has been edited and the edit has been stable for `settle_updates` app updates (i.e. the gizmo drag
ended), the world-space offset is transferred to the rigid-body root and the descendant's own
transform is restored. A root xform edit is picked up by PhysX both when stopped (parsed on Play) and
while playing (verified numerically by diagnose_gui_physics.py). Transfers are logged to the console.

teleport()/reset_to_pose() move bodies with the physics tensor API while playing (pose + zero
velocity) and with a USD root edit while stopped.
"""

from __future__ import annotations

from pxr import Gf, Tf, Usd, UsdGeom


def _local(prim):
    return UsdGeom.Xformable(prim).GetLocalTransformation(Usd.TimeCode.Default())


def _world(prim):
    return UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())


def _set_root_world(prim, world):
    """Author translate + orient on the root (keeps scale 1, matches the scene's op convention)."""
    parent_w = _world(prim.GetParent())
    local = world * parent_w.GetInverse()
    tr = Gf.Transform(local)
    xf = UsdGeom.Xformable(prim)
    ops = {op.GetOpName(): op for op in xf.GetOrderedXformOps()}
    if "xformOp:translate" in ops and "xformOp:orient" in ops and len(ops) == 2:
        ops["xformOp:translate"].Set(Gf.Vec3d(tr.GetTranslation()))
        q = tr.GetRotation().GetQuat()
        ops["xformOp:orient"].Set(type(ops["xformOp:orient"].Get())(q))
    else:
        xf.ClearXformOpOrder()
        xf.AddTransformOp(UsdGeom.XformOp.PrecisionDouble).Set(local)


def _restore_local(prim, saved):
    """Restore a descendant's authored transform to the state captured at load time."""
    xf = UsdGeom.Xformable(prim)
    order, values = saved
    xf.ClearXformOpOrder()
    for name in order:
        attr = prim.GetAttribute(name)
        if attr and name in values:
            attr.Set(values[name])
    xf.GetXformOpOrderAttr().Set(order)


class RigidBodyGuard:
    def __init__(self, stage, body_paths, settle_updates=12, log=print):
        self.stage, self.log, self.settle = stage, log, settle_updates
        self.bodies = [stage.GetPrimAtPath(p) for p in body_paths]
        self.saved = {}  # descendant path -> (xformOpOrder, {op: value}, rest local matrix)
        for b in self.bodies:
            for d in Usd.PrimRange(b):
                if d != b and d.IsA(UsdGeom.Xformable):
                    xf = UsdGeom.Xformable(d)
                    order = list(xf.GetXformOpOrderAttr().Get() or [])
                    vals = {n: d.GetAttribute(n).Get() for n in order if d.GetAttribute(n)}
                    self.saved[str(d.GetPath())] = (order, vals, _local(d))
        self.pending = {}  # descendant path -> updates since last change
        self.transfers = []
        self._busy = False
        self._listener = Tf.Notice.Register(Usd.Notice.ObjectsChanged, self._on_changed, stage)

    def _owner(self, path):
        for b in self.bodies:
            if path.HasPrefix(b.GetPath()) and path != b.GetPath():
                return b
        return None

    def _on_changed(self, notice, sender):
        if self._busy:
            return
        for p in list(notice.GetChangedInfoOnlyPaths()) + list(notice.GetResyncedPaths()):
            prim_path = p.GetPrimPath()
            if not p.IsPropertyPath() or not p.name.startswith("xformOp"):
                continue
            if str(prim_path) in self.saved and self._owner(prim_path) is not None:
                self.pending[str(prim_path)] = 0

    def update(self):
        """Call once per app update. Transfers settled descendant edits to their rigid-body root."""
        done = []
        for path, age in list(self.pending.items()):
            if age < self.settle:
                self.pending[path] = age + 1
                continue
            done.append(path)
        for path in done:
            del self.pending[path]
            prim = self.stage.GetPrimAtPath(path)
            body = self._owner(prim.GetPath())
            order, vals, rest_local = self.saved[path]
            if Gf.IsClose(_local(prim), rest_local, 1e-9):
                continue
            # world transform the user gave the descendant, and where it sits with its rest local
            w_edit = _world(prim)
            w_rest = rest_local * _world(prim.GetParent())
            body_w = _world(body)
            new_body_w = body_w * w_rest.GetInverse() * w_edit
            self._busy = True
            try:
                _set_root_world(body, new_body_w)
                _restore_local(prim, (order, vals))
            finally:
                self._busy = False
            moved = new_body_w.ExtractTranslation() - body_w.ExtractTranslation()
            rec = {"edited": path, "body": str(body.GetPath()), "delta_m": [round(x, 4) for x in moved]}
            self.transfers.append(rec)
            self.log(f"[guard] '{path}' was moved inside rigid body '{body.GetPath()}'; "
                     f"transferred offset {rec['delta_m']} m to the rigid body so physics follows the visual.")

    def close(self):
        if self._listener:
            self._listener.Revoke()
            self._listener = None


def teleport(stage, rigid_prims, path, position, orientation=None, playing=False):
    """Move a rigid body safely: physics API while playing (pose + zero velocity), USD root edit when stopped."""
    if playing:
        rp = rigid_prims[path]
        p, q = rp.get_world_poses()
        rp.set_world_poses(positions=[list(position)], orientations=[orientation if orientation is not None else q.numpy()[0]])
        rp.set_velocities(linear_velocities=[[0.0, 0.0, 0.0]], angular_velocities=[[0.0, 0.0, 0.0]])
    else:
        prim = stage.GetPrimAtPath(path)
        w = _world(prim)
        r = Gf.Matrix4d(1)
        r.SetRotateOnly(w.ExtractRotationQuat() if orientation is None else
                        Gf.Quatd(orientation[0], Gf.Vec3d(*orientation[1:])))
        r.SetTranslateOnly(Gf.Vec3d(*position))
        _set_root_world(prim, r)
