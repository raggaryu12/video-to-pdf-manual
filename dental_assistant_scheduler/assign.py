"""
歯科医院アシスタント配置の自動割当てスクリプト（ダミーデータ版 / MVP）

前提:
- 出勤日そのもの（誰がいつ来るか）は Google フォーム等で確定済みとし、
  schedule.csv には最終的に出勤する日の行だけが入っている。
- このスクリプトが決めるのは「出勤している日に、どのドクターに誰を配置するか」だけ。

条件の優先順位（設計で合意した内容をそのままロジックに反映）:
  Lv3・Lv2（コア要員）: S1(一貫性) > S3(レベル充足) > S5(週4日以上配置)
  Lv1（フィラー）      : S5(週4日以上配置) を最優先で空き枠に詰め込む
  S2(早退区分の一致)   : 上記で複数候補が並んだ場合のタイブレークにのみ使う

チーム編成:
  各ドクター・各日で Lv3 を1人以上、できれば Lv2 も1人。Lv1 は必須要員に数えない。
"""
import argparse
import csv
import html
from collections import defaultdict

SYMBOL_SLOTS = {
    "〇": ("A", "B", "C"),
    "AB": ("A", "B"),
    "A": ("A",),
    "BC": ("B", "C"),
}

WEEKDAY_JP = ["月", "火", "水", "木", "金", "土", "日"]
WEEKLY_TARGET_DAYS = 4

LEVEL_LABEL = {3: "Lv3", 2: "Lv2", 1: "Lv1"}
LEVEL_COLOR = {3: "#dcefe3", 2: "#dde7f7", 1: "#f2f2f2"}


def load_staff(path):
    staff = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            staff[row["staff_id"]] = {
                "role": row["role"],
                "level": int(row["level"]) if row["level"] else None,
            }
    return staff


def load_schedule(path):
    attendance = {}
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            symbol = row["symbol"].strip()
            if symbol not in SYMBOL_SLOTS:
                raise ValueError(
                    f"未対応の記号です: '{symbol}' ({row['date']} {row['staff_id']})。"
                    f"対応記号: {list(SYMBOL_SLOTS)}"
                )
            attendance[(row["date"], row["staff_id"])] = set(SYMBOL_SLOTS[symbol])
    return attendance


def apply_requests(attendance, path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            if row["type"] == "休み":
                attendance.pop((row["date"], row["staff_id"]), None)
    return attendance


def slots_cover(assistant_slots, doctor_slots):
    """アシスタントの出勤枠がドクターの出勤枠を全てカバーしているか"""
    return doctor_slots.issubset(assistant_slots)


def weekday_jp(date_str):
    from datetime import date

    y, m, d = (int(x) for x in date_str.split("-"))
    return WEEKDAY_JP[date(y, m, d).weekday()]


def pick_candidate(pool, doctor_id, doctor_slots, date, attendance, used_today,
                    weekly_count, preferred_map):
    """S1(継続)を最優先で試し、崩れる場合はS3充足優先・S2をタイブレークに新規選定する"""
    pref = preferred_map.get(doctor_id)
    if pref and pref not in used_today:
        pref_slots = attendance.get((date, pref))
        if pref_slots and slots_cover(pref_slots, doctor_slots):
            return pref, "継続"

    doctor_leaves_early = "C" not in doctor_slots
    candidates = []
    for aid in pool:
        if aid in used_today:
            continue
        a_slots = attendance.get((date, aid))
        if not a_slots or not slots_cover(a_slots, doctor_slots):
            continue
        a_leaves_early = "C" not in a_slots
        # タイブレーク優先順: 早退区分が一致(S2) → 週内の配置回数が少ない人を優先(S5への配慮)
        candidates.append((a_leaves_early != doctor_leaves_early, weekly_count[aid], aid))
    if not candidates:
        return None, None

    candidates.sort(key=lambda t: (t[0], t[1]))
    chosen = candidates[0][2]
    note = "新規" if pref is None else "変更"
    preferred_map[doctor_id] = chosen
    return chosen, note


def run_assignment(staff, attendance):
    dates = sorted({d for (d, _sid) in attendance})
    doctor_ids = sorted(sid for sid, info in staff.items() if info["role"] == "doctor")
    lv3_ids = sorted(sid for sid, info in staff.items() if info["level"] == 3)
    lv2_ids = sorted(sid for sid, info in staff.items() if info["level"] == 2)
    lv1_ids = sorted(sid for sid, info in staff.items() if info["level"] == 1)

    preferred_lv3 = {}
    preferred_lv2 = {}
    weekly_count = defaultdict(int)
    assignments = []
    compromise_log = []

    for date in dates:
        used_today = set()
        team_size_today = defaultdict(int)
        day_doctors = [d for d in doctor_ids if (date, d) in attendance]

        for doctor_id in day_doctors:
            doctor_slots = attendance[(date, doctor_id)]

            lv3_pick, lv3_note = pick_candidate(
                lv3_ids, doctor_id, doctor_slots, date, attendance,
                used_today, weekly_count, preferred_lv3,
            )
            if lv3_pick:
                used_today.add(lv3_pick)
                weekly_count[lv3_pick] += 1
                team_size_today[doctor_id] += 1
                assignments.append(dict(date=date, doctor_id=doctor_id, assistant_id=lv3_pick,
                                         level=3, note=lv3_note, filler="no"))
            else:
                compromise_log.append(dict(
                    date=date, doctor_id=doctor_id, issue="Lv3不足",
                    detail="条件(出勤枠が一致)を満たすLv3アシスタントがいません",
                ))

            lv2_pick, lv2_note = pick_candidate(
                lv2_ids, doctor_id, doctor_slots, date, attendance,
                used_today, weekly_count, preferred_lv2,
            )
            if lv2_pick:
                used_today.add(lv2_pick)
                weekly_count[lv2_pick] += 1
                team_size_today[doctor_id] += 1
                assignments.append(dict(date=date, doctor_id=doctor_id, assistant_id=lv2_pick,
                                         level=2, note=lv2_note, filler="no"))
            else:
                compromise_log.append(dict(
                    date=date, doctor_id=doctor_id, issue="Lv2不在",
                    detail="条件を満たすLv2アシスタントがおらず、Lv3のみで対応しています",
                ))

        # Lv1はフィラー: 週4日未達の人を優先して空いているドクターに詰め込む(S5優先)
        lv1_today = [a for a in lv1_ids if (date, a) in attendance and a not in used_today]
        for aid in sorted(lv1_today, key=lambda a: weekly_count[a]):
            if weekly_count[aid] >= WEEKLY_TARGET_DAYS:
                continue
            a_slots = attendance[(date, aid)]
            eligible = [d for d in day_doctors if slots_cover(a_slots, attendance[(date, d)])]
            if not eligible:
                continue
            target_doctor = min(eligible, key=lambda d: team_size_today[d])
            used_today.add(aid)
            weekly_count[aid] += 1
            team_size_today[target_doctor] += 1
            assignments.append(dict(date=date, doctor_id=target_doctor, assistant_id=aid,
                                     level=1, note="フィラー", filler="yes"))

    # 週次サマリ: 出勤しているのに週4日の配置に届かなかった人を記録(S5未達ログ)
    for aid in lv3_ids + lv2_ids + lv1_ids:
        working_days = sum(1 for d in dates if (d, aid) in attendance)
        if working_days >= WEEKLY_TARGET_DAYS and weekly_count[aid] < WEEKLY_TARGET_DAYS:
            compromise_log.append(dict(
                date="(週間)", doctor_id="-", issue="週4日未達",
                detail=f"{aid} は出勤{working_days}日に対し、配置は{weekly_count[aid]}日でした",
            ))

    return dates, doctor_ids, assignments, compromise_log, weekly_count


def write_assignment_csv(path, assignments):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "youbi", "doctor_id", "assistant_id", "level", "note", "filler"])
        for row in sorted(assignments, key=lambda r: (r["date"], r["doctor_id"], r["level"])):
            writer.writerow([
                row["date"], weekday_jp(row["date"]), row["doctor_id"],
                row["assistant_id"], row["level"], row["note"], row["filler"],
            ])


def write_compromise_log(path, compromise_log):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "doctor_id", "issue", "detail"])
        for row in compromise_log:
            writer.writerow([row["date"], row["doctor_id"], row["issue"], row["detail"]])


def write_html_report(path, dates, doctor_ids, assignments, compromise_log, weekly_count, staff):
    by_date_doctor = defaultdict(list)
    for row in assignments:
        by_date_doctor[(row["date"], row["doctor_id"])].append(row)

    def cell_html(date, doctor_id):
        rows = sorted(by_date_doctor.get((date, doctor_id), []), key=lambda r: r["level"])
        if not rows:
            return "<span class='empty'>―</span>"
        parts = []
        for r in rows:
            badge = "F" if r["filler"] == "yes" else r["note"]
            parts.append(
                f"<span class='chip' style='background:{LEVEL_COLOR[r['level']]}'>"
                f"{html.escape(r['assistant_id'])}"
                f"<small>{LEVEL_LABEL[r['level']]}/{html.escape(badge)}</small></span>"
            )
        return "".join(parts)

    table_rows = []
    for date in dates:
        cells = "".join(
            f"<td>{cell_html(date, d)}</td>" for d in doctor_ids
        )
        table_rows.append(f"<tr><th>{html.escape(date)}({weekday_jp(date)})</th>{cells}</tr>")

    header_cells = "".join(f"<th>{html.escape(d)}</th>" for d in doctor_ids)

    summary_rows = []
    for aid in sorted(weekly_count):
        level = staff[aid]["level"]
        summary_rows.append(
            f"<tr><td>{html.escape(aid)}</td><td>{LEVEL_LABEL[level]}</td>"
            f"<td>{weekly_count[aid]}</td></tr>"
        )

    log_rows = "".join(
        f"<tr><td>{html.escape(str(r['date']))}</td><td>{html.escape(str(r['doctor_id']))}</td>"
        f"<td>{html.escape(r['issue'])}</td><td>{html.escape(r['detail'])}</td></tr>"
        for r in compromise_log
    ) or "<tr><td colspan='4'>妥協した条件はありませんでした</td></tr>"

    doc = f"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>週間アシスタント配置表</title>
<style>
  body {{ font-family: "Hiragino Sans", "Yu Gothic", sans-serif; margin: 24px; color: #222; }}
  h1 {{ font-size: 20px; }}
  h2 {{ font-size: 16px; margin-top: 32px; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 12px; }}
  th, td {{ border: 1px solid #ccc; padding: 6px 8px; font-size: 13px; text-align: left; vertical-align: top; }}
  th {{ background: #f5f5f5; }}
  .chip {{ display: inline-block; padding: 2px 6px; border-radius: 4px; margin: 2px; }}
  .chip small {{ display: block; font-size: 10px; color: #555; }}
  .empty {{ color: #aaa; }}
  .note {{ color: #666; font-size: 12px; }}
</style>
</head>
<body>
  <h1>週間アシスタント配置表（ダミーデータ）</h1>
  <p class="note">凡例: チップ内の下段は「レベル / 継続・変更・新規・フィラー(F)」を示します。</p>
  <table>
    <tr><th>日付</th>{header_cells}</tr>
    {''.join(table_rows)}
  </table>

  <h2>週間の配置日数サマリ（目標: 週{WEEKLY_TARGET_DAYS}日以上）</h2>
  <table>
    <tr><th>アシスタントID</th><th>レベル</th><th>配置日数</th></tr>
    {''.join(summary_rows)}
  </table>

  <h2>妥協ログ（条件を満たせなかった箇所）</h2>
  <table>
    <tr><th>日付</th><th>ドクター</th><th>内容</th><th>詳細</th></tr>
    {log_rows}
  </table>
</body>
</html>
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    parser = argparse.ArgumentParser(description="歯科医院アシスタント配置の自動割当て(MVP)")
    parser.add_argument("--staff", default="sample_data/staff.csv")
    parser.add_argument("--schedule", default="sample_data/schedule.csv")
    parser.add_argument("--requests", default="sample_data/requests.csv")
    parser.add_argument("--out-csv", default="output/assignment.csv")
    parser.add_argument("--out-html", default="output/report.html")
    parser.add_argument("--out-log", default="output/compromise_log.csv")
    args = parser.parse_args()

    staff = load_staff(args.staff)
    attendance = load_schedule(args.schedule)
    attendance = apply_requests(attendance, args.requests)

    dates, doctor_ids, assignments, compromise_log, weekly_count = run_assignment(staff, attendance)

    write_assignment_csv(args.out_csv, assignments)
    write_compromise_log(args.out_log, compromise_log)
    write_html_report(args.out_html, dates, doctor_ids, assignments, compromise_log, weekly_count, staff)

    print(f"配置件数: {len(assignments)}")
    print(f"妥協ログ件数: {len(compromise_log)}")
    print(f"出力: {args.out_csv}, {args.out_html}, {args.out_log}")


if __name__ == "__main__":
    main()
