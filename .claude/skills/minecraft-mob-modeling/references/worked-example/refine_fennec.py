#!/usr/bin/env python3
"""Worked example 2: REFINING an existing model (review -> edit -> verify).

Takes the committed fennec and applies a small review-driven brush-up,
exercising the refinement toolkit end to end:

  review findings (review_geo.py fennec.geo.json --texture fennec.png):
    * 三次ディテール 2% と薄い → 首周りが寂しい
    * 尻尾のカールが浅く、後ろ姿のシルエットが弱い
    * スタンス(脚の左右間隔)がやや狭く安定感に欠ける

  fixes demonstrated here:
    1. Model.load()      — 既存 geo を読み込み(既存 UV はピン留めされ不変)
    2. ボーン回転の編集    — 尻尾カールを -14° → -22°/節に(UV 影響なし)
    3. translate_subtree — 脚 4 本を外へ 0.25 ずつ(移動は UV 不変)
    4. キューブ追加        — 首元にクリームの襟巻き(inflate 殻)。新規 UV は
                            自動で空き領域へパックされ既存テクスチャを壊さない
    5. 差分テクスチャ      — 既存 fennec.png を読み込み、新規襟巻きの矩形
                            (uv_map() で取得)だけ描き足して別名保存
    6. 検証              — validate / review --diff / render で before-after 確認

Run:  python3 refine_fennec.py
Then: python3 ../../scripts/review_geo.py fennec_refined.geo.json --diff fennec.geo.json
      python3 ../../scripts/render_geo.py fennec_refined.geo.json \
              --texture fennec_refined.png -o fennec_refined_preview.png --scale 10
"""
import os
import random
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "scripts"))
from geo_builder import Model  # noqa: E402

from PIL import Image  # noqa: E402

OUT = os.path.dirname(os.path.abspath(__file__))

# ---- 1. load: existing cubes keep their uv anchors --------------------
m = Model.load(os.path.join(OUT, "fennec.geo.json"))

# ---- 2. perk up the tail curl (rotation edit — texture untouched) -----
for name in ("tail_0", "tail_1", "tail_2"):
    m[name].rotation = (-22, 0, 0)

# ---- 3. widen the stance (pure move — texture untouched) --------------
for name in ("leg_front_right", "leg_back_right"):
    m.translate_subtree(name, (-0.25, 0, 0))
for name in ("leg_front_left", "leg_back_left"):
    m.translate_subtree(name, (0.25, 0, 0))

# ---- 4. add a cream neck ruff (new cube -> auto-packed into free UV) --
# Shell around the head base / neck: sits between head (z -8..-4) and
# chest, inflate lifts it off both so nothing z-fights.
ruff = m["head"].cube(origin=(-2.5, 5.5, -5.5), size=(5, 4, 2), inflate=0.75)
m.pack_uv()          # resolve the new cube's uv now so we can paint it

geo_path = os.path.join(OUT, "fennec_refined.geo.json")
m.save(geo_path)
print(m.stats())

# ---- 5. incremental texture: paint ONLY the new rects -----------------
CREAM = (247, 240, 224, 255)
CREAM_SH = (229, 216, 191, 255)
BASE = (227, 203, 164, 255)

img = Image.open(os.path.join(OUT, "fennec.png")).convert("RGBA")
px = img.load()
rng = random.Random(7)
for face, (x, y, w, h) in ruff.face_rects().items():
    for j in range(y, y + h):
        for i in range(x, x + w):
            px[i, j] = CREAM
            if rng.random() < 0.22:
                px[i, j] = CREAM_SH
    if face in ("north", "east", "west", "south"):    # base color at the top
        for i in range(x, x + w):                     # so it blends into fur
            if rng.random() < 0.5:
                px[i, y] = BASE

tex_path = os.path.join(OUT, "fennec_refined.png")
img.save(tex_path)
print(f"wrote {geo_path}\nwrote {tex_path}")
