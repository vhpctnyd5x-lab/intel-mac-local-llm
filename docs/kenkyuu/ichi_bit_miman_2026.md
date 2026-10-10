# 1 bit/重み未満のLLM圧縮をQwen3.6-35B-A3Bに使えるか

調査日: 2026-10-10。対象は Intel Mac（i7-9750H、RAM 16GB、Radeon 5300M 4GB）と、Qwen3.6-35B-A3B の GGUF（専門家を256→160に削った k160、約8.29GB）。手元の先行メモは[bit_yori_shita.md](bit_yori_shita.md)。

## 判定

**現行ランタイムには採用しない。** 0.1〜0.55 BPWで重み容量を大きく減らす論文はあるが、LittleBit/NanoQuant/BTC-LLMの報告はMoE対象ではなく、低ビット側では困惑度や正答率が大きく落ちる例がある。いずれも低ランク・二値因子や符号帳を使う別表現で、現行GGUFをそのまま変換して動かすものではない。推論の速さもCUDAカーネル等の専用実装に依存し、MacのCPU/Radeon上の実測は見つからなかった。

容量の理論下限は魅力的なので、**実装採用とは切り離した小型PTQ再現実験なら価値あり**。推奨は公式実装のあるNanoQuant、Qwen3-1.7B、0.55 BPW、2回、Google Cloud L4の課金上限を12 GPU時間（約$3）に設定。論文の結果が再現できるかを確かめるだけで、Qwen3.6 MoEやMacでの速度を証明する実験ではない。

## 方式ごとの比較

| 手法 | 学習・圧縮方法 | 低ビット品質（元との差） | MoE実績 | 推論実装・llama.cpp |
|---|---|---|---|---|
| [LittleBit](https://arxiv.org/html/2506.13771v5) | PTQではない。二値の低ランク因子と補償スケールを作り、教師モデルからの知識蒸留を含むQAT。WikiText-2/C4、系列長2048、5 epoch。公式[コード](https://github.com/SamsungLabs/LittleBit)は単一CUDA GPUの学習手順を公開。NanoQuant論文Table 4の比較では、Llama2-7Bを196M tokenで処理するLittleBitに123.6 H100 GPU時間を報告。 | 論文Table 1のQwQ-32B（密モデル）はFP16 PPL 6.34、0.3 BPWで16.48（2.60倍）、0.1 BPWで35.26（5.56倍）。Table 2のLlama2-7Bでは平均正答率62.97%→47.26%（0.55 BPW）、45.20%（0.3 BPW）。圧縮後も言語モデリングと常識推論の劣化は大きい。 | Table 1の最大はQwQ-32B。Qwen3系の実験はなく、MoEの結果もない。 | 論文Figure 6はA100上の独自CUDA GEMVで、0.1 BPWの最大11.6倍は単一MLP層の測定。CPU用・llama.cpp用の公開実装ではない。factorized forwardを実装する必要がある。 |
| [NanoQuant](https://arxiv.org/html/2602.06694v1) | PTQ。事前学習・蒸留は不要だが、128校正例（約0.26M token）を用いた層ごとの再構成、ADMM初期化、STEによる因子調整がある。公式[コード](https://github.com/SamsungLabs/NanoQuant)あり。 | 論文Table 2で最小は0.55 BPW（したがって0.1〜0.5の数値は未報告）。Qwen3-1.7BはFP16 PPL 9.39→33.74（3.59倍）、Qwen3-0.6Bは12.66→52.94（4.18倍）、Qwen3-14Bは6.37→17.06（2.68倍）。Table 3のゼロショット比較は選択モデルの1-bit設定で、0.55 BPWの正答率を示していない。 | Qwen3の密モデル（0.6〜14B）を評価。Qwen3-30B-A3B等のMoEは表にない。 | 独自CUDA GEMV/GEMM。Table 4はLlama2-7Bの0.26M校正tokenをH100で1.7 GPU時間、0.55 BPWも別条件で評価。70Bは単一H100で13時間（論文本文）。Mac CPU/AMD向けカーネルやGGUF出力は確認できず。 |
| [BTC-LLM](https://arxiv.org/html/2506.12040v2) | PTQ。重み全体のQAT/蒸留ではないが、学習可能な変換をブロック単位で最適化し、二値パターンを符号帳化する。論文は圧縮処理のGPU時間を示さず、Figure 5の速度評価のみH800上の独自Binary Codebook LUT-GEMM。論文がコード先としてリンクする[GitHub](https://github.com/Chooovy/BTC-LLM)は調査時点でREADMEのみ（実装ファイルなし）。 | 0.1〜0.5 BPWの評価なし。論文Table 1の最低は0.7 BPW。Qwen3-0.6BはAppendix Table 7でFP16 PPL 20.95→120.08（0.8 BPW、5.73倍）、平均正答率48.91%→40.25%（−8.66ポイント）。Qwen3-1.7Bは1.11 BPWでPPL 16.71→32.56。 | Qwen3-0.6B/1.7Bなど密モデルの例あり。MoEはなし。 | Figure 5の最大1.6倍はH800のカーネル測定。二値符号帳LUT演算が前提で、CPU版・GGUF・llama.cpp対応は確認できない。 |

### 読み取り上の注意

- **0.1 BPWは既存の均一な2-bit列を可変長符号にする手法ではない。** LittleBit/NanoQuantは重み行列を低ランクの二値因子へ置き換える。BTC-LLMは重み変換と二値符号帳を使う。したがって、手元のGGUFにハフマン符号を後掛けするだけでは再現できない。先行メモの実測では現行2-bit記号は約1.996〜1.999 bit/記号で、後段のエントロピー符号化では縮小が1%未満。
- 「未学習」はNanoQuant/BTC-LLMの**事前学習・全モデルQATが不要**という意味。校正データ上で因子・変換・スケールを反復最適化する処理はある。
- 「MoE対応」は論文の評価結果で判定した。公式実装がQwen系を列挙していても、密モデルの表だけならMoEでの再現性を示さない。

## 2026年のMoE直接研究

[MoBiE](https://arxiv.org/abs/2604.06798)はQwen3-30B-A3Bを含むMoE二値化を掲げ、今回の対象に最も近い。ただしarXivは撤回表示で、著者が導出上の根本的誤り等を理由に撤回したと記載。PDFも公開されず、リンク先GitHubも現在404。初版概要にある性能値は**採用判断の根拠にしない**。現時点で信頼して使える「Qwen3.x MoEの0.1〜0.5 BPW結果」は見つからなかった。

## このMacでの容量・速度・賢さ

- 先行メモの現在値はファイル約8.29GB（AGENTS.md表記の7.7GiBとほぼ同じ）、常駐8.0〜8.2GB、生成8〜9字/秒、知識23/25、操作36〜39/41。すでに16GB機で動作しているため、圧縮の主な価値はメモリ余裕と読み出し帯域。
- 単純な重み本体の下限計算では、35B×BPW÷8より、0.1 BPW≈0.44GB、0.3≈1.31GB、0.55≈2.41GB。これは**全パラメータに報告BPWを適用した理論値**で、固定テンソル、スケール、GGUFメタデータ、k160で残る実パラメータ構成を反映しない。実ファイルがこの大きさになる保証ではない。
- 重みが小さくなる分、同じCPUカーネルならメモリ読み出しには有利。ただし各方式は低ランク因子の積や符号帳参照など追加演算を要し、報告速度は主にNVIDIA CUDA上。i7-9750Hで速くなるかは未測定で、Radeon 5300M用CUDAは使えない。llama.cppはGGUFを要求するが、3方式の公式実装に互換GGUF/ggml経路はない。**今の8〜9字/秒からの改善率は予測不能**。
- 品質面は容量ほど楽観できない。密Qwen3ですらNanoQuantの0.55 BPWでPPLが約2.7〜4.2倍、LittleBitは0.1〜0.3 BPWでQwQ-32BのPPLが2.6〜5.6倍。Qwen3.6 MoE/k160固有の知識25問・操作41問への影響は未測定。よって本番の「早い・安い・賢い」を満たす実証はない。

## $5以内の最小実験案（実行は未着手）

**NanoQuantでQwen3-1.7Bを0.55 BPWにし、WikiText-2 PPLを2回測る。** BTC-LLMは現状実コードがなく、LittleBitのQATは高コストなので今回は選ばない。

1. Google CloudのSpot L4を1枚、CUDA 12.4、Python 3.12で用意。公式NanoQuantの`pip install .`とCUDAカーネルcompileを行う。論文の環境はPyTorch 2.6.0、Transformers 4.51.3、datasets 4.0.0、lm_eval 0.4.9、CUDA 12.4（本文Appendix C）。GitHubの依存にはaccelerate、cut_cross_entropy、gemlite、optimum、zeus-ml等も含まれる。
2. Qwen/Qwen3-1.7BのBF16基準PPLを同じWikiText-2評価条件で記録。その後、公式スクリプトで`--bits 0.55 --num_calib_samples 128 --nonfact_epochs 8 --fact_epochs 8 --admm_outer_iters 400 --ppl_task wikitext2`を使い、校正seedを変えて2回圧縮・評価。実測BPW、PPL、ピークVRAM、圧縮時間、出力サイズを保存する。
3. 論文Table 2の照合値はBF16 9.39、NanoQuant 0.55 BPWで33.74。再現値が近くても**品質が基準のままという意味ではない**。2回ともPPLが基準の1.5倍を超えたら、より低ビットの追試と35B転用検討を打ち切る。良好なら初めてゼロショット評価と推論形式の調査へ進む。

**時間・費用見積り:** 小型Qwen3-1.7BのL4所要時間は公式値がないため推定。論文Table 4のLlama2-7B/H100（0.26M校正token）1.7 GPU時間を参考に、2回＋PPL・環境作成込みで通常2〜6時間、Spot再試行を含む**課金上限12 GPU時間**に設定する。提示単価$0.25/時なら上限$3、残り$2を予備にする。12時間に到達したら停止し、VMと課金対象ディスクを残さない。H100実測からL4時間への換算は未検証である。

## まとめ（結論→数字→次）

- 結論: 35B-A3B k160には現時点で不採用。容量圧縮は魅力だが、MoE品質・Mac速度・GGUF互換の証拠が足りない。
- 数字: NanoQuant Qwen3-1.7BはPPL 9.39→33.74（0.55 BPW、論文Table 2）。L4 12時間で上限約$3。
- 次: 費用を使う場合も、まずNanoQuantの小型再現を2回だけ行い、良好な場合に限り次段階を検討する。

## 参照

- LittleBit: [論文（v5）](https://arxiv.org/html/2506.13771v5)、[公式実装](https://github.com/SamsungLabs/LittleBit)
- NanoQuant: [ICML 2026論文](https://proceedings.mlr.press/v306/chong26a.html)、[論文HTML・表](https://arxiv.org/html/2602.06694v1)、[公式実装](https://github.com/SamsungLabs/NanoQuant)
- BTC-LLM: [論文（v2）](https://arxiv.org/html/2506.12040v2)、[公開GitHub](https://github.com/Chooovy/BTC-LLM)
- MoBiE: [arXiv撤回表示](https://arxiv.org/abs/2604.06798)
- llama.cpp: [公式GGUF/モデル説明](https://github.com/ggml-org/llama.cpp/blob/master/docs/models.md)
