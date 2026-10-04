# Spot VM 試験

Macを閉じても CPU 試験を続け、状態・結果を非公開GCSへ残す。`kernel/` は使わない。

```sh
python3 gcloud/shiken/tamesu.py test
bash gcloud/shiken/hajimeru.sh --mondai dougu/kekka/himitsu/jiyuu_himitsu.jsonl \
  --opts '{"raw_template": true}' \
  --args 'KOUKAI_VOCAB_KEEP=vocab_keep_9999_q36_ids.txt --spec-type none -cram 512'
```

起動後に表示される `mimamoru.sh` を別端末で実行する。別条件は別々に `hajimeru.sh` を起動し、それぞれの見張りコマンドを走らせる。環境変数は `--env KERNEL_NAME=value` を繰り返す。`--opts` は `KERNEL_JIYUU_OPTS` のJSON object。

既定は `c3-standard-8` Spot、Debian 12、最大4時間、100GB自動削除ディスク。`MACHINE_TYPE=n2-standard-8` で変更可能。模型は `gs://$BUCKET/models/Qwen3.6-35B-A3B-UD-Q2_K_XL-k160.gguf`、既定BUCKETは chishiki と同じ `${PROJECT}-chishiki`。llama.cpp `src` と `dougu/jikken/vocab_keep_9999_q36_ids.txt` を転送し、VMでCPUビルドする。

予定費用（us-central1概算、料金は変動）: Spot VM 約 $0.20〜0.35/h (c3) または $0.10〜0.18/h (n2)、100GB標準ディスク約 $0.0055/h、外部IPv4約 $0.005/h。最大4時間なら VM等は概ね $0.45〜1.45。GCS保管・模型/問題の転送費は別。最新価格は [Compute Engine料金表](https://cloud.google.com/products/compute/pricing) と [Spot料金](https://cloud.google.com/spot-vms/pricing) を参照。Spot単価は毎日変わり得る。

問題本文は起動時に非公開バケットへアップロードし、ログには出さない。VM内のMarkdown詳細レポートはアップロードせず、GCS `result.json` は `pass`, `total`, 各問 `id/status/seconds` のみ。状態と一般ログは10分ごとに写す。VMの実行専用SAには一時的なバケット権限と、自己削除だけの期限付きCompute roleを付け、見張り完了後に除去する。複数条件は別VM・別prefix。

未確認: Cloud上でのSpot空き状況、CPUビルド/試験の所要時間、実料金、実バケットの既存IAM/リージョン。Cloudコマンドはまだ実行していない。
