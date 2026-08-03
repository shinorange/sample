# 実例: フェネックギツネ (fennec)

スキルの全技法を 1 体に詰めた実例。**テクスチャ生成コードや新規モデルの
スクリプトを書く前に `build_fennec.py` を読む**こと。構成の手本として使う。

| ファイル | 内容 |
|---|---|
| build_fennec.py | モデル+テクスチャを生成する単一スクリプト(コメントに技法名を明記) |
| fennec.geo.json | 生成物: 12 ボーン / 17 キューブ(板ポリ 2)/ 64×64 |
| fennec.png | 生成物: テクスチャ(コードで描画、シード固定) |
| fennec_flat.png | ボーン別色分けプレビュー(構造確認用) |
| fennec_preview.png | テクスチャ付き 6 ビュープレビュー |

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
