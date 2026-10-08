# Blender の小さな道具箱

`import kit` で開始。呼出側は `dougu.sanjigen.run(台本, Path(出力先), timeout=300)`。単位m、上Z、正面-Y。初期物体は消す。

## 関数

- 基本形: `cube(size=2)`、`uv_sphere()`、`cylinder(radius=1,depth=2,vertices=16)`、`cone(radius=1,depth=2,vertices=12)`、`torus()`、`plane()`、`monkey()`。全て name/location/scale/rotation(度)/color 指定可。
- 変形: `transform(o,location=None,rotation=None,scale=None)`。回転・角度は度。
- 面: `extrude(o,faces=[面番号],distance=.2,direction=(0,0,1))`、`inset(o,faces=[面番号],thickness=.1)`。faces=None は全面。
- 修飾: `bevel(o,width=.1,segments=2)`、`subdivision(o,levels=1)`、`mirror(o,axis='X')`、`array(o,count=2,offset=(1.2,0,0))`（相対間隔）、`boolean(o,cutter,operation='DIFFERENCE')`（切削物体は残る）。既定で確定、apply=Falseで残す。
- 軽量化: `decimate(o,ratio=.5)`、`voxel_remesh(o,voxel_size=.1)`、`quadriflow(o,faces=500)`（対応時のみ）。再構築後はUV再作成。
- 法線・陰影: `normals(o)`、`shade(o,smooth=True)`（Falseはフラット）。
- UV: `smart_project(o,angle=66)`、`cube_project(o)`、`unwrap(o,angle=60)`（角度シーム）、`uv_islands(o)` は島数。
- 材質: `material(o,color=(.6,.6,.6,1),metallic=0,roughness=.5)` は材質。`bake_texture(o,kind='noise',filename='texture.png',resolution=128)` はPNGパス。kind=noise/voronoi、Cycles CPU、16〜512px。UV自動補完。
- 骨: `armature(o,bones=None)`。bonesは `(名前,始点,終点,親名またはNone)` の列。既定2本、自動ウェイト。位置は形に合わせる。
- 保存: `export('model.glb',objects=None)`。glb/obj/fbx/stl/blend。全メッシュと骨、blendは全シーン。`preview('preview.png')` は自動カメラ・照明の512px PNG。省略時も最後に自動下見。

## 椅子

```python
import kit
kit.cube(name='座面',scale=(.45,.45,.07),location=(0,0,.9))
kit.cube(name='背',scale=(.45,.07,.45),location=(0,.38,1.4))
for x in (-.35,.35):
    for y in (-.35,.35):
        kit.cube(name='脚',scale=(.05,.05,.45),location=(x,y,.45))
kit.export('chair.glb')
```

## 低ポリの木

```python
import kit
t = kit.cylinder(radius=.12,depth=1.5,vertices=8,location=(0,0,.75))
kit.material(t,color=(.25,.1,.03,1))
for z,r in ((1.3,.7),(1.8,.55),(2.3,.35)):
    o = kit.cone(radius=r,depth=1,vertices=8,location=(0,0,z))
    kit.material(o,color=(.05,.35,.08,1))
kit.export('tree.glb')
```

## キャラの頭の下書き

```python
import kit
h = kit.uv_sphere(name='頭',scale=(.8,.7,1))
kit.smart_project(h)
for x in (-.3,.3):
    e = kit.uv_sphere(name='目',radius=.12,location=(x,-.65,.2))
kit.export('head.glb')
kit.preview()
```

出力は相対パス。importはbpy/bmesh/mathutils/math/random/kitのみ。open/exec/eval・OS・ネット禁止。ASTだけでは完全隔離不可。macOS砂箱必須（書込例外: 専用一時領域・/private/var/folders・/dev）。読取隔離なし。下見engineはBLENDER_WORKBENCH/BLENDER_EEVEE_NEXT/CYCLES（CPU）。戻り値: ok/error/log（40行）、files、stats（頂点・面・三角形・UV・島・材質）、preview。
