# Intel Mac・CPU だけの生成機能調査

調査日: **2026-10-08（日本時間）**。公開一次資料・配布ファイル一覧・この Mac の読取確認による。インストール、模型の大容量ダウンロード、生成 API 呼出し、課金、カーネル変更、commit はしていない。

## 1. 結論

| 優先 | 結論 |
| --- | --- |
| 今日の第1弾・最大3つ | **SD1.5＋stable-diffusion.cpp、U²-Net＋rembg、日本語 Open JTalk**。取得する主要模型は合計約 **4.44GB**。依存・ソースを含む取得予算は **7GB（推測）**、上限10GBを設ける。 |
| 次に試す画像模型 | SD-Turbo の少ステップ生成、その後 FLUX.2-klein-4B。最新・小型でも文字エンコーダと VAE を別に数える。 |
| 3D の近道 | 生成画像→背景除去→外部の画像→3D→Blender で整理。ローカルだけなら文字から Python 台本を作って手続き的モデリング。ただし **インストール済み Blender のヘッドレス起動が今回の環境では異常終了**。第1弾から外す。 |
| 動画・高品質3D・長い音楽 | この CPU では外部 GPU を基本とする。ローカルの短い動画は、まず画像列・パン・ズーム・台本アニメーションを合成する。 |
| 「圧縮すれば35Bと同じように動く」 | **重みが収まる場合はあるが、速さ・総メモリ・CPU対応は別問題**。動画の中間データや CUDA 専用演算は GGUF 化だけでは解決しない。 |
| 外部送信 | 模型取得と推論送信を別操作にする。通常の生成はネットワーク禁止。NVIDIA・GCP は送る内容・費用・期限を本人が承認したジョブだけ。 |

ここで「第1弾」は **Intel CPU 対応の実装・配布物が確認でき、CUDA/Metal を前提にしない構成**という意味。SD・rembg・Open JTalk の生成実行そのものは未検証であり、「この Mac で完走済み」とは書かない。導入時は後掲の1本を完走させてからカーネルへ接続する。

### 実機確認と数字の読み方

| 項目 | 確認結果・区別 |
| --- | --- |
| 対象 | i7-9750H・16GB・AVX2・GPU 計算なし。CPU型番・RAM・頭脳8GB常駐は依頼の前提。実機読取は x86_64、macOS **26.7.1**。 |
| Blender | `/Applications/Blender.app/Contents/MacOS/Blender --version` → **4.5.10 LTS**、hash `6dc0b208d1b5`。 |
| 道具 | brew・cmake・clang は既存。通常の `python3` は **3.14 系**なので、PyTorch用・背景除去用には流用しない。 |
| 実行確認 | Blender の作業試験と最小起動の2回とも SIGSEGV。最小起動の終了コード **139**。クラッシュ記録は `MTLBackend::metal_is_supported` など GPU backend 選択を指す。Python 台本実行前。サンドボックス外でも同じかは未確認。 |
| 背景除去の配布確認 | pip の `--dry-run --only-binary=:all:`、対象 `macosx_13_0_x86_64 / CPython 3.11` で、第1弾の固定版一式の依存解決が **終了コード0**。インストール・推論はしていない。 |
| 大きさ | GB は十進（10⁹ byte）、GiB は2³⁰ byte。**重みだけ**と**文字エンコーダ・VAE込み**を区別。未配布の量子化サイズは「推測」。同じ重みの `.bin` と `.safetensors` を重複取得しない。 |
| 必要RAM | 原則 **生成プロセス単体のピーク予算の推測**。OS・ほかのアプリ・頭脳を含まない。16GB全体を模型に使えるわけではない。公式GPU VRAMは別記する。 |
| 時間 | 同型Macの比較可能な実測を確認できなかった。以下の時間はすべて **推測・導入判断用の粗い幅**。GPUの宣伝値をCPU値に換算したものではない。画像はバッチ1、指定解像度・ステップ、音声/動画は生成された1秒あたり。 |
| 判定 | **○**=CPU経路あり、**△**=移植/依存固定/メモリ工夫が必要、**×**=公式CUDA前提または16GBでは不適。○でもCPU速度の保証ではない。 |
| 商用 | コードと重みは別。表の「可」は条件・用途制限の遵守が前提。出力の権利や第三者素材の使用許諾を一律保証する意味ではない。 |

## 2. Intel Mac で踏みやすい互換性の穴

| 実装 | この Mac での扱い | 一次資料 |
| --- | --- | --- |
| stable-diffusion.cpp / ggml | x86 AVX2・macOS・CPU 対応。`SD_METAL=OFF` 等でCPU専用ビルド。PyTorch不要。調査時 master は `a1ded76da5818803fca97a3b433669ef727d32cf`。 | [対応一覧](https://github.com/leejet/stable-diffusion.cpp)、[CPUビルド](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/build.md)、[ビルド選択肢](https://github.com/leejet/stable-diffusion.cpp/blob/master/CMakeLists.txt) |
| PyTorch CPU | 現行macOS wheelは arm64。PyPIで確認できた **Intel wheelの最終安定版は2.2.2**。Python3.11＋NumPy1.26系の隔離環境が基本。最新模型の依存を満たせなければ外部Linuxへ。 | [現行配布対象](https://github.com/pytorch/pytorch/blob/main/RELEASE.md)、[2.2.2ファイル](https://pypi.org/project/torch/2.2.2/#files) |
| ONNX Runtime CPU | 最新版任せにしない。**1.23.2** の CPython3.11・macOS13以上・x86_64 wheelを確認。新しい安定版のIntel wheelを今回のPyPI一覧では確認できなかった。 | [1.23.2ファイル](https://pypi.org/project/onnxruntime/1.23.2/#files) |
| rembg の最新版 | **2.0.85**。現在の既定は BRIA RMBG-2.0、商用条件も違う。`u2net` を明示。Numba/llvmliteもIntel対応版に固定する。 | [README・模型一覧](https://github.com/danielgatis/rembg)、[2.0.85](https://pypi.org/project/rembg/2.0.85/)、[Numba0.62.1](https://pypi.org/project/numba/0.62.1/) |
| Core ML | Core ML自体はCPU実行経路を持つので「Intelで絶対不可能」とはしない。ただしApple Silicon/ANE用の最適化・変換済み模型・高速化報告は本機の根拠にならない。今回は採用しない。 | [computeUnits](https://developer.apple.com/documentation/coreml/mlmodelconfiguration/computeunits) |
| MLX・CUDA・TensorRT | MLXのApple GPU向け経路、CUDA/TensorRT、CUDA拡張は本機に使えない。`device='cpu'` だけで拡張依存まで消えるわけではない。 | [MLX](https://github.com/ml-explore/mlx)、[TRELLISの要件](https://github.com/microsoft/TRELLIS) |
| FP16 / BF16 / FP8 | 本機はAVX2。新GPUの低精度演算能力を持たない。FP16ファイルでもCPU計算がFP32に広がる実装がある。FP8ファイルも読み込み時FP16へ展開する場合があり、ファイルサイズ≠RAM。 | [sd.cpp形式・ビルド説明](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/build.md) |

## 3. 画像生成

必要RAM・所要時間・未配布の量子化サイズは **推測**。GGUFは入れ物であり、対応模型の実装が別途必要。

| 模型・判定 | 重みGB・付属物 | RAM GB | CPU実装・条件 | 1枚の目安時間（推測） | ライセンス・商用 | 出典 |
| --- | --- | --- | --- | --- | --- | --- |
| **SD1.5 ○** | 公式単一FP32 **4.265**。変換後Q8約1.2/Q4約0.7（推測）、CLIP/VAE込み。 | 3–6 | stable-diffusion.cpp、512²、20ステップ。Q8から始める。 | 3–20分 | CreativeML OpenRAIL-M、条件付き可。コードMIT。 | [模型](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5)、[量子化](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/quantization_and_gguf.md) |
| **SD-Turbo ○** | 公式FP32 **5.215**。既成GGUF Q8 **2.024**、FP16 **2.61**。 | 4–7 | sd.cpp、512²、1–4ステップ、CFG1。SD2系なのでSD1.5用ControlNetをそのまま使わない。 | 20秒–4分 | 現在の配布LICENSEはStability AI Community。年商100万USD未満など条件付き商用、超過は別契約。旧非商用記述と混同しない。 | [公式](https://huggingface.co/stabilityai/sd-turbo)、[現LICENSE](https://huggingface.co/stabilityai/sd-turbo/blob/main/LICENSE.md)、[第三者変換](https://huggingface.co/Green-Sky/SD-Turbo-GGUF) |
| **SDXL-Turbo ○/△** | 公式単一FP16 **6.938**。Q8約3.8/Q4約2.2（推測）。 | 7–12（512²） | sd.cpp、512²、1–4ステップ、CFG1。1024²はRAM/時間増。 | 2–15分 | Stability AI Community、条件付き商用。 | [公式模型・条件](https://huggingface.co/stabilityai/sdxl-turbo)、[sd.cpp対応一覧](https://github.com/leejet/stable-diffusion.cpp) |
| **FLUX.2-klein-4B ○/△** | diffusion Q4_K_M **2.604**/Q8 **4.301**。別のQwen3-4B文字エンコーダQ4約2.5＋VAE約0.3（推測）。Q4構成合計約5.4。 | 8–13 | sd.cpp、4ステップ。まず512²で測る。Qwen頭脳のGGUFを文字エンコーダ代わりにはできない。 | 512²で5–45分、1024²で20–120分 | **4BはApache-2.0、可**。9Bやdevのライセンスを流用しない。 | [公式](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B)、[実装と付属模型](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/flux2.md)、[Q4/Q8ファイル](https://huggingface.co/unsloth/FLUX.2-klein-4B-GGUF) |
| **FLUX.1-schnell △** | diffusion Q4_K_S **6.784**。T5-XXL・CLIP・VAEを足すと約10–12（推測）。 | 12–18 | sd.cpp、4ステップ、文字エンコーダの逐次解放、低解像度。16GBでは余裕がなく初手にしない。 | 512²で20–120分 | Apache-2.0、可。 | [公式](https://huggingface.co/black-forest-labs/FLUX.1-schnell)、[GGUF](https://huggingface.co/city96/FLUX.1-schnell-gguf)、[実装手順](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/flux.md) |
| **Z-Image-Turbo △** | diffusion6B Q4約3.5–4＋Qwen3-4B Q4約2.5＋VAE、合計約6.5–7（推測）。 | 10–15 | sd.cpp対応。8 NFEの蒸留模型。H800の「秒未満」は本機の速度ではない。 | 512²で10–90分 | Apache-2.0、可。 | [公式模型](https://huggingface.co/Tongyi-MAI/Z-Image-Turbo)、[sd.cpp手順](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/z_image.md) |
| SDXL base △ | FP16約7、Q4約2–3（推測）。 | 10–16 | sd.cpp、1024²・20–30ステップ。Turboと比べ計算量大。 | 30–180分 | CreativeML Open RAIL++-M、条件付き可。 | [公式](https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0) |
| SD1.5＋LCM-LoRA ○ | SD1.5 Q8約1.2＋LoRA約0.07（推測）。 | 3–6 | sd.cpp、LCM sampler、4–8ステップ。LoRA併用の量子化対応は固定版で確認。 | 1–8分 | LoRAのカードはOpenRAIL++、条件付き商用可。基底SDのOpenRAIL-M条件も適用。 | [公式LCM-LoRA](https://huggingface.co/latent-consistency/lcm-lora-sdv1-5)、[実装](https://github.com/leejet/stable-diffusion.cpp) |

調査時の実装には新しい画像模型も増えている。**対応一覧にあることだけでIntel Macでの安定性・速度を認定しない**。FLUX.2-klein-4Bを最新小型枠、SD1.5を堅い基準枠にする。

## 4. 画像編集・テクスチャ作成

| 模型/処理・判定 | 重みGB | RAM GB（推測） | CPU実装・用途 | 1枚の時間（推測） | 商用 | 出典 |
| --- | --- | --- | --- | --- | --- | --- |
| SD1.5 img2img ○ | 上表と共用、追加0 | 3–6 | sd.cpp、入力画像＋strength。色・絵柄変更、テクスチャの下絵。 | 2–20分/512² | 基底OpenRAIL-M条件付き可 | [sd.cpp SD手順](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/sd.md) |
| SD1.5 inpainting ○ | 専用模型FP32約4.3、Q8約1.2（推測） | 3–7 | マスク対応の模型/実装で部分修正。img2imgはマスク編集と同義ではない。 | 3–25分/512² | CreativeML OpenRAIL-M、条件付き商用可 | [専用模型](https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-inpainting)、[CLI](https://github.com/leejet/stable-diffusion.cpp/blob/master/examples/cli/main.cpp) |
| SD1.5 ControlNet ○/△ | 基底＋制御網Q8約0.4–0.8（推測） | 4–8 | sd.cpp、輪郭/深度など。プリプロセッサにもCPU実装が必要。 | 5–40分/512² | 配布カードはOpenRAIL、条件付き商用可。基底SDの条件も適用 | [制御網](https://huggingface.co/lllyasviel/ControlNet-v1-1)、[実装](https://github.com/leejet/stable-diffusion.cpp) |
| FLUX.2-klein-4B 編集 △ | 上表と共用 | 9–15 | sd.cppの参照画像経路。生成と編集を共用できる小型候補。 | 10–90分/512² | Apache-2.0、可 | [模型カード](https://huggingface.co/black-forest-labs/FLUX.2-klein-4B)、[編集例](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/flux2.md) |
| FLUX.1-Kontext-dev / Qwen-Image-Edit × | Kontext Q4本体約7、Qwen20B Q4本体約12、いずれも付属模型別（推測） | 16–32以上 | sd.cpp対応はあるが本機には重い。外部GPUへ。 | 数十分–数時間/枚、OOMもあり（推測） | 各dev/独自条件、Qwen系は対象版のApache条件を確認 | [Kontext](https://huggingface.co/black-forest-labs/FLUX.1-Kontext-dev)、[Qwen編集](https://huggingface.co/Qwen/Qwen-Image-Edit) |
| Pillow/OpenCV・手続き的テクスチャ ○ | 模型なし | 0.1–1 | 合成、マスク、タイル化、ノイズ、色調、法線の補助。軽い操作は拡散模型を使わない。 | 0.01–5秒/1024² | PillowはHPND、OpenCVはApache-2.0、可 | [Pillow](https://github.com/python-pillow/Pillow)、[OpenCV](https://github.com/opencv/opencv) |

生成した1枚の画像は、そのまま整合するPBR材質・シームレスUV・正常な法線になるわけではない。色テクスチャ、粗さ、金属度、法線の各用途を分けて検証する。

## 5. 動画（文字→動画、画像→動画）

動画の「1秒」は **完成動画の1秒**。時間は1フレームずつの足算ではなく、フレーム数・時空間Attention・VAE decodeに強く依存する。以下の範囲は推測で、完走の保証なし。

| 模型/処理・判定 | 重みGB・量子化 | RAM GB（推測） | 実装/制約 | 完成動画1秒の時間（推測） | ライセンス・商用 | 出典 |
| --- | --- | --- | --- | --- | --- | --- |
| Wan2.1 T2V 1.3B △ | 公式diffusion **5.68**、UMT5 **11.36**、VAE **0.51**。Q4込み構成約5–7（推測） | 12–24 | sd.cpp、まず低解像度・短フレーム。**1.3B版はT2V**、公式I2V14Bと混同しない。 | 0.5–8時間。解像度を極端に下げた実験枠 | Apache-2.0、可 | [公式](https://huggingface.co/Wan-AI/Wan2.1-T2V-1.3B)、[sd.cpp](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/wan.md) |
| Wan2.1/2.2 I2V・大模型 × | 14B本体Q4約8–10、付属物別（推測） | 24–64以上 | C++量子化経路があっても動画バッファが大きい。外部GPU。 | 数時間以上/秒、OOMの可能性 | 対象模型のApache-2.0条件 | [公式Wan2.2](https://github.com/Wan-Video/Wan2.2) |
| AnimateDiff＋SD1.5 △ | motion adapter FP16 **1.82**＋基底/CLIP/VAE | 8–18 | PyTorch CPU・古い対応依存が必要。少フレーム・低解像度の研究枠。sd.cppのSD対応から自動的に対応するわけではない。 | 10–120分/秒（256²の短い試作） | motion Apache-2.0＋基底の条件 | [実装](https://github.com/guoyww/AnimateDiff)、[adapter](https://huggingface.co/guoyww/animatediff-motion-adapter-v1-5-2) |
| Stable Video Diffusion XT × | FP16構成約5–10、対応済みCPU用Q4構成は未確認 | 16–32以上 | Diffusers CPUは理論上の経路。旧Intel torchでの依存固定・float32展開が障害。画像→25フレーム。 | 1–8時間/秒、未成立の可能性 | SVD Community系。対象版LICENSEの商用条件確認が必要、無条件商用可とはしない | [公式・LICENSE](https://huggingface.co/stabilityai/stable-video-diffusion-img2vid-xt) |
| LTX-Video旧2B △/×、LTX-2.5 × | 旧2B Q4本体約1.5＋T5（推測、CPU対応セット未確認）。**2.5配布に22B transformer BF16約42.02GB**あり、Q4本体だけ約12GB（推測）、文字エンコーダ別 | 旧版でも16–32、新版32以上 | 旧版の小さい数値を新LTXに適用しない。現行sd.cppはLTX-2.3/2.5対応を掲示。外部GPU推奨。 | 新版の本機完走時間は算定不可 | 旧2BのApache系と2.xのLightricks独自条件を区別。2.xは年商等で商用契約が必要 | [旧系](https://huggingface.co/Lightricks/LTX-Video)、[現行配布・LICENSE](https://huggingface.co/Lightricks/LTX-2.5) |
| FFmpeg画像列・パン/ズーム ○ | 模型なし | 0.1–1 | CPU encode。静止画から紹介動画、字幕、音声、BGMを合成。これは新たな動きを推論する動画生成ではない。 | 0.05–2秒/動画秒（720p・軽いフィルタ） | LGPL/GPLはビルド構成次第、商用利用可能、再配布条件あり | [フィルタ](https://ffmpeg.org/ffmpeg-filters.html)、[ライセンス](https://ffmpeg.org/legal.html) |

本機で「短くても高品質なI2V」を第1弾に保証できる候補は確認できなかった。画像生成＋FFmpegなら軽量な制作工程を先に作れる。

## 6. 3D生成とBlenderの手作業

### 6.1 文字/画像→3D

| 模型/方式・判定 | 大きさGB | RAM GB（推測） | CPU実装/問題点 | 1オブジェクトの時間（推測） | ライセンス・商用 | 出典 |
| --- | --- | --- | --- | --- | --- | --- |
| **TripoSR 画像→3D △** | 公式 `model.ckpt` **1.677**、量子化CPU配布は未確認 | 6–12 | `run.py --device cpu`、CUDA不在のfallbackあり。torch2.2.2環境、torchmcubesのCPUビルド、依存固定が必要。mesh resolutionを128–256へ、chunkを小さく。テクスチャベイクはxatlas/modernglも検証が必要。 | 2–30分（低解像度・mesh抽出、ベイク別） | コード・重みMIT、可 | [README](https://github.com/VAST-AI-Research/TripoSR)、[CPU選択](https://github.com/VAST-AI-Research/TripoSR/blob/main/run.py)、[CPU mesh抽出](https://github.com/VAST-AI-Research/TripoSR/blob/main/tsr/models/isosurface.py)、[重み](https://huggingface.co/stabilityai/TripoSR) |
| Shap-E 文字/画像→3D △ | diffusion・transmitter等、FP32一式約1.5–3（推測）。標準GGUFなし | 5–12 | PyTorch CPU、device指定・依存固定。小物の粗い形状向き、mesh decodeまで測る。 | 5–60分 | MIT、可 | [公式実装](https://github.com/openai/shap-e)、[配布経路](https://github.com/openai/shap-e/blob/main/shap_e/models/download.py) |
| Hunyuan3D-2mini 画像→形状 △ | 形状0.6B、FP16本体約1.2（推測）。画像encoder・VAE等別、通常GGUF一式未確認 | 8–16（形状のみ） | PyTorchのCPU数学経路は検討できるが、**Intel Mac完走の一次実測は未確認**。texture工程・custom rasterizerを分離。第1弾にはしない。 | 30–180分、未成立の場合あり | Tencent Hunyuan Community。条件付き商用、EU/UK/韓国除外・大規模事業の別許諾条件 | [公式小型版](https://huggingface.co/tencent/Hunyuan3D-2mini)、[実装](https://github.com/Tencent-Hunyuan/Hunyuan3D-2)、[LICENSE](https://huggingface.co/tencent/Hunyuan3D-2/blob/main/LICENSE.txt) |
| **Hunyuan3D-2.1 ×** | mesh/paint/PBR多数。Intel CPU用の検証済み量子化一式なし | CPU算定未確認。公式はshape **10GB VRAM**、texture **21GB**、両方 **29GB** | CUDA/rasterizer等を含む。形状だけの数字でPBR込みCPU対応とはしない。外部GPU。 | 本機では算定不可 | Tencent Community、条件付き商用。地域除外・100万MAU超など別許諾条件 | [公式要件](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)、[対象LICENSE](https://huggingface.co/tencent/Hunyuan3D-2.1/blob/main/LICENSE) |
| **TRELLIS ×** | 複数のflow/decoder/DINO模型。CPU量子化一式未確認 | CPU算定未確認。公式 **NVIDIA VRAM16GB以上** | Linux＋CUDA、spconv、nvdiffrast等。CPU指定だけの移植は成立しない。NVIDIA APIまたはGCPへ。 | 本機では算定不可 | 主要コード/重みMIT。ただし追加encoder等の条件も確認 | [公式要件](https://github.com/microsoft/TRELLIS)、[重み](https://huggingface.co/microsoft/TRELLIS-image-large) |
| **手続き的モデリング ○（実機は保留）** | 生成模型なし、既存Blender追加取得0 | 0.5–4 | Qwenが部品/寸法/演算のJSON計画を作り、固定Python台本でmeshを組む。画像→3D模型ではない。 | 単純小物0.1–30秒＋起動数秒 | Blender GPL、商用制作可。制作物へGPLが自動伝播するわけではない | [Blenderライセンス](https://www.blender.org/about/license/)、[Python API](https://docs.blender.org/api/4.5/) |

TripoSRの公式「0.5秒未満」は **A100** の数字。CPU欄には転記しない。生成meshには、穴・浮遊面・背面の誤推定・不均一な三角形があり、ゲーム用トポロジー・UV・リグが完成するとは限らない。

### 6.2 BlenderをCPU台本で扱える範囲

機能の対応と、今回のBlender実行不成立は別。以下は4.5 APIを使う実装案で、**この環境で完走したという報告ではない**。

| 作業 | 台本/方法 | 目安（推測） | 制約・一次資料 |
| --- | --- | --- | --- |
| ポリゴン編集 | `bmesh`、extrude、subdivide、merge、Boolean、Decimate、法線整理 | 数百～数万面で0.1–30秒 | Booleanの自己交差、単位・向き・非多様体を確認。[bmesh](https://docs.blender.org/api/4.5/bmesh.html) |
| 自動リトポ | `bpy.ops.object.quadriflow_remesh(target_faces=...)`、Voxel Remesh、Decimate | 10秒–10分 | QuadriFlowは四角化であり、人間の関節エッジ設計の代替ではない。UV/頂点群は失われうる。Decimateは四角化ではない。[Object API](https://docs.blender.org/api/4.5/bpy.ops.object.html) |
| 手作業に近いリトポ | 低ポリmeshを作ってShrinkwrap、Mirror、表面への頂点移動 | 数秒–数分/台本 | 画像だけで良いエッジループを保証しない。途中の正面・側面画像で確認。[Shrinkwrap](https://docs.blender.org/manual/en/4.5/modeling/modifiers/deform/shrinkwrap.html) |
| UV展開 | Edit modeで全選択→`bpy.ops.uv.smart_project()`、island配置 | 0.1–30秒 | Smart Projectは手動seam設計ではない。生成/リトポ後にやり直す。[UV API](https://docs.blender.org/api/4.5/bpy.ops.uv.html) |
| テクスチャ | SD/Pillowで色画像、UVごとに画像を割当、ノードでPBR組立 | 作成は画像欄、割当は数秒 | 色空間（色=sRGB、法線/粗さ=Non-Color）、画像参照の持ち運びを確認。[Shader nodes](https://docs.blender.org/api/4.5/bpy.types.ShaderNodeTexImage.html) |
| ベイク | Cycles、`scene.cycles.device='CPU'`、UVとactive画像ノードを準備、`bpy.ops.object.bake()` | 256–1024²で10秒–20分 | selected-to-activeのhigh/low mesh、cage、サンプル数で大きく変わる。EeveeをCPUレンダラー扱いしない。[Bake API](https://docs.blender.org/api/4.5/bpy.ops.object.html#bpy.ops.object.bake) |
| リグ | Armature、EditBone、vertex groups、Armature modifier、親子関係 | 0.1–60秒/単純rig | 名前・骨軸・rest poseを固定。自動weightsは手直しが必要。rigとモーション生成は別。[Armature API](https://docs.blender.org/api/4.5/bpy.types.Armature.html) |
| 書き出し | `bpy.ops.export_scene.gltf(export_format='GLB',...)` | 0.1–30秒 | GLB/glTF優先。骨・材質・画像・アニメーションを別viewerで再読込確認。FBX/OBJ/STLは用途別。[glTF exporter](https://docs.blender.org/api/4.5/bpy.ops.export_scene.html#bpy.ops.export_scene.gltf) |

最小試験（今回この起動は139で失敗。導入済みだから動くとは判断しない）:

```bash
/Applications/Blender.app/Contents/MacOS/Blender --background --factory-startup --disable-autoexec --python-exit-code 1 --python-expr 'import bpy; print(bpy.app.version_string)'
```

`--help` のこのビルドのGPU backend候補は **metalのみ**。`--gpu-backend opengl` を未確認の回避策として勧めない。CPU Cyclesも、起動時のMetalデバイス調査を飛ばすとは限らない。実行環境/既存インストールの調査か別の互換ビルドが必要であり、今回の文書作成では変更しない。

起動問題が解決した後の固定台本の核（説明用。ファイルは今回作っていない）:

```python
import bpy, math
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.mesh.primitive_cube_add(size=1)
mesh = bpy.context.object
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.subdivide(number_cuts=3)
bpy.ops.object.mode_set(mode='OBJECT')
# 形状整理→リトポ→UVの順。面数などは受理済み仕様から制限付きで設定。
bpy.ops.object.quadriflow_remesh(target_faces=80, seed=1)
bpy.ops.object.mode_set(mode='EDIT')
bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(66), island_margin=0.02)
bpy.ops.object.mode_set(mode='OBJECT')
bpy.ops.object.armature_add()
rig = bpy.context.object
mesh.parent = rig
modifier = mesh.modifiers.new('Rig', 'ARMATURE')
modifier.object = rig
group = mesh.vertex_groups.new(name='Bone')
group.add(list(range(len(mesh.data.vertices))), 1.0, 'REPLACE')
# ベイクには材質、active Image Texture、UV、画像保存が別途必要。
bpy.context.scene.render.engine = 'CYCLES'
bpy.context.scene.cycles.device = 'CPU'
bpy.ops.export_scene.gltf(filepath='/private/tmp/model.glb', export_format='GLB')
```

## 7. 音声・音楽・効果音・日本語TTS

量子化済み模型があっても、対象CPUで扱える実装を併記する。音楽生成と文章を読むTTSは別用途。

| 模型/方式・判定 | 重みGB（量子化状態） | RAM GB（推測） | CPU実装・日本語 | 完成音声1秒の時間（推測） | ライセンス・商用 | 出典 |
| --- | --- | --- | --- | --- | --- | --- |
| **Open JTalk ○・第1弾** | 辞書＋HTS音声約0.02–0.1（推測）、非ニューラル、量子化不要 | 0.03–0.2 | C/C++ CLI、日本語。声は古いが軽く、CPU対応が明確。 | 0.01–0.2秒 | 本体BSD-3-Clause、同梱MeiなどCC-BY-3.0、表示条件付き商用可 | [公式](https://open-jtalk.sourceforge.net/)、[brew](https://formulae.brew.sh/formula/open-jtalk)、[導入/test/音声](https://github.com/Homebrew/homebrew-core/blob/master/Formula/o/open-jtalk.rb) |
| **Kokoro-82M ○/△** | FP32公式 **0.327**。ONNX int8約0.09–0.15＋voice（推測） | 0.3–1.5 | ONNX CPU候補。日本語は`misaki[ja]`等のG2Pと日本語voiceが必要。sherpaの中国語/英語パッケージを日本語対応と誤認しない。 | 0.1–2秒 | Apache-2.0、可、使用voiceの条件も確認 | [公式](https://huggingface.co/hexgrad/Kokoro-82M)、[G2P](https://github.com/hexgrad/misaki)、[ONNX実装](https://github.com/thewh1teagle/kokoro-onnx)、[sherpaの対象言語](https://k2-fsa.github.io/sherpa/onnx/tts/pretrained_models/kokoro.html) |
| Piper ○（日本語は未確認） | 各voice約0.015–0.1（推測）、ONNX | 0.1–0.5 | CPUの軽量TTS。日本語の品質・正規のvoice配布は今回確認できず、日本語第1弾にしない。 | 0.01–0.3秒 | 現行エンジンGPL-3.0。**voice別MODEL_CARDが別条件**、商用可否は声ごと | [現行実装](https://github.com/OHF-Voice/piper1-gpl)、[voice条件](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/VOICES.md) |
| Bark small △ | 複数段模型、FP32約1.5–3（推測）、CPU用一式のint8は未確認 | 4–8 | PyTorch CPU、日本語含む多言語。内容の逸脱や速度に注意。 | 5–60秒 | MIT、可 | [公式・CPU設定](https://github.com/suno-ai/bark) |
| **MusicGen-small △** | 配布 `model.safetensors` **2.36**（付属物込みの非量子化配布）。小checkpoint **0.84** は必要物が同じとは限らない。int8約0.5–1.5（推測、標準CPU一式未確認） | 4–8 | AudioCraft PyTorch CPU、旧Intel依存を固定。短いBGM研究向け。 | 10–120秒 | **コードMIT、重みCC-BY-NC-4.0。商用不可** | [模型](https://huggingface.co/facebook/musicgen-small)、[実装とライセンス](https://github.com/facebookresearch/audiocraft)、[CPUの使い方](https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md) |
| **Stable Audio Open Small △** | 341M系、本体配布 **1.68**。CPU用Q4/int8標準配布未確認 | 4–8 | Stable Audio ToolsにCPU選択例あり、最大約11秒の効果音/ループ。最新依存とtorch2.2.2の互換は未確認。 | 5–90秒 | Stability AI Community、年商等の条件付き商用 | [公式・CPU例・条件](https://huggingface.co/stabilityai/stable-audio-open-small) |
| Stable Audio Open 1.0 / AudioLDM2 △/× | 1.0本体約4.9、付属物別。AudioLDM2約3–8（推測）、CPU量子化一式未確認 | 10–24 | PyTorch CPU理論経路、長い効果音/音楽。Intel依存とRAMが障害。外部へ | 30–300秒、またはOOM | 1.0は対象Stability license条件。AudioLDM2はCC-BY-NC-SA-4.0、商用不可 | [1.0](https://huggingface.co/stabilityai/stable-audio-open-1.0)、[AudioLDM2](https://github.com/haoheliu/AudioLDM2)、[LICENSE](https://github.com/haoheliu/AudioLDM2/blob/main/LICENSE) |
| 手続き的効果音・MIDI ○ | 模型なし | 0.02–0.5 | Python/SoX/FFmpeg、発振・noise・envelope。MIDIからの音楽は音源ライセンスを別確認。 | 0.001–0.1秒 | コード/音源別。SoX・FFmpegの再配布条件、SoundFontの条件 | [SoX](https://sox.sourceforge.net/)、[FFmpeg音声フィルタ](https://ffmpeg.org/ffmpeg-filters.html) |

音声を外部へ送る声の複製・音声プロンプトは、文字だけのTTSとは送信対象も違う。勝手に声をアップロードする導線を作らない。

## 8. アップスケール・背景除去・ほか

| 模型/処理・判定 | 重みGB | RAM GB（推測） | CPU実装・用途 | 時間（推測） | ライセンス・商用 | 出典 |
| --- | --- | --- | --- | --- | --- | --- |
| **U²-Net ○・第1弾** | ONNX FP32 **約0.176**、量子化不要 | 0.3–1.5 | rembg＋ONNX CPU、模型入力320²、元画像へmaskを戻す | 0.3–5秒/枚（1MP程度） | rembgはMIT、U²-Net原著repoはApache-2.0、条件付き商用可。変換物の出所も保存 | [rembg](https://github.com/danielgatis/rembg)、[原著LICENSE](https://github.com/xuebinqin/U-2-Net/blob/master/LICENSE)、[ONNX取得](https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx) |
| U²-NetP ○ | ONNX FP32約0.005 | 0.05–0.4 | rembg、軽いmask。細い髪・半透明には限界 | 0.05–1秒/枚 | 原著repo Apache-2.0、rembg MIT、条件付き商用可 | [模型とu2netp](https://github.com/danielgatis/rembg#models) |
| BRIA RMBG-2.0 △ | ONNX約1.02、非量子化 | 2–5 | rembg最新版の既定、1024²。明示的に除外しないと想定外の模型を取得する | 5–60秒/枚 | **BRIA独自条件、商用は別許諾**。rembgのMITでは覆えない | [公式条件](https://huggingface.co/briaai/RMBG-2.0) |
| Real-ESRGAN x4plus △ | `.pth`約0.067、FP32。CPU用int8標準一式未確認 | 1–4（tile256） | PyTorch CPU、tile/half=False、旧依存固定。ONNX変換は検証が別途必要 | 30–300秒/512²→2048² | BSD-3-Clause、可 | [公式](https://github.com/xinntao/Real-ESRGAN)、[tile/CPU実装](https://github.com/xinntao/Real-ESRGAN/blob/master/inference_realesrgan.py) |
| **waifu2x-ncnn-vulkan ○** | 模型約0.01–0.1（推測） | 0.2–2 | ncnn CPUもあり。**`-g -1`** がCPU選択。名前のvulkanだけでGPU必須と判断しない。絵の2倍拡大 | 5–90秒/512²→1024² | コードMIT、同梱模型の条件確認 | [CPUオプション](https://github.com/nihui/waifu2x-ncnn-vulkan) |
| Lanczos/Pillow、FFmpeg ○ | 模型なし | 0.05–0.5 | 高品質補間。失われた細部を推論して復元する模型ではない | 0.01–1秒/枚 | Pillow/FFmpegの条件 | [Pillow resize](https://pillow.readthedocs.io/en/stable/reference/Image.html#PIL.Image.Image.resize) |
| Whisper small/base ○（生成の補助） | small FP16約0.466、Q5約0.19。base FP16約0.148（推測） | 0.3–1.5 | whisper.cpp CPU、音声→字幕、日本語入力の補助。これは音声生成ではない | 0.1–2秒/入力音声秒 | MIT、可 | [公式サイズとCPU](https://github.com/ggml-org/whisper.cpp) |
| SVG・曲線・CAD的mesh ○ | 新模型なし | 0.05–2 | Qwenの仕様→固定演算台本、ロゴ下絵・図形・寸法付き形状。ラスター生成より適した用途あり | 秒単位 | 利用ライブラリ・素材ごとの条件 | [Blender bmesh](https://docs.blender.org/api/4.5/bmesh.html)、[trimesh](https://github.com/mikedh/trimesh) |

## 9. 外部で回す案

### 9.1 NVIDIA Build / NIM の生成模型

**公開カタログ/文書の確認一覧**であり、認証付き実行・利用枠の確認はしていない。Buildの「Downloadable」はGPUへ自前配備できるという表示で、無料hosted endpointの保証ではない。画像/動画を読むVLM・生成画像検出器は生成模型一覧から除外した。

| 模型 | 用途 | 今回確認できた提供状態 | 条件・出典 |
| --- | --- | --- | --- |
| `black-forest-labs/flux.1-schnell` | 画像 | hosted `POST /v1/genai/black-forest-labs/flux.1-schnell` 文書あり、1–4 steps | 本体Apache-2.0とサービス条件は別。[API](https://docs.api.nvidia.com/nim/reference/black-forest-labs-flux_1-schnell-infer) |
| `black-forest-labs/flux.1-dev` | 画像 | Visual Models APIs一覧にendpoint掲載 | devの重み条件をschnellと混同しない。[一覧](https://docs.api.nvidia.com/nim/reference/visual-models-apis)、[模型](https://build.nvidia.com/black-forest-labs/flux_1-dev) |
| `black-forest-labs/flux.2-klein-4b` | 画像・編集 | 一覧にInfer掲載、BuildはDownloadable。編集入力の制限・hosted可用性は実行未確認 | [一覧](https://docs.api.nvidia.com/nim/reference/visual-models-apis)、[Build](https://build.nvidia.com/explore/visual-design) |
| `stabilityai/stable-diffusion-xl` | 画像 | hosted `POST /v1/genai/stabilityai/stable-diffusion-xl` 文書あり | [API](https://docs.api.nvidia.com/nim/reference/stabilityai-stable-diffusion-xl-infer) |
| `stabilityai/stable-diffusion-3-medium` | 画像 | hosted APIの模型・生成文書あり | [模型/API文書](https://docs.api.nvidia.com/nim/reference/stabilityai-stable-diffusion-3-medium) |
| `stabilityai/stable-diffusion-3.5-large` | 画像 | Build掲載、NIM API文書あり。無料hosted実行は未確認 | [Build一覧](https://build.nvidia.com/explore/visual-design)、[NIM API](https://docs.nvidia.com/nim/visual-genai/1.5.0/api/stable-diffusion-3.5-large.html) |
| `microsoft/trellis` | 画像→3D | hosted Infer文書あり。mesh/GLB等の返却仕様・入力上限を接続時確認 | [Infer](https://docs.api.nvidia.com/nim/reference/microsoft-trellis-infer) |
| `black-forest-labs/flux.1-kontext-dev` | 画像編集 | BuildはDownloadable。今回のVisual API一覧には専用Inferを確認できず | [Build](https://build.nvidia.com/explore/visual-design)。自前GPU配備案と扱う |
| `nvidia/cosmos-predict1-7b` | 世界/動画生成 | Visual一覧のendpoint欄は **「-」**。掲載だけで呼べる動画APIとはしない | [一覧](https://docs.api.nvidia.com/nim/reference/visual-models-apis)、[模型](https://docs.api.nvidia.com/nim/reference/nvidia-cosmos-1_0-diffusion-7b) |
| Magpie TTS Zeroshot / Multilingual | TTS | Build/NIM模型あり。今回、日本語の無料hosted endpointは確認できず。Zeroshotの公開support matrixは英語 | [Build模型](https://build.nvidia.com/nvidia/magpie-tts-zeroshot/modelcard)、[対応表](https://docs.nvidia.com/nim/speech/26.05.0/reference/support-matrix/tts.html) |

**音楽・効果音・汎用I2V・Hunyuan3Dを無料hosted APIで何でも呼べるという根拠は確認できなかった**。DGX Spark/StationのComfyUIプレイブックにFLUX/Wan/HunyuanVideoが載っていても、hosted生成API一覧ではない。[NVIDIAのローカルGPU用プレイブック](https://build.nvidia.com/station/comfyui/instructions)

| 無料枠/運用 | 判断 |
| --- | --- |
| hosted無料枠 | 現在のBuildには「開発用の無料serverless APIs」という案内がある。2024公式記事には無料creditsの説明があるが、**2026-10の全アカウント共通の付与数・有効期限・日次補充・動画/3Dの消費量は確認できない**。1000回・永久無料・毎日回復とは書かない。[Build](https://build.nvidia.com/explore/visual-design)、[2024公式説明](https://developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members/) |
| 既存スキルとの差 | `nvidia-agent`の内部説明は有限creditsを前提とする。現行の公開案内と同一の枠か未確認。実行前にアカウント画面で残量・rate limit・expiryを確認し、枯渇時に有料サービスへ自動切替しない。 |
| 自前NIM | Developer Programの開発/試験用利用と、本番用AI Enterprise契約は別。NIMソフトの試用が無料でもGPU VM・storageは有料。[公式説明](https://developer.nvidia.com/blog/access-to-nvidia-nim-now-available-free-to-developer-program-members/) |
| 呼出方式 | 画像/3Dは `ai.api.nvidia.com/v1/genai/...` 等。通常のLLM向けOpenAI互換 `chat/completions` や `nv ask` に模型名だけ足しても画像/3D APIにはならない。専用adapterを用意する。 |
| 鍵 | 既存 `nvidia-agent` / `ai-keychain` の本人承認経由を使う。今回キーの取得・読取はしていない。 |
| 承認単位 | 模型、送信prompt、画像/音声、保持条件、枠または料金、最大試行回数を確定してから承認。リトライはジョブ上限内。 |

### 9.2 Google Cloud GPU 単発

| 候補 | 向く作業 | メモリ/費用の判断 | 一次資料 |
| --- | --- | --- | --- |
| T4 16GB＋Linux VM | SD/SDXL、TripoSR、小型音楽、低解像度動画 | GPU単体の公開例 **$0.35/時**。CPU VM・RAM・disk・通信・税は別。地域で変わる。安い基準枠、最新巨大模型には不足 | [GPU料金](https://cloud.google.com/products/compute/gpus-pricing)、[地域/枠](https://docs.cloud.google.com/compute/docs/gpus/gpu-regions-zones) |
| G2 / L4 24GB | FLUX小型、TRELLIS、Hunyuanの形状、軽めI2V | G2の**VM全体**の料金で見積もる。Hunyuan2.1 shape＋paintの公式29GBには24GB1枚が不足しうる、段階実行が必要 | [G2仕様](https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines)、[VM価格](https://cloud.google.com/products/compute/pricing/accelerator-optimized) |
| A100 40/80GB等 | Hunyuan3D texture込み、LTX-2.x、大型動画 | 本機に合わせた無理なCPU移植より単発外部実行。availability・quota・VM最小構成によって高価になる | [GPU仕様](https://docs.cloud.google.com/compute/docs/gpus)、[料金](https://cloud.google.com/products/compute/gpus-pricing) |
| Spot VM | 中断からやり直せる一発生成 | 割引はあるが中断される。固定の最安値を約束せず、模型cacheと成果物を永続diskへ。deadline必須 | [Spot](https://docs.cloud.google.com/compute/docs/instances/spot)、[料金説明](https://cloud.google.com/products/compute/gpus-pricing) |

単発ジョブの提案手順:

1. GPU quota・地域・空き・模型licenseを確認。**無料トライアルのGPU利用制限**を確認し、無料creditsだけを根拠に起動しない。[無料枠の制限](https://docs.cloud.google.com/free/docs/free-cloud-features)、[GPU quota](https://docs.cloud.google.com/compute/resource-usage)
2. CPU/GPU/RAM/disk/通信込み見積を作り、送信対象・最大運転時間とともに本人承認。例: 総額$2、実行30分以内は**設定する上限案であって価格保証ではない**。
3. Linuxの隔離環境にCUDA対応の公式依存を入れ、模型をcache。入力1本→出力1本を完走。以後もジョブは1つずつ。
4. 成果物を回収し、hash・mesh/画像/音声の再読込を確認。VM停止だけではdisk等の課金が終わらないため、停止/削除の範囲も起動時に承認する。予算アラートは請求の強制上限ではない。[予算の扱い](https://docs.cloud.google.com/billing/docs/how-to/budgets)
5. 起動した仕事は既存 `dougu/matsu.sh gcp` の監視対象にする。Codexは処理/監視を裏に放置せず前で完了まで待つ。Macで夜通し推論はしない。

## 10. 量子化で何が減り、何が残るか

### 10.1 サイズと画質

| 方式 | 理想的な重みサイズ比（FP16比） | 画質/実装の読み方 | 一次資料 |
| --- | --- | --- | --- |
| GGUF Q8 / int8 weight-only | 約1/2、scale等で少し増える | 最初の比較基準。誤差はある。全tensorが8bitとは限らず、VAE/正規化などは高精度のままの場合がある | [sd.cpp量子化](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/quantization_and_gguf.md) |
| GGUF Q4 | 約1/4＋scale等 | より小さいが、細部・質感・文字・prompt忠実度の差は模型と量子化対象次第。**数値的な「画質低下○%」を共通値として示せる一次報告はない**。Q4_0とQ4_K_Mも同じではない | [実装](https://github.com/leejet/stable-diffusion.cpp)、[FLUX.2 4Bの実配布](https://huggingface.co/unsloth/FLUX.2-klein-4B-GGUF) |
| ONNX int8 | fp32比で理想約1/4 | Convの量子化/非量子化、QDQ・校正データ・kernel対応で変わる。動的量子化を何でも適用すれば速くなるわけではない。TTSは聞き比べ、背景除去は髪/縁で評価 | [ONNX量子化](https://onnxruntime.ai/docs/performance/model-optimizations/quantization.html) |
| Q-Diffusion | 4bit PTQ | 論文は複数時刻に合わせた校正で、**無条件拡散模型のFID差最大2.34**を報告。従来PTQの大きな劣化を抑えた。単なるGGUF weight-onlyやSD1.5全体への保証ではない | [原論文](https://arxiv.org/abs/2302.04304) |
| SVDQuant / Nunchaku | weight＋activationを4bit、高精度low-rank branch併用 | 改訂版論文はFLUX.1のメモリ **3.5倍削減**、laptop RTX4090でW4A16基準比 **3.0倍高速**。専用GPU kernelの結果でありAVX2 CPUや通常GGUFには転用できない | [原論文v4](https://arxiv.org/abs/2411.05007v4)、[engine](https://github.com/nunchaku-tech/nunchaku) |

実ファイルの例: FLUX.2-klein-4BはQ8_0 **4.301GB**→Q4_K_M **2.604GB**、約 **39.5%削減**。FP16からの理想比だけでなく、残すtensor・形式の付随量を含む実物で決める。文字encoder/VAEの容量はこの数字に含まない。[配布一覧](https://huggingface.co/unsloth/FLUX.2-klein-4B-GGUF)

### 10.2 「35Bが動くから生成も動く」が成立しない理由

| 比較点 | 頭脳LLMと生成模型の違い |
| --- | --- |
| MoE | 頭脳の35Bは、すべての重みを各tokenで同時に計算するdense35Bではない。専門家を減らした効果をdense画像transformerへ同率適用できない。 |
| 反復回数 | 拡散は画像全体/動画全体を複数回denoiseする。4bit化は反復回数を減らさない。CPUでは**蒸留・少ステップ・小解像度**が重要。 |
| 重み以外のRAM | activation、Attention、VAE、文字encoder、画像encoder、複数frame、変換時の元重み/コピーが残る。ファイル8GBならRAM8GBという式ではない。 |
| 公式メモリ例 | sd.cppの512² SD1.x表は通常 **f16約2.3G→q4約2.0G**、Flash Attention利用時 **約1.9G→約1.5G**。重みの理想4倍圧縮ほど総使用量は減らない。これは公式の条件付き参考値で、このMacの実測ではない。[公式表](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/quantization_and_gguf.md) |
| 演算対応 | CPU用kernelがない3Dのrasterizerやsparse convolutionは圧縮しても動かない。FP8/NVFP4/INT4 GPU高速化の数字も本機にはない。 |
| 解放とswap | 頭脳停止はプロセス終了と解放を確認する。模型の「unload」要求だけでRAMが空いたと決めない。swapで完走したことを実用速度の成功にしない。 |

### 導入後に測る最小の比較

同じ模型・prompt・seed・sampler・解像度・ステップでFP16/Q8/Q4を比べる。人物/文字/細い形状など **3種類以上×3seed** を目安に、壁時計・ピークRSS・swap増加・破綻を保存。まず1本の完走が先。少数画像でFIDや一般的画質順位を結論づけない。Q8で良ければQ4を無理に使わない。TTSは日本語の固有名詞/数/句読点、背景除去は髪/透明物/似た背景で比較する。

## 11. 第1弾の入れ方（実行手順案、今回未実行）

### 11.1 取得量の上限

| 取得物 | 取得量GB | 根拠/扱い |
| --- | --- | --- |
| SD1.5公式 `v1-5-pruned-emaonly.safetensors` | **4.265** | HFのblob size。FP16ファイルが同じ公式repoにあるとは仮定しない。別の7.7GB checkpointは不要 |
| U²-Net ONNX | **約0.176** | 既成配布。U²-NetPなら約0.005だが今回は品質基準の大きい方 |
| Open JTalk・辞書・音声 | 約0.1（推測） | brewの本体/resource。既存Blender取得0だが初回候補からは除外 |
| CPU C++ソース、ggml等 | 0.5以内を予算化（推測） | shallow clone、不要なWebP/WebM機能を切る |
| rembg一式のwheel | 0.3以内を予算化（推測） | CPU限定、Torch不要。pipのIntel向け依存解決は確認済み |
| Python3.11/ビルド道具の不足分 | 1.5以内を予算化（推測） | 本機はcmake/clang既存。brew最新のIntel bottleがなくsource buildとなる場合あり |
| 合計 | **約6.84GBの予算、7GBへ丸める（推測）** | **取得上限10GB**。量子化後のローカル生成ファイルは追加ダウンロードではないが、diskには別に必要 |

取得量は模型だけなら約4.44GBと確認できるが、道具込みの実測ではない。新しい巨大なビルド依存が必要になったら残量を再確認し、**10GBを越えてそのまま進めない**。既存Xcode command line toolsを使い、フルXcode/Blender/Torch/CUDAは追加しない。変換元＋Q8＋ビルド/venvで空きdisk **15GB程度（推測）** を別に確保する。

共通の作業場所例（以下は後日の導入用で、今回作っていない）:

```bash
export SEISEI_HOME="$PWD/dougu/kekka/seisei_runtime"
mkdir -p "$SEISEI_HOME/models" "$SEISEI_HOME/out"
```

### 11.2 SD1.5＋stable-diffusion.cpp

**理由:** CPU/AVX2対応、PyTorch不要、画像生成/編集を共用、商用条件が把握しやすい。初回は速度より基準を作る。SD-Turboへの変更は第2弾にする。

```bash
# cmake/clangがなければ先に不足分だけ用意。本機は既存。
git clone --depth 1 --recurse-submodules --shallow-submodules https://github.com/leejet/stable-diffusion.cpp.git "$SEISEI_HOME/stable-diffusion.cpp"
git -C "$SEISEI_HOME/stable-diffusion.cpp" rev-parse HEAD
# 固定して再現する版: a1ded76da5818803fca97a3b433669ef727d32cf
# 将来HEADが変わったら上記版をfetchしてcheckoutし、submoduleも合わせる。
cmake -S "$SEISEI_HOME/stable-diffusion.cpp" -B "$SEISEI_HOME/stable-diffusion.cpp/build" -DCMAKE_BUILD_TYPE=Release -DSD_METAL=OFF -DSD_CUDA=OFF -DSD_VULKAN=OFF -DSD_OPENCL=OFF -DSD_SYCL=OFF -DSD_WEBP=OFF -DSD_WEBM=OFF -DGGML_METAL=OFF -DGGML_NATIVE=ON
cmake --build "$SEISEI_HOME/stable-diffusion.cpp/build" --config Release -j 4
curl --fail --location --output "$SEISEI_HOME/models/sd15.safetensors" 'https://huggingface.co/stable-diffusion-v1-5/stable-diffusion-v1-5/resolve/451f4fe16113bff5a5d2269ed5ad43b0592e9a14/v1-5-pruned-emaonly.safetensors'
"$SEISEI_HOME/stable-diffusion.cpp/build/bin/sd-cli" -M convert -m "$SEISEI_HOME/models/sd15.safetensors" --type q8_0 -o "$SEISEI_HOME/models/sd15-q8.gguf"
```

CPUビルドの既定とCLIは更新されるので、固定版の `sd-cli --help` と合わせる。Threadsはまず **4**、後で4/6を測る。頭脳停止・RAM解放を確認してから変換/生成する。[CPUビルド](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/build.md)、[変換例](https://github.com/leejet/stable-diffusion.cpp/blob/master/docs/quantization_and_gguf.md)

**試す1行（ローカル生成）:**

```bash
"$SEISEI_HOME/stable-diffusion.cpp/build/bin/sd-cli" -m "$SEISEI_HOME/models/sd15-q8.gguf" -p 'a small red toy robot on a plain white background, studio photo' --width 512 --height 512 --steps 20 --cfg-scale 7 --sampling-method euler --seed 42 --threads 4 -o "$SEISEI_HOME/out/sd15-test.png"
```

受入条件: PNGが512×512、20steps完走、プロセス終了、所要時間/ピークRAMを記録、入力を外に送らない。生成の時だけ模型を読み込むCLIにすれば、終了後に頭脳を戻しやすい。

### 11.3 背景除去: rembg＋U²-Net

**理由:** CPU ONNX、模型0.176GB、生成画像→素材/3D入力へすぐ役立つ。最新rembgの既定BRIAを使わず、ライセンスと取得物を固定する。

Python3.11がなければ `brew install python@3.11`。本機のOS向けIntel bottleがない場合はsource buildになる。3.14環境へ直接入れない。

```bash
"$(brew --prefix python@3.11)/bin/python3.11" -m venv "$SEISEI_HOME/rembg-venv"
"$SEISEI_HOME/rembg-venv/bin/python" -m pip install --only-binary=:all: 'rembg[cpu]==2.0.85' 'onnxruntime==1.23.2' 'numpy==2.3.5' 'numba==0.62.1' 'llvmlite==0.45.1' 'scipy==1.16.3' 'scikit-image==0.26.0'
export U2NET_HOME="$SEISEI_HOME/models/rembg"
mkdir -p "$U2NET_HOME"
curl --fail --location --output "$U2NET_HOME/u2net.onnx" 'https://github.com/danielgatis/rembg/releases/download/v0.0.0/u2net.onnx'
```

Numba0.62.1は `numpy<2.4`、`llvmlite<0.46`。上記はIntel向けwheel解決確認済み。CLI extrasを増やさずPython APIを使う。[依存/配布](https://pypi.org/project/numba/0.62.1/)、[rembg](https://pypi.org/project/rembg/2.0.85/)

**試す1行（入力に前節の画像を使用）:**

```bash
U2NET_HOME="$SEISEI_HOME/models/rembg" "$SEISEI_HOME/rembg-venv/bin/python" -c 'import os; from pathlib import Path; from rembg import remove,new_session; root=Path(os.environ["SEISEI_HOME"]); model=root/"models/rembg/u2net.onnx"; assert model.is_file(), "模型を先に取得する"; session=new_session("u2net",providers=["CPUExecutionProvider"]); (root/"out/cutout.png").write_bytes(remove((root/"out/sd15-test.png").read_bytes(),session=session))'
```

受入条件: RGBA PNG・背景のalpha・主体の欠けを確認、CPU provider、模型の追加取得なし。rembg/poochは模型が欠けるかchecksumが不正だと自動取得を試すため、**存在確認だけでネットワーク禁止とはならない**。通常運用はあらかじめhash確認＋OS側ネットワーク禁止を適用し、失敗はエラーにする。初期導入と推論は分離する。

### 11.4 日本語TTS: Open JTalk

**理由:** CPU専用・小さい・日本語の標準経路。自然さではKokoro等に劣るが、重い頭脳を止めずに説明を声にする基礎になる。

```bash
# 本機OSに対応するIntel bottleがなければソースから。CUDA/Metal不要。
brew install --build-from-source open-jtalk
printf '%s\n' 'こんにちは。画像を作りました。' > "$SEISEI_HOME/out/tts-input.txt"
```

本体・辞書・voiceはbrew formulaのresourceから取得される。追加の不明な声を探してアップロードしない。Mei voiceのCC-BY等の表示は製品の素材クレジットに残す。[formulaと公式test](https://github.com/Homebrew/homebrew-core/blob/master/Formula/o/open-jtalk.rb)

**試す1行:**

```bash
open_jtalk -x "$(brew --prefix open-jtalk)/dic" -m "$(brew --prefix open-jtalk)/voice/mei/mei_normal.htsvoice" -ow "$SEISEI_HOME/out/tts.wav" "$SEISEI_HOME/out/tts-input.txt"
```

受入条件: ローカルWAVが非空、日本語の数・名前・句読点を聞き比べる。APIもサーバーも不要。

## 12. カーネルからの呼び方と「育つ」の設計案

**現状の接続状況:** `kernel/tanmatsu.py` は許可表を使い、任意shell/Python等を通さない。上のCLIをそのまま既存端末道具へ投げて「接続済み」とはしない。以下は将来の専用道具adapterの設計案。本調査では実装しない。

| 専用道具案 | 呼出方法 | 頭脳/メモリ | 境界 |
| --- | --- | --- | --- |
| `image_generate` / `image_edit` | `subprocess.run([固定sd-cli, '-m', 固定模型, ...], shell=False, timeout=...)` | 仕様をJSONへ確定→頭脳の正規の停止/解放確認→CPU生成→終了/解放→頭脳復帰。停止権限をadapterへ無条件付与しない | 模型名・steps・解像度・出力先はallowlist/上限。ファイルはジョブ専用作業域 |
| `remove_background` | 固定venv Pythonの**登録済みwrapper**→`new_session('u2net', providers=['CPUExecutionProvider'])` | 小さく、RAMに余裕があれば頭脳と共存可。ジョブ間にsession解放 | 初期模型の存在/hashを確認、推論時ネットワーク禁止。任意のPythonコードを入力させない |
| `tts_ja` | `subprocess.run([固定open_jtalk, '-x', 固定辞書, '-m', 固定声, '-ow', 出力, 入力txt], shell=False, timeout=...)` | 頭脳を常駐したままでも軽い | 文字数上限・固定voice・入力をUTF-8ファイル化、shellへの文字列連結なし |
| `mesh_edit`（保留） | 固定Blender executable＋固定Python台本＋検証済みJSON引数 | headless問題解消後。軽いmeshは共存、大きいベイクは排他 | `--factory-startup --disable-autoexec --python-exit-code 1`。LLM生成の任意Pythonを本番で自動実行しない |
| `remote_generate`（通常OFF） | NVIDIA/GCPの専用adapter | 手元はジョブ管理と結果読込だけ | **承認対象が確定するまで送信/課金しない**。local失敗を契機に勝手にremoteへfallbackしない |

CLIの呼出形の例（これだけで門番やadapterの実装が完成するわけではない）:

```python
# accepted_specは型/値/パスを検証済み、runtime/out_dirはカーネルが固定。
subprocess.run(
    [str(runtime / 'stable-diffusion.cpp/build/bin/sd-cli'),
     '-m', str(runtime / 'models/sd15-q8.gguf'),
     '-p', accepted_spec['prompt'], '--width', '512', '--height', '512',
     '--steps', '20', '--seed', '42', '--threads', '4',
     '-o', str(out_dir / 'image.png')],
    shell=False, timeout=1800, check=True,
)
```

`HF_HUB_OFFLINE`等の環境変数だけでは全ライブラリの送信を止められない。固定模型のCLI＋OS/実行sandboxのネットワーク拒否を通常運用の境界にする。Blenderの`--disable-autoexec`も明示した`--python`を禁止するものではないので、台本は登録済みの固定版を使う。

| 育てる情報 | 保存する内容 | 小さく育つ理由 |
| --- | --- | --- |
| 成功した制作レシピ | prompt、negative、seed、模型/実装hash、サイズ、steps、素材/voiceの条件、出力hash | 同じ模型を巨大な再学習なしで使い直せる |
| 実機の物差し | 壁時計・ピークRSS・swap・成功率・CPU threads・本人の採用/修正 | 1回の速度から一般化せず、設定を選ぶ根拠になる |
| 3D工程の結果 | mesh面数・manifold・UV重なり・normal・rig名・GLB再読込結果 | 「ファイルが出た」を「使えるモデル」に近づける |
| 学習の境界 | 素材/成果物の記録はローカル、外部送信は別承認 | 制作ログの蓄積と生成模型のfine-tuningを混同しない。16GB CPUで画像LoRA学習が軽いとは約束しない |

**次の実装順:** 3つを各1本完走・記録→ローカル専用adapter→Blender起動問題の切分け→SD-Turbo/FLUX小型の比較→承認付きの外部3D/動画。今回の納品はこの調査文書のみ。
