# 実例: フェネックギツネ (fennec)

スキルの全技法を 1 体に詰めた実例。**新規作成のコードを書く前に
`build_fennec.py`、既存モデルの改造コードを書く前に `refine_fennec.py`
を読む**こと。構成の手本として使う。

| ファイル | 内容 |
|---|---|
| build_fennec.py | 【新規作成】モデル+テクスチャを生成する単一スクリプト(コメントに技法名を明記) |
| fennec.geo.json | 生成物: 12 ボーン / 17 キューブ(板ポリ 2)/ 64×64 |
| fennec.png | 生成物: テクスチャ(コードで描画、シード固定) |
| fennec_flat.png | ボーン別色分けプレビュー(構造確認用) |
| fennec_preview.png | テクスチャ付き 6 ビュープレビュー |
| refine_fennec.py | 【ブラッシュアップ】fennec を読み込みレビュー指摘を修正する実例(load / 回転編集 / translate_subtree / キューブ追加+差分テクスチャ) |
| fennec_refined.geo.json | 改良版生成物(尻尾カール強化・スタンス拡大・襟巻き追加) |
| fennec_refined.png | 改良版テクスチャ(既存 PNG に新規矩形だけ描き足し) |
| fennec_refined_preview.png | 改良版プレビュー(fennec_preview.png と並べて before/after 比較) |

## この実例が使っている技法(→ 詳細は各リファレンス)

- 小型四足アーキタイプの実寸ブロックアウト(anatomy-patterns.md)
- 二次パーツの食い込み: 頭・胸毛・後脚の腿(detail-techniques.md)
- 三段テーパーの鼻先、`inflate_step` による整数サイズのままの尻尾の先細り
- `segment_chain()` の尻尾(曲げ -14°/節で上向きカール)
- 厚さ 0 の板ポリ頬毛 + テクスチャ透過でギザギザの毛先
- 耳ボーンの微回転 ±12°(アニメ可能なボーンとして分離)
- 左手足・左耳の **mirror UV 共有**(pack_uv() を途中で呼び、右の uv を
  ピン留め共有する 2 段構え)
- 脚の外側面を胴から 0.25 ずらして z-fight 回避
- パレット 5 段 + 色相シフト、カウンターシェーディング、シード付きノイズ、
  UV 座標は全て `uv_map()` 経由(texturing.md)

## 再現手順(検証ループの手本)

```bash
python3 build_fennec.py
python3 ../../scripts/validate_geo.py fennec.geo.json --texture fennec.png
#   → エラー 0 / 警告は mirror 共有 4 件のみが正常
python3 ../../scripts/render_geo.py fennec.geo.json -o fennec_flat.png --scale 10
python3 ../../scripts/render_geo.py fennec.geo.json --texture fennec.png \
        -o fennec_preview.png --scale 10
#   → PNG を必ず目視(Read)してから完成と判断する
```

## ブラッシュアップ編(refine_fennec.py)

review_geo のレポートを起点に、UV 保全の三原則(review-refinement.md)を
守って改良するループの手本:

```bash
python3 ../../scripts/review_geo.py fennec.geo.json --texture fennec.png
#   → 指摘: 三次ディテール薄い / (目視) 尻尾カール浅い・スタンス狭い
python3 refine_fennec.py
python3 ../../scripts/review_geo.py fennec_refined.geo.json --diff fennec.geo.json
#   → 14 変更のみ: 襟巻き +1 キューブ(空き UV へ自動配置)、脚 ±0.25、
#     尻尾回転 -14→-22。想定外の差分ゼロを確認してから次へ
python3 ../../scripts/validate_geo.py fennec_refined.geo.json --texture fennec_refined.png
python3 ../../scripts/render_geo.py fennec_refined.geo.json \
        --texture fennec_refined.png -o fennec_refined_preview.png --scale 10
#   → before (fennec_preview.png) と after を両方 Read して比較
```
