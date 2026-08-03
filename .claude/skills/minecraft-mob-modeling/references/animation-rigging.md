# リギングとアニメーション基礎

モデリング段階の判断(pivot 位置・ボーン分割・命名)がアニメーション品質を
決める。**アニメを付けない予定でも、この規約でリグを組んでおく**。後から
pivot を直すと全ポーズが崩れ、実質作り直しになる。

## 目次
1. [pivot 配置の原則](#pivot-配置の原則)
2. [ボーン分割の判断基準](#ボーン分割の判断基準)
3. [Bedrock アニメーション JSON と Molang](#bedrock-アニメーション-json-と-molang)
4. [定番アニメーションのレシピ](#定番アニメーションのレシピ)
5. [Java 側 (setupAnim) の対応](#java-側-setupanim-の対応)

## pivot 配置の原則

- pivot = **関節の回転中心**。解剖学的な関節位置に置く:
  - 肩 = 腕キューブ上端の中心よりやや内側(胴に 1 unit 食い込んだ点)
  - 股関節 = 脚上端、顎 = 顎キューブの後端上部、尾 = 付け根
  - 首 = 頭キューブ下端ではなく「首の付け根」(胴前端上部)
- 検証法: そのボーンを ±30° 回転させた絵を想像する(またはレンダラーで
  rotation を仮入れして描画)。パーツが胴から剥離したり、めり込み過ぎたり
  しなければ正しい。
- 関節をまたぐキューブは禁物。曲げたとき伸びない。キューブは関節で分割し、
  互いに 1〜2 unit 重ねる(重なりが「肉」になり隙間を隠す)。

## ボーン分割の判断基準

ボーンは「独立して動く最小単位」にだけ作る:

- 必須: root / body / head / 各脚 / (あれば)尾・翼・顎
- 尾・首・触手は節ごとにボーン(セグメントチェーン)
- 動かない飾り(角・ベルト)は親ボーンに直付けし、ボーンを作らない
- 迷ったら**作る側に倒す**。使わないボーンのコストはゼロに近いが、
  足りないボーンの追加は UV とテクスチャの再配置を伴うことがある
- 命名規約(anatomy-patterns.md と共通): `root`, `body`, `head`,
  `leg_front_right`, `arm_left`, `tail_0`…。頭は必ず `head`
  (エンジンの視線追従・装備表示が名前を見る)

## Bedrock アニメーション JSON と Molang

RP/animations/mymob.animation.json:

```json
{
  "format_version": "1.8.0",
  "animations": {
    "animation.mymob.walk": {
      "loop": true,
      "anim_time_update": "query.modified_distance_moved",
      "bones": {
        "leg_front_right": { "rotation": [ "math.cos(query.anim_time * 38.17) * 40.0", 0, 0 ] },
        "leg_front_left":  { "rotation": [ "math.cos(query.anim_time * 38.17 + 180) * 40.0", 0, 0 ] },
        "leg_back_right":  { "rotation": [ "math.cos(query.anim_time * 38.17 + 180) * 40.0", 0, 0 ] },
        "leg_back_left":   { "rotation": [ "math.cos(query.anim_time * 38.17) * 40.0", 0, 0 ] }
      }
    },
    "animation.mymob.look_at_target": {
      "loop": true,
      "bones": {
        "head": { "rotation": [ "query.target_x_rotation", "query.target_y_rotation", 0 ] }
      }
    },
    "animation.mymob.idle": {
      "loop": true,
      "bones": {
        "body": { "position": [ 0, "math.sin(query.anim_time * 90) * 0.3", 0 ] },
        "tail_0": { "rotation": [ 0, "math.sin(query.anim_time * 120) * 12", 0 ] }
      }
    }
  }
}
```

要点:
- Molang の三角関数は**度**で動く(`math.cos(360)` で 1 周)。
- `query.anim_time` は再生秒数。`anim_time_update: query.modified_distance_moved`
  に差し替えると「移動距離」が時間になり、**歩速と脚の回転が自動同期**する。
  バニラ四足の魔法定数 `38.17`(= Java の 0.6662 rad)をそのまま使う。
- 対脚は位相 180° ずらし(対角歩行)。振幅 30〜45° が自然域。
- 視線追従は `head` ボーンに `query.target_x_rotation / target_y_rotation`。
- クライアントエンティティ(entity.json)の `animations` に登録し、
  `scripts.animate` か animation controller で再生条件を書く(常時系は
  `"scripts": {"animate": ["look_at_target", {"walk": "query.modified_move_speed > 0.01"}]}`)。

## 定番アニメーションのレシピ

- **歩行(4足)**: 上記の通り対角位相。精巧化: 脚と同位相で body に
  ±0.3 unit の上下 + 頭に逆位相の小さな上下(首の慣性)。
- **歩行(2足)**: 腕を脚と逆位相で振る。振幅は脚 40°・腕 30°。
- **アイドル呼吸**: body の scale でなく **position.y を sin で ±0.2〜0.4**。
  胸だけのボーンがあれば scale x/z を 1.00〜1.03 で膨らませるとより上質。
- **尾のしなり**: セグメントチェーン各節に同じ sin を**位相 30〜45° ずつ遅らせて**
  与える: `tail_n.rotation.y = sin(t*120 + n*40) * 15`。先端ほど振幅を
  1.2〜1.5 倍にすると鞭のしなりになる。
- **羽ばたき**: 翼ボーン rotation.z を sin で ±40〜70°。ホバリング中は
  周波数を上げ振幅を下げる。
- **威嚇・咆哮**: 顎ボーン rotation.x 20〜35° + head を -10° 上げ +
  body を 5° 後傾。0.2 秒で開き 0.5 秒で戻すと重みが出る。
- **死亡**: root の rotation.z を 0→90°(0.5 秒、ease)+ position.y 沈み。

## Java 側 (setupAnim) の対応

バニラ式 Java モッドでは同じ式をコードで書く(ラジアン):

```java
@Override
public void setupAnim(T entity, float limbSwing, float limbSwingAmount,
                      float ageInTicks, float netHeadYaw, float headPitch) {
    this.head.yRot = netHeadYaw * ((float)Math.PI / 180F);
    this.head.xRot = headPitch * ((float)Math.PI / 180F);
    this.rightLeg.xRot = Mth.cos(limbSwing * 0.6662F) * 1.4F * limbSwingAmount;
    this.leftLeg.xRot  = Mth.cos(limbSwing * 0.6662F + (float)Math.PI) * 1.4F * limbSwingAmount;
    this.tail.yRot = Mth.sin(ageInTicks * 0.1F) * 0.25F;  // idle 揺れ
}
```

- `limbSwing`(移動距離)と `limbSwingAmount`(0〜1 の移動量)のペアが
  Bedrock の `modified_distance_moved` / `modified_move_speed` に対応する。
- `0.6662F` は Bedrock の `38.17` と同じ角速度(rad/度の違いだけ)。
- 複雑なキーフレームアニメを Java でやるなら GeckoLib に切り替え、
  Blockbench の Animate タブで作った .animation.json をそのまま使う。
