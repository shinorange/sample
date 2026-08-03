# ジオメトリフォーマット完全リファレンス

Minecraft MOB モデルのファイル形式・座標系・UV 計算の正確な仕様。
モデルを**書く前に必ずこの座標系とUVの節を確認**すること。ここを間違えると
全部品の位置とテクスチャがずれる。

## 目次
1. [座標系と単位](#座標系と単位)
2. [Bedrock ジオメトリ (.geo.json)](#bedrock-ジオメトリ-geojson)
3. [Box UV の展開レイアウト(最重要)](#box-uv-の展開レイアウト)
4. [Per-face UV](#per-face-uv)
5. [inflate / mirror / rotation](#inflate--mirror--rotation)
6. [Java エンティティモデル(モッド)](#java-エンティティモデルモッド)
7. [ゲームに載せる: リソースパック配線](#ゲームに載せるリソースパック配線)
8. [フォーマット選択ガイド](#フォーマット選択ガイド)

## 座標系と単位

- **1 unit = 1/16 ブロック = 1 テクスチャピクセル**(基準密度)。16 units = 1 ブロック = 1m。
- **Y が上**。原点 `(0,0,0)` はエンティティの**足元中央**。
- **MOB の正面は -Z(北)**。頭・鼻先は -Z 方向に伸ばす。バニラの全モデル
  (豚の頭、牛の頭など)がこの向き。Blockbench のグリッドの「N」マークが正面。
- +X は東。左右対称パーツは X の符号で対にする(例: 右脚 pivot x=-1.9, 左脚 x=+1.9)。
- キューブの `origin` は **最小コーナー**(x,y,z が最も小さい角)で、`size` は
  +x/+y/+z 方向へ伸びる。例: ヒューマノイドの頭 = `origin [-4, 24, -4], size [8, 8, 8]`。

## Bedrock ジオメトリ (.geo.json)

現行フォーマット(format_version 1.12.0 以降)。Blockbench でそのまま
開ける・エクスポートできる。最小の完全な例:

```json
{
  "format_version": "1.12.0",
  "minecraft:geometry": [
    {
      "description": {
        "identifier": "geometry.mymob",
        "texture_width": 64,
        "texture_height": 64,
        "visible_bounds_width": 3,
        "visible_bounds_height": 3,
        "visible_bounds_offset": [0, 1, 0]
      },
      "bones": [
        { "name": "root", "pivot": [0, 0, 0] },
        {
          "name": "body", "parent": "root", "pivot": [0, 12, 0],
          "cubes": [
            { "origin": [-4, 12, -2], "size": [8, 12, 4], "uv": [16, 16] }
          ]
        },
        {
          "name": "head", "parent": "body", "pivot": [0, 24, 0],
          "cubes": [
            { "origin": [-4, 24, -4], "size": [8, 8, 8], "uv": [0, 0] },
            { "origin": [-4, 24, -4], "size": [8, 8, 8], "uv": [32, 0],
              "inflate": 0.5 }
          ]
        }
      ]
    }
  ]
}
```

重要な仕様:
- `identifier` は必ず `geometry.` で始める。クライアントエンティティ定義から
  この ID で参照される。
- `texture_width/height` は **UV 座標系の解像度**。テクスチャ画像はこのサイズ
  (または整数倍。倍にすると HD テクスチャ)でなければならない。
- ボーンの `pivot` は回転中心(モデル空間の絶対座標)。**ボーンはキューブを
  平行移動しない**。キューブの `origin` は常にモデル空間の絶対座標で書く。
  pivot はアニメーションと `rotation` の回転軸としてだけ効く。
- 親ボーンは子より先に定義されている必要はないが、先に書く方が読みやすい。
- `visible_bounds_*` は描画カリング範囲(ブロック単位)。モデルより小さいと
  画面端でモデルが消える。余裕を持たせる。
- 旧 1.8 形式(トップレベルに `"geometry.name": {...}`)は書かないこと。
  読む必要があれば Blockbench で変換。

## Box UV の展開レイアウト

キューブ 1 個のテクスチャは、`uv: [u, v]` を起点に**十字に似た固定レイアウト**で
展開される。サイズ `(w, h, d)`(幅・高さ・奥行)のキューブの場合:

```
                u+d      u+d+w    u+d+2w
        v   ┌────┬────────┬────────┐
            │    │  up    │ down   │      ← 高さ d の行
        v+d ├────┼────────┼────────┼────────┐
            │east│ north  │ west   │ south  │  ← 高さ h の行
            │(d) │ (w)    │ (d)    │ (w)    │
            └────┴────────┴────────┴────────┘
            u    u+d      u+d+w    u+2d+w   u+2d+2w
```

- **north = 正面**(-Z 面)。占有領域: 幅 `2*(w+d)`、高さ `d+h`。
- ヒューマノイドの頭 8×8×8 を `uv:[0,0]` に置くと、プレイヤースキンと同じ
  配置になる(正面が (8,8)〜(16,16))。この一致で計算を検算できる。
- **box UV はサイズが整数のときだけきれいに並ぶ**。小数サイズのキューブは
  面同士がテクスチャピクセルを共有して滲むので、per-face UV にするか、
  サイズを整数にして `inflate` で微調整する。
- UV 領域は他のキューブと重ねない(左右対称パーツで意図的に共有する場合を
  除く)。`scripts/geo_builder.py` の自動パッキングを使えば重なりは起きない。

## Per-face UV

面ごとに矩形を指定する形式。`uv` をオブジェクトにする:

```json
{ "origin": [-2, 0, -2], "size": [4, 4, 4],
  "uv": {
    "north": { "uv": [0, 0],  "uv_size": [4, 4] },
    "east":  { "uv": [4, 0],  "uv_size": [4, 4] },
    "up":    { "uv": [0, 4],  "uv_size": [4, 4] }
  } }
```

- **書かなかった面は描画されない**。埋まって見えない面を削って描画コストと
  テクスチャ領域を節約できる(精巧モデルでキューブ数が多いときに有効)。
- `uv_size` を負にするとその軸で反転サンプリングになる。
- 複数キューブで同じ矩形を再利用できる(鱗・レンガ的な繰り返し表現)。
- box UV と per-face UV はキューブ単位で混在してよい。

## inflate / mirror / rotation

- `inflate: n` — UV を変えずにキューブを全方向へ n unit 膨らませる。
  用途: (1) 服・毛皮・鎧の**重ね着レイヤー**(本体と同じ origin/size で
  inflate 0.25〜0.5 の外殻を重ねる。ゾンビ服・プレイヤーの外側レイヤーが
  この方式)。(2) **Z-fighting 回避**(完全に同じ平面に 2 面が重なると
  チラつく。0.1〜0.25 ずらす)。(3) 整数サイズを保ったままの微妙な太さ調整。
  負の inflate で痩せさせることもできる。
- `mirror: true` — テクスチャを左右反転サンプリング(east/west 面が入れ替わり
  U が反転)。**右手足のUVを左手足で再利用**してテクスチャ領域を半分にする
  ための機能。ボーンに書けば配下のキューブのデフォルトになる。
  非対称な模様(紋章・傷)があるパーツには使わない。
- キューブ単位の `rotation: [x, y, z]`(度)+ `pivot` — ボーンを増やさずに
  1 キューブだけ傾ける。牙・羽根・アホ毛など**アニメーションしない**傾き向け。
  アニメーションで動かす部位の傾きはボーンの `rotation` で付ける。
- 回転の合成順は環境差の罠があるので、**2 軸以上の複合回転は Blockbench で
  最終確認**する。1 軸回転はどの実装でも同じ。

## Java エンティティモデル(モッド)

Forge/NeoForge/Fabric のバニラ式モデルは Java コードで同じキューブ構造を書く。
**座標系が Bedrock と違う**:

| | Bedrock geo | Java ModelPart |
|---|---|---|
| Y 軸 | 上が + | **下が +** |
| 足元 | y = 0 | y = 24 |
| 変換 | `java_y = 24 - bedrock_y` (pivot) | |
| inflate | `inflate` | `CubeDeformation` |
| UV 起点 | `uv: [u, v]` | `.texOffs(u, v)` |

```java
public static LayerDefinition createBodyLayer() {
    MeshDefinition mesh = new MeshDefinition();
    PartDefinition root = mesh.getRoot();
    PartDefinition body = root.addOrReplaceChild("body",
        CubeListBuilder.create().texOffs(16, 16)
            .addBox(-4.0F, 0.0F, -2.0F, 8, 12, 4, CubeDeformation.NONE),
        PartPose.offset(0.0F, 12.0F, 0.0F));   // pivot: 24 - 12 = 12
    body.addOrReplaceChild("head",
        CubeListBuilder.create().texOffs(0, 0)
            .addBox(-4.0F, -8.0F, -4.0F, 8, 8, 8),
        PartPose.offset(0.0F, 0.0F, 0.0F));    // 頭の addBox は pivot 相対
    return LayerDefinition.create(mesh, 64, 64);  // texture_width/height
}
```

- Java では `addBox` の座標は**親 PartPose からの相対**。Bedrock の絶対座標と
  混同しない。
- 手書き変換はミスりやすいので、**Blockbench の「Modded Entity」プロジェクトで
  作って Java エクスポート**するのが安全。geo.json → Modded Entity の変換も
  Blockbench 上でできる。
- 複雑なアニメーション付きモッド MOB は **GeckoLib** を使うと Bedrock 形式の
  .geo.json + .animation.json をそのまま Java モッドで再生できる(推奨)。
- バニラの見た目を差し替えるだけなら **OptiFine CEM**(.jem/.jpm)という
  選択肢もある(Blockbench の OptiFine Entity プロジェクト)。

## ゲームに載せる: リソースパック配線

Bedrock アドオンでモデルを実際に表示する最小配線(RP = リソースパック):

```
RP/
├── manifest.json
├── models/entity/mymob.geo.json
├── textures/entity/mymob.png
├── entity/mymob.entity.json          ← クライアントエンティティ(結線役)
└── render_controllers/mymob.json     ← 省略可(単純な場合)
```

`entity/mymob.entity.json`:
```json
{
  "format_version": "1.10.0",
  "minecraft:client_entity": {
    "description": {
      "identifier": "custom:mymob",
      "materials": { "default": "entity_alphatest" },
      "textures":  { "default": "textures/entity/mymob" },
      "geometry":  { "default": "geometry.mymob" },
      "render_controllers": [ "controller.render.mymob" ],
      "spawn_egg": { "base_color": "#c9a86a", "overlay_color": "#3e2f23" }
    }
  }
}
```

`render_controllers/mymob.json`:
```json
{
  "format_version": "1.10.0",
  "render_controllers": {
    "controller.render.mymob": {
      "geometry": "Geometry.default",
      "materials": [ { "*": "Material.default" } ],
      "textures": [ "Texture.default" ]
    }
  }
}
```

- マテリアル: `entity` = 不透明、`entity_alphatest` = 透過ピクセルを抜く
  (羽・ヒレ・板ポリを使うなら必須)、`entity_emissive_alpha` = 発光系。
- 挙動(スポーン・AI)はビヘイビアパック側 `BP/entities/mymob.json` が必要
  だが、モデリングの範囲外なのでここでは扱わない。

## フォーマット選択ガイド

| 目的 | 作る形式 |
|---|---|
| Bedrock アドオン | .geo.json(このスキルの標準。スクリプト群が対応) |
| Java モッド(静的〜簡単な動き) | Blockbench Modded Entity → Java エクスポート |
| Java モッド(複雑なアニメ) | GeckoLib(.geo.json + .animation.json) |
| バニラ Java の見た目差し替え | OptiFine CEM (.jem) |
| 配布・編集用ソース | .bbmodel(Blockbench プロジェクト。テクスチャ埋め込み可) |

**このスキルでは .geo.json を一次成果物にする。** Blockbench で読み書きでき、
GeckoLib にそのまま使え、スクリプトで検証・プレビューできるため。
