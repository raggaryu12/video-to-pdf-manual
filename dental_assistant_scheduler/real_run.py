"""
実データ（横持ちの月間カレンダーCSV）を読み込んで assign.py のロジックで
配置を行う実行スクリプト。2026年10月のダミーではない実データ用。

入力CSVの前提（提供されたファイルに合わせた決め打ち）:
- 1行目: タイトル行（無視）
- 2行目: ヘッダー（日付, 曜日, ドクター17名, スタッフ33名, A/B/C枠計3列）
- 3行目以降: 日別の出退勤記号

レベル・除外の扱い:
- レベル(1/2/3)と、レベル未確定で対象外とするスタッフは real_data/roster.json
  の levels に null で表現する（levelがnullの人は自動的に除外される）
- レベル表にない新しいスタッフを暫定レベルで含める場合も roster.json 側で対応し、
  このスクリプトやコミット物に実名の注記を書かない

スタッフの実名一覧・レベル・除外設定は real_data/roster.json（.gitignore対象、
コミットしない）にまとめ、このスクリプト自体には実名を書かない。
"""
import csv
import json
import sys
from collections import defaultdict

import assign

ROSTER_PATH = "real_data/roster.json"


def load_roster(path=ROSTER_PATH):
    with open(path, encoding="utf-8") as f:
        roster = json.load(f)
    return roster["doctors"], roster["staff"], roster["levels"]


def build_id_maps(doctor_names, staff_names, level):
    """記号IDへの変換表を作る（コミット物には実名を含めないため）"""
    excluded = {name for name, lv in level.items() if lv is None}
    name_to_id = {}
    id_to_name = {}

    for i, name in enumerate(doctor_names, start=1):
        sid = f"D{i:02d}"
        name_to_id[("doctor", name)] = sid
        id_to_name[sid] = name

    counters = {3: 0, 2: 0, 1: 0}
    for name in staff_names:
        if name in excluded:
            continue
        lv = level[name]
        counters[lv] += 1
        sid = f"L{lv}-{counters[lv]:02d}"
        name_to_id[("staff", name)] = sid
        id_to_name[sid] = name

    return name_to_id, id_to_name, excluded


def write_name_mapping(path, id_to_name):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["id", "name"])
        for sid, name in sorted(id_to_name.items()):
            writer.writerow([sid, name])


def normalize_symbol(raw):
    """記号を(A,B,Cの出席枠, 要確認フラグ)に変換する。空欄/×は欠勤。"""
    v = raw.strip()
    if v in ("", "×"):
        return None, False
    if v in ("研修", "旅行", "変", "■"):
        return None, True
    if v == "〇":
        return ("A", "B", "C"), False
    if v == "AB":
        return ("A", "B"), False
    if v == "A":
        return ("A",), False
    if v == "BC":
        return ("B", "C"), False
    if v == "B":
        return ("B",), True
    if v.startswith("-") and v[1:].isdigit():
        return ("A", "B", "C"), True
    if v.endswith("-") and v[:-1].isdigit():
        return ("B", "C"), True
    # 指/全/鎮/特/A20/●/BC付き数字など、未知の記号は「出勤扱い(終日)」で暫定処理
    return ("A", "B", "C"), True


def parse_date(md_str):
    month, day = (int(x) for x in md_str.split("/"))
    year = 2026
    return f"{year:04d}-{month:02d}-{day:02d}"


def load_wide_csv(path, roster_path=ROSTER_PATH):
    doctor_names, staff_names, level = load_roster(roster_path)
    name_to_id, id_to_name, excluded = build_id_maps(doctor_names, staff_names, level)

    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))

    header = rows[1]
    doctor_start = 2
    staff_start = doctor_start + len(doctor_names)
    assert header[doctor_start:doctor_start + len(doctor_names)] == doctor_names, (
        "ドクター列の並びが想定と違います: " + str(header[doctor_start:doctor_start + len(doctor_names)])
    )
    assert header[staff_start:staff_start + len(staff_names)] == staff_names, (
        "スタッフ列の並びが想定と違います: " + str(header[staff_start:staff_start + len(staff_names)])
    )

    staff = {}
    for name in doctor_names:
        staff[name_to_id[("doctor", name)]] = {"role": "doctor", "level": None}
    for name in staff_names:
        if name in excluded:
            continue
        staff[name_to_id[("staff", name)]] = {"role": "assistant", "level": level[name]}

    attendance = {}
    symbol_log = defaultdict(lambda: {"count": 0, "example": None})

    for row in rows[2:]:
        if not row or not row[0].strip():
            continue
        date_str = parse_date(row[0].strip())

        for i, name in enumerate(doctor_names):
            sid = name_to_id[("doctor", name)]
            raw = row[doctor_start + i]
            slots, flagged = normalize_symbol(raw)
            if flagged:
                key = raw.strip() or "(空欄)"
                symbol_log[key]["count"] += 1
                if symbol_log[key]["example"] is None:
                    symbol_log[key]["example"] = f"{date_str} {sid}"
            if slots:
                attendance[(date_str, sid)] = set(slots)

        for i, name in enumerate(staff_names):
            if name in excluded:
                continue
            sid = name_to_id[("staff", name)]
            raw = row[staff_start + i]
            slots, flagged = normalize_symbol(raw)
            if flagged:
                key = raw.strip() or "(空欄)"
                symbol_log[key]["count"] += 1
                if symbol_log[key]["example"] is None:
                    symbol_log[key]["example"] = f"{date_str} {sid}"
            if slots:
                attendance[(date_str, sid)] = set(slots)

    return staff, attendance, symbol_log, id_to_name, excluded


def write_named_versions(out_dir, suffix, dates, doctor_ids, assignments, compromise_log,
                          weekly_count, staff, id_to_name, report_title):
    """実名版のCSV/HTMLを出力する(.gitignore対象。リポジトリにはコミットしない)"""

    def nm(x):
        return id_to_name.get(x, x)

    doctor_ids_named = [nm(d) for d in doctor_ids]
    staff_named = {nm(k): v for k, v in staff.items()}
    assignments_named = [
        {**a, "doctor_id": nm(a["doctor_id"]), "assistant_id": nm(a["assistant_id"])}
        for a in assignments
    ]
    weekly_count_named = {(nm(aid), w): c for (aid, w), c in weekly_count.items()}

    ids_sorted = sorted(id_to_name.keys(), key=len, reverse=True)
    compromise_log_named = []
    for row in compromise_log:
        new_row = dict(row)
        new_row["doctor_id"] = nm(row["doctor_id"])
        detail = row["detail"]
        for _id in ids_sorted:
            if _id in detail:
                detail = detail.replace(_id, id_to_name[_id])
        new_row["detail"] = detail
        compromise_log_named.append(new_row)

    with open(f"{out_dir}/assignment_{suffix}_実名版.csv", "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "youbi", "doctor_id", "assistant_id", "level", "note", "filler"])
        for row in sorted(assignments_named, key=lambda r: (r["date"], r["doctor_id"], r["level"])):
            writer.writerow([
                row["date"], assign.weekday_jp(row["date"]), row["doctor_id"],
                row["assistant_id"], row["level"], row["note"], row["filler"],
            ])

    assign.write_html_report(
        f"{out_dir}/report_{suffix}_実名版.html",
        dates, doctor_ids_named, assignments_named, compromise_log_named,
        weekly_count_named, staff_named, report_title=report_title,
    )


def write_symbol_log(path, symbol_log):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["symbol", "count", "example", "interpreted_as"])
        for symbol, info in sorted(symbol_log.items(), key=lambda kv: -kv[1]["count"]):
            slots, _ = normalize_symbol(symbol if symbol != "(空欄)" else "")
            interpreted = "".join(slots) if slots else "欠勤扱い"
            writer.writerow([symbol, info["count"], info["example"], interpreted])


def main():
    in_path = sys.argv[1] if len(sys.argv) > 1 else "real_data/2026-10_schedule_wide.csv"
    out_dir = "real_data/output"

    staff, attendance, symbol_log, id_to_name, excluded = load_wide_csv(in_path)

    dates, doctor_ids, assignments, compromise_log, weekly_count = assign.run_assignment(
        staff, attendance
    )

    # コミット/共有してよいのは記号IDのみを含むこれらのファイル
    assign.write_assignment_csv(f"{out_dir}/assignment_202610.csv", assignments)
    assign.write_compromise_log(f"{out_dir}/compromise_log_202610.csv", compromise_log)
    assign.write_html_report(
        f"{out_dir}/report_202610.html", dates, doctor_ids, assignments,
        compromise_log, weekly_count, staff,
        report_title="2026年10月 アシスタント配置表（実データ試行・記号ID表記）",
    )
    write_symbol_log(f"{out_dir}/symbol_log_202610.csv", symbol_log)

    # 実名対応表・実名版CSV/HTML: リポジトリにはコミットしない前提の別ファイル
    write_name_mapping(f"{out_dir}/name_mapping_202610.csv", id_to_name)
    write_named_versions(
        out_dir, "202610", dates, doctor_ids, assignments, compromise_log,
        weekly_count, staff, id_to_name,
        report_title="2026年10月 アシスタント配置表（実名版）",
    )

    print(f"対象日数: {len(dates)}")
    print(f"配置件数: {len(assignments)}")
    print(f"妥協ログ件数: {len(compromise_log)}")
    print(f"要確認だった記号の種類: {len(symbol_log)}")
    print(f"除外したスタッフ数: {len(excluded)}（氏名は real_data/roster.json を参照）")


if __name__ == "__main__":
    main()
