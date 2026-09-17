# 歯科医院アシスタント配置スケジューラ（MVP / ダミーデータ版）

1日をA・B・Cの3枠に分け、その日出勤しているドクターに対してアシスタントを自動で割り当てるツールです。
出勤日そのもの（誰がいつ来るか）は Google フォーム等で確定済みという前提で、**「配置」だけ**を担当します。

## 使い方

```bash
python3 assign.py \
  --staff sample_data/staff.csv \
  --schedule sample_data/schedule.csv \
  --requests sample_data/requests.csv \
  --out-csv output/assignment.csv \
  --out-html output/report.html \
  --out-log output/compromise_log.csv
```

引数を省略すると `sample_data/` の同梱ダミーデータと `output/` への出力になります。

## 入力CSV

- `staff.csv`: `staff_id,role,level`（role=doctor/assistant、levelはassistantのみ 1/2/3）
- `schedule.csv`: `date,staff_id,symbol`（出勤する日だけ行を作る。symbolは `〇`=終日, `AB`=B迄で早退, `A`=A迄, `BC`=Bから）
- `requests.csv`: `date,staff_id,type`（typeは現状「休み」のみ。schedule.csvより優先される）

## 条件の優先順位

- Lv3・Lv2（コア要員）: **一貫性（同じドクターに付き続ける）＞ レベル充足（Lv3必須1人＋Lv2できれば1人）＞ 週4日以上配置**
- Lv1（フィラー）: 必須要員には数えず、**週4日以上配置を優先**して余っている枠に詰め込む
- 早退区分（AB/フル）の一致は、上記で候補が並んだときのタイブレークにのみ使用

## 出力

- `output/assignment.csv`: 縦持ちの配置結果（Excelに貼り付け用）
- `output/report.html`: 週間マトリクス・週次配置日数サマリ・妥協ログをまとめたHTML1枚
- `output/compromise_log.csv`: レベル充足や週4日目標を満たせなかった箇所の一覧

## MVPでの割り切り

- 相性・新人教育ペアは考慮しない
- 出勤日自体の決定（誰が何日出勤するか）はこのツールの対象外
- `schedule.csv`のsymbolは `〇/AB/A/BC` のみ対応（実際の手書きシフト表にある `■`・`変`・時刻指定等は、確定済みの出退勤に変換してから入力する前提）
