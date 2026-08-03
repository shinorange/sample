---
name: minecraft-mob-modeling
description: >-
  Minecraft の MOB/エンティティの精巧な 3D モデル(Bedrock .geo.json /
  Blockbench / Java エンティティモデル)を設計・生成・テクスチャリング・
  検証・プレビューするための技法集とツール群。ユーザーが「マイクラのMOBを
  作りたい」「エンティティ/アドオン/モッドのモデルが欲しい」「.geo.json や
  .bbmodel を作って・直して」「ドット絵テクスチャを描いて」「モデルの
  プロポーションを確認したい」等、Minecraft の 3D モデルに関わる作業を
  求めたら必ずこのスキルを使うこと。「オリジナルモンスターを追加したい」の
  ように 3D モデルと明言されない依頼や、既存モデルの改良・レビューでも使う。
---

# Minecraft MOB 精巧モデリング

Minecraft の MOB モデルはキューブ(直方体)だけで構成される特殊な 3D 形式。
一般的な 3D モデリングの常識(ポリゴン・スカルプト・スムージング)は通用せず、
**「箱の組み方・UV の割り方・ドット絵」の三位一体**で精巧さが決まる。
このスキルはその技法と、モデルをコードで生成・検証・目視確認するツールを提供する。

## 成果物の標準

一次成果物は **Bedrock ジオメトリ (.geo.json) + テクスチャ PNG + プレビュー PNG**。
.geo.json は Blockbench でそのまま開け、Bedrock アドオンに直接使え、
GeckoLib 経由で Java モッドにも使える最も汎用的な形式
(Java コード等が必要な場合 → references/geometry-format.md のフォーマット選択ガイド)。

## ワークフロー

精巧なモデルは一発では書けない。**「生成 → 検証 → レンダリング → 目視 → 修正」の
ループを最低 2〜3 周回す**こと。レンダリング画像を Read して自分の目で確認する
工程を省略しない(座標のバグ・比率の破綻は画像でしか気づけない)。

### 1. 要件と設計(コードを書く前に決める)

- MOB のコンセプト、ターゲット(Bedrock アドオン / Java モッド / アセットのみ)
- **アーキタイプ**: references/anatomy-patterns.md から体型の型を選ぶ
  (ヒューマノイド/小型・大型四足/鳥/魚/蛇/節足/浮遊/ボス)
- **サイズ**: references/vanilla-calibration.md でバニラ比の高さを決める
  (1 ブロック = 16 units。プレイヤー = 32 units が万物の基準)
- ディテールの見せ場(顔? 尾? 発光模様?)を 1〜2 個決める

### 2. ブロックアウト(一次形状)

`scripts/geo_builder.py` を import した Python スクリプトを書いて生成する
(JSON 手書きは UV 計算を間違えるので原則スクリプト経由):

```python
import sys; sys.path.insert(0, "<このスキルのscripts絶対パス>")
from geo_builder import Model, segment_chain

m = Model("geometry.mymob", texture_size=(64, 64))
m.bone("root", pivot=(0, 0, 0))
body = m.bone("body", parent="root", pivot=(0, 8, 0))
body.cube(origin=(-4, 5, -6), size=(8, 6, 12))       # UV は自動パッキング
head = m.bone("head", parent="body", pivot=(0, 9, -5))
head.cube(origin=(-3, 7, -10), size=(6, 5, 5))
segment_chain(m, "tail", m["body"], start=(0, 9, 6),
              direction=(0, 0, 1), seg_size=(3, 3, 4), count=3,
              bend_deg=(-15, 0, 0), taper=0.5)
m.save("mymob.geo.json")
print(m.stats())        # ボーン数・キューブ数・bbox・UV 使用率
```

アーキタイプの寸法表から一次キューブ(頭・胴・脚)だけ置き、すぐ次へ。

### 3. 検証とレンダリング(毎周回す)

```bash
python3 scripts/validate_geo.py mymob.geo.json            # エラー/警告のリント
python3 scripts/render_geo.py mymob.geo.json -o prev.png  # 6ビュー描画
```

→ **prev.png を Read で開いて目視**。チェック観点:
シルエットで正体が分かるか / 頭身・脚の太さ / パーツの浮き・めり込み /
奥行き方向のテーパー。references/detail-techniques.md 末尾のチェックリストを使う。

### 4. ディテールパス(二次・三次)

references/detail-techniques.md の技法で肉付けする。要点だけ:
- 二次パーツ(耳・鼻先・尾)は本体に 1〜2 unit **食い込ませる**
- 尾・首・触手は `segment_chain()`、耳膜・ヒレ・たてがみは厚さ 0 の
  `plane()` + 透過テクスチャ
- 服・毛皮・鎧は同寸 + `inflate=0.25〜0.5` の殻レイヤー
- 微回転(±5〜15°)は三次ディテールだけ。1 unit 未満の形状はテクスチャで
- テクセル密度 1 unit = 1 px を全キューブで統一(このスキル最重要ルール)

### 5. テクスチャ

references/texturing.md に従い PIL で描く。**UV 座標は必ず
`m.uv_map()` / `m.uv_report()` から取得**(ハードコード禁止)。
パレットは 1 素材 4〜6 段 + 色相シフト。エンジンが面方向の陰影を付けるので
方向性ライティングは焼き込まない。

```bash
python3 scripts/render_geo.py mymob.geo.json --texture mymob.png -o prev_tex.png
```

→ 目視で目の位置・mirror の向き・透過の抜けを確認。

### 6. 納品

- 出力一式: `.geo.json` + テクスチャ `.png` + プレビュー `.png`
- `validate_geo.py` エラー 0 を確認(z-fight 警告は埋没継ぎ目のみ許容)
- ゲームに載せる場合: references/geometry-format.md の「リソースパック配線」
  のテンプレでクライアントエンティティ等を添える
- アニメーションも欲しいと言われたら references/animation-rigging.md の
  レシピ(歩行 38.17 定数・視線追従・アイドル)から組む

## リファレンス(必要な時に読む)

| ファイル | いつ読むか |
|---|---|
| references/geometry-format.md | 座標系・UV 計算・JSON 仕様の正確な確認。Java/GeckoLib/CEM への変換。RP 配線 |
| references/anatomy-patterns.md | 新規 MOB の体型設計(実寸入りテンプレート 9 種 + ボーン命名規約) |
| references/detail-techniques.md | 精巧化の全技法(階層・板ポリ・殻・チェーン・微回転・チェックリスト) |
| references/texturing.md | テクスチャを描く前(パレット・面別手順・素材イディオム・顔) |
| references/vanilla-calibration.md | サイズ決定時(バニラ寸法の物差し) |
| references/animation-rigging.md | pivot 配置の確認・アニメ制作時 |
| references/worked-example/ | 全工程の実例(fennec)。テクスチャ生成コードを書く前に必読 |

## スクリプト

| スクリプト | 役割 |
|---|---|
| scripts/geo_builder.py | Python でモデル構築。box UV 自動パッキング、segment_chain、uv_map、stats |
| scripts/validate_geo.py | .geo.json リント(UV 境界/重複・z-fight・pivot・テクスチャ整合)。--strict で警告も fail |
| scripts/render_geo.py | 6 ビュー(front/left/right/back/top/iso)を PNG に描画。--texture でテクスチャ確認。要 Pillow |

既存の .geo.json を渡された場合も validate → render から入る(現状把握が先)。
Blockbench プロジェクト (.bbmodel) を渡されたら、Blockbench 上で geo.json
エクスポートしてもらうか、bbmodel 内の `elements`/`outliner` を直接読む
(構造は geo.json と同型でキーが違うだけ)。

## してはいけないこと

- UV・寸法の暗算での JSON 手書き(必ず geo_builder 経由)
- レンダリング画像を見ずに「完成」と報告すること
- 1 unit 未満のジオメトリでの模様表現(テクスチャでやる)
- キューブを増やすことを精巧さと同一視すること(detail-techniques.md 冒頭参照)
- テクセル密度の不統一、純色 (#ff0000 級) のパレット
