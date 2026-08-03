#!/usr/bin/env python3
"""render_geo.py — Software preview renderer for Bedrock entity geometry.

Renders a .geo.json to a labeled multi-view contact sheet PNG so you can SEE
the model (silhouette, proportions, texture placement) without Minecraft or
Blockbench. Requires Pillow (pip install pillow).

Usage:
    python3 render_geo.py model.geo.json -o preview.png
    python3 render_geo.py model.geo.json --texture tex.png -o preview.png
    python3 render_geo.py model.geo.json --views front,left,iso --scale 12

Views: front (the face; mobs face -Z/north), back, left, right, top, iso
       (three-quarter view from the front-left, yaw/pitch adjustable).

What it is good for:  proportion/silhouette checks, texture-UV sanity,
                      spotting gaps and misplaced cubes, iterating quickly.
What it is NOT:       a pixel-perfect Minecraft render. Compound multi-axis
                      bone rotations may differ slightly from the engine's
                      Euler order — verify final poses in Blockbench.

Flat mode (no --texture): each BONE gets a stable color (name hash) with
per-face directional shading that mimics Minecraft entity lighting
(top bright / bottom dark / sides mid), plus thin outlines.
"""
from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import math
import sys
from typing import Dict, List, Optional, Tuple

try:
    from PIL import Image, ImageChops, ImageDraw
except ImportError:
    print("render_geo.py needs Pillow:  pip install pillow", file=sys.stderr)
    sys.exit(2)

Vec3 = Tuple[float, float, float]
EPS = 1e-9

# ---------------------------------------------------------------- math bits


def rot_x(d):
    r = math.radians(d)
    c, s = math.cos(r), math.sin(r)
    return [[1, 0, 0], [0, c, -s], [0, s, c]]


def rot_y(d):
    r = math.radians(d)
    c, s = math.cos(r), math.sin(r)
    return [[c, 0, s], [0, 1, 0], [-s, 0, c]]


def rot_z(d):
    r = math.radians(d)
    c, s = math.cos(r), math.sin(r)
    return [[c, -s, 0], [s, c, 0], [0, 0, 1]]


def mat_mul(a, b):
    return [[sum(a[i][k] * b[k][j] for k in range(3)) for j in range(3)]
            for i in range(3)]


def mat_vec(m, v):
    return tuple(sum(m[i][k] * v[k] for k in range(3)) for i in range(3))


def euler_zyx(rx, ry, rz):
    """Bedrock-style bone rotation (applied about the pivot)."""
    return mat_mul(rot_z(rz), mat_mul(rot_y(ry), rot_x(rx)))


class Transform:
    """Rotation about a pivot: p' = R (p - pivot) + pivot, composable."""

    def __init__(self, m=None, t=(0.0, 0.0, 0.0)):
        self.m = m or [[1, 0, 0], [0, 1, 0], [0, 0, 1]]
        self.t = t

    @classmethod
    def pivot_rot(cls, rotation, pivot):
        m = euler_zyx(*rotation)
        px, py, pz = pivot
        rp = mat_vec(m, (px, py, pz))
        return cls(m, (px - rp[0], py - rp[1], pz - rp[2]))

    def compose(self, other: "Transform") -> "Transform":
        """self ∘ other (apply `other` first)."""
        m = mat_mul(self.m, other.m)
        t = mat_vec(self.m, other.t)
        return Transform(m, (t[0] + self.t[0], t[1] + self.t[1], t[2] + self.t[2]))

    def apply(self, v: Vec3) -> Vec3:
        r = mat_vec(self.m, v)
        return (r[0] + self.t[0], r[1] + self.t[1], r[2] + self.t[2])

    def apply_dir(self, v: Vec3) -> Vec3:
        return mat_vec(self.m, v)


# ------------------------------------------------------------- geo parsing

# Local-space face definitions for a cube origin o, size s.
# Corners listed so the texture rect maps as:
#   corner[0] = texture (x, y)  [top-left of the face rect]
#   corner[1] = texture (x+w, y)
#   corner[2] = texture (x, y+h)
#   corner[3] = texture (x+w, y+h)
# Texture V grows downward; model Y grows upward, so the *top* of a side
# face rect is the cube's *upper* edge.
def face_corners(o, s):
    x0, y0, z0 = o
    x1, y1, z1 = o[0] + s[0], o[1] + s[1], o[2] + s[2]
    return {
        #        TL            TR            BL            BR         normal
        "north": ((x1, y1, z0), (x0, y1, z0), (x1, y0, z0), (x0, y0, z0), (0, 0, -1)),
        "south": ((x0, y1, z1), (x1, y1, z1), (x0, y0, z1), (x1, y0, z1), (0, 0, 1)),
        "east":  ((x1, y1, z1), (x1, y1, z0), (x1, y0, z1), (x1, y0, z0), (1, 0, 0)),
        "west":  ((x0, y1, z0), (x0, y1, z1), (x0, y0, z0), (x0, y0, z1), (-1, 0, 0)),
        "up":    ((x1, y1, z1), (x0, y1, z1), (x1, y1, z0), (x0, y1, z0), (0, 1, 0)),
        "down":  ((x1, y0, z0), (x0, y0, z0), (x1, y0, z1), (x0, y0, z1), (0, -1, 0)),
    }


def box_uv_rects(uv, size) -> Dict[str, Tuple[float, float, float, float]]:
    w = math.ceil(abs(size[0]) - 1e-9)
    h = math.ceil(abs(size[1]) - 1e-9)
    d = math.ceil(abs(size[2]) - 1e-9)
    u, v = uv
    return {
        "up":    (u + d, v, w, d),
        "down":  (u + d + w, v, w, d),
        "east":  (u, v + d, d, h),
        "north": (u + d, v + d, w, h),
        "west":  (u + d + w, v + d, d, h),
        "south": (u + d + w + d, v + d, w, h),
    }


class Face:
    __slots__ = ("quad", "normal", "uv_rect", "flip_u", "bone", "kind")

    def __init__(self, quad, normal, uv_rect, flip_u, bone, kind):
        self.quad = quad          # 4 world-space corners (TL TR BL BR)
        self.normal = normal      # world-space normal
        self.uv_rect = uv_rect    # (x, y, w, h) in texture px, or None
        self.flip_u = flip_u
        self.bone = bone
        self.kind = kind          # face name


def collect_faces(geo: dict) -> Tuple[List[Face], Tuple[int, int]]:
    desc = geo.get("description", {})
    tex_size = (desc.get("texture_width", 64), desc.get("texture_height", 64))
    bones = {b["name"]: b for b in geo.get("bones", [])}

    tf_cache: Dict[str, Transform] = {}

    def bone_tf(name: str) -> Transform:
        if name in tf_cache:
            return tf_cache[name]
        b = bones[name]
        own = Transform()
        rot = b.get("rotation")
        if rot and any(abs(r) > EPS for r in rot):
            own = Transform.pivot_rot(rot, b.get("pivot", (0, 0, 0)))
        parent = b.get("parent")
        tf = bone_tf(parent).compose(own) if parent in bones else own
        tf_cache[name] = tf
        return tf

    faces: List[Face] = []
    for b in geo.get("bones", []):
        tf = bone_tf(b["name"])
        bone_mirror = bool(b.get("mirror"))
        for c in b.get("cubes", []):
            o = list(c.get("origin", (0, 0, 0)))
            s = list(c.get("size", (0, 0, 0)))
            inf = c.get("inflate", 0)
            if inf:
                o = [o[i] - inf for i in range(3)]
                s = [s[i] + 2 * inf for i in range(3)]
            ctf = tf
            crot = c.get("rotation")
            if crot and any(abs(r) > EPS for r in crot):
                ctf = tf.compose(Transform.pivot_rot(crot, c.get("pivot", (0, 0, 0))))

            uv = c.get("uv", [0, 0])
            mirror = c.get("mirror", bone_mirror)
            per_face = isinstance(uv, dict)
            rects = None if per_face else box_uv_rects(uv, c.get("size", s))
            if rects is not None and mirror:
                rects["east"], rects["west"] = rects["west"], rects["east"]

            for fname, (tl, tr, bl, br, n) in face_corners(o, s).items():
                uv_rect, flip = None, False
                if per_face:
                    fd = uv.get(fname)
                    if fd is None:
                        continue          # omitted face: not rendered
                    fuv = fd.get("uv", [0, 0])
                    fsz = fd.get("uv_size", [0, 0])
                    uv_rect = (fuv[0], fuv[1], fsz[0], fsz[1])  # may be negative => flip
                else:
                    uv_rect = rects[fname]
                    flip = mirror
                quad = tuple(ctf.apply(p) for p in (tl, tr, bl, br))
                normal = ctf.apply_dir(n)
                faces.append(Face(quad, normal, uv_rect, flip, b["name"], fname))
    return faces, tex_size


# ---------------------------------------------------------------- rendering

VIEWS = {
    #        right          up            toward-camera
    "front": ((-1, 0, 0), (0, 1, 0), (0, 0, -1)),
    "back":  ((1, 0, 0), (0, 1, 0), (0, 0, 1)),
    "left":  ((0, 0, 1), (0, 1, 0), (-1, 0, 0)),
    "right": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
    "top":   ((1, 0, 0), (0, 0, -1), (0, 1, 0)),
    "bottom": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
}


def iso_basis(yaw_deg: float, pitch_deg: float):
    """Three-quarter view: orbit the `front` camera by yaw, then pitch.

    Orbiting the camera equals rotating the world by the inverse (transpose).
    """
    m = mat_mul(rot_x(pitch_deg), rot_y(yaw_deg))
    mi = [[m[j][i] for j in range(3)] for i in range(3)]
    right, up, toward = (mat_vec(mi, v) for v in VIEWS["front"])
    return right, up, toward


def bone_color(name: str) -> Tuple[int, int, int]:
    h = int(hashlib.md5(name.encode()).hexdigest()[:6], 16)
    hue = (h % 360) / 360.0
    r, g, b = colorsys.hsv_to_rgb(hue, 0.45, 0.85)
    return int(r * 255), int(g * 255), int(b * 255)


def shade(normal: Vec3) -> float:
    """Approximate Minecraft's fixed directional entity lighting."""
    nx, ny, nz = normal
    length = math.sqrt(nx * nx + ny * ny + nz * nz) or 1.0
    ny /= length
    nz /= length
    base = 0.76 + 0.24 * ny if ny >= 0 else 0.76 + 0.26 * ny
    return max(0.35, min(1.0, base + 0.04 * abs(nz)))


def solve_affine(dst_pts, src_pts):
    """PIL AFFINE coefficients mapping DEST canvas px -> SRC texture px."""
    (x0, y0), (x1, y1), (x2, y2) = dst_pts
    (u0, v0), (u1, v1), (u2, v2) = src_pts
    det = (x1 - x0) * (y2 - y0) - (x2 - x0) * (y1 - y0)
    if abs(det) < 1e-12:
        return None
    a = ((u1 - u0) * (y2 - y0) - (u2 - u0) * (y1 - y0)) / det
    b = ((u2 - u0) * (x1 - x0) - (u1 - u0) * (x2 - x0)) / det
    c = u0 - a * x0 - b * y0
    d = ((v1 - v0) * (y2 - y0) - (v2 - v0) * (y1 - y0)) / det
    e = ((v2 - v0) * (x1 - x0) - (v1 - v0) * (x2 - x0)) / det
    f = v0 - d * x0 - e * y0
    return (a, b, c, d, e, f)


def render_view(faces: List[Face], basis, scale: float, texture: Optional[Image.Image],
                tex_size, pad: int = 12, ground: bool = True) -> Image.Image:
    right, up, toward = basis

    def project(p: Vec3):
        return (sum(p[i] * right[i] for i in range(3)),
                sum(p[i] * up[i] for i in range(3)),
                sum(p[i] * toward[i] for i in range(3)))

    projected = []
    for f in faces:
        pts = [project(p) for p in f.quad]
        depth = sum(p[2] for p in pts) / 4.0
        projected.append((depth, pts, f))
    if not projected:
        return Image.new("RGBA", (64, 64), (0, 0, 0, 0))

    xs = [p[0] for _, pts, _ in projected for p in pts]
    ys = [p[1] for _, pts, _ in projected for p in pts]
    minx, maxx = min(xs), max(xs)
    miny, maxy = min(ys), max(ys)
    gy0 = None
    if ground and abs(up[1] - 1) < EPS:      # views with world +Y as screen-up
        miny = min(miny, 0.0)
    w = max(1, int((maxx - minx) * scale)) + 2 * pad
    h = max(1, int((maxy - miny) * scale)) + 2 * pad
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    def to_px(pt):
        return (pad + (pt[0] - minx) * scale,
                pad + (maxy - pt[1]) * scale)

    if ground and abs(up[1] - 1) < EPS:
        gy = to_px((0, 0))[1]
        draw.line([(0, gy), (w, gy)], fill=(128, 128, 128, 120), width=1)

    # far faces first (painter's algorithm; `toward` points at the camera)
    projected.sort(key=lambda t: t[0])
    for depth, pts, f in projected:
        px = [to_px(p) for p in pts]      # TL TR BL BR
        quad = [px[0], px[1], px[3], px[2]]
        area = 0.0
        for i in range(4):
            x1p, y1p = quad[i]
            x2p, y2p = quad[(i + 1) % 4]
            area += x1p * y2p - x2p * y1p
        if abs(area) < 1.0:
            continue                      # edge-on / degenerate
        s = shade(f.normal)
        if texture is not None and f.uv_rect is not None:
            tx, ty, tw_, th_ = f.uv_rect
            sx = texture.size[0] / tex_size[0]
            sy = texture.size[1] / tex_size[1]
            # source triangle TL, TR, BL (flip handles mirror / negative sizes)
            u0, u1 = tx, tx + tw_
            v0, v1 = ty, ty + th_
            if f.flip_u:
                u0, u1 = u1, u0
            src = [(u0 * sx, v0 * sy), (u1 * sx, v0 * sy), (u0 * sx, v1 * sy)]
            dst = [px[0], px[1], px[2]]
            coeff = solve_affine(dst, src)
            if coeff is None:
                continue
            warped = texture.transform((w, h), Image.AFFINE, coeff,
                                       resample=Image.NEAREST)
            # keep only pixels inside the quad AND opaque in the texture
            poly = Image.new("L", (w, h), 0)
            ImageDraw.Draw(poly).polygon(quad, fill=255)
            alpha = warped.getchannel("A").point(lambda a: 255 if a >= 128 else 0)
            mask = ImageChops.multiply(poly, alpha)
            if s < 0.999:
                warped = warped.convert("RGB").point(
                    lambda ch, s_=s: int(ch * s_)).convert("RGBA")
            img.paste(warped, (0, 0), mask)
        else:
            r, g, b = bone_color(f.bone)
            col = (int(r * s), int(g * s), int(b * s), 255)
            edge = (int(r * s * 0.55), int(g * s * 0.55), int(b * s * 0.55), 255)
            draw.polygon(quad, fill=col, outline=edge)
    return img


def contact_sheet(tiles: List[Tuple[str, Image.Image]], scale: float) -> Image.Image:
    label_h = 16
    pad = 8
    heights = [im.size[1] for _, im in tiles]
    row_h = max(heights) + label_h + pad
    total_w = sum(im.size[0] for _, im in tiles) + pad * (len(tiles) + 1)
    sheet = Image.new("RGBA", (max(total_w, 200), row_h + 24 + pad),
                      (34, 34, 40, 255))
    draw = ImageDraw.Draw(sheet)
    x = pad
    for name, im in tiles:
        draw.text((x + 2, 2), name, fill=(230, 230, 230, 255))
        sheet.paste(im, (x, label_h), im)
        x += im.size[0] + pad
    # scale bar: 16 units = 1 block
    bar = int(16 * scale)
    y = sheet.size[1] - 14
    draw.line([(pad, y), (pad + bar, y)], fill=(230, 230, 230, 255), width=2)
    draw.text((pad + bar + 6, y - 7), "16 units = 1 block", fill=(230, 230, 230, 255))
    return sheet


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("geo")
    ap.add_argument("-o", "--out", default=None, help="output PNG (default: <geo>.preview.png)")
    ap.add_argument("--texture", help="texture PNG to map (else flat bone colors)")
    ap.add_argument("--views", default="front,left,right,back,top,iso")
    ap.add_argument("--scale", type=float, default=8.0, help="pixels per model unit")
    ap.add_argument("--yaw", type=float, default=35.0, help="iso view yaw")
    ap.add_argument("--pitch", type=float, default=25.0, help="iso view pitch")
    ap.add_argument("--index", type=int, default=0, help="geometry index in file")
    args = ap.parse_args()

    with open(args.geo, "r", encoding="utf-8") as f:
        data = json.load(f)
    geos = data.get("minecraft:geometry")
    if not geos:
        print("not a 1.12+ bedrock geometry file", file=sys.stderr)
        return 1
    geo = geos[args.index]

    faces, tex_size = collect_faces(geo)
    texture = None
    if args.texture:
        texture = Image.open(args.texture).convert("RGBA")

    tiles = []
    for vname in [v.strip() for v in args.views.split(",") if v.strip()]:
        if vname == "iso":
            basis = iso_basis(args.yaw, args.pitch)
        elif vname in VIEWS:
            basis = VIEWS[vname]
        else:
            print(f"unknown view {vname!r} (choose from "
                  f"{', '.join(list(VIEWS) + ['iso'])})", file=sys.stderr)
            return 1
        tiles.append((vname, render_view(faces, basis, args.scale, texture, tex_size)))

    out = args.out or (args.geo.rsplit(".geo.json", 1)[0] + ".preview.png")
    contact_sheet(tiles, args.scale).save(out)
    ident = geo.get("description", {}).get("identifier", "?")
    print(f"rendered {ident}: {len(faces)} faces -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
