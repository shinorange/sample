#!/usr/bin/env python3
"""geo_builder.py — Programmatic builder/editor for Minecraft Bedrock entity geometry (.geo.json).

Build mob models in Python instead of hand-writing JSON — or load an existing
model for refinement with Model.load(path) (existing UVs stay pinned; new
cubes auto-pack around them; translate_subtree()/remove_bone() for edits):

    from geo_builder import Model

    m = Model("geometry.fennec", texture_size=(64, 64))
    root = m.bone("root", pivot=(0, 0, 0))
    body = m.bone("body", parent="root", pivot=(0, 5, 2))
    body.cube(origin=(-3, 3, -4), size=(6, 5, 9))          # uv auto-packed
    head = m.bone("head", parent="body", pivot=(0, 7, -3))
    head.cube(origin=(-2.5, 6, -7), size=(5, 4, 4))
    head.cube(origin=(-2.5, 10, -6), size=(2, 3, 0))       # 0-thick plane (ear)
    m.save("fennec.geo.json")
    print(m.stats())

Conventions (Bedrock geometry space):
  * Units: 1 unit = 1/16 block ("pixel"). 16 units = 1 block = 1 m.
  * Y is up. (0, 0, 0) = ground point under the entity's center.
  * The mob's FRONT faces -Z (north). Build heads/snouts toward negative Z.
  * Cube `origin` is the corner with the smallest x, y, z; `size` extends
    toward +x, +y, +z. Example: a humanoid head is
    origin=(-4, 24, -4), size=(8, 8, 8).
  * Bone/cube `pivot` is the rotation center in world (model) units.
  * `inflate` grows the cube by N units on every side WITHOUT changing its
    UV footprint — used for overlay shells (clothes, fur) and z-fight offsets.

UV handling:
  * By default every cube gets box-UV, auto-packed into the declared texture
    size with a shelf packer at save() time. Pass uv=(u, v) to pin a cube
    manually; auto cubes will avoid pinned rectangles.
  * Box-UV footprint of a cube of size (w, h, d):
        width  = 2 * (ceil(w) + ceil(d)),  height = ceil(d) + ceil(h)
    Layout (relative to the uv anchor):
        row 1 (v .. v+d):       [d..d+w]=up   [d+w..d+2w]=down
        row 2 (v+d .. v+d+h):   [0..d]=east   [d..d+w]=north(front)
                                [d+w..d+w+d]=west  [d+w+d..2d+2w]=south(back)
  * uv_map() / uv_report() expose the final per-face pixel rectangles so a
    texture-painting script can paint exactly the right pixels.

No third-party dependencies (stdlib only).
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

Vec3 = Tuple[float, float, float]

FACES = ("north", "south", "east", "west", "up", "down")


def _ceil(v: float) -> int:
    return int(math.ceil(v - 1e-9))


@dataclass
class Cube:
    origin: Vec3
    size: Vec3
    uv: Optional[Tuple[int, int]] = None        # None => auto-pack at save()
    inflate: float = 0.0
    mirror: Optional[bool] = None
    pivot: Optional[Vec3] = None                # per-cube rotation pivot
    rotation: Optional[Vec3] = None             # per-cube rotation (degrees)
    per_face_uv: Optional[Dict[str, dict]] = None  # advanced: explicit per-face UV

    def footprint(self) -> Tuple[int, int]:
        """Box-UV footprint (w, h) in texture pixels."""
        w, h, d = (_ceil(abs(s)) for s in self.size)
        return 2 * (w + d), d + h

    def face_rects(self) -> Dict[str, Tuple[int, int, int, int]]:
        """Per-face texture rects (x, y, w, h) relative to texture origin.

        Requires uv to be resolved (after save()/pack_uv()). Zero-area faces
        (from 0-thick planes) are omitted.
        """
        if self.uv is None:
            raise ValueError("UV not resolved yet — call Model.pack_uv() or save() first")
        u, v = self.uv
        w, h, d = (_ceil(abs(s)) for s in self.size)
        rects = {
            "up":    (u + d,         v,     w, d),
            "down":  (u + d + w,     v,     w, d),
            "east":  (u,             v + d, d, h),
            "north": (u + d,         v + d, w, h),
            "west":  (u + d + w,     v + d, d, h),
            "south": (u + d + w + d, v + d, w, h),
        }
        return {f: r for f, r in rects.items() if r[2] > 0 and r[3] > 0}


@dataclass
class Bone:
    name: str
    parent: Optional[str] = None
    pivot: Vec3 = (0.0, 0.0, 0.0)
    rotation: Optional[Vec3] = None
    mirror: Optional[bool] = None
    cubes: List[Cube] = field(default_factory=list)

    def cube(self, origin: Vec3, size: Vec3, uv: Optional[Tuple[int, int]] = None,
             inflate: float = 0.0, mirror: Optional[bool] = None,
             pivot: Optional[Vec3] = None, rotation: Optional[Vec3] = None) -> Cube:
        c = Cube(origin=tuple(origin), size=tuple(size), uv=tuple(uv) if uv else None,
                 inflate=inflate, mirror=mirror,
                 pivot=tuple(pivot) if pivot else None,
                 rotation=tuple(rotation) if rotation else None)
        self.cubes.append(c)
        return c

    def plane(self, origin: Vec3, size: Vec3, **kw) -> Cube:
        """Convenience: a cube that is 0 thick on exactly one axis (fin/ear/whisker)."""
        if list(size).count(0) != 1:
            raise ValueError("plane() needs exactly one zero in size, got %r" % (size,))
        return self.cube(origin, size, **kw)


class Model:
    def __init__(self, identifier: str, texture_size: Tuple[int, int] = (64, 64),
                 visible_bounds: Tuple[float, float, Vec3] = None,
                 format_version: str = "1.12.0"):
        if not identifier.startswith("geometry."):
            identifier = "geometry." + identifier
        self.identifier = identifier
        self.texture_size = tuple(texture_size)
        self.format_version = format_version
        self.visible_bounds = visible_bounds  # (width, height, offset) or None -> auto
        self.bones: List[Bone] = []
        self._by_name: Dict[str, Bone] = {}

    # ---------------------------------------------------------------- bones
    def bone(self, name: str, parent=None, pivot: Vec3 = (0, 0, 0),
             rotation: Optional[Vec3] = None, mirror: Optional[bool] = None) -> Bone:
        if name in self._by_name:
            raise ValueError(f"duplicate bone name: {name}")
        pname = parent.name if isinstance(parent, Bone) else parent
        if pname is not None and pname not in self._by_name:
            raise ValueError(f"parent bone {pname!r} not defined yet (define parents first)")
        b = Bone(name=name, parent=pname, pivot=tuple(pivot),
                 rotation=tuple(rotation) if rotation else None, mirror=mirror)
        self.bones.append(b)
        self._by_name[name] = b
        return b

    def __getitem__(self, name: str) -> Bone:
        return self._by_name[name]

    # -------------------------------------------------------- load & edit
    @classmethod
    def load(cls, path: str, index: int = 0) -> "Model":
        """Load an existing .geo.json for review/refinement.

        Loaded cubes keep their uv anchors (pinned), so pack_uv()/save()
        leaves existing texture mappings untouched — new cubes added
        afterwards auto-pack into the remaining free space. This is the
        backbone of the edit workflow: MOVING cubes never breaks the
        texture; only RESIZING them changes the UV footprint.
        """
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        geos = data.get("minecraft:geometry")
        if not geos:
            raise ValueError(f"{path}: not a 1.12+ bedrock geometry file "
                             "(legacy 1.8 files: convert in Blockbench first)")
        g = geos[index]
        desc = g.get("description", {})
        m = cls(desc.get("identifier", "geometry.unnamed"),
                texture_size=(desc.get("texture_width", 64),
                              desc.get("texture_height", 64)),
                format_version=data.get("format_version", "1.12.0"))
        if "visible_bounds_width" in desc:
            m.visible_bounds = (desc.get("visible_bounds_width"),
                                desc.get("visible_bounds_height"),
                                tuple(desc.get("visible_bounds_offset", (0, 0, 0))))
        for bj in g.get("bones", []):
            b = Bone(name=bj.get("name", "?"), parent=bj.get("parent"),
                     pivot=tuple(bj.get("pivot", (0, 0, 0))),
                     rotation=tuple(bj["rotation"]) if bj.get("rotation") else None,
                     mirror=bj.get("mirror"))
            m.bones.append(b)
            m._by_name[b.name] = b
            for cj in bj.get("cubes", []):
                uv = cj.get("uv", [0, 0])
                c = Cube(origin=tuple(cj.get("origin", (0, 0, 0))),
                         size=tuple(cj.get("size", (0, 0, 0))),
                         uv=None if isinstance(uv, dict) else tuple(uv),
                         inflate=cj.get("inflate", 0.0),
                         mirror=cj.get("mirror"),
                         pivot=tuple(cj["pivot"]) if cj.get("pivot") else None,
                         rotation=tuple(cj["rotation"]) if cj.get("rotation") else None,
                         per_face_uv=uv if isinstance(uv, dict) else None)
                b.cubes.append(c)
        return m

    def subtree(self, name: str) -> List[str]:
        """Names of `name` and all its descendant bones."""
        targets = {name}
        grew = True
        while grew:
            grew = False
            for b in self.bones:
                if b.parent in targets and b.name not in targets:
                    targets.add(b.name)
                    grew = True
        return [b.name for b in self.bones if b.name in targets]

    def translate_subtree(self, name: str, delta: Vec3) -> List[str]:
        """Move a bone and all its descendants (pivots + cubes) by delta.

        Pure translation never changes UV footprints, so the existing
        texture stays valid. Use for proportion fixes: widen the stance,
        raise the head, shift the tail base, etc.
        """
        dx, dy, dz = delta
        moved = self.subtree(name)
        for n in moved:
            b = self._by_name[n]
            b.pivot = (b.pivot[0] + dx, b.pivot[1] + dy, b.pivot[2] + dz)
            for c in b.cubes:
                c.origin = (c.origin[0] + dx, c.origin[1] + dy, c.origin[2] + dz)
                if c.pivot:
                    c.pivot = (c.pivot[0] + dx, c.pivot[1] + dy, c.pivot[2] + dz)
        return moved

    def remove_bone(self, name: str, recursive: bool = True) -> List[str]:
        """Remove a bone. recursive=True also removes descendants;
        recursive=False reattaches children to the removed bone's parent."""
        if name not in self._by_name:
            raise KeyError(name)
        if recursive:
            targets = set(self.subtree(name))
        else:
            targets = {name}
            new_parent = self._by_name[name].parent
            for b in self.bones:
                if b.parent == name:
                    b.parent = new_parent
        self.bones = [b for b in self.bones if b.name not in targets]
        for n in targets:
            self._by_name.pop(n, None)
        return sorted(targets)

    # ------------------------------------------------------------------ UV
    def pack_uv(self, padding: int = 0) -> None:
        """Assign box-UV anchors to every cube with uv=None (shelf packing).

        Cubes are sorted tallest-first and placed left-to-right on shelves.
        Pinned (manual) UV rects are treated as obstacles. Raises ValueError
        with a size suggestion when the texture is too small.
        """
        tw, th = self.texture_size
        obstacles: List[Tuple[int, int, int, int]] = []
        autos: List[Cube] = []
        for b in self.bones:
            for c in b.cubes:
                if c.per_face_uv is not None:
                    continue
                if c.uv is not None:
                    w, h = c.footprint()
                    obstacles.append((c.uv[0], c.uv[1], w, h))
                else:
                    autos.append(c)

        def overlaps(x, y, w, h) -> bool:
            for (ox, oy, ow, oh) in obstacles:
                if x < ox + ow and ox < x + w and y < oy + oh and oy < y + h:
                    return True
            return False

        # Tallest-first scanline packing: for each cube take the topmost,
        # then leftmost, free spot. Simple, deterministic, and never stuck
        # on pinned obstacles (worst case it scans the whole texture).
        autos.sort(key=lambda c: (-c.footprint()[1], -c.footprint()[0]))
        for c in autos:
            w, h = c.footprint()
            w += padding
            h += padding
            if w > tw:
                raise ValueError(
                    f"cube footprint {w}px wider than texture {tw}px — "
                    f"increase texture_size (try {2 * tw}x{2 * th})")
            spot = None
            for y in range(th - h + 1):
                for x in range(tw - w + 1):
                    if not overlaps(x, y, w, h):
                        spot = (x, y)
                        break
                if spot:
                    break
            if spot is None:
                raise ValueError(
                    f"texture {tw}x{th} too small for all cubes — "
                    f"increase texture_size (try {tw * 2}x{th * 2}) or share UVs")
            c.uv = spot
            obstacles.append((spot[0], spot[1], w, h))

    def uv_map(self) -> Dict[str, List[Dict[str, Tuple[int, int, int, int]]]]:
        """{bone_name: [face_rects per cube, ...]} — call after pack_uv()/save()."""
        return {b.name: [c.face_rects() for c in b.cubes] for b in self.bones}

    def uv_report(self) -> str:
        lines = [f"UV map for {self.identifier} ({self.texture_size[0]}x{self.texture_size[1]}):"]
        for b in self.bones:
            for i, c in enumerate(b.cubes):
                lines.append(f"  {b.name}[{i}] size={c.size} uv={c.uv}")
                for f, (x, y, w, h) in c.face_rects().items():
                    lines.append(f"      {f:<5} x={x:<3} y={y:<3} w={w:<3} h={h}")
        return "\n".join(lines)

    # --------------------------------------------------------------- bounds
    def bounding_box(self) -> Tuple[Vec3, Vec3]:
        lo = [1e9] * 3
        hi = [-1e9] * 3
        for b in self.bones:
            for c in b.cubes:
                for i in range(3):
                    a = c.origin[i] - c.inflate
                    z = c.origin[i] + c.size[i] + c.inflate
                    lo[i] = min(lo[i], a, z)
                    hi[i] = max(hi[i], a, z)
        if lo[0] > hi[0]:
            return (0, 0, 0), (0, 0, 0)
        return tuple(lo), tuple(hi)

    # ----------------------------------------------------------------- save
    def to_dict(self) -> dict:
        self.pack_uv()
        lo, hi = self.bounding_box()
        if self.visible_bounds:
            vb_w, vb_h, vb_off = self.visible_bounds
        else:
            vb_w = max(hi[0] - lo[0], hi[2] - lo[2]) / 16.0 + 1
            vb_h = (hi[1] - lo[1]) / 16.0 + 0.5
            vb_off = (0, (hi[1] + lo[1]) / 32.0, 0)
        bones_json = []
        for b in self.bones:
            bj: dict = {"name": b.name, "pivot": list(b.pivot)}
            if b.parent:
                bj["parent"] = b.parent
            if b.rotation:
                bj["rotation"] = list(b.rotation)
            if b.mirror is not None:
                bj["mirror"] = b.mirror
            if b.cubes:
                cubes_json = []
                for c in b.cubes:
                    cj: dict = {"origin": list(c.origin), "size": list(c.size)}
                    if c.per_face_uv is not None:
                        cj["uv"] = c.per_face_uv
                    else:
                        cj["uv"] = list(c.uv)
                    if c.inflate:
                        cj["inflate"] = c.inflate
                    if c.mirror is not None:
                        cj["mirror"] = c.mirror
                    if c.rotation:
                        cj["rotation"] = list(c.rotation)
                        cj["pivot"] = list(c.pivot if c.pivot else (0, 0, 0))
                    cubes_json.append(cj)
                bj["cubes"] = cubes_json
            bones_json.append(bj)
        return {
            "format_version": self.format_version,
            "minecraft:geometry": [{
                "description": {
                    "identifier": self.identifier,
                    "texture_width": self.texture_size[0],
                    "texture_height": self.texture_size[1],
                    "visible_bounds_width": round(vb_w, 3),
                    "visible_bounds_height": round(vb_h, 3),
                    "visible_bounds_offset": [round(v, 3) for v in vb_off],
                },
                "bones": bones_json,
            }],
        }

    def save(self, path: str, indent: int = 2) -> None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=indent)
            f.write("\n")

    # ---------------------------------------------------------------- stats
    def stats(self) -> str:
        n_cubes = sum(len(b.cubes) for b in self.bones)
        n_planes = sum(1 for b in self.bones for c in b.cubes if 0 in c.size)
        lo, hi = self.bounding_box()
        used = 0
        for b in self.bones:
            for c in b.cubes:
                w, h = c.footprint()
                used += w * h
        tw, th = self.texture_size
        return (f"{self.identifier}: {len(self.bones)} bones, {n_cubes} cubes "
                f"({n_planes} planes), bbox {tuple(round(v, 1) for v in lo)}"
                f"..{tuple(round(v, 1) for v in hi)} units, "
                f"UV usage ~{100 * used // (tw * th)}% of {tw}x{th}")


# ------------------------------------------------------------------ helpers
def segment_chain(model: Model, base_name: str, parent, start: Vec3,
                  direction: Vec3, seg_size: Vec3, count: int,
                  bend_deg: Vec3 = (0, 0, 0), taper: float = 0.0,
                  inflate: float = 0.0, inflate_step: float = 0.0):
    """Create a chain of bones+cubes (tail, tentacle, neck, vine...).

    Each segment is a child of the previous one, pivoted at its base, with an
    incremental `bend_deg` rotation — small per-segment angles add up to a
    smooth organic curve that still animates well.

    start:        pivot of the first segment (base of the chain)
    direction:    unit-ish axis the chain grows along, e.g. (0, 0, 1) backward
    seg_size:     (w, h, l) of one segment along its local axes
    taper:        units to shrink w/h per segment. Fractional tapers break
                  box-UV alignment — prefer integer taper, or use
                  inflate_step for sub-unit tapering with integer sizes.
    inflate_step: added to inflate each segment (e.g. -0.25 thins the chain
                  toward the tip while keeping sizes integer)
    Returns the list of created bones (tip last).
    """
    dx, dy, dz = direction
    if sum(1 for d in (dx, dy, dz) if d) != 1:
        raise ValueError("direction must be a single cardinal axis, e.g. (0,0,-1)")
    axis = 0 if dx else (1 if dy else 2)
    sign = (dx + dy + dz) > 0

    bones = []
    pname = parent.name if isinstance(parent, Bone) else parent
    px, py, pz = start
    w, h, length = seg_size
    for i in range(count):
        b = model.bone(f"{base_name}_{i}", parent=pname, pivot=(px, py, pz),
                       rotation=tuple(bend_deg) if any(bend_deg) else None)
        # cross-section w x h perpendicular to the axis, `length` along it
        if axis == 2:    # z
            o = [px - w / 2, py - h / 2, pz if sign else pz - length]
            s = [w, h, length]
        elif axis == 1:  # y
            o = [px - w / 2, py if sign else py - length, pz - h / 2]
            s = [w, length, h]
        else:            # x
            o = [px if sign else px - length, py - h / 2, pz - w / 2]
            s = [length, h, w]
        b.cube(origin=tuple(o), size=tuple(s), inflate=inflate)
        bones.append(b)
        step = length if sign else -length
        px, py, pz = (px + step if axis == 0 else px,
                      py + step if axis == 1 else py,
                      pz + step if axis == 2 else pz)
        w = max(1.0, w - taper)
        h = max(1.0, h - taper)
        inflate += inflate_step
        pname = b.name
    return bones


if __name__ == "__main__":
    # Smoke test: classic humanoid proportions.
    m = Model("geometry.demo_humanoid", texture_size=(64, 64))
    m.bone("root", pivot=(0, 0, 0))
    body = m.bone("body", parent="root", pivot=(0, 12, 0))
    body.cube(origin=(-4, 12, -2), size=(8, 12, 4))
    head = m.bone("head", parent="body", pivot=(0, 24, 0))
    head.cube(origin=(-4, 24, -4), size=(8, 8, 8))
    for side, sx in (("right", -1), ("left", 1)):
        arm = m.bone(f"arm_{side}", parent="body", pivot=(sx * 5, 22, 0))
        arm.cube(origin=(sx * 4 if sx > 0 else -8, 12, -2), size=(4, 12, 4),
                 mirror=(sx > 0))
        leg = m.bone(f"leg_{side}", parent="root", pivot=(sx * 1.9, 12, 0))
        leg.cube(origin=(sx * 1.9 - 2, 0, -2), size=(4, 12, 4), mirror=(sx > 0))
    m.save("/tmp/demo_humanoid.geo.json")
    print(m.stats())
    print(m.uv_report())
