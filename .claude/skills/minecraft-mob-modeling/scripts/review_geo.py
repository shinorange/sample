#!/usr/bin/env python3
"""review_geo.py — Automated review report / structural diff for mob models.

The entry point for BRUSHING UP an existing model. Produces a prioritized
findings report (validation issues, craft-rule violations, metrics vs the
skill's guidelines) so the refinement loop starts from facts, not vibes.

Usage:
    python3 review_geo.py model.geo.json [--texture tex.png]
    python3 review_geo.py model.geo.json --report review.md
    python3 review_geo.py new.geo.json --diff old.geo.json   # what changed?
    python3 review_geo.py model.geo.json --render prefix     # + preview PNGs

Report sections:
  1. 検証        validate_geo と同じエラー/警告(必ず最初に潰す)
  2. 構造        ボーン/キューブ数・階層・命名規約・対称性
  3. プロポーション  bbox・頭身・ディテール三階層の体積配分
  4. UV/密度     テクセル密度 1:1 違反・テクスチャ空き領域
  5. テクスチャ   パレット規模・純色・半透明(--texture 時)
  6. 参考値      数値メトリクス一覧

Severity: [E] 必ず直す / [W] 直すべき(意図的なら明記して残す) /
          [N] 指摘(検討) / [i] 情報。Exit code 1 = [E] あり。

--diff OLD compares bones/cubes/uv between OLD and the model and prints an
edit summary — run it after every refinement pass to confirm the edit did
exactly what you intended and nothing else.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from typing import Dict, List, Optional, Tuple

sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
from validate_geo import (Report, box_uv_rect, face_uv_rects,  # noqa: E402
                          load_geometry, validate)

AXES = "xyz"


class Finding:
    def __init__(self, sev: str, section: str, msg: str):
        self.sev = sev          # E / W / N / i
        self.section = section
        self.msg = msg


def fmt3(v) -> str:
    return "(" + ", ".join(f"{x:g}" for x in v) + ")"


# ------------------------------------------------------------------ review

def review(geo: dict, rep: Report, texture_path: Optional[str]) -> Tuple[List[Finding], Dict]:
    f: List[Finding] = []
    metrics: Dict[str, object] = {}
    desc = geo.get("description", {})
    tw = desc.get("texture_width", 0)
    th = desc.get("texture_height", 0)
    bones = geo.get("bones", [])
    by_name = {b.get("name"): b for b in bones}

    # ---- 1. validation results become findings ---------------------------
    for e in rep.errors:
        f.append(Finding("E", "検証", e))
    for w in rep.warnings:
        f.append(Finding("W", "検証", w))

    # ---- 2. structure ----------------------------------------------------
    n_cubes = sum(len(b.get("cubes", [])) for b in bones)
    n_planes = sum(1 for b in bones for c in b.get("cubes", [])
                   if list(c.get("size", [1, 1, 1])).count(0) == 1)
    metrics["bones"] = len(bones)
    metrics["cubes"] = n_cubes
    metrics["planes"] = n_planes

    def depth(b, seen=()):
        p = b.get("parent")
        if not p or p not in by_name or p in seen:
            return 1
        return 1 + depth(by_name[p], seen + (b.get("name"),))

    metrics["hierarchy_depth"] = max((depth(b) for b in bones), default=0)

    root = by_name.get("root")
    if root is None:
        f.append(Finding("N", "構造", "ルートボーン 'root' がない — 全体移動・"
                         "死亡転倒アニメの受け皿として root (pivot 0,0,0) を推奨"))
    elif tuple(root.get("pivot", (0, 0, 0))) != (0, 0, 0):
        f.append(Finding("N", "構造", f"root の pivot が {fmt3(root['pivot'])} — "
                         "原点 (0,0,0) 推奨"))
    if "head" not in by_name:
        f.append(Finding("N", "構造", "'head' という名前のボーンがない — 視線追従"
                         "アニメ・装備表示は head 名を前提にする(頭が無い MOB なら無視可)"))

    for b in bones:
        n = b.get("name", "")
        if n.endswith("_right"):
            twin = n[:-6] + "_left"
            if twin not in by_name:
                f.append(Finding("N", "構造", f"{n} に対応する {twin} がない"))
            else:
                tb = by_name[twin]
                p1 = b.get("pivot", (0, 0, 0))
                p2 = tb.get("pivot", (0, 0, 0))
                if (abs(p1[0] + p2[0]) > 0.01 or abs(p1[1] - p2[1]) > 0.01
                        or abs(p1[2] - p2[2]) > 0.01):
                    f.append(Finding("N", "構造", f"{n}/{twin} の pivot が鏡映に"
                                     f"なっていない: {fmt3(p1)} vs {fmt3(p2)}"))
                if len(b.get("cubes", [])) != len(tb.get("cubes", [])):
                    f.append(Finding("N", "構造", f"{n}/{twin} のキューブ数が不一致"))
        if n and not all(ch.isascii() and (ch.isalnum() or ch == "_") for ch in n):
            f.append(Finding("N", "構造", f"ボーン名 {n!r} — ASCII の snake_case 推奨"))

    if n_cubes > 200:
        f.append(Finding("W", "構造", f"キューブ {n_cubes} 個 — 上限目安 200 超。"
                         "隠れ面カリングと統合を検討 (detail-techniques.md)"))
    elif n_cubes > 120:
        f.append(Finding("N", "構造", f"キューブ {n_cubes} 個 — 精巧カスタム上限帯。"
                         "増やす前に『テクスチャで描けないか』を確認"))

    # ---- 3. proportions --------------------------------------------------
    lo = [1e9] * 3
    hi = [-1e9] * 3
    vol_list = []            # (volume, label, is_plane)
    for b in bones:
        for i, c in enumerate(b.get("cubes", [])):
            s = c.get("size", (0, 0, 0))
            o = c.get("origin", (0, 0, 0))
            inf = c.get("inflate", 0)
            for k in range(3):
                lo[k] = min(lo[k], o[k] - inf)
                hi[k] = max(hi[k], o[k] + s[k] + inf)
            v = 1.0
            for k in range(3):
                v *= max(s[k] + 2 * inf, 0.25)      # planes get token thickness
            vol_list.append((v, f"{b.get('name')}[{i}]"))
    if not vol_list:
        return f, metrics
    size = [hi[k] - lo[k] for k in range(3)]
    metrics["bbox_units"] = f"{size[0]:g} x {size[1]:g} x {size[2]:g}"
    metrics["bbox_blocks"] = (f"{size[0] / 16:.2f} x {size[1] / 16:.2f} x "
                              f"{size[2] / 16:.2f}")
    if lo[1] < -0.01:
        f.append(Finding("W", "プロポーション", f"最下点 y={lo[1]:g} が地面 (y=0) より"
                         "下 — 接地基準は y=0(飛行/水棲は意図的なら可)"))

    head = by_name.get("head")
    if head and head.get("cubes"):
        h_lo, h_hi = 1e9, -1e9
        for c in head["cubes"]:
            h_lo = min(h_lo, c["origin"][1])
            h_hi = max(h_hi, c["origin"][1] + c["size"][1])
        ratio = (h_hi - h_lo) / max(size[1], 1e-9)
        metrics["head_ratio"] = f"{ratio:.2f} (頭高/全高)"
        if ratio < 0.12:
            f.append(Finding("N", "プロポーション", f"頭身比 {ratio:.2f} — 1/8 未満。"
                             "威圧系なら妥当、そうでなければ頭を大きく (vanilla-calibration.md)"))

    total_v = sum(v for v, _ in vol_list) or 1.0
    max_v = max(v for v, _ in vol_list)
    prim = sum(v for v, _ in vol_list if v >= 0.25 * max_v)
    tert = sum(v for v, _ in vol_list if v < 0.03 * max_v)
    sec = total_v - prim - tert
    metrics["detail_tiers"] = (f"一次 {100 * prim / total_v:.0f}% / "
                               f"二次 {100 * sec / total_v:.0f}% / "
                               f"三次 {100 * tert / total_v:.0f}% (体積比, 目安 65/30/5)")
    if prim / total_v > 0.92:
        f.append(Finding("N", "プロポーション", "体積のほぼ全てが一次キューブ — "
                         "二次・三次ディテールを足す余地 (detail-techniques.md の階層)"))

    n_rot_bones = sum(1 for b in bones if b.get("rotation")
                      and any(abs(r) > 0.01 for r in b["rotation"]))
    n_rot_cubes = sum(1 for b in bones for c in b.get("cubes", [])
                      if c.get("rotation") and any(abs(r) > 0.01 for r in c["rotation"]))
    metrics["rotations"] = f"ボーン {n_rot_bones} / キューブ {n_rot_cubes}"
    if n_rot_bones + n_rot_cubes == 0 and n_cubes >= 12:
        f.append(Finding("N", "プロポーション", "回転が 1 つもない — 耳・尾・牙などに"
                         "±5〜15° の微回転を入れると生体感が出る"))

    # ---- 4. UV / texel density ------------------------------------------
    covered = set()
    n_pf_cubes = 0
    n_density_bad = 0
    for b in bones:
        for i, c in enumerate(b.get("cubes", [])):
            s = c.get("size", (0, 0, 0))
            uv = c.get("uv")
            if isinstance(uv, dict):
                n_pf_cubes += 1
                dims = {"north": (s[0], s[1]), "south": (s[0], s[1]),
                        "east": (s[2], s[1]), "west": (s[2], s[1]),
                        "up": (s[0], s[2]), "down": (s[0], s[2])}
                for fn, fd in uv.items():
                    fsz = fd.get("uv_size", [0, 0])
                    w_exp, h_exp = dims.get(fn, (0, 0))
                    if w_exp and h_exp:
                        if (abs(abs(fsz[0]) - w_exp) > 0.01
                                or abs(abs(fsz[1]) - h_exp) > 0.01):
                            n_density_bad += 1
                    fuv = fd.get("uv", [0, 0])
                    x0 = int(min(fuv[0], fuv[0] + fsz[0]))
                    y0 = int(min(fuv[1], fuv[1] + fsz[1]))
                    for px in range(x0, x0 + int(abs(fsz[0]))):
                        for py in range(y0, y0 + int(abs(fsz[1]))):
                            covered.add((px, py))
            elif isinstance(uv, list):
                x, y, w, h = box_uv_rect(uv, s)
                for px in range(x, x + w):
                    for py in range(y, y + h):
                        covered.add((px, py))
    if n_density_bad:
        f.append(Finding("W", "UV/密度", f"per-face UV の {n_density_bad} 面で uv_size が"
                         "面の実寸と不一致 — テクセル密度 1:1 が壊れている"
                         "(意図的な繰り返し共有なら明記して残す)"))
    if tw and th:
        free = 100 * (1 - len(covered) / (tw * th))
        metrics["texture_free"] = f"{free:.0f}% 空き ({tw}x{th})"
        if free < 10:
            f.append(Finding("N", "UV/密度", f"テクスチャ空き {free:.0f}% — 今後の"
                             "パーツ追加余地が少ない。次サイズへの移行を検討"))

    # ---- 5. texture ------------------------------------------------------
    if texture_path:
        try:
            from PIL import Image
            img = Image.open(texture_path).convert("RGBA")
            colors = img.getcolors(maxcolors=1 << 20) or []
            opaque = [(n, c) for n, c in colors if c[3] == 255]
            metrics["palette"] = f"{len(opaque)} 色 (不透明)"
            if len(opaque) > 40:
                f.append(Finding("N", "テクスチャ", f"不透明 {len(opaque)} 色 — "
                                 "バニラ感を出すなら素材ごと 4〜6 段に整理 (texturing.md)"))
            import colorsys
            pure = 0
            for n, (r, g, bl, a) in opaque:
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, bl / 255)
                if s > 0.85 and v > 0.9:
                    pure += n
            if pure:
                f.append(Finding("N", "テクスチャ", f"純色級ピクセルが {pure} px — "
                                 "バニラの彩度レンジ(低め)から浮きやすい"))
        except ImportError:
            f.append(Finding("i", "テクスチャ", "Pillow 未導入のためパレット検査を省略"))
        except OSError as exc:
            f.append(Finding("E", "テクスチャ", f"テクスチャを開けない: {exc}"))

    return f, metrics


# -------------------------------------------------------------------- diff

def cube_sig(c: dict) -> dict:
    return {k: c.get(k) for k in
            ("origin", "size", "uv", "inflate", "mirror", "rotation", "pivot")}


def diff_geo(old: dict, new: dict) -> List[str]:
    out: List[str] = []
    for key in ("identifier", "texture_width", "texture_height"):
        ov = old.get("description", {}).get(key)
        nv = new.get("description", {}).get(key)
        if ov != nv:
            out.append(f"description.{key}: {ov} -> {nv}")
    ob = {b.get("name"): b for b in old.get("bones", [])}
    nb = {b.get("name"): b for b in new.get("bones", [])}
    for n in sorted(set(nb) - set(ob)):
        out.append(f"+ bone {n} ({len(nb[n].get('cubes', []))} cubes)")
    for n in sorted(set(ob) - set(nb)):
        out.append(f"- bone {n} ({len(ob[n].get('cubes', []))} cubes)")
    for n in sorted(set(ob) & set(nb)):
        b0, b1 = ob[n], nb[n]
        for attr in ("parent", "pivot", "rotation", "mirror"):
            if b0.get(attr) != b1.get(attr):
                out.append(f"~ bone {n}.{attr}: {b0.get(attr)} -> {b1.get(attr)}")
        c0 = b0.get("cubes", [])
        c1 = b1.get("cubes", [])
        for i in range(max(len(c0), len(c1))):
            if i >= len(c0):
                out.append(f"+ cube {n}[{i}] size={c1[i].get('size')} "
                           f"uv={c1[i].get('uv')}")
            elif i >= len(c1):
                out.append(f"- cube {n}[{i}] size={c0[i].get('size')}")
            else:
                s0, s1 = cube_sig(c0[i]), cube_sig(c1[i])
                changed = [k for k in s0 if s0[k] != s1[k]]
                for k in changed:
                    out.append(f"~ cube {n}[{i}].{k}: {s0[k]} -> {s1[k]}")
    return out


# -------------------------------------------------------------------- main

SEV_ORDER = {"E": 0, "W": 1, "N": 2, "i": 3}
SEV_LABEL = {"E": "[E] 必ず直す", "W": "[W] 直すべき", "N": "[N] 指摘", "i": "[i] 情報"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("geo")
    ap.add_argument("--texture")
    ap.add_argument("--report", help="write the report to this file (markdown)")
    ap.add_argument("--diff", metavar="OLD_GEO",
                    help="print a structural diff OLD -> GEO and exit")
    ap.add_argument("--render", metavar="PREFIX",
                    help="also write PREFIX_flat.png (+PREFIX_tex.png with --texture)")
    args = ap.parse_args()

    if args.diff:
        rep0, rep1 = Report(), Report()
        old = load_geometry(args.diff, rep0)
        new = load_geometry(args.geo, rep1)
        if old is None or new is None:
            for r in (rep0, rep1):
                r.dump()
            return 1
        lines = diff_geo(old, new)
        print(f"diff {args.diff} -> {args.geo}: {len(lines)} change(s)")
        for ln in lines:
            print("  " + ln)
        return 0

    rep = Report()
    geo = load_geometry(args.geo, rep)
    if geo is None:
        rep.dump()
        return 1
    validate(geo, rep, args.texture)
    findings, metrics = review(geo, rep, args.texture)
    findings.sort(key=lambda x: SEV_ORDER.get(x.sev, 9))

    lines = [f"# モデルレビュー: {args.geo}", ""]
    counts = defaultdict(int)
    for fd in findings:
        counts[fd.sev] += 1
    lines.append("集計: " + "  ".join(f"{SEV_LABEL[s]}: {counts[s]}"
                                      for s in "EWNi" if counts[s]))
    lines.append("")
    cur = None
    for fd in findings:
        if fd.sev != cur:
            cur = fd.sev
            lines.append(f"## {SEV_LABEL[fd.sev]}")
        lines.append(f"- ({fd.section}) {fd.msg}")
    lines.append("")
    lines.append("## 参考値")
    for k, v in metrics.items():
        lines.append(f"- {k}: {v}")
    lines.append("")
    lines.append("次の一手: [E]→[W] を潰す → render_geo で before を保存 → 修正 → "
                 "--diff で意図した変更だけか確認 → render で after を目視比較。")

    text = "\n".join(lines)
    print(text)
    if args.report:
        with open(args.report, "w", encoding="utf-8") as fh:
            fh.write(text + "\n")

    if args.render:
        import render_geo as rg
        faces, tex_size = rg.collect_faces(geo)
        views = [(v, rg.VIEWS[v]) for v in ("front", "left", "top")] + \
                [("iso", rg.iso_basis(35, 25))]
        tiles = [(n, rg.render_view(faces, b, 8.0, None, tex_size))
                 for n, b in views]
        rg.contact_sheet(tiles, 8.0).save(args.render + "_flat.png")
        print(f"\nwrote {args.render}_flat.png")
        if args.texture:
            from PIL import Image
            tex = Image.open(args.texture).convert("RGBA")
            tiles = [(n, rg.render_view(faces, b, 8.0, tex, tex_size))
                     for n, b in views]
            rg.contact_sheet(tiles, 8.0).save(args.render + "_tex.png")
            print(f"wrote {args.render}_tex.png")

    return 1 if counts["E"] else 0


if __name__ == "__main__":
    sys.exit(main())
