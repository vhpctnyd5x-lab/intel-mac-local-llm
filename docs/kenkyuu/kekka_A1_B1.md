# A1・B1 の結果（2026-10-05、クラウドのセッション）

## 結論

- **A1・B1 とも、模型での数字はまだ無い。** クラウドの環境から Hugging Face へつなげず（ネットワークの決まりで接続を断られた）、Qwen3-0.6B などの重みと wikitext-2 を取れなかった。
- 代わりに、**測る台本を作り、模型なしで動くことを確かめた**（下の「自己点検」）。Mac の本人側で回せば、そのまま数字が出る。
- 判定: A1 **分からない**、B1 **分からない**（測っていない）。35B（k160）へ持っていく価値も、まだ言えない。

## 作った物（`dougu/kenkyuu/`）

| ファイル | 何をするか |
|---|---|
| `huff.c` | 正準ハフマンの符号化・復号（C、`gcc -O2 -shared -fPIC -o huff.so huff.c`）。文脈なし／「1つ前の記号」文脈（A3）の両方 |
| `a1_jouhouryou.py` | A1/A3。BF16（safetensors か GGUF）をテンソルごとに符号・指数部・仮数部に分け、0次の情報量、指数部ハフマン＋符号と仮数部8ビット（DFloat11 と同じ形）、1つ前の指数部を文脈にした符号（A3）、zstd（そのまま／上下バイトを分けて）を測る。**ハフマンは実際に符号化して復号し、元と一致しなければ止まる** |
| `a1_shiken.py` | A1 台本の自己点検（合成データ） |
| `b1_haibun.py` | B1。候補の型ごとに一様に量子化した版をほどき、imatrix の重みつき誤差 Σ_j a_j Σ_i (W−Ŵ)² をテンソル×型で実測し、平均ビットの上限の下で誤差の合計が最小になるよう型を選ぶ（凸包に沿った貪欲法）。`llama-quantize --tensor-type-file` の表を書く |
| `b1_hakaru.sh` | B1 の流れ全部: imatrix（回ごとに校正文の別の部分）→ 候補の型ごとに量子化 → 割り振り → 混ぜた版 → 一様な版と困惑度を比べる。既定は 2.5 ビット（一様 IQ2_S）と 3.0625 ビット（一様 IQ3_XXS）、2回 |

比べ方の決め事（B1）: 埋め込みと出力はどの版も Q8_0 に固定し、平均ビットは `blk.*` の重みだけで数える。一様な版も `--pure --imatrix` で作る（llama.cpp の既定の混ぜ方は使わない）。

## 自己点検（合成データ。模型の結果ではない）

- A1: 正規分布の乱数（σ=0.02、2²⁰個）を BF16 にした物で、指数部 2.54 ビット・ハフマン込み 10.59 ビット/重み（情報量から 0.05 ビット差）。復号は一致。記号が1種類だけ・極端に偏った場合も復号一致。GGUF と safetensors の読み口で同じ数字。
- B1: 4テンソルの小さな偽の模型で、目標ビットを守り、誤差の大きいテンソルから上の型へ上げることを確かめた（候補は Q4_0・Q5_0・Q8_0。本番の候補の IQ 系は llama-quantize が要るので未確認）。
- llama.cpp（`6c59c40`）を組み立て、`--tensor-type-file`（正規表現）と `--pure` が併用できることをコードで確かめた。`llama-quantize` で本物の模型を作る所は**まだ動かしていない**。

## 本人に頼むこと（Mac、i7-9750H）

何を・どこで・何時間（時間は見込み。測っていない）:

1. 準備（10分）: `pip install numpy zstandard` と llama.cpp の `gguf-py`。Qwen3-0.6B を取り、`convert_hf_to_gguf.py --outtype bf16` で BF16 の GGUF。`llama.cpp/scripts/get-wikitext-2.sh` で wikitext-2（校正は wiki.train.raw、評価は wiki.test.raw。重ならない）。
2. A1（10〜20分の見込み）:
   ```bash
   cd dougu/kenkyuu && gcc -O2 -shared -fPIC -o huff.so huff.c && python3 a1_shiken.py
   python3 a1_jouhouryou.py ~/models/Qwen3-0.6B/model.safetensors --out a1.tsv
   ```
   出た表をこの紙に貼る。比べる先: DFloat11 の報告は元の約70%。
3. B1（1〜2時間の見込み。まず `RUNS=1 CHUNKS=10` で1本を完走させてから）:
   ```bash
   LLAMA=~/llama.cpp/build/bin SRC=qwen3-0.6b-bf16.gguf CALIB=wikitext-2-raw/wiki.train.raw \
   EVAL=wikitext-2-raw/wiki.test.raw OUT=~/b1_out THREADS=6 bash dougu/kenkyuu/b1_hakaru.sh
   ```
   `~/b1_out/b1.tsv` と `haibun-*.txt`（どの型が何個）を貼る。生成物（GGUF）は commit しない。

## 判定の決め方（測った後）

- A1: 指数部ハフマンで BF16 の何%になるか。A3（文脈）が0次よりどれだけ下がるか。0.1 ビット/重み未満なら「効かない」。
- B1: 2回とも、混ぜた版の困惑度が一様な版より低ければ「効いた」。回で向きが変わるなら「分からない」。困惑度は同じ文では決定的なので、2回は「校正文を変えた imatrix」の2回。

## 35B（k160）について（まだ推測）

- A1 は**量子化前**の話なので、Q2 の GGUF には直接は効かない（量子化後の記号はほぼ均一、`bit_yori_shita.md` の 3.）。効くとしたら、BF16 から自前で量子化し直す道か、B1 と組む道。
- B1 は k160 と同じ「imatrix の使われ方」で決める延長。0.6B で効いたら、次は専門家単位（よく呼ばれる専門家は IQ2、まれな専門家は IQ1_M）に広げる。

## 次

1. 本人側で A1・B1 を回して数字を入れる（上の 2・3）。
2. クラウドで続けるなら、環境のネットワーク設定で `huggingface.co`（と重みの置き場の `cdn-lfs*.huggingface.co` 等）を許す。
3. 数字が出たら A2（偏りを残す量子化）と、B1 の専門家単位版へ。
