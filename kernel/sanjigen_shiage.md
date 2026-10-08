# 画像由来3Dの仕上げ

`dougu/sanjigen_shiage.py` を kit に足す。kernel は未変更。
組込側で `configure_output(_output)` を呼び、`TOOLS` を kit に登録する。
出力は相対名。Z上・正面−Y・左＋X。回転/倍率を確定する。

## 道具

- `import_model(path)`：glb/obj/fbx一覧。`clean(obj)`：近接点/小穴/法線を直し非多様体を報告。開口は `fill_holes=False`。
- `split_parts(obj,how,min_faces)`：loose/material/normal_angle/vertex_color。UV/頂点色を保持し「部品」へ。原本/小片も残す。体/艤装は認識しない。`save_parts('parts')`：個別glb。
- `remesh(obj,kind,target_faces)`：voxel/quadriflow/decimate。面数は目安。薄板のvoxelはdecimateへ。リグ前に使う。
- `smart_uv`、`uv_pack(obj)`。`uv_layout_png`：白地黒線の下絵。AIに線を変えず塗ってもらう。`apply_texture(obj,path)` で貼り替える。
- `bake_from_original(src,dst)`：頂点色/基本色をCycles CPU、selected-to-active、自動cageで転写。位置を揃える。裏写りは `cage` を縮める。
- `project_views(obj,{'front':画像,...})`：前後左右上下＋斜め4方向（front_leftなど）。正投影し法線/alphaで混ぜて焼く。姿勢/余白を揃え背景透明に。未提供方向は黒。遮蔽/ずれは手直し。
- `auto_rig(body,parts=艤装一覧)`：17骨＋自動ウェイト。A/Tポーズの下書き、要手直し。parts省略時は他の部品を艤装扱い。髪/服は渡さない。
- `animate(rig,kind,seconds)`：idle/walk/wave/turn、新Action。その場歩き、IKなし。`render_animation_mp4` は現カメラ。`turntable_video` は周回カメラ＋仮照明。内蔵FFmpeg/H.264対応版が必要。
- `report()`：面数、部品数、UV島/重なり、画像寸法。`uv_overlap_complete=False` は検査未完。

## 艦娘glbの例

```python
import kit
original = kit.import_model('/入力/艦娘.glb')[0]
kit.clean(original, fill_holes=False)
parts = kit.split_parts(original, 'loose', min_faces=20)
body = parts[0]  # 最大部品。体か確認する
body.name = '体'
equipment = parts[1:]
for i, p in enumerate(equipment):
    p.name = '艤装_' + str(i)
kit.save_parts('parts')
kit.remesh(body, 'quadriflow', 8000)
for p in equipment:
    kit.remesh(p, 'decimate', 2000)
for p in parts:
    kit.smart_uv(p)
    kit.bake_from_original(original, p, 1024, path=p.name + '_色.png')
    kit.uv_layout_png(p, p.name + '_UV.png')
rig = kit.auto_rig(body, parts=equipment)
kit.animate(rig, 'idle', 3)
kit.turntable_video('回転.mp4', 3, 'CYCLES')
print(kit.report())
```

試験：`python3 -m unittest dougu.test_sanjigen_shiage`。
実機はClaudeが砂箱外で `SEISEI_BLENDER=1` を付ける。Codexは起動禁止。
[API](https://docs.blender.org/api/4.5/bpy.ops.object.html)
