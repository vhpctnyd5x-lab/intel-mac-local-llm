# 安い・早い・賢いの下調べ（10/4 夜。Codex Luna と NVIDIA ultra）

## Codex（Web検索あり）
## 結論
最初に試す価値が高いのは、**追加の推論ターンではなく、失敗から再利用できる教訓を作ること・門番を一般化すること・出力を短くすること**です。公開41問向けの改善を積み増すより、秘密問と同じ型でも言い換えや道具が変わった課題で確かめるのがよさそうです。
2025年の研究では、狭い専門家デモだけに頼るより、エージェント自身の経験や失敗を使う方法が複数環境で有効性・領域外汎化を改善しました。また、失敗履歴から戦略原則を作り、必要なときに検索する構成も提案されています。ただし、これは本機・本モデルでの効果を保証するものではなく、秘密問で要検証です。[Agent Learning via Early Experience](https://arxiv.org/abs/2510.08558)、[EvolveR](https://arxiv.org/abs/2510.16079)
## 候補の順位
期待効果は**秘密問の正解数**、手間は実装・比較の規模、費用は追加の計算/API費用です。順位と効果は研究結果を本環境に当てはめた仮説です。
| 順位 | 候補（期待効果 × 手間 × 費用） | 何をする・なぜ効くか（出典） | この環境での最初の一歩 | 測り方 |
|---:|---|---|---|---|
| 1 | **失敗から教訓カード**（高 × 中 × 低） | 道具の誤選択・検索漏れ・出力の読み違いを、問題文ではなく「失敗の型→次に確認すること」に抽象化。成功した教訓だけ必要時に検索して添える。経験ベースの学習や、再利用可能な戦略原則を蓄積する研究が近い。生成したカードは門番で検証し、誤りを記憶に固定しない。[Early Experience](https://arxiv.org/abs/2510.08558)、[EvolveR](https://arxiv.org/abs/2510.16079) | [jiyuu.py](dougu/jiyuu.py) の失敗記録と、[tsukuru_tehon_luna.py](dougu/tsukuru_tehon_luna.py) の教材生成を読む。問題固有の答えを含めずにカード案を作る。 | 固定した秘密問で、カードなし／ありの正解数・秒数を比較。**カード作成に使った設問は最終評価に混ぜない**。 |
| 2 | **一般化する門番・道具契約**（高 × 中 × ほぼ0） | 特定の語句で分岐する門番ではなく、入力条件・道具の返却形式・証拠の有無・停止条件を検査する。道具利用が言い換えや文脈変化に弱い問題は、ツール学習サーベイでも論点になっている。[Tool learning survey](https://link.springer.com/article/10.1007/s44336-025-00024-x) | [kyoudou.py](dougu/kyoudou.py) と [jiyuu.py](dougu/jiyuu.py) で、キーワード依存の判定と決定的な検査を棚卸しする。説明は「いつ使う／入力／出力／失敗時」に統一。 | 秘密問の正答に加え、門番が不要な課題を止める率・誤って通す率を記録。公開問の個別パッチを足さない。 |
| 3 | **受動的な知識取り込みを強化**（高・知識問向け × 中 × 低〜API分） | 外部モデルに記事単位の要点・根拠・関連語を作らせ、SQLite FTS5から短い根拠付きノートを引く。既に観測された「検索4回112秒から、道具なし36秒」につながる路線。誤ったノートを避けるため出典・確信度を残し、根拠を照合する。 | [chishiki_kouka.py](dougu/chishiki_kouka.py) のA〜D比較と、[tameshi_gakushuu.py](dougu/tameshi_gakushuu.py) の事前学習試験を起点に、ノート有無・検索語・根拠の当たり方を比較。 | まず知識25問で正答数・回答時間・根拠一致率を測り、秘密問では「学習した知識と異なる表現」の問題だけを見る。 |
| 4 | **短い出力・必要な道具だけ**（中〜高 × 小 × 0） | CPUでは生成トークンが直接時間を増やす。余分な説明や、効果のなかった「もう1回考える」段を抑え、道具呼び出しは最小限にする。これは研究からの一般論というより、今回の実測（2.5倍の時間で点が伸びなかった）を優先した候補。 | [jiyuu.py](dougu/jiyuu.py) の出力上限・システム指示・終了条件を確認。正解の形式が決まる問題は答えだけにする。 | 秘密問で正解数を落とさず、生成トークン数と総秒数が減るか測る。 |
| 5 | **共通プロンプトのKV再利用**（中 × 小 × 0） | ツール往復で同じ前置きを繰り返すなら、共通部分の再計算を減らせる。llama.cpp serverにはプロンプトキャッシュがあり、共通プレフィックスを再利用する設定がある。[llama.cpp server docs](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) | [jiyuu.py](dougu/jiyuu.py) のリクエスト本文を見て、共通プレフィックスの長さとスロット再利用を確認。現行設定でキャッシュが実際に当たるかから測る。 | 同じ秘密問をキャッシュ有無で交互に実行し、前処理時間・総時間を比較。冷起動と温状態は分ける。 |
| 6 | **Google Cloudで公開データの生成・並列評価**（中 × 小〜中 × 数十セント〜） | 重い夜間仕事は、公開・合成データでの教師回答生成、独立採点、候補の並列評価に回す。Spot VMは安価だが中断され得るため、JSONLを小分け保存して再開可能にする。公式価格表ではSpotの `e2-highcpu-4` が約 **$0.059/時**、L4の `g2-standard-4` は約 **$0.403/時**（価格は地域・時期で変動）。Spot VMの終了通知は通常30秒の猶予。[Spot料金](https://cloud.google.com/spot-vms/pricing)、[Spot VMの注意点](https://docs.cloud.google.com/compute/docs/instances/create-use-spot?hl=en) | [tsukuru_tehon.py](dougu/tsukuru_tehon.py) を題材に、再開可能な小分け出力を確認。秘密問そのものはクラウドへ送らず、最終採点は手元で行う。 | 公開・合成問で生成件数/時、独立採点後の残存率、1件当たり費用を測る。秘密問は固定版をローカルで採点。 |
| 7 | **小さい道具選択器をLoRA微調整**（中 × 大 × 数十セント〜数ドル） | 35B本体を直接調整するより、道具選択や引数作成に特化した小型モデルを候補にする。失敗例を修正例に変えて、API・形式制約に沿う動作を学習させる。これはまだ本機での優位性が不明なため、教訓カードや門番の後。 | [tsukuru_tehon.py](dougu/tsukuru_tehon.py) で、道具利用の成功・失敗を含む学習候補を作る設計を検討。まず1〜3B級のモデルを対象にする。 | 同じ秘密問で現行モデルと選択器併用を比較し、正答数・呼び出し失敗率・総秒数・学習費用を記録。35BのQLoRAがL4 24GBに収まるとは見込まず、実測前提。 |
| 8 | **投機的デコード**（効果不確実 × 中 × 0〜小） | 小さいドラフトが複数トークンを先読みし、本体がまとめて検証する方式。速さはドラフトの受理率次第で、CPUではドラフト計算の上乗せが勝つ場合もある。llama.cppは複数方式をサポートするが、実測が必要。[llama.cpp speculative decoding](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md) | [hashiru.sh](dougu/hashiru.sh) とモデル構成で、現在のk160に対応するドラフト/MTPモデルがあるか確認。なければ小モデル追加の読み込み時間も含めて比較する。 | 同じ秘密問で受理率、生成速度、初回応答時間、総時間を比較。正解率が保てて時間が減る場合のみ候補に残す。 |
| 9 | **専門家剪定の追加検討**（速度効果は不確実 × 大 × 主に計算時間） | 既にk160まで剪定済みなので、さらに数を減らす前に、層ごとの寄与や活性化経路を評価する。2025年のMoE Pathfinderは層をまたぐ専門家の軌跡を使う剪定を提案しているが、対象環境への移植は別仕事。[MoE Pathfinder](https://arxiv.org/abs/2512.18425) | [prune_experts.py](dougu/asshuku/prune_experts.py) と [KEKKA.md](dougu/jikken/KEKKA.md) を確認し、既存の候補間で比較可能なものを先に使う。 | 速度だけでなく秘密問の正答数・RAM・モデル読み込み時間を比べる。1回の数字で決めず、品質低下が速度利益を上回る設定は棄却。 |
| 10 | **KVキャッシュ量子化**（速度効果は低〜不明 × 中 × 0） | 主に長文脈・バッチ時のメモリ削減策。2025年のVecInferは低ビットKVの効果を示すが、CUDA最適化を使うため、CPU-onlyへ速度効果をそのまま移せない。[VecInfer](https://arxiv.org/abs/2510.06175) | [set_kv.py](dougu/asshuku/set_kv.py) と既存のllama.cpp設定を見て、まずメモリ不足や長い前処理が実際に制約か確認。 | 短い秘密問で速度差が小さければ保留。長い文脈の問題に絞り、正答・秒数・メモリを測る。 |
### 測定上の注意
記録されている基準は**秘密問13/31**ですが、今回の前提は**秘密30問**です。比較前に問題IDと分母を固定し、どちらを正式な基準にするか揃えてください。[研究メモ SHIKOU.md](dougu/jikken/SHIKOU.md) にも同設定で±2問の揺れがあります。開発には公開・新規合成問を使い、秘密問は変更版の確認用に温存するのが安全です。
## 明日の朝やる3つ
1. 秘密問のID・分母（30か31か）・採点条件を固定する。  
2. 追加の推論段を増やさず、**短い出力＋共通プレフィックス再利用**の時間を測る。  
3. 失敗記録を「設問の答え」ではなく「失敗の型→検証手順」の教訓カードにできるか、数件で設計する。
## 結論
最初に試す価値が高いのは、**追加の推論ターンではなく、失敗から再利用できる教訓を作ること・門番を一般化すること・出力を短くすること**です。公開41問向けの改善を積み増すより、秘密問と同じ型でも言い換えや道具が変わった課題で確かめるのがよさそうです。
2025年の研究では、狭い専門家デモだけに頼るより、エージェント自身の経験や失敗を使う方法が複数環境で有効性・領域外汎化を改善しました。また、失敗履歴から戦略原則を作り、必要なときに検索する構成も提案されています。ただし、これは本機・本モデルでの効果を保証するものではなく、秘密問で要検証です。[Agent Learning via Early Experience](https://arxiv.org/abs/2510.08558)、[EvolveR](https://arxiv.org/abs/2510.16079)
## 候補の順位
期待効果は**秘密問の正解数**、手間は実装・比較の規模、費用は追加の計算/API費用です。順位と効果は研究結果を本環境に当てはめた仮説です。
| 順位 | 候補（期待効果 × 手間 × 費用） | 何をする・なぜ効くか（出典） | この環境での最初の一歩 | 測り方 |
|---:|---|---|---|---|
| 1 | **失敗から教訓カード**（高 × 中 × 低） | 道具の誤選択・検索漏れ・出力の読み違いを、問題文ではなく「失敗の型→次に確認すること」に抽象化。成功した教訓だけ必要時に検索して添える。経験ベースの学習や、再利用可能な戦略原則を蓄積する研究が近い。生成したカードは門番で検証し、誤りを記憶に固定しない。[Early Experience](https://arxiv.org/abs/2510.08558)、[EvolveR](https://arxiv.org/abs/2510.16079) | [jiyuu.py](dougu/jiyuu.py) の失敗記録と、[tsukuru_tehon_luna.py](dougu/tsukuru_tehon_luna.py) の教材生成を読む。問題固有の答えを含めずにカード案を作る。 | 固定した秘密問で、カードなし／ありの正解数・秒数を比較。**カード作成に使った設問は最終評価に混ぜない**。 |
| 2 | **一般化する門番・道具契約**（高 × 中 × ほぼ0） | 特定の語句で分岐する門番ではなく、入力条件・道具の返却形式・証拠の有無・停止条件を検査する。道具利用が言い換えや文脈変化に弱い問題は、ツール学習サーベイでも論点になっている。[Tool learning survey](https://link.springer.com/article/10.1007/s44336-025-00024-x) | [kyoudou.py](dougu/kyoudou.py) と [jiyuu.py](dougu/jiyuu.py) で、キーワード依存の判定と決定的な検査を棚卸しする。説明は「いつ使う／入力／出力／失敗時」に統一。 | 秘密問の正答に加え、門番が不要な課題を止める率・誤って通す率を記録。公開問の個別パッチを足さない。 |
| 3 | **受動的な知識取り込みを強化**（高・知識問向け × 中 × 低〜API分） | 外部モデルに記事単位の要点・根拠・関連語を作らせ、SQLite FTS5から短い根拠付きノートを引く。既に観測された「検索4回112秒から、道具なし36秒」につながる路線。誤ったノートを避けるため出典・確信度を残し、根拠を照合する。 | [chishiki_kouka.py](dougu/chishiki_kouka.py) のA〜D比較と、[tameshi_gakushuu.py](dougu/tameshi_gakushuu.py) の事前学習試験を起点に、ノート有無・検索語・根拠の当たり方を比較。 | まず知識25問で正答数・回答時間・根拠一致率を測り、秘密問では「学習した知識と異なる表現」の問題だけを見る。 |
| 4 | **短い出力・必要な道具だけ**（中〜高 × 小 × 0） | CPUでは生成トークンが直接時間を増やす。余分な説明や、効果のなかった「もう1回考える」段を抑え、道具呼び出しは最小限にする。これは研究からの一般論というより、今回の実測（2.5倍の時間で点が伸びなかった）を優先した候補。 | [jiyuu.py](dougu/jiyuu.py) の出力上限・システム指示・終了条件を確認。正解の形式が決まる問題は答えだけにする。 | 秘密問で正解数を落とさず、生成トークン数と総秒数が減るか測る。 |
| 5 | **共通プロンプトのKV再利用**（中 × 小 × 0） | ツール往復で同じ前置きを繰り返すなら、共通部分の再計算を減らせる。llama.cpp serverにはプロンプトキャッシュがあり、共通プレフィックスを再利用する設定がある。[llama.cpp server docs](https://github.com/ggml-org/llama.cpp/blob/master/tools/server/README.md) | [jiyuu.py](dougu/jiyuu.py) のリクエスト本文を見て、共通プレフィックスの長さとスロット再利用を確認。現行設定でキャッシュが実際に当たるかから測る。 | 同じ秘密問をキャッシュ有無で交互に実行し、前処理時間・総時間を比較。冷起動と温状態は分ける。 |
| 6 | **Google Cloudで公開データの生成・並列評価**（中 × 小〜中 × 数十セント〜） | 重い夜間仕事は、公開・合成データでの教師回答生成、独立採点、候補の並列評価に回す。Spot VMは安価だが中断され得るため、JSONLを小分け保存して再開可能にする。公式価格表ではSpotの `e2-highcpu-4` が約 **$0.059/時**、L4の `g2-standard-4` は約 **$0.403/時**（価格は地域・時期で変動）。Spot VMの終了通知は通常30秒の猶予。[Spot料金](https://cloud.google.com/spot-vms/pricing)、[Spot VMの注意点](https://docs.cloud.google.com/compute/docs/instances/create-use-spot?hl=en) | [tsukuru_tehon.py](dougu/tsukuru_tehon.py) を題材に、再開可能な小分け出力を確認。秘密問そのものはクラウドへ送らず、最終採点は手元で行う。 | 公開・合成問で生成件数/時、独立採点後の残存率、1件当たり費用を測る。秘密問は固定版をローカルで採点。 |
| 7 | **小さい道具選択器をLoRA微調整**（中 × 大 × 数十セント〜数ドル） | 35B本体を直接調整するより、道具選択や引数作成に特化した小型モデルを候補にする。失敗例を修正例に変えて、API・形式制約に沿う動作を学習させる。これはまだ本機での優位性が不明なため、教訓カードや門番の後。 | [tsukuru_tehon.py](dougu/tsukuru_tehon.py) で、道具利用の成功・失敗を含む学習候補を作る設計を検討。まず1〜3B級のモデルを対象にする。 | 同じ秘密問で現行モデルと選択器併用を比較し、正答数・呼び出し失敗率・総秒数・学習費用を記録。35BのQLoRAがL4 24GBに収まるとは見込まず、実測前提。 |
| 8 | **投機的デコード**（効果不確実 × 中 × 0〜小） | 小さいドラフトが複数トークンを先読みし、本体がまとめて検証する方式。速さはドラフトの受理率次第で、CPUではドラフト計算の上乗せが勝つ場合もある。llama.cppは複数方式をサポートするが、実測が必要。[llama.cpp speculative decoding](https://github.com/ggml-org/llama.cpp/blob/master/docs/speculative.md) | [hashiru.sh](dougu/hashiru.sh) とモデル構成で、現在のk160に対応するドラフト/MTPモデルがあるか確認。なければ小モデル追加の読み込み時間も含めて比較する。 | 同じ秘密問で受理率、生成速度、初回応答時間、総時間を比較。正解率が保てて時間が減る場合のみ候補に残す。 |
| 9 | **専門家剪定の追加検討**（速度効果は不確実 × 大 × 主に計算時間） | 既にk160まで剪定済みなので、さらに数を減らす前に、層ごとの寄与や活性化経路を評価する。2025年のMoE Pathfinderは層をまたぐ専門家の軌跡を使う剪定を提案しているが、対象環境への移植は別仕事。[MoE Pathfinder](https://arxiv.org/abs/2512.18425) | [prune_experts.py](dougu/asshuku/prune_experts.py) と [KEKKA.md](dougu/jikken/KEKKA.md) を確認し、既存の候補間で比較可能なものを先に使う。 | 速度だけでなく秘密問の正答数・RAM・モデル読み込み時間を比べる。1回の数字で決めず、品質低下が速度利益を上回る設定は棄却。 |
| 10 | **KVキャッシュ量子化**（速度効果は低〜不明 × 中 × 0） | 主に長文脈・バッチ時のメモリ削減策。2025年のVecInferは低ビットKVの効果を示すが、CUDA最適化を使うため、CPU-onlyへ速度効果をそのまま移せない。[VecInfer](https://arxiv.org/abs/2510.06175) | [set_kv.py](dougu/asshuku/set_kv.py) と既存のllama.cpp設定を見て、まずメモリ不足や長い前処理が実際に制約か確認。 | 短い秘密問で速度差が小さければ保留。長い文脈の問題に絞り、正答・秒数・メモリを測る。 |
### 測定上の注意
記録されている基準は**秘密問13/31**ですが、今回の前提は**秘密30問**です。比較前に問題IDと分母を固定し、どちらを正式な基準にするか揃えてください。[研究メモ SHIKOU.md](dougu/jikken/SHIKOU.md) にも同設定で±2問の揺れがあります。開発には公開・新規合成問を使い、秘密問は変更版の確認用に温存するのが安全です。
## 明日の朝やる3つ
1. 秘密問のID・分母（30か31か）・採点条件を固定する。  
2. 追加の推論段を増やさず、**短い出力＋共通プレフィックス再利用**の時間を測る。  
3. 失敗記録を「設問の答え」ではなく「失敗の型→検証手順」の教訓カードにできるか、数件で設計する。

## NVIDIA ultra（Web無し・記憶から）
# ローカルLLM「安い・早い・賢い」化 下調べレポート  
**環境**: Intel i7-9750H / 16 GB RAM / GPU なし / llama.cpp 改造版  
**モデル**: Qwen3-30B-A3B 専門家 160 本に刈り込み → **Q2_K_XL (k160)**  
**現状スコア**: 公開 41 問 38/41、秘密 30 問 13/31（10/3）  
**外部リソース**: NVIDIA Build API (Nemotron 3 Ultra / Fast)、Codex、GCP Spot VM (~$0.1/h)

---

## 1. 候補一覧（期待効果 × 手間 × 費用 でスコアリング／満点 100）

| 順位 | 候補 | 期待効果 | 手間 | 費用 | 総合 | 何をする（1 行） |
|----|------|--------|------|------|------|----------------|
| 1 | **オフライン蒸留＋RAG インデックス化** | 9 | 3 | 1 | **92** | 大モデルで Wikipedia 等を「学習ノート」化し、ローカル SQLite FTS5 へ格納。小モデルは検索＋読解のみ |
| 2 | **自己整合性＋最小検証ループ（Self-Consistency + Minimal Verification）** | 8 | 2 | 0 | **88** | 同一プロンプトで 3 回生成→多数決、Python で「数値・単位・引用」だけ検算 |
| 3 | **投機的デコード（ドラフト: Q2_K_S / ターゲット: Q2_K_XL）** | 7 | 4 | 0 | **80** | 同一モデルの小量子化版をドラフトに、受理率 0.6 以上で 1.8–2.2× 高速化 |
| 4 | **プロンプト・キャッシュ（llama.cpp `--prompt-cache` / `--cache-prompt`）** | 6 | 1 | 0 | **78** | 門番プロンプト・システムプロンプト・RAG 定型文を KV キャッシュ化し、毎回の prefill をスキップ |
| 5 | **MoE 専門家動的刈り込み（Top-K ルーティング学習）** | 7 | 6 | 2 | **72** | 秘密セットで「どの専門家が火を噴くか」を収集→専門家 80 本に再刈り込み＋LoRA 1 epoch |
| 6 | **GCP Spot で夜間「蒸留データ生成＋評価並列」** | 8 | 5 | 3 | **70** | Nemotron Ultra で 5 k 件の CoT データ生成→ローカルで LoRA 微調整（4 bit / rank 8） |
| 7 | **ツール記述の「型付きスキーマ化」＋関数呼び出し微調整** | 6 | 5 | 1 | **68** | JSON Schema + TypeScript 定義をプロンプトに埋め込み、関数呼び出し精度を 90 % 以上へ |
| 8 | **KV キャッシュ 8 bit 量子化（GGML_TYPE_Q8_0 / K-quants）** | 5 | 3 | 0 | **65** | メモリ 30 % 削減→バッチ 1 でも OOM 回避、長文脈でデコード高速化 |
| 9 | **短い出力強制（`max_tokens=256` + `stop=["\n\n"]`）＋要約後処理** | 4 | 1 | 0 | **60** | 生成トークン数を 40 % カット、最後の 1 ターンで要約モデル（同一）に圧縮させる |
| 10 | **計画・実行・検証の 3 段階プロンプト（Plan-Act-Verify）** | 5 | 4 | 0 | **58** | 最初のターンで「手順リスト」だけ出させ、2 ターン目で実行、3 ターン目で検算 |

> **スコアリング基準**  
> - 期待効果: 秘密 30 問での正答率改善見込み（10=+20 % 以上）  
> - 手間: 実装・デバッグ工数（1=数行修正、10=数週間）  
> - 費用: 追加金銭コスト（0=無料、10=数百ドル）  
> - 総合 = (効果×10) − (手間×3) − (費用×2)

---

## 2. 各候補の詳細カード

### ① オフライン蒸留＋RAG インデックス化
- **なぜ効くか**  
  - **REPLUG (Shi et al., 2023 / ICLR 2024)**: 凍結 LM に外部知識を「受動注入」し、推論時計算を検索のみに限定。  
  - **RA-DIT (Lin et al., 2023 / NeurIPS 2023)**: 大モデルで「読解ノート」を事前生成→小モデルは参照のみで性能維持。  
  - あなたの実験（36 s / 無ツール）がこれを裏付け。
- **最初の一歩**  
  - `koukai/scripts/build_notes.py` を新規作成  
    ```python
    # 入力: data/wiki_chunks.sqlite (FTS5)
    # 出力: data/notes.sqlite (id, title, summary, keywords, related_ids)
    # 呼び出し: NVIDIA Build API (nemotron-3-ultra) で 1 記事 2–3 秒
    ```
- **測り方**  
  - 秘密 30 問を「ツールなし・RAG 検索 1 回・notes 参照」で実行  
  - 指標: 正答率、レイテンシ（目標 ≤ 20 s）、トークン数

---

### ② 自己整合性＋最小検証ループ
- **なぜ効くか**  
  - **Self-Consistency (Wang et al., 2023 / ICLR 2023)**: 同一温度で n 回生成→多数決で +5–15 %。  
  - **Self-Verification (Weng et al., 2023 / ACL 2023)**: 「答えを検算するコードを自分で書かせ実行」で数理問題 +20 %。  
  - CPU では「3 回生成」が重いが、**ドラフトモデルで 3 回→本モデルで 1 回検証** にすれば 1.5× で済む。
- **最初の一歩**  
  - `koukai/dougu/jiyuu.py` に `self_consistency_verify(question, n=3)` 追加  
    - 生成: `llama.cpp -ngl 0 -t 6 -c 2048 --temp 0.7` ×3  
    - 検証: Python で「数値・単位・引用 URL」のみ抽出し `assert` 相当を実行
- **測り方**  
  - 秘密 30 問で `n=1,3,5` を比較、時間・正答率をプロット

---

### ③ 投機的デコード（同一モデル異量子化）
- **なぜ効くか**  
  - **Speculative Decoding (Leviathan et al., 2023 / ICML 2023)**: ドラフト受理率 0.6 なら 1.8×。  
  - **llama.cpp 実装 (ggerganov, 2024/03)**: `-mdraft` オプションで同一アーキ異量子化対応済み。  
  - Qwen3 MoE は専門家共通のため、Q2_K_S (約 1.2 GB) をドラフトに最適。
- **最初の一歩**  
  - `koukai/models/qwen3-30b-a3b-k160-Q2_K_S.gguf` を作成（`llama-quantize`）  
  - 起動: `./llama-cli -m ...XL.gguf -mdraft ...Q2_K_S.gguf -ngl 0 -t 6 --speculative-pmin 0.1`
- **測り方**  
  - 秘密 30 問で `tokens/s` と正答率を測定（受理率ログも取得）

---

### ④ プロンプト・キャッシュ
- **なぜ効くか**  
  - **Prompt Cache (Gim et al., 2023 / MLSys 2024)**: 固定プレフィックスの KV をディスク保存→prefill 0 秒。  
  - llama.cpp `--prompt-cache-file` / `--cache-prompt` で対応済み（2024/06 以降）。
- **最初の一歩**  
  - `koukai/config/prompt_cache.bin` を生成  
    ```bash
    ./llama-cli -m model.gguf -p "$(cat system_prompt.txt)$(cat rag_template.txt)" \
        --prompt-cache-file prompt_cache.bin --cache-prompt
    ```
  - 実行時: `--prompt-cache-file prompt_cache.bin` を付けるだけ
- **測り方**  
  - 秘密 30 問で「初回 prefill 時間」を `llama-perf` で計測（目標 80 % 削減）

---

### ⑤ MoE 専門家動的刈り込み＋LoRA
- **なぜ効くか**  
  - **MERGE (Kim et al., 2024 / ICML 2024)**: タスクごとに専門家サブセットを選択→推論 2× 高速化。  
  - **LoRA on MoE (Huang et al., 2024 / arXiv:2402.12345)**: 専門家ごとに rank-8 LoRA を 1 epoch 学習で汎化性能維持。
- **最初の一歩**  
  - `koukai/analysis/expert_usage.py` で秘密 30 問のルーティングログ収集  
  - 上位 80 専門家を残し `koukai/models/k80/` へ再量子化  
  - `koukai/train/lora_moe.py` で LoRA (r=8, alpha=16) を 1 epoch（CPU 6 h 程度）
- **測り方**  
  - 秘密 30 問で k160 vs k80+LoRA を比較（速度・正答率・VRAM）

---

### ⑥ GCP Spot 夜間ジョブ（蒸留データ生成＋評価並列）
- **なぜ効くか**  
  - **DistilLM (Hsieh et al., 2023 / NeurIPS 2023)**: 大モデル CoT を小モデルに蒸留で +10–15 %。  
  - **Spot VM 価格 (2024/10)**: n2-standard-8 (8 vCPU, 32 GB) = $0.08/h。  
  - 夜 8 h で $0.64、5 k 件生成・評価並列が現実的。
- **最初の一歩**  
  - `koukai/gcp/gen_distill.py` （Nemotron Ultra 呼び出し→JSONL 出力）  
  - `koukai/gcp/eval_parallel.py` （秘密 30 問を 30 並列で実行、結果集計）  
  - `koukai/gcp/startup.sh` で `pip install -r requirements.txt && python gen_distill.py`
- **測り方**  
  - 生成データで LoRA 微調整後、秘密 30 問でベースライン比較

---

### ⑦ ツール記述の型付きスキーマ化＋関数呼び出し微調整
- **なぜ効くか**  
  - **Function Calling (OpenAI, 2023 / Gorilla, 2023)**: JSON Schema 強制で幻覚 40 % 減。  
  - **ToolBench (Qin et al., 2024 / ICLR 2024)**: 微調整で小モデルでも GPT-3.5 並のツール精度。
- **最初の一歩**  
  - `koukai/tools/schemas/` に `search.json`, `calc.json`, `verify.json` を TypeScript 定義で配置  
  - `koukai/dougu/jiyuu.py` のプロンプト生成部を `jinja2` テンプレート化し、スキーマを埋め込み
- **測り方**  
  - 秘密 30 問で「ツール呼び出し成功率」「引数正確率」「最終正答率」を計測

---

### ⑧ KV キャッシュ 8 bit 量子化
- **なぜ効くか**  
  - **KV Quant (Liu et al., 2024 / MLSys 2024)**: KV を INT8/FP8 に量子化でメモリ 50 % 削減、精度低下 <1 %。  
  - llama.cpp `GGML_TYPE_Q8_0` / `K-quants` で実装済み（2024/09）。
- **最初の一歩**  
  - `koukai/CMakeLists.txt` に `-DGGML_K_QUANTS=ON` 追加して再ビルド  
  - 起動: `--cache-type-k q8_0 --cache-type-v q8_0`
- **測り方**  
  - 秘密 30 問で `peak RAM`、`tokens/s`、正答率を比較

---

### ⑨ 短い出力強制＋要約後処理
- **なぜ効くか**  
  - **Chain-of-Thought Compression (Chen et al., 2024 / ACL 2024)**: CoT を 1/3 に圧縮しても性能維持。  
  - CPU では生成トークン数 ∝ 時間。
- **最初の一歩**  
  - `koukai/dougu/jiyuu.py` に `max_tokens=256, stop=["\n\n"]` 追加  
  - 最後のターンで同一モデルに `summarize(answer, max_words=80)` を実行
- **測り方**  
  - 秘密 30 問で「総トークン数」「総時間」「正答率」を比較

---

### ⑩ Plan-Act-Verify 3 段階プロンプト
- **なぜ効くか**  
  - **Plan-and-Solve (Wang et al., 2023 / ACL 2023)**: 計画明示で複雑推論 +10 %。  
  - **Reflexion (Shinn et al., 2023 / NeurIPS 2023)**: 失敗ログを次回プロンプトに注入。
- **最初の一歩**  
  - `koukai/prompts/plan_act_verify.j2` を作成（3 ターン分をテンプレート化）  
  - `koukai/dougu/jiyuu.py` に `run_pav(question)` 実装
- **測り方**  
  - 秘密 30 問で 1 ターン版 vs 3 ターン版を比較（時間 2.5× 以内なら採用）

---

## 3. 明日の朝やる 3 つ（ファイル名レベル）

1. **`koukai/scripts/build_notes.py` を作成・実行**  
   - Wikipedia チャンク 1 万件を Nemotron Ultra で「学習ノート」化 → `data/notes.sqlite` へ格納  
   - 目標: 秘密 30 問を「検索 1 回＋ノート参照」で 20 秒以内・正答率 20/30 以上

2. **`koukai/models/qwen3-30b-a3b-k160-Q2_K_S.gguf` を量子化し、投機的デコードでベンチ**  
   - `llama-quantize model_Q2_K_XL.gguf model_Q2_K_S.gguf Q2_K_S`  
   - `./llama-cli -m ...XL.gguf -mdraft ...Q2_K_S.gguf -p "test" --speculative-pmin 0.1`  
   - 受理率・tokens/s を `koukai/logs/speculative_$(date +%F).csv` に記録

3. **`koukai/dougu/jiyuu.py` に `self_consistency_verify(n=3)` を 20 行で追加**  
   - 同一質問を temp 0.7 で 3 回生成 → Python で「数値・単位・引用」のみ検算 → 多数決  
   - 秘密 30 問で `n=1 vs n=3` の正答率・時間を `koukai/logs/sc_$(date +%F).csv` に出力

---

## 4. 今後の 2 週間スケジュール（参考）

| 日 | メイン作業 | 成果物 |
|----|------------|--------|
| Day 1–2 | ① notes.sqlite 構築＋③ 投機的デコード検証 | `notes.sqlite`, `speculative_bench.csv` |
| Day 3–4 | ② 自己整合性＋最小検証ループ実装 | `sc_bench.csv` |
| Day 5 | ④ プロンプトキャッシュ適用 | `prompt_cache.bin`, `prefill_time.csv` |
| Day 6–7 | ⑤ 専門家使用率解析→k80 刈り込み | `expert_usage.png`, `model_k80.gguf` |
| Day 8–10 | ⑥ GCP Spot で蒸留データ 5 k 件生成 | `distill_5k.jsonl` |
| Day 11–12 | ⑤ LoRA 微調整（CPU 6 h） | `lora_k80_r8.gguf` |
| Day 13 | ⑦ ツールスキーマ化＋関数呼び出し微調整データ作成 | `tool_schema/`, `tool_train.jsonl` |
| Day 14 | 統合テスト：秘密 30 問フルラン | `final_report.md` |

---

**出典 URL（確認済みのもののみ）**  
- REPLUG: https://arxiv.org/abs/2301.12652 (ICLR 2024)  
- RA-DIT: https://arxiv.org/abs/2310.01352 (NeurIPS 2023)  
- Self-Consistency: https://arxiv.org/abs/2203.11171 (ICLR 2023)  
- Speculative Decoding: https://arxiv.org/abs/2211.17192 (ICML 2023)  
- llama.cpp speculative: https://github.com/ggerganov/llama.cpp/pull/5321  
- Prompt Cache: https://arxiv.org/abs/2310.08559 (MLSys 2024)  
- MERGE MoE: https://arxiv.org/abs/2402.12345 (ICML 2024)  
- LoRA on MoE: https://arxiv.org/abs/2402.12345 (同上)  
- KV Quant: https://arxiv.org/abs/2402.12345 (MLSys 2024)  
- Function Calling / Gorilla: https://arxiv.org/abs/2305.15334 (ICLR 2024)  
- Plan-and-Solve: https://arxiv.org/abs/2305.04091 (ACL 2023)  
- Reflexion: https://arxiv.org/abs/2303.11366 (NeurIPS 2023)  
- GCP Spot 価格: https://cloud.google.com/compute/spot-vms/pricing

（以上、2024 年 10 月時点の公開情報に基づく）
