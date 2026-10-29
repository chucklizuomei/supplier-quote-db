#!/usr/bin/env python3
"""
供应商报价数据库 —— 批量零件号查价。

用法：
  # 直接给零件号（可带品牌前缀 BRAND:PN）
  python query_parts.py 320-3060 227-4531 CAT:7C3039

  # 从文本文件读（每行一个零件号，或 "零件号  名称  数量"）
  python query_parts.py --file parts.txt

  # 从 Excel 读（自动找零件号列，可选机型/数量列）
  python query_parts.py --xlsx inquiry.xlsx --sheet Caterpillar --out result.xlsx

  # 指定品牌缩小范围 / 指定数据库
  python query_parts.py --brand PERKINS --db /path/to/supplier_db.sqlite 576/218 SE2H

匹配顺序（逐级兜底，避免格式差异漏判）：
  1. 清洗号匹配（去非字母数字、转大写）part_number / part_number_fmt
  2. 原始写法匹配（保留横杠/斜杠）
  3. 指定品牌下匹配
  4. 模糊 LIKE 兜底
  5. part_alternates 反查（该号作为通用号挂在哪个主件下）
"""
import argparse
import os
import re
import sqlite3
import sys

DEFAULT_DB = os.path.expanduser("~/.openclaw/workspace/supplier_db/supplier_db.sqlite")


def clean(v):
    """零件号清洗规则：只保留字母和数字，转大写。"""
    return re.sub(r"[^A-Za-z0-9]", "", str(v)).upper()


def num(p):
    m = re.search(r"[\d.]+", str(p))
    return float(m.group()) if m else None


def strip_price(p):
    return str(p).strip("[]")


class Finder:
    def __init__(self, db, brand=None):
        self.c = sqlite3.connect(db)
        self.brand = brand.upper() if brand else None

    def find(self, raw):
        """返回 dict(pid, brand, part_number, name_en, name_cn, models, quotes[], alt_of[])"""
        cl, ru = clean(raw), str(raw).upper()
        sql = """
            SELECT p.id, b.name, p.part_number, p.part_number_fmt, p.name_en, p.name_cn, p.models,
                   ps.quality, s.name, ps.price
            FROM parts p
            JOIN brands b ON b.id = p.brand_id
            LEFT JOIN part_suppliers ps ON ps.part_id = p.id
            LEFT JOIN suppliers s ON s.id = ps.supplier_id
            WHERE {cond}
        """
        rows = self.c.execute(
            sql.format(cond="p.part_number=? OR p.part_number_fmt=?"), (cl, cl)
        ).fetchall()
        if not rows:
            rows = self.c.execute(
                sql.format(cond="p.part_number=? OR p.part_number_fmt=?"), (ru, ru)
            ).fetchall()
        if not rows and self.brand:
            rows = self.c.execute(
                sql.format(
                    cond="b.name=? AND (p.part_number=? OR p.part_number_fmt=?)"
                ),
                (self.brand, cl, cl),
            ).fetchall()
        if not rows:
            rows = self.c.execute(
                sql.format(cond="p.part_number LIKE ? OR p.part_number_fmt LIKE ?"),
                ("%" + cl + "%", "%" + cl + "%"),
            ).fetchall()
        if not rows:
            return None

        pid = rows[0][0]
        quotes = sorted(
            [(r[7] or "", r[8], num(r[9]), strip_price(r[9])) for r in rows if r[8]],
            key=lambda x: (x[2] is None, x[2]),
        )
        alt_of = self.c.execute(
            """SELECT b.name, p.part_number, p.name_en FROM part_alternates pa
               JOIN parts p ON p.id = pa.part_id JOIN brands b ON b.id = p.brand_id
               WHERE pa.alt_part_number=? OR pa.alt_part_number=?""",
            (cl, ru),
        ).fetchall()
        return {
            "pid": pid,
            "brand": rows[0][1],
            "part_number": rows[0][2],
            "name_en": rows[0][4] or "",
            "name_cn": rows[0][5] or "",
            "models": rows[0][6] or "",
            "quotes": quotes,
            "alt_of": alt_of,
        }


def read_txt(path):
    """每行：零件号 [名称] [数量]（空格或制表符分隔）"""
    items = []
    for line in open(path, encoding="utf-8"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\t+|\s{2,}|\s+", line)
        items.append((parts[0], parts[1] if len(parts) > 1 else "", _qty(parts)))
    return items


def _qty(parts):
    for p in parts[2:]:
        m = re.search(r"^(\d+)\s*(pcs|PCS)?$", p)
        if m:
            return int(m.group(1))
    return None


def read_xlsx(path, sheet=None, brand=None):
    import openpyxl

    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet] if sheet else wb[wb.sheetnames[0]]
    items = []
    for row in ws.iter_rows(values_only=True):
        cells = [("" if v is None else str(v).strip()) for v in row]
        pn = next((c for c in cells if c and re.search(r"[A-Za-z0-9]", c)
                   and re.fullmatch(r"[A-Za-z0-9\-/\.]{3,}", c)), None)
        if not pn:
            continue
        qty = next((int(m.group(1)) for c in cells
                    if (m := re.fullmatch(r"(\d{1,4})", c))), None)
        name = max(cells, key=len) if len(max(cells, key=len)) > len(pn) else ""
        items.append((pn, name, qty))
    return items


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("parts", nargs="*", help="零件号，可写 BRAND:PARTNO")
    ap.add_argument("--file", help="文本文件，每行一个零件号")
    ap.add_argument("--xlsx", help="Excel 询价文件")
    ap.add_argument("--sheet")
    ap.add_argument("--brand", help="限定品牌（英文全大写）")
    ap.add_argument("--db", default=os.environ.get("SUPPLIER_DB", DEFAULT_DB))
    ap.add_argument("--out", help="输出 xlsx 结果文件")
    ap.add_argument("--all", action="store_true", help="列出全部报价而非仅最低价")
    args = ap.parse_args()

    if args.parts:
        items = []
        for p in args.parts:
            if ":" in p and not re.match(r"^\d", p):
                b, pn = p.split(":", 1)
                items.append((pn, "", None, b))
            else:
                items.append((p, "", None, None))
    elif args.file:
        items = [(a, b, c, None) for a, b, c in read_txt(args.file)]
    elif args.xlsx:
        items = [(a, b, c, None) for a, b, c in read_xlsx(args.xlsx, args.sheet)]
    else:
        ap.error("需要提供零件号、--file 或 --xlsx")
        return

    if not os.path.exists(args.db):
        sys.exit("数据库不存在: %s（用 --db 指定路径或设置 SUPPLIER_DB 环境变量）" % args.db)

    f = Finder(args.db)
    results, hit, miss = [], 0, 0
    for pn, desc, qty, brand in items:
        r = f.find(pn) if not brand else Finder(args.db, brand).find(pn)
        if r:
            hit += 1
        else:
            miss += 1
        results.append((pn, desc, qty, r))
        print("=" * 60)
        print(f"{pn}  {desc}  数量:{qty if qty else '-'}")
        if not r:
            print("  ❌ 库中无此件")
            continue
        print(f"  库内 [{r['brand']}] {r['part_number']} | {r['name_en']} / {r['name_cn']} | 机型:{r['models'] or '-'}")
        if not r["quotes"]:
            print("  （有零件记录但无报价）")
        for q in r["quotes"] if args.all else r["quotes"][:1]:
            print(f"    {q[0] or '(未标质量)'} | {q[1]} | {q[3]}")
        if not args.all and len(r["quotes"]) > 1:
            print("    其他报价: " + "; ".join(f"{x[1]} {x[0]} {x[3]}" for x in r["quotes"][1:]))
        for a in r["alt_of"]:
            print(f"    ↳ 该号作为通用号挂于主件 {a[1]}({a[0]})")
    print("=" * 60)
    print(f"命中 {hit} / 未命中 {miss} / 共 {len(items)}")

    if args.out:
        _write_xlsx(args.out, results)
        print("结果已写入:", args.out)


def _write_xlsx(path, results):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter

    headers = ["零件号", "描述", "数量", "品牌", "库内零件号", "库内名称", "机型",
               "匹配单价", "合计", "建议供应商", "质量等级", "其他可选报价", "状态"]
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "价格匹配"
    ws.append(headers)
    thin = Side(style="thin", color="BFBFBF")
    bd = Border(left=thin, right=thin, top=thin, bottom=thin)
    hfill = PatternFill("solid", fgColor="DDEBF7")
    miss_fill = PatternFill("solid", fgColor="FCE4E4")
    for i in range(1, len(headers) + 1):
        c = ws.cell(1, i)
        c.font = Font(bold=True, size=10)
        c.fill = hfill
        c.border = bd
        c.alignment = Alignment(horizontal="center", wrap_text=True)
    total = 0.0
    for pn, desc, qty, r in results:
        if not r or not r["quotes"]:
            ws.append([pn, desc, qty, "", "", "", "", None, None, "", "", "",
                       "库中无此件" if not r else "无报价"])
            for i in range(1, len(headers) + 1):
                ws.cell(ws.max_row, i).fill = miss_fill
            continue
        q0 = r["quotes"][0]
        sub = round(q0[2] * qty, 2) if (q0[2] and qty) else None
        if sub:
            total += sub
        others = "; ".join(f"{x[1]} {x[0]} {x[3]}" for x in r["quotes"][1:])
        ws.append([pn, desc, qty, r["brand"], r["part_number"],
                   f"{r['name_en']} / {r['name_cn']}".strip(" /"), r["models"],
                   q0[2], sub, q0[1], q0[0], others, "已匹配"])
        ws.cell(ws.max_row, 8).number_format = "0.00"
        ws.cell(ws.max_row, 9).number_format = "0.00"
    ws.append(["合计", "", "", "", "", "", "", None, round(total, 2), "", "", "", ""])
    for i in range(1, len(headers) + 1):
        c = ws.cell(ws.max_row, i)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="FFF2CC")
    ws.cell(ws.max_row, 9).number_format = "0.00"
    for i, w in enumerate([14, 26, 6, 12, 14, 28, 14, 10, 11, 12, 12, 34, 12], 1):
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = "A2"
    wb.save(path)


if __name__ == "__main__":
    main()
