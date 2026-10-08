# Intel Mac の画像→3D（本番未接続）

Codex は取得・pip・Blender・実推論を実行しない。Claude が次を実行する。

## 準備

```bash
TRIPOSR_COMMIT='<公式リポジトリで確認した40桁SHA>' bash dougu/triposr_junbi.sh
```

SHA は捏造しない。未指定・main・タグ・短縮SHAは取得前に停止。既存cloneはHEAD一致が必須で、自動resetしない。
新しい seisei_venv のみ変更。uta_venv は土台の実行ファイルを確認するだけ。
torch 2.2.2 / NumPy 1.26.4 / Python 3.11。CPU専用、MPS/CUDAは使わない。
直接依存と主要間接依存を固定し、導入後の全版は models/triposr/pip-freeze.txt に保存。
固定版のwheelがない必須ネイティブ依存は停止する（別版探索・torchmcubesビルドはしない）。
上流のrequirements.txtは導入しない。rembgは未導入で、上流import用の明示的な無効化shimのみ。
背景処理はApple Visionのhaikeiだけ。rembgを呼ぶコードはエラーにする。
isosurface.py は import 一箇所の小パッチ。上流のgrid/forwardで軸・閉曲面・法線を確認してから模型取得へ進む。
ベイク依存の固定wheelだけ任意扱い。導入失敗の詳細は bake-install.log、GLBは頂点色で出す。
模型のSHAは準備時に解決・記録し、TripoSRのconfig.yaml/model.ckptと、設定が指定する画像encoderをローカルへ配置。
encoderも必要な場合は1.7GB以外に追加取得がある。実行時のconfigはローカルパスに変換する。

## 最初の1本（準備後、Claudeが実行）

```bash
python3 dougu/sanjigen_gazou.py '/絶対パス/入力.png' '/絶対パス/新規出力先' --mc-resolution 128 --chunk-size 2048 --no-texture
```

まず128・ベイクなしで完走させる。通常は `run(image_path, out_dir, mc_resolution=256, chunk_size=8192, texture=True)`。
背景の透明PNG→余白調整（占有率0.85）→灰色合成→TripoSR CPU→GLB。
ベイク時は1024px。macOSのOpenGLが使えなければ推論は繰り返さず頂点色へ切り替え、理由を返す。
下見PNGはtrimeshのmeshをPillowで簡易正投影（512px・painter法）。Blender/ディスプレイ/pygletは不要。
戻り値は `ok / 結果 / 画像 / 場所`。出力は model.glb / preview.png / jissoku.json / triposr.log。
空の出力先限定。失敗後は原因を確認し、次は別の新規出力先を使う。部分成果を勝手に消さない。

## 隔離・計測

sandbox-exec の外側プロファイルでネット禁止、書込は出力先・専用一時領域・/dev/nullだけ。
Apple Visionが内側で広いプロファイルを使っても、外側の制限を解除できない。
秘密環境は引き継がない。HF/Transformersもoffline設定。設定・模型・コードは参照だけ。
これは書込/ネット隔離であり、機密ファイルの読み取り隔離ではない。
最大2時間。時間切れ・中断時は起動したプロセス群を停止し、裏に残さない。
時間は背景除去・模型読込・推論・抽出・ベイク・下見を含む。
Darwinのru_maxrss（byte）をMiBへ変換。worker/背景helperの個別最大RSSで、同時合計・Mac全体使用量ではない。
失敗時もworkerが動ければ段階・経過・RSSを jissoku.json に残す。SIGKILL/OOMでは報告を保証できない。

## 試験

```bash
PYTHONDONTWRITEBYTECODE=1 python3 dougu/test_sanjigen_gazou.py
SEISEI_TRIPOSR=1 SEISEI_TRIPOSR_IMAGE='/絶対パス/入力.png' PYTHONDONTWRITEBYTECODE=1 python3 dougu/test_sanjigen_gazou.py
```

通常試験は標準ライブラリのみで、ネット・pip・模型・Blender・実際の切り抜きを呼ばない。
実機試験は128/2048/ベイクなし。出力は一時領域で試験終了時に除去する。作品保存は上のCLIを使う。
本番kernelの変更・組込・commitは行わない。

## 見込み（未測定の推測）

| 設定 | 時間 | workerピークRSS |
| --- | --- | --- |
| MC128・chunk2048・頂点色 | 2〜20分 | 5〜10 GiB |
| MC256・chunk8192・頂点色 | 5〜30分 | 6〜12 GiB |
| MC256・1024pxベイク | 上記に数分〜十数分追加 | 8〜14 GiB程度、超過もあり得る |

CPU実機未測定の幅であり、所要時間・16GB内完走を保証する数字ではない。
chunkはrendererの中間バッファを減らすが、MCグリッド全体は残る。重い併用は避け、まず1本の実測で判断。
模型約1.7GB＋画像encoder＋torch/依存＋clone/cache。準備時の一時複製も見込み、空き10GB以上が目安。
初回取得時間は回線次第で、上の推論時間に含めない。
