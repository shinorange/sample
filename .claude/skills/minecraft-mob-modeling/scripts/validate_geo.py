#!/usr/bin/env python3
"""validate_geo.py — Lint a Minecraft Bedrock entity geometry (.geo.json).

Usage:
    python3 validate_geo.py model.geo.json [--texture texture.png] [--strict]

Checks (E = error, W = warning):
  E structure     format_version / minecraft:geometry / description present,
                  identifier starts with "geometry."
  E bones         duplicate names, unknown parents, parent cycles
  E uv-bounds     box-UV footprints and per-face UVs stay inside the declared
                  texture_width/height
  W uv-overlap    two cubes' box-UV rects overlap (texture bleeding, unless
                  sharing is intentional e.g. mirrored limbs)
  W fractional    box-UV cube with fractional size (texture bleeds across
                  face borders; per-face UV or integer sizes are safer)
  W z-fight       two UNROTATED cubes (after bone translation only) have
                  coplanar overlapping faces — they will flicker in-game.
                  Fix with inflate (+/-0.25) or by moving a face 0.1+ units.
  W pivot         bone pivot far outside the model's bounding box
  W texture       (--texture) file dimensions are not an integer multiple of
                  texture_width/height; stray semi-transparent pixels
  W plane         zero-thickness cube note (fine, but must be intentional)

Exit code: 1 if any errors (or, with --strict, any warnings), else 0.

The z-fight check only sees axis-aligned geometry: rotated bones/cubes are
skipped (rotation almost always breaks coplanarity anyway).
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from typing import Dict, List, Optional, Tuple

EPS = 1e-6


def ceil_(v: float) -> int:
    return int(math.ceil(abs(v) - 1e-9))


class Report:
    def __init__(self) -> None:
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def error(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def dump(self) -> None:
        for e in self.errors:
            print(f"  E {e}")
        for w in self.warnings:
            print(f"  W {w}")


def load_geometry(path: str, rep: Report) -> Optional[dict]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        rep.error(f"cannot read/parse JSON: {exc}")
        return None
    if "minecraft:geometry" not in data:
        # legacy 1.8 format uses "geometry.name" top-level keys
        legacy = [k for k in data if k.startswith("geometry.")]
        if legacy:
            rep.error("legacy 1.8 format detected — re-export as 1.12.0+ "
                      "(Blockbench: File > Convert Project > Bedrock Entity)")
        else:
            rep.error("missing 'minecraft:geometry' array")
        return None
    if not data.get("format_version"):
        rep.warn("missing format_version (expected e.g. \"1.12.0\")")
    geos = data["minecraft:geometry"]
    if not isinstance(geos, list) or not geos:
        rep.error("'minecraft:geometry' must be a non-empty array")
        return None
    if len(geos) > 1:
        rep.warn(f"file contains {len(geos)} geometries; validating the first only")
    return geos[0]


def box_uv_rect(uv, size) -> Tuple[int, int, int, int]:
    w, h, d = (ceil_(s) for s in size)
    return int(uv[0]), int(uv[1]), 2 * (w + d), d + h


def face_uv_rects(uv, size) -> Dict[str, Tuple[float, float, float, float]]:
    w, h, d = (ceil_(s) for s in size)
    u, v = uv
    return {
        "up":    (u + d, v, w, d),
        "down":  (u + d + w, v, w, d),
        "east":  (u, v + d, d, h),
        "north": (u + d, v + d, w, h),
        "west":  (u + d + w, v + d, d, h),
        "south": (u + d + w + d, v + d, w, h),
    }


def rects_overlap(a, b) -> bool:
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    if aw <= 0 or ah <= 0 or bw <= 0 or bh <= 0:
        return False
    return ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah


def validate(geo: dict, rep: Report, texture_path: Optional[str] = None) -> dict:
    desc = geo.get("description", {})
    ident = desc.get("identifier", "")
    if not ident:
        rep.error("description.identifier missing")
    elif not ident.startswith("geometry."):
        rep.error(f"identifier {ident!r} must start with 'geometry.'")
    tw = desc.get("texture_width", 0)
    th = desc.get("texture_height", 0)
    if not tw or not th:
        rep.warn("texture_width/texture_height missing — UVs cannot be checked")

    bones = geo.get("bones", [])
    if not bones:
        rep.error("no bones")
        return {}

    # ---- bone graph ------------------------------------------------------
    names = {}
    for b in bones:
        n = b.get("name")
        if not n:
            rep.error("bone without a name")
            continue
        if n in names:
            rep.error(f"duplicate bone name {n!r}")
        names[n] = b
    for b in bones:
        p = b.get("parent")
        if p and p not in names:
            rep.error(f"bone {b.get('name')!r}: unknown parent {p!r}")
    for b in bones:  # cycle detection
        seen = set()
        cur = b.get("name")
        while cur:
            if cur in seen:
                rep.error(f"parent cycle involving bone {cur!r}")
                break
            seen.add(cur)
            cur = names.get(cur, {}).get("parent")

    # ---- cubes: UV, bbox, world faces -----------------------------------
    n_cubes = 0
    n_planes = 0
    uv_rects: List[Tuple[str, Tuple[int, int, int, int], bool]] = []  # (label, rect, mirrored)
    world_boxes = []            # (label, lo, hi) for unrotated cubes
    lo_all = [1e9] * 3
    hi_all = [-1e9] * 3

    def bone_translation(bone) -> Tuple[bool, Tuple[float, float, float]]:
        """Walk up the chain; returns (is_rotationless, accumulated offset).

        In bedrock geo, bone pivots don't translate cubes (cube coords are
        already in model space); only ROTATION moves things. So for the
        z-fight check we just need to know whether any ancestor rotates.
        """
        cur = bone
        depth = 0
        while cur is not None and depth < 64:
            r = cur.get("rotation")
            if r and any(abs(x) > EPS for x in r):
                return False, (0, 0, 0)
            cur = names.get(cur.get("parent"))
            depth += 1
        return True, (0, 0, 0)

    for b in bones:
        bname = b.get("name", "?")
        static, _ = bone_translation(b)
        for i, c in enumerate(b.get("cubes", [])):
            n_cubes += 1
            label = f"{bname}[{i}]"
            size = c.get("size", [0, 0, 0])
            origin = c.get("origin", [0, 0, 0])
            inflate = c.get("inflate", 0)
            if any(s < 0 for s in size):
                rep.error(f"{label}: negative size {size}")
                continue
            if size.count(0) == 1:
                n_planes += 1
            elif size.count(0) > 1:
                rep.warn(f"{label}: size {size} has {size.count(0)} zero axes — invisible")
            for k in range(3):
                lo_all[k] = min(lo_all[k], origin[k] - inflate)
                hi_all[k] = max(hi_all[k], origin[k] + size[k] + inflate)

            uv = c.get("uv")
            if isinstance(uv, dict):        # per-face UV
                if tw and th:
                    for fname, fd in uv.items():
                        fuv = fd.get("uv", [0, 0])
                        fsz = fd.get("uv_size", [0, 0])
                        x0 = min(fuv[0], fuv[0] + fsz[0])
                        x1 = max(fuv[0], fuv[0] + fsz[0])
                        y0 = min(fuv[1], fuv[1] + fsz[1])
                        y1 = max(fuv[1], fuv[1] + fsz[1])
                        if x0 < 0 or y0 < 0 or x1 > tw or y1 > th:
                            rep.error(f"{label}.{fname}: per-face UV {fuv}+{fsz} "
                                      f"outside {tw}x{th}")
            elif isinstance(uv, list):      # box UV
                if any(abs(s - round(s)) > EPS for s in size):
                    rep.warn(f"{label}: fractional size {size} with box UV — "
                             f"faces share texture pixels; consider per-face UV")
                if tw and th:
                    rect = box_uv_rect(uv, size)
                    x, y, w, h = rect
                    if x < 0 or y < 0 or x + w > tw or y + h > th:
                        rep.error(f"{label}: box UV {uv} footprint {w}x{h} "
                                  f"outside texture {tw}x{th}")
                    uv_rects.append((label, rect, bool(c.get("mirror") or b.get("mirror"))))
            else:
                rep.warn(f"{label}: no uv")

            rot = c.get("rotation")
            cube_static = static and not (rot and any(abs(x) > EPS for x in rot))
            if cube_static:
                lo = [origin[k] - inflate for k in range(3)]
                hi = [origin[k] + size[k] + inflate for k in range(3)]
                world_boxes.append((label, lo, hi))

    # ---- box-UV overlaps -------------------------------------------------
    reported = set()
    for i in range(len(uv_rects)):
        for j in range(i + 1, len(uv_rects)):
            la, ra, ma = uv_rects[i]
            lb, rb, mb = uv_rects[j]
            if rects_overlap(ra, rb):
                key = (la, lb)
                if key not in reported:
                    reported.add(key)
                    hint = " (mirrored pair — OK if intentional)" if ma or mb else ""
                    rep.warn(f"UV overlap: {la} {ra} <-> {lb} {rb}{hint}")

    # ---- z-fighting ------------------------------------------------------
    for i in range(len(world_boxes)):
        for j in range(i + 1, len(world_boxes)):
            la, alo, ahi = world_boxes[i]
            lb, blo, bhi = world_boxes[j]
            for axis in range(3):
                o1, o2 = (axis + 1) % 3, (axis + 2) % 3
                overlap = (min(ahi[o1], bhi[o1]) - max(alo[o1], blo[o1]) > EPS and
                           min(ahi[o2], bhi[o2]) - max(alo[o2], blo[o2]) > EPS)
                if not overlap:
                    continue
                # Only SAME-FACING coplanar faces flicker (touching cubes,
                # i.e. one's max == other's min, are normal construction —
                # backface culling hides that seam). Same-facing means both
                # max faces or both min faces on the same plane.
                plane = None
                if abs(ahi[axis] - bhi[axis]) < EPS:
                    plane = ahi[axis]
                elif abs(alo[axis] - blo[axis]) < EPS:
                    plane = alo[axis]
                if plane is not None:
                    rep.warn(f"z-fight risk: {la} and {lb} both have a face on "
                             f"{'xyz'[axis]}={plane:g} — offset by 0.1-0.25 or "
                             f"inflate (ignore if the seam is buried inside "
                             f"another cube)")
                    break

    # ---- pivots ----------------------------------------------------------
    if lo_all[0] < hi_all[0]:
        margin = 8
        for b in bones:
            p = b.get("pivot", [0, 0, 0])
            if any(p[k] < lo_all[k] - margin or p[k] > hi_all[k] + margin for k in range(3)):
                rep.warn(f"bone {b.get('name')!r}: pivot {p} far outside model bbox")

    # ---- texture file ----------------------------------------------------
    if texture_path and tw and th:
        try:
            from PIL import Image
            img = Image.open(texture_path).convert("RGBA")
            iw, ih = img.size
            if iw % tw or ih % th or (iw // tw) != (ih // th):
                rep.warn(f"texture {iw}x{ih} is not an integer multiple of "
                         f"declared {tw}x{th}")
            alphas = img.getchannel("A").getcolors(maxcolors=100000) or []
            semi = sum(n for n, a in alphas if 0 < a < 255)
            if semi:
                rep.warn(f"texture has {semi} semi-transparent pixels — entity "
                         f"cutout rendering shows them fully opaque or invisible")
        except ImportError:
            rep.warn("Pillow not installed — skipped texture checks (pip install pillow)")
        except OSError as exc:
            rep.error(f"cannot open texture: {exc}")

    return {
        "identifier": ident, "bones": len(bones), "cubes": n_cubes,
        "planes": n_planes, "texture": f"{tw}x{th}",
        "bbox": (tuple(round(v, 2) for v in lo_all),
                 tuple(round(v, 2) for v in hi_all)) if n_cubes else None,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("geo")
    ap.add_argument("--texture")
    ap.add_argument("--strict", action="store_true", help="warnings also fail")
    args = ap.parse_args()

    rep = Report()
    geo = load_geometry(args.geo, rep)
    stats = validate(geo, rep, args.texture) if geo else {}

    print(f"{args.geo}:")
    rep.dump()
    if stats:
        bbox = stats.pop("bbox", None)
        line = ", ".join(f"{k}={v}" for k, v in stats.items())
        print(f"  i {line}")
        if bbox:
            (x0, y0, z0), (x1, y1, z1) = bbox
            print(f"  i bbox {x1 - x0:g} x {y1 - y0:g} x {z1 - z0:g} units "
                  f"(y {y0:g}..{y1:g}) = "
                  f"{(x1 - x0) / 16:.2f} x {(y1 - y0) / 16:.2f} x {(z1 - z0) / 16:.2f} blocks")
    n_e, n_w = len(rep.errors), len(rep.warnings)
    print(f"  {'FAIL' if n_e else 'OK'}: {n_e} errors, {n_w} warnings")
    return 1 if (n_e or (args.strict and n_w)) else 0


if __name__ == "__main__":
    sys.exit(main())
