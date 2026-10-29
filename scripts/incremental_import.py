#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
增量追加脚本 - 追加新零件/新报价到已有数据库

读取 Excel「增量数据」Sheet，按以下逻辑处理：

  已有零件号 + 新供应商报价  →  追加报价行
  已有零件号 + 已有供应商    →  取高价（已存在则跳过）
  全新零件号                →  整条入库（含品牌/供应商/报价）
  已有零件 + 新代替件号     →  追加 part_alternates

用法:
  python3 incremental_import.py dry-run   <xlsx>   # 预览
  python3 incremental_import.py real      <xlsx>   # 执行
  python3 incremental_import.py real      <xlsx>  --backup  # 执行前自动备份DB

示例:
  python3 incremental_import.py real "/Users/zuomeica/Downloads/增量数据_20260914.xlsx"
"""

import sys, re, sqlite3, openpyxl, shutil, os
from collections import defaultdict
from datetime import datetime

# ─────────────────────────── 配置 ───────────────────────────
DB       = "/Users/zuomeica/.openclaw/workspace/supplier_db/supplier_db.sqlite"
SHEET    = "增量数据"        # Sheet 名，大小写敏感
# ────────────────────────────────────────────────────────────

if len(sys.argv) < 3:
    print(f"用法: python3 {sys.argv[0]} [dry-run|real [--backup]] <xlsx>")
    sys.exit(1)

MODE = sys.argv[1]
if MODE not in ("dry-run", "real"):
    print("MODE 必须是 dry-run 或 real"); sys.exit(1)

BACKUP_FLAG = "--backup" in sys.argv
# 覆盖模式（需用户明确要求才启用）：同一零件+同一供应商+同一质量等级，直接用本次价格覆盖旧价，
# 不再走默认的「取高价 / 低价跳过」规则。质量等级不同的记录视为不同条目，不会被覆盖。
OVERRIDE = "--override" in sys.argv
FILE = [a for a in sys.argv[2:] if not a.startswith("--")][0]

if not os.path.exists(FILE):
    print(f"❌ 文件不存在: {FILE}"); sys.exit(1)

print("=" * 60)
print(f"  模式: {'DRY-RUN（仅预览）' if MODE == 'dry-run' else 'REAL（写入数据库）'}")
print(f"  文件: {FILE}")
print(f"  数据库: {DB}")
print(f"  预备份: {'是' if (MODE=='real' and BACKUP_FLAG) else '否'}")
if OVERRIDE:
    print("  ⚠️ 覆盖模式：同件+同供应商+同质量 → 本次价格直接覆盖旧价（不取高价）")
print("=" * 60)

# ─────────────────────────── 工具函数 ───────────────────────
def cl(v):
    return str(v).strip() if v is not None else ""

def clean_pn(v):
    if not v: return ""
    return re.sub(r'[^A-Za-z0-9]', "", str(v)).upper()

def extract_num(price_str):
    if not price_str: return 0.0
    m = re.search(r'[\d.]+', str(price_str))
    return float(m.group()) if m else 0.0

def fmt_price(v):
    if v is None: return None
    s = str(v).strip()
    if not s: return None
    s = re.sub(r'[元/个件套台]', '/', s)
    if s.startswith("[") and s.endswith("]"): return s
    return f"[{s}]"

def clean_price_disp(v):
    if not v: return ""
    if v.startswith("[") and v.endswith("]"): return v[1:-1]
    return str(v)

# ─────────────────────────── 读取 Excel ─────────────────────
if not os.path.exists(FILE):
    print(f"❌ 文件不存在: {FILE}"); sys.exit(1)

wb = openpyxl.load_workbook(FILE, data_only=True)
if SHEET not in wb.sheetnames:
    avail = ", ".join(wb.sheetnames)
    print(f"❌ 未找到 Sheet「{SHEET}」，可用: {avail}")
    sys.exit(1)

ws = wb[SHEET]
rows_raw = []
for ri in range(4, ws.max_row + 1):          # 假设同样从第4行起
    r = [ws.cell(ri, c).value for c in range(1, 15)]
    if any(v is not None and str(v).strip() != "" for v in r):
        rows_raw.append((ri, r))

print(f"增量数据总行: {len(rows_raw)}")

# ─────────────────────────── 解析行 ─────────────────────────
def clean_alt(v):
    """代替件号清洗：拒绝明显不是零件号的值（小数值/过长的纯数字，通常是价格差额等公式结果）"""
    if v is None: return ""
    if isinstance(v, (int, float)):
        # 整数可能是以数字形式录入的零件号；带小数的一律视为公式/差额，丢弃
        if isinstance(v, float) and not float(v).is_integer():
            return ""
    s = clean_pn(v)
    if not s: return ""
    # 纯数字且长度 > 12 或含小数转换痕迹 → 丢弃
    if s.isdigit() and len(s) > 12:
        return ""
    return s

def parse_row(ri, r):
    """返回 [(supplier, price, quality), ...] 和基础信息"""
    b  = cl(r[0]).upper()
    pn = clean_pn(r[1])
    en = cl(r[2]).upper()
    cn = cl(r[3])
    mo = cl(r[4])
    qu = cl(r[5])
    pr = cl(r[6])
    s1 = cl(r[7]); p1 = fmt_price(r[8])
    s2 = cl(r[9]); p2 = fmt_price(r[10])
    alt_b = clean_alt(r[11])
    alt_c = clean_alt(r[12])
    alt_d = clean_alt(r[13])
    return {
        "row": ri, "brand": b, "part_number": pn,
        "name_en": en, "name_cn": cn, "models": mo,
        "quality": qu, "params": pr,
        "quotes": [(s, p, qu) for s, p in [(s1, p1), (s2, p2)] if s and p],
        "alts": [x for x in [alt_b, alt_c, alt_d] if x],
    }

records = []
skip_no_price = 0
skip_no_pn = 0
for ri, r in rows_raw:
    rec = parse_row(ri, r)
    if not rec["brand"]:
        continue
    if not rec["part_number"]:
        # 规则（2026-09-14）：无零件号的产品一律拒绝入库
        skip_no_pn += 1
        continue
    if not rec["quotes"]:
        skip_no_price += 1
        continue
    records.append(rec)

print(f"有效行（含零件号+至少一组供应商+价格）: {len(records)}")
print(f"跳过（无零件号·依规拒绝入库）: {skip_no_pn}")
print(f"跳过（无价格）: {skip_no_price}")

if len(records) == 0 and skip_no_pn > 0:
    print("\n❌ 本批数据全部无零件号，依据规则「无零件号一律拒绝入库」，已终止，未写入任何数据。")
    sys.exit(0)

# ─────────────────────────── 统计预览 ───────────────────────
existing_parts = set()   # (brand, pn)
existing_alts  = set()   # (part_id, alt_pn) 已在库的代替件

conn = sqlite3.connect(DB)
for (b, pn, fmt) in conn.execute(
    "SELECT b.name, p.part_number, p.part_number_fmt FROM parts p JOIN brands b ON b.id=p.brand_id"
).fetchall():
    # 同时登记原始号与清洗号，确保含特殊字符的零件号也能正确识别为“已存在”
    existing_parts.add((b.upper(), pn.upper()))
    if fmt:
        existing_parts.add((b.upper(), fmt.upper()))
for (pid, alt) in conn.execute("SELECT part_id, alt_part_number FROM part_alternates").fetchall():
    existing_alts.add((pid, alt.upper()))

new_parts_list   = []   # 全新零件
existing_parts_list = [] # 已有零件（只需追加报价）

for rec in records:
    key = (rec["brand"], rec["part_number"])
    if key in existing_parts:
        existing_parts_list.append(rec)
    else:
        new_parts_list.append(rec)

print(f"\n统计预览:")
print(f"  全新零件: {len(new_parts_list)}")
print(f"  已有零件（追加报价）: {len(existing_parts_list)}")

# 品牌分布
brands_new = defaultdict(int)
for r in new_parts_list:
    brands_new[r["brand"]] += 1
print(f"\n全新零件品牌分布 (top10):")
for b, n in sorted(brands_new.items(), key=lambda x: -x[1])[:10]:
    print(f"  {b}: {n}")

existing_brands = {r[0] for r in conn.execute("SELECT name FROM brands").fetchall()}
existing_supps  = {r[0] for r in conn.execute("SELECT name FROM suppliers").fetchall()}
existing_ps     = {}  # (part_id, supplier_id, quality) → (price_str, num)
supp_name = {r[1]: r[0] for r in conn.execute("SELECT id, name FROM suppliers").fetchall()}
part_label = {}
for (pid, brand, pn, name_cn) in conn.execute(
    "SELECT p.id, b.name, p.part_number, p.name_cn FROM parts p JOIN brands b ON b.id=p.brand_id"
).fetchall():
    part_label[pid] = f"{brand} {pn} {name_cn or ''}".strip()

for (pid, sid, q, price) in conn.execute(
    "SELECT part_id, supplier_id, quality, price FROM part_suppliers"
).fetchall():
    num = extract_num(price)
    key = (pid, sid, q)
    if key not in existing_ps or num > existing_ps[key][1]:
        existing_ps[key] = (price, num)

new_brands=0; new_supps=0; new_parts=0; new_ps=0; new_alts=0
upd_ps=0; skip_same=0; skip_low=0; skip_alt_exists=0; ovr_ps=0

def get_pid(b, pn):
    # 同时匹配原始号与清洗号
    row = conn.execute(
        "SELECT p.id FROM parts p JOIN brands b ON b.id=p.brand_id "
        "WHERE b.name=? AND (p.part_number=? OR p.part_number_fmt=?)",
        (b, pn, pn)
    ).fetchone()
    return row[0] if row else None

# ── 覆盖/冲突预览（dry-run 也显示，便于确认） ──
def preview_conflicts():
    lines = []
    for rec in existing_parts_list:
        pid = get_pid(rec["brand"], rec["part_number"])
        if pid is None:
            continue
        for (s, p_str, q) in rec["quotes"]:
            sid = supp_name.get(s)
            if sid is None:
                continue
            key = (pid, sid, q)
            if key in existing_ps:
                old_str, old_num = existing_ps[key]
                new_num = extract_num(p_str)
                tag = "覆盖" if OVERRIDE else ("取高价-保留" if new_num <= old_num else "更新为高价")
                lines.append(f"  {tag}  {part_label.get(pid,'')} | {s} | {q} | 旧 {old_str} → 新 {p_str}")
    return lines

conf = preview_conflicts()
if conf:
    print(f"\n同件+同供应商+同质量 已存在 {len(conf)} 条：")
    for l in conf:
        print(l)

# ─────────────────────────── DRY-RUN 终止（不写库） ──────────
if MODE == "dry-run":
    conn.close()
    print("\nℹ️ DRY-RUN：以上为预览结果，未写入数据库。确认无误后用 real 模式执行。")
    sys.exit(0)

# ─────────────────────────── REAL 执行 ─────────────────────
if MODE == "real":
    if BACKUP_FLAG:
        bak = DB + f".bak_inc_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy(DB, bak)
        print(f"\n✅ 数据库已备份: {os.path.basename(bak)}")

# ── A. 处理全新零件 ──
for rec in new_parts_list:
    b, pn = rec["brand"], rec["part_number"]

    # 品牌
    if b not in existing_brands:
        conn.execute("INSERT OR IGNORE INTO brands(name) VALUES (?)", (b,))
        existing_brands.add(b); new_brands += 1
    bid = conn.execute("SELECT id FROM brands WHERE name=?", (b,)).fetchone()[0]

    # 零件
    conn.execute(
        """INSERT OR IGNORE INTO parts
           (brand_id, part_number, part_number_fmt, name_en, name_cn, models, quality, params, src_row)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (bid, pn, pn, rec["name_en"], rec["name_cn"], rec["models"],
         rec["quality"], rec["params"], rec["row"])
    )
    pid = get_pid(b, pn)
    new_parts += 1

    # 供应商报价
    for (s, p_str, q) in rec["quotes"]:
        if s not in existing_supps:
            conn.execute("INSERT OR IGNORE INTO suppliers(name) VALUES (?)", (s,))
            existing_supps.add(s); new_supps += 1
        sid = conn.execute("SELECT id FROM suppliers WHERE name=?", (s,)).fetchone()[0]
        key = (pid, sid, q)
        if key in existing_ps:
            old_str, old_num = existing_ps[key]
            new_num = extract_num(p_str)
            if OVERRIDE:
                # 覆盖模式：无条件用本次价格替换旧价
                conn.execute(
                    "UPDATE part_suppliers SET price=? WHERE part_id=? AND supplier_id=? AND quality=?",
                    (p_str, pid, sid, q)
                )
                existing_ps[key] = (p_str, new_num); ovr_ps += 1
            elif new_num > old_num:
                conn.execute(
                    "UPDATE part_suppliers SET price=? WHERE part_id=? AND supplier_id=? AND quality=?",
                    (p_str, pid, sid, q)
                )
                existing_ps[key] = (p_str, new_num); upd_ps += 1
            elif new_num == old_num:
                skip_same += 1
            else:
                skip_low += 1
        else:
            conn.execute(
                """INSERT OR IGNORE INTO part_suppliers
                   (part_id, supplier_id, quality, price, priority, src_row)
                   VALUES (?,?,?,?,?,?)""",
                (pid, sid, q, p_str, 0, rec["row"])
            )
            existing_ps[key] = (p_str, extract_num(p_str)); new_ps += 1

    # 代替件
    for alt_pn in rec["alts"]:
        conn.execute(
            """INSERT OR IGNORE INTO part_alternates
               (part_id, alt_part_number, alt_brand, alt_quality, src_row)
               VALUES (?,?,?,?,?)""",
            (pid, alt_pn, b, rec["quality"], rec["row"])
        )
        new_alts += 1

# ── B. 处理已有零件（只追加新报价） ──
for rec in existing_parts_list:
    b, pn = rec["brand"], rec["part_number"]
    pid = get_pid(b, pn)
    if pid is None: continue

    for (s, p_str, q) in rec["quotes"]:
        if s not in existing_supps:
            conn.execute("INSERT OR IGNORE INTO suppliers(name) VALUES (?)", (s,))
            existing_supps.add(s); new_supps += 1
        sid = conn.execute("SELECT id FROM suppliers WHERE name=?", (s,)).fetchone()[0]
        key = (pid, sid, q)
        if key in existing_ps:
            old_str, old_num = existing_ps[key]
            new_num = extract_num(p_str)
            if OVERRIDE:
                # 覆盖模式：无条件用本次价格替换旧价
                conn.execute(
                    "UPDATE part_suppliers SET price=? WHERE part_id=? AND supplier_id=? AND quality=?",
                    (p_str, pid, sid, q)
                )
                existing_ps[key] = (p_str, new_num); ovr_ps += 1
            elif new_num > old_num:
                conn.execute(
                    "UPDATE part_suppliers SET price=? WHERE part_id=? AND supplier_id=? AND quality=?",
                    (p_str, pid, sid, q)
                )
                existing_ps[key] = (p_str, new_num); upd_ps += 1
            elif new_num == old_num:
                skip_same += 1
            else:
                skip_low += 1
        else:
            conn.execute(
                """INSERT OR IGNORE INTO part_suppliers
                   (part_id, supplier_id, quality, price, priority, src_row)
                   VALUES (?,?,?,?,?,?)""",
                (pid, sid, q, p_str, 0, rec["row"])
            )
            existing_ps[key] = (p_str, extract_num(p_str)); new_ps += 1

    # 代替件（检查是否已在库）
    for alt_pn in rec["alts"]:
        alt_key = (pid, alt_pn.upper())
        if alt_key in existing_alts:
            skip_alt_exists += 1
            continue
        conn.execute(
            """INSERT OR IGNORE INTO part_alternates
               (part_id, alt_part_number, alt_brand, alt_quality, src_row)
               VALUES (?,?,?,?,?)""",
            (pid, alt_pn, b, rec["quality"], rec["row"])
        )
        existing_alts.add(alt_key)
        new_alts += 1

conn.commit()

n_brands = conn.execute("SELECT COUNT(*) FROM brands").fetchone()[0]
n_supps  = conn.execute("SELECT COUNT(*) FROM suppliers").fetchone()[0]
n_parts  = conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
n_ps     = conn.execute("SELECT COUNT(*) FROM part_suppliers").fetchone()[0]
n_alts   = conn.execute("SELECT COUNT(*) FROM part_alternates").fetchone()[0]
ok       = conn.execute("PRAGMA integrity_check").fetchone()[0]
conn.close()

# ─────────────────────────── 报告 ──────────────────────────
print(f"\n{'=' * 60}")
print(f"✅ 增量导入完成")
print(f"{'=' * 60}")
print(f"  新增品牌:   +{new_brands}  总={n_brands}")
print(f"  新增供应商: +{new_supps}  总={n_supps}")
print(f"  新增零件:   +{new_parts}  总={n_parts}")
print(f"  新增报价:   +{new_ps}  更新(取高价):{upd_ps}  覆盖(本次为准):{ovr_ps}  同价已存:{skip_same}  跳过(价低):{skip_low}  总={n_ps}")
print(f"  新增代替件: +{new_alts}  跳过(已存在):{skip_alt_exists}  总={n_alts}")
print(f"  完整性:     {ok}")

if new_parts == 0 and new_ps == 0 and upd_ps == 0:
    print(f"\n  💡 本次无新增内容，可能原因:")
    print(f"     - 增量数据中的零件号已全部存在于数据库")
    print(f"     - 所有报价价格低于或等于已有报价")

print(f"\n  📝 建议: 同步备份 → python3 backup_to_drive.py")
