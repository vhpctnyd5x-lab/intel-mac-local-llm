# 「作る」への追加部品（Claude の組込用）

`seisei_hoka.py` は kernel に依存しない標準ライブラリの部品。kernel は変更していない。
成功・失敗とも `ok / 結果 / 画像 / 場所`。`画像` はPNGの下見だけで、音声は空リスト。
出力は未作成または空の新規フォルダのみ。使用済みの出力先は、失敗後も再利用せず新しくする。
ログ・台本・入力文は出力先の `.work/` と `text.txt` に残る。入力元は変更しない。
ネットワークは禁止。Mac標準と既存のBlenderだけを使い、音声・模型・追加パッケージを取得しない。
Blenderのネットワークはsandbox-execで禁止。他はネットワーク処理のない固定コマンドとAppleのローカル画像処理を使う。

## 接続する引数

| tsukuru 側 | 呼び出す関数 |
| --- | --- |
| `kind=koe` | `koe(text, voice="Kyoko", rate=None, out_dir=seisei.new_folder(...))` |
| `kind=haikei` | `haikei(image_path, out_dir=seisei.new_folder(...))` |
| `kind=douga, video_kind=gazou` | `douga("gazou", out_dir, images=[...], audio_path=None, seconds=6, motion="zoom")` |
| `kind=douga, video_kind=3d` | `douga("3d", out_dir, glb_path=..., seconds=4, engine="WORKBENCH")` |

`video_kind` は外側の `kind=douga` と内側の種別を区別するための接続案。
`koe_list()` は上記4キーに `声=[名前,...]` を追加する。ja_JPの既存音声のみ。
`rate` は80〜500語/分、文は2000字まで。AIFF原本とAACのM4Aを保存する。
背景除去は事前に `build_haikei()`。`swiftc -O`、ビルド先はgit対象外の `dougu/bin/haikei`。
既存バイナリが古ければ上書きせず停止する。古い物を別に退避してからビルドする。
前景マスクは人物に限定しない。利用不可時は物体の注目領域へ切り替えるが、これは精密な輪郭ではないので結果に近似と表示する。
SwiftはVisionをCPU指定、Core Imageをソフトウェア指定で動かす。プロセスのクラッシュは再実行しない。
動画は最大1280×720・24fps・30秒、画像1〜8枚。`motion="pan"` は横流し。
音声はm4a/wav。短い音は最後に無音、長い音は動画の長さに切る。
Blenderは `-b --factory-startup --disable-autoexec -t 2`、既存sanjigenと同じsandbox-exec設定。
`.work` 内に設定・一時領域を限定し、環境の秘密を渡さず、時間切れはプロセス群を停止する。
WorkBench/Eeveeの描画は外で確認する。CodexではMetal確認のクラッシュ歴があるため起動しない。

## 頭脳向け hint の文案

`HINTS` と `hint(request)` を参照（各種1〜2行）。本体の既存画像/3D判定より先に追加判定する。

## Claude が外で行う確認

```sh
python3 -m unittest dougu/test_seisei_hoka.py
SEISEI_BLENDER=1 python3 -m unittest dougu.test_seisei_hoka.BlenderIntegrationTests.test_image_movie_with_sound
SEISEI_BLENDER=1 python3 -m unittest dougu.test_seisei_hoka.BlenderIntegrationTests.test_glb_turntable
```

SEISEI_BLENDER付きの2行だけがBlenderを起動する。まず短い画像＋音の1本を完走し、その後GLB一周を確認する。
映像をQuickTimeで開き、H.264/AAC・音の有無・寄り/横流し・GLBの中心/画角・最初の下見を目視する。
必要なら手持ちの人物・物・動物の写真をそれぞれ別の新規出力先で `haikei` に渡す。
Visionがクラッシュした場合はその場で停止し、ログの終了信号を確認する（再試行しない）。
組込後は本物の作品フォルダで1依頼を完走する。通常試験は一時フォルダのみ。
Codexのseatbelt内では音声サービス待ちが終わらないため、実物のsay/afconvert試験は理由付きで見送る。
afconvert単独も手元で作るPCM音声から一度試したが、砂箱内の `afconvert -hf` はm4afのdata_formatsが空、変換は終了コード2だった。外の試験で確認する。
外の通常試験では実物を実行する。標準Swiftモジュールの初回ビルドは時間がかかるので、bin内のキャッシュを再利用し並列2本に制限する。

## 今回の実機結果

Swiftのビルドは成功。CodexはBlenderを一度も起動していない。
Visionの一度の実行は、前景マスクでVision Code 16（Revision1未対応）、代替でOpenCLのCPU処理失敗・CVPixelBuffer作成失敗（-6662）。
クラッシュ信号ではなく終了コード1で停止。繰り返さず、Codex内での実物試験は見送りにした。
最終の通常試験は20件・15件通過・5件見送り（Blender 2、say、AAC、Visionの実物確認）。
これは砂箱内の一度の結果であり、外での成功や人物・物・動物の輪郭精度は未確認。
`dougu/ura.sh` は砂箱内ではpsを使えず、外の処理全体が0件とは確認できない。
外では `ps -axo pid,etime,command` で `seisei-direct-say-1008` と `dougu/bin/build-` の今回の試験・ビルドも確認する。

## 仕様の参照

- [Apple: 前景インスタンスマスク](https://developer.apple.com/documentation/vision/vngenerateforegroundinstancemaskrequest)
- [Apple: 物体の注目領域](https://developer.apple.com/documentation/vision/vngenerateobjectnessbasedsaliencyimagerequest)
- [Blender 4.5: SequenceEditor（strips）](https://docs.blender.org/api/4.5/bpy.types.SequenceEditor.html)
