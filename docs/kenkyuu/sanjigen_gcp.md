# 画像から3D：L4 1枚の期限付きGCP試作

確認日：2026-10-08。**初回準備は本人承認で1回実行済み（後述）。今回の修正ではVM起動・課金・GPU推論・commitはしていない。**
通常生成を起動から20分以内に終える目標。初回準備は別枠。速度・品質・L4でのPBR完走は未測定で、達成保証ではない。

## 構成と公式確認

| 段 | 固定する公式模型 | 根拠・制約 |
|---|---|---|
| 1方向の形 | `tencent/Hunyuan3D-2.1` / `hunyuan3d-dit-v2-1` | [公式2.1](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1)：形10GB、paint21GB、同時保持29GB。別プロセスに分離する |
| 複数方向の形 | `tencent/Hunyuan3D-2mv` / `hunyuan3d-dit-v2-mv` | [公式模型](https://huggingface.co/tencent/Hunyuan3D-2mv)、[公式実行例](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/examples/shape_gen_multiview.py)。2系READMEの形6GBは系列の目安で、全設定の2mv保証値ではない |
| PBR | `tencent/Hunyuan3D-2.1` / `hunyuan3d-paintpbr-v2-1` | [公式paint実装](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/hy3dpaint/textureGenPipeline.py) は外部メッシュを受ける。2mv→2.1 paintはこのAPIを組み合わせた試作で、組合せの実測保証はない |
| textの前段 | `Tencent-Hunyuan/HunyuanDiT-v1.1-Diffusers-Distilled` | [公式2系text実装](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/hy3dgen/text2image.py) で1枚を作り、2.1へ。直接text→3Dではない。公式wrapperは本文の先頭60文字しか使わないため短い記述を推奨 |

VMは `g2-standard-8`（8 vCPU・32GiB RAM・L4 24GB×1）。GPUを別途二重指定・二重加算しない。[公式G2仕様](https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines#g2-vms)。
Google公式 `deeplearning-platform-release` の `common-cu129-ubuntu-2204-nvidia-580` を具体名に解決して使用。[公式DLVM一覧](https://docs.cloud.google.com/deep-learning-vm/docs/images)。
2.1公式の検証環境はPython3.10／torch2.5.1+cu124。台本はそのvenvを別に作るが、DLVM側CUDA12.9との拡張ビルドは実機未検証。CUDAのminor差異警告・ビルド失敗が出る場合は実行を止め、対応toolkitを含むイメージで環境を作り直す。cu124/Debian11の旧DLVMは公式表でサポート終了のため既定にしない。
現在のsandboxではgcloudの読むだけの画像一覧もcredentials.dbへの書込制限で失敗した。具体的なイメージの存在は実行前に本人の環境で確認が必要。

コードcommitとHF revisionは `gcloud/sanjigen/cache.py` に固定。上流mainの更新を毎回取り込まない。pipは公式pinを元にUI・訓練専用依存を外し、最初の解決結果を `requirements.lock.txt` とvenvごと保存する。

## 使い方

作るだけでは動かない。既定は**ローカル検証と計画表示だけ**で、gcloudを呼ばない。

```bash
# front必須。back/left/rightは同じキャラ・同じ艤装・同じポーズの方向違い。
bash gcloud/sanjigen/hajimeru.sh /path/to/images --mode mv --texture on --faces 100000
# 1枚なら自動でsingle。明示singleではfrontだけを使う。
bash gcloud/sanjigen/hajimeru.sh /path/to/images --mode single --texture off
bash gcloud/sanjigen/hajimeru.sh --mode text --prompt '全身、直立、艤装付き少女、白背景'
```

PNGは64〜8192px。透明PNGを推奨。方向を示す名前は `front.png back.png left.png right.png`。
`--octree 256|384|512`、既定384。`--faces 1000〜1000000` は**三角形数の目標**で、トポロジー保護により一致しないことがある。`--seed` で再現性を補助。
`--provision auto` はSpotで開始し、**作成時の容量不足だけ**通常へ1回fallback。`spot` は通常へ落ちず、`standard` は最初から通常。IAM・quota・認証失敗を容量不足と見なさない。Spot中断や起動後失敗では自動再実行しない。

地域は `ZONE=us-central1-a`（既定）または `ZONE=asia-northeast1-a`。GPU枠1枚と実際の空きは別。`PROJECT` と `BUCKET` は環境変数で指定可能。`IMAGE_NAME` で公式DLVMの具体名を固定できる。バケットはVMと同じ地域・UBLA有効・公開アクセス防止enforcedが必要。不適合な既存設定は変更せず止める。

### 初回：必ず段を分ける

以下の `--execute --accept-license` は、本人が課金・アップロード・ライセンスを承認した後だけ使う。
同時に複数台は起動しない。段ごとに前で待ち、終了を確認して次へ。

```bash
export PROJECT=your-project-id
export ZONE=us-central1-a
# 読むだけの命令で具体名を取り、準備と通常生成で同じIMAGE_NAMEを使う。
export IMAGE_NAME=$(gcloud compute images describe-from-family common-cu129-ubuntu-2204-nvidia-580 --project=deeplearning-platform-release --format='value(name)')
# 1. pip/torch/CUDA拡張を固める。重みはまだ取得しない。
bash gcloud/sanjigen/hajimeru.sh --prepare-only env --provision spot --execute --accept-license
# 2. 複数方向用の重み（形＋PBR＋背景除去）をHFから1度だけGCSへ。
bash gcloud/sanjigen/hajimeru.sh --prepare-only weights --mode mv --texture on --execute --accept-license
# 3. 1枚用も使うなら、2.1 shapeを追加。既存paint等は再取得しない。
bash gcloud/sanjigen/hajimeru.sh --prepare-only weights --mode single --texture on --execute --accept-license
# textを使う時だけ追加。重いので別の1台・別の30分枠。
bash gcloud/sanjigen/hajimeru.sh --prepare-only weights --mode text --texture on --execute --accept-license
# 通常の1回
bash gcloud/sanjigen/hajimeru.sh /path/to/images --mode mv --texture on --faces 100000 --execute --accept-license
```

`--prepare-only all` もあるが冷間環境＋全重みを30分で揃えられる保証はなく非推奨。
環境がない通常生成はHFへfallbackせず失敗する。重み準備も環境が先に必要。
HFの模型ごとにtarとSHA256完成印を保存。途中で切れた模型は次回取り直すが、完成済み模型は保持する。別リージョンにはその地域のバケットで準備をやり直す。
環境鍵にDLVMの具体名・コードcommit・torch・cache.py内容が入るため、イメージfamilyの最新版が変わると再準備になる。同じ `IMAGE_NAME` を保存して使い続ける。版を更新する時は改めて準備する。

### 初回容量と時間

容量は [HF2.1 API](https://huggingface.co/api/models/tencent/Hunyuan3D-2.1?blobs=true)、[HF2mv API](https://huggingface.co/api/models/tencent/Hunyuan3D-2mv?blobs=true)、[DINO API](https://huggingface.co/api/models/facebook/dinov2-giant?blobs=true)、[text API](https://huggingface.co/api/models/Tencent-Hunyuan/HunyuanDiT-v1.1-Diffusers-Distilled?blobs=true) の2026-10-08ファイルサイズから合計した**十進GB**。モデルのパラメータ数とは違う。

| 保存物 | 容量 | 初回時間の推測 |
|---|---:|---:|
| 2.1 shape＋VAE | 約8.02GB | HF取得＋GCS保存3〜8分 |
| 2mv形（safetensorsのみ） | 約4.93GB | 同2〜6分 |
| 2.1 paint | 約6.89GB | DINO等とまとめて4〜12分 |
| DINOv2 giant | 約4.55GB | 上のpaint欄に含めて推測 |
| RealESRGAN＋u2net | 約0.24GB | 1〜3分 |
| text追加 | 約14.49GB | 5〜15分 |
| venv＋ソース＋CUDA拡張 | **推測12〜20GB** | pip取得・解決・compile・GCS保存10〜25分 |

通常mv＋PBRの模型は約16.6GB、single＋PBRは約19.7GB。両方なら約24.6GB、textも揃えると約39.1GB。環境tarが別途必要。
無圧縮tarでCPU時間を節約。初回はHF→VM→GCSの二段転送。実効100MB/sなら16.6GBの片道だけ約2.8分（推測）。HF制限・ネットワーク・pipビルド次第で上表を超える。
保存完了印のないtarは使わない。GCSに重みを保管するのはライセンス許諾の範囲内で自分だけが使う目的に限定する。

## 通常生成の流れ・20分の判定

背景除去→形→面削減→paint（onだけ）→GLB確認・CPU下見PNG。形とpaintを別プロセスにして、前段のCUDA文脈を確実に解放する。
元画像のアスペクト比を保ち正方形の余白を付ける。2.1 paintは再remeshを無効にし、細部を再び潰すことを避ける。
形は30 steps・octree384、paintは6 views・推論512px・ベイク2048px（公式保存処理で半分の1024pxになる）。これらは時間とVRAMを優先した試作設定。
固定した公式paint実装のlist画像入力は未初期化変数を読む不具合があるため、paintは正面1枚をstyle参照に使う。多方向の拘束は形の段に適用し、背面の色・模様は推測が残る。OBJのMTL任せでPBRマップが落ちないよう、別のCPUプロセスでBlenderのBase Color・Metallic・Roughnessへ明示接続し、GLB JSONに両テクスチャが埋め込まれたことを確認する。

| 段 | 再利用時の時間予想（すべて推測） |
|---|---:|
| VM起動・小さいOS依存の復元 | 1〜3分 |
| GCSから環境と重みの復元・SHA検証 | 2〜5分 |
| 背景除去 | 0.2〜1分 |
| 形＋抽出 | 1〜4分 |
| 面削減 | 0.1〜1分 |
| PBR | 3〜7分 |
| GLB・下見・GCS保存 | 0.5〜2分 |
| 合計 | **約8〜23分：20分未満の保証なし** |

textはさらに2〜5分程度の推測で、20分達成はより難しい。まず画像入力・texture offを1回測り、次にPBRを1回測る。1回の数字だけで性能を決めない。
通常ジョブ本体は `/proc/uptime` を基準に起動後19分で停止し、保存に余裕を残す。間に合わない場合は失敗を返し、形が既にできていればそれも持ち帰る。20分は成功の目標で、Spot供給待ち・手元の転送・IAM伝播を含む全体SLAではない。
初回準備は27.5分で停止、VM内の見張りは28.5分前後に保存・自己削除。GCP側には [max-run-duration=30m / DELETE](https://docs.cloud.google.com/compute/docs/instances/limit-vm-runtime) を作成時に設定し、startup失敗でもVM・自動削除boot diskが残り続けないようにする。削除APIの実際の完了には遅延があり得る。

成果物：`gs://<BUCKET>/sanjigen/<RUN_ID>/model.glb`、`preview.png`、`startup.log`、`timings.json`、`mesh.json`、`status.json`。入力は同runの `input/`（手元への取り戻しから除外）。共通重み・環境は `cache/sanjigen/<鍵>/`。
形の元データ `shape-raw.glb` とOBJ・PBRマップ・背景除去画像も残し、部分的な失敗を調べられるようにする。`status.json=success` とGLB・PNGの実体が揃った時だけ完了とする。
ログは60秒ごとにGCSへ。強制Spot中断では最後のログ・status・成果物の保存は保証されない。

起動台本はその1台だけを前で監視し、終了後自動で手元へ取り戻す。手動で再取得する場合：

```bash
bash gcloud/sanjigen/torimodosu.sh sanjigen-YYYYMMDD-HHMMSS-NNN --bucket your-bucket
# 既定保存先: ~/Documents/カーネルの作品/<RUN_ID>/
# sandbox内で試す場合、許可された場所を --out で指定する。
```

既存の `bash dougu/matsu.sh gcp` も前で使用可能だが、こちらはプロジェクト中の全VMを待つので通常は専用監視だけを使う。隠れたバックグラウンド処理は起動しない。
期限付きSAはキーを作らず、metadata経由。自己削除権限を今回のVMだけ、GCSを今回のrunとcacheだけに絞り、2時間でIAM条件を失効。通常終了後、手元台本がbindingとSAを削除する。中断・状態未確定時は権限を奪わず警告を残すので、30分後に削除状態を見てSA/bindingを整理する（SA自体は期限で自動削除されない）。

## 費用の見込み

USD、税・為替・割引なし。2026-10-08に取得した [G2公式価格表](https://cloud.google.com/products/compute/pricing/accelerator-optimized) の地域別G2行（通常・Current Spot pricing）。[Spot公式価格](https://cloud.google.com/spot-vms/pricing) は変動するため実行前に再確認する。下表はGPUを含むVM料金だけを時給×1/3、×1/2で換算した計画値。

| 地域 | 種類 | 時給 | 20分 | 30分 |
|---|---|---:|---:|---:|
| us-central1（Iowa） | Spot | $0.486496 | $0.1622 | $0.2432 |
| us-central1 | 通常 | $0.853624312 | $0.2845 | $0.4268 |
| asia-northeast1（東京） | Spot | $0.623204 | $0.2077 | $0.3116 |
| asia-northeast1 | 通常 | $1.096224308 | $0.3654 | $0.5481 |

追加：200GBのpd-balanced・外部IPv4は20分で**推測 $0.02〜0.03**、30分で**推測 $0.03〜0.04**。[公式disk料金](https://cloud.google.com/products/compute/disks-image-pricing)、[公式network料金](https://cloud.google.com/vpc/network-pricing)。boot diskはVMと一緒に自動削除。
GCS Standardはキャッシュ30〜60GBなら保管料**推測 $0.6〜1.5/月**程度（地域・実保存量による）。[公式Storage料金](https://cloud.google.com/storage/pricing)。同地域VMへの転送を使い、地域跨ぎを避ける。手元へのPNG・GLB・ログ等のダウンロード、GCS操作料金は別。生のshape、OBJ、PBRマップも残すため1回のサイズは要測定。
初回envとweightsを2台に分け30分ずつ使う場合、VMだけIowa Spot約$0.4865、東京Spot約$0.6232。通常fallbackなら約$0.8536／$1.0962。text・single追加準備や失敗やり直しは別途。
自動削除はVMだけ。バケット・キャッシュ・成果物・共有custom roleは残る。保存期間・削除は本人が別途決める。

## ライセンスと本人が承認する点

2.1は [Tencent Hunyuan 3D 2.1 Community License](https://huggingface.co/tencent/Hunyuan3D-2.1/blob/main/LICENSE)、2mvは [2.0 Community License](https://huggingface.co/tencent/Hunyuan3D-2mv/blob/main/LICENSE)。単純なApache/MITではない。
両版のTerritoryはEU・英国・韓国を除く。日本・米国は地域内だが、対象地域外での利用・配布・表示はWorksだけでなくOutputにも制限がある。個人利用と条件内の商用利用は可能だが、版の公開時点の直前月に製品・サービス合計MAUが100万超の場合は別許諾が必要。
配布・サービス提供にはライセンス写し、表示・通知等の条件がある。公開出力のAI生成表示、法令・Acceptable Use Policy遵守も確認。TencentがOutputの権利を主張しないことは、元のキャラ・絵・商標の権利まで得られる意味ではない。
textのHunyuanDiT、DINOv2、RealESRGAN、u2net、Blender等の依存はそれぞれのライセンスも確認する。原文はバケット内の固定ソース・HF模型にも保持。

実行前に本人が承認する具体事項：課金プロジェクト・地域、通常fallbackの許可と上限、入力画像/文章のクラウド送信、模型重みの私用バケット保管、利用・公開先の地域と用途、元絵・キャラの利用権、キャッシュの継続保管料、今回VM・boot disk・期限付きSA/bindingの終了時削除。`--execute --accept-license` がその実行意思の明示になる。

## Tripo・Meshyに近づける工夫：艤装の細い・薄い部品

商用サービスと同等の品質は保証しない。縦長・横長・平面化を、見えない背面の推測、方向間の矛盾、前処理、表面抽出、面削減のどこで起こるか分けて測る。

| 工夫 | 根拠と限界 |
|---|---|
| 正面・背面・左右を実際に揃える | [公式2mv例](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/examples/shape_gen_multiview.py) は方向辞書を使う。[公式方向定義](https://github.com/Tencent-Hunyuan/Hunyuan3D-2/blob/main/hy3dgen/shapegen/preprocessors.py) に合わせる。frontから時計回り90度がleftキー、180度back、270度rightという模型規約に注意。左右を名前だけで推測せず実機で確認。別ポーズ・別装備や「もっともらしい生成背面」は誤拘束になり得る |
| 余白付き等比縮小、同じ画角・スケール | [公式preprocessor](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/hy3dshape/hy3dshape/preprocessors.py) に再中心化・resizeがある。縦横の独立resizeをしない。透明入力で細線を保持。独立背景除去や切り抜きが装備を消すことがあるのでclean PNGを必ず見る |
| 入力1024px、octree384→512を比較 | 画像だけ高解像度にしてもencoder側が縮小し得る。[公式2.1 API](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/api_models.py) のoctree上限は512。抽出格子を細かくするのは細部保持のための推論で、薄部の復元保証はない。512は時間・VRAM増、24GB/20分枠では未測定 |
| 面数を10万→20万以上で比較 | 表面が既に消えた後で面数を増やしても戻らない。raw GLBと削減後を比較。境界・トポロジー・法線保護は [PyMeshLab公式decimation](https://pymeshlab.readthedocs.io/en/latest/filter_list.html#meshing_decimation_quadric_edge_collapse) の設定。条件により目標面数まで減らせない。細い砲身・アンテナは安易なfloater除去もしない |
| paintの再remeshを切る | [公式paint API](https://github.com/Tencent-Hunyuan/Hunyuan3D-2.1/blob/main/hy3dpaint/textureGenPipeline.py) の `use_remesh=False` を使う。既存の細部を変える段を減らす。テクスチャは失われた厚み・形状を復元できない |
| キャラ・背負う艤装・砲・盾などを部品ごとに作る | 模型の正規化空間を1部品で使うと相対的に細部が大きくなる、という工学的推論。別runに分け、Blender等でスケール・位置を手動で揃える。座標や縮尺は各runで失われるので自動組立はこの台本の対象外。重なる取付部を意識した切り出し・共通基準寸法を用意する |
| 極薄板や直線部品は手で作り直す | 画像だけから見えない厚さは一意に決まらない。砲身を円柱、板を厚み付き面として作り、生成済みキャラに組むのが安定しやすいという推論。AI生成だけに拘らず下書きを使う |

最初の判定：①clean PNGに全艤装が残る、②raw GLBの前後左右で平面化・伸びがない、③削減で砲身が消えない、④PBRとUVが付く、⑤各段秒数・GPU peakと総秒数を測る。未見の別キャラでも確認する。
peak VRAMそのものの自動集計はまだ未実装。今回の送り役で約1分ごとの `nvidia-smi` を記録するが、短いピークは取り逃がす。OOMが出れば解像度・num_chunks・view数を一つずつ下げる。通常生成の30分上限やライセンス条件は緩めない。準備だけ明示指定で最大50分。

## ローカル検査

```bash
bash gcloud/sanjigen/verify.sh
```

`bash -n`、shellcheck（導入済みの場合だけ）、Python本体と埋込部分のpy_compile、入力検証12件とdry-runでgcloud非接続を確認。偽gcloudの正常終了・欠落回収・シリアル保存失敗、状態履歴・Spot通知保持も検査する。模型API・依存ビルド・GLB材質・クラウドIAM・速度はGPU実行後の判定が必要。静的検査だけで「動いた」とは報告しない。

## 2026-10-08 初回の失敗と再準備の費用

本人承認で `--prepare-only env --provision spot --execute` を1回実行。
`us-central1-a` の `sanjigen-20261008-111928-6178`（g2-standard-8＋L4、Spot）は起動し、30分上限で削除された。
**初回は0.25ドル前後を使って成果なし**（本人報告による概算。請求明細での確定値ではない）。
バケットにはinput/code.tar.gzとinput/config.jsonのみ。status・ログ・成果物が無いため、起動台本が開始したか、ビルドの停止箇所、Spot中断の有無は判定不能。
ローカル回帰検査で、元の起動表示 `$RUN_ID。` がMac標準Bashでは未定義変数として扱われ、VM作成後の監視を止めることを再現。`${RUN_ID}。` に修正した。これは手元の監視停止を説明するが、VM側に成果物が無い原因までは説明しない。

選択：段分割ではなく **`--prepare-max-minutes 50`** を追加。既定30分、prepare-only専用、30〜50の整数のみ。
準備の実処理は起動から上限の5分前まで（50分指定なら約45分、起動時間を含む）。残りは最終保存・シリアル保存待ち・削除の猶予。
GCPのmax-run-durationと手元の監視期限（上限＋5分）も連動し、通常生成は延長不可。
環境作成はソース取得、venv、torch、推論依存、custom-rasterizer、mesh-painter、検査、キャッシュ保存を一度に行う。
各段の実測値がまだ無いため「env-a/b各30分以内」とは保証できない。分割すると巨大venvの追加保存/復元と2回の起動、キャッシュ依存関係の実装が増える。
今回は最小変更の延長を選び、まず各段の実測を得る。Spotでの完走保証や途中ビルド再開はない。完成したenv/重みキャッシュのみ次回再利用できる。

| 条件（1回） | 費用の見込み | 根拠 |
|---|---:|---|
| Spot、30分 | 約$0.25 | 初回の概算を基準。厳密な現行単価ではない |
| Spot、50分 | 約$0.42、予算目安$0.50 | $0.25×50/30。追加GCS操作・保存・転送は別、単価不変の仮定 |
| Spot、30分×2段 | 約$0.50＋追加保存/復元 | 2台とも上限まで使う仮定。短く終われば安くなる |

20分の延長分は約$0.17。2段とも30分使う場合より約$0.08少ない、という条件付きの比較であり、確定請求や最安保証ではない。
200GiBのpd-balancedはUS料金$0.000136986/GiB時なら30分約$0.014、50分約$0.023（上の初回基準がディスクを含むなら二重加算しない）。
GCSのキャッシュはVM削除後も残り継続課金。ダウンロード先への転送も別料金。
Spot単価は変更されるため、実行前に[公式VM料金](https://cloud.google.com/products/compute/pricing)と[公式Spot料金](https://cloud.google.com/spot-vms/pricing)を確認。
ディスク料金は[公式表](https://cloud.google.com/compute/disks-image-pricing)。

### 新しい診断と回収

- startup-script最初の実行命令からログをローカルとシリアルに出す。GCS宛先のmetadata取得後に即送信し、送り役が約60秒ごとにstatus・ログ・nvidia-smi・dfを送る。metadata取得前の障害やSDK不在/権限問題はGCSへ送れないため、手元のシリアル採取で補う。
- status.jsonは段の開始/完了ごとに原子的に更新。completed_stagesに時刻を保持し、ビルドの命令と失敗出力をstartup.logへ出す。終了trapで最終状態・成果物を送る。
- instance/preemptedを5秒間隔で確認し、TRUEは以後消さずpreemption.jsonに保存。shutdown-scriptも最後の送信を試す。[Spotの終了猶予はbest effortで通常最大30秒](https://docs.cloud.google.com/compute/docs/instances/spot)。強制停止で送信が間に合う保証はない。
- 待機中は約1分ごとにバケットログ末尾8行を表示。シリアルは各監視周期（約20秒）と通常終了時に `get-serial-port-output` で手元のserial-port-1.txtへ保存。成果物送信後のvm-finished.jsonを見て、保存成功のserial-collected.jsonを返すまでVMは最大60秒待って自己削除する。保存失敗でも上限は延ばさず、エラーを表示する。
- SpotやGCP期限で先に削除されたVMのシリアルは取り直せない。待機中に採れた最新分を残す。手元の停止・ネットワーク障害時は採取できない。[公式シリアル取得](https://docs.cloud.google.com/sdk/gcloud/reference/compute/instances/get-serial-port-output)。
- torimodosuはstatusが無い/不正でもPython例外で落ちず、最終段・完了印・Spot通知・ログ/シリアルの有無と末尾を報告する。欠落だけから原因や成功を決めつけない。`--out`で保存先を指定できる。

次の再準備1回（今回の承認は修正のみなので、**新しい起動・課金には改めて本人承認が必要**）：

```bash
bash gcloud/sanjigen/hajimeru.sh --prepare-only env --prepare-max-minutes 50 --provision spot --execute --accept-license
```

Claudeはこの1行を明示timeout付きrun_in_background（最大70分程度）で起動し、一覧に載せる。台本内で対象VMを待つため別の見張りを重ねない。
