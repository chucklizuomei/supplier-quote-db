#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
拆分 Perkins "主件号+通用号" 合并脏件。
规则（用户 2026-09-27 确认）：
  合并件号 = A(主件) + B(通用号/交叉号)
  → A 作为主件（已存在则沿用，不存在则把合并件重命名为 A）
  → B 作为通用号写入 part_alternates（代替件），挂到 A 下（可被 alt_part_number 查询命中）
  → 合并件上的报价迁移到 A；若 A 已存在则删除合并脏件
用法: python3 clean_split_merged.py [dry-run|real]
"""
import sys, re, sqlite3, shutil
from datetime import datetime

DB="/Users/zuomeica/.openclaw/workspace/supplier_db/supplier_db.sqlite"
MODE=sys.argv[1] if len(sys.argv)>1 else "dry-run"

# 确认过的 Perkins 合并件方案 (merged_pid, A主件, B通用号)
PLAN=[
 (693, "3135X032", "3135X031"),
 (1709,"3135X041", "3135X042"),
 (873, "4115P015", "T426384"),
 (402, "4132F071", "T418992"),
 (1708,"4181A041", "4181A019"),
 (4414,"CH11304",  "T436534"),
 (1707,"U5LL0021", "U5LL0015"),
 (685, "U5LP0035", "68301"),
 (3048,"U5MW0194", "U5MW0206"),
 (706, "ZZ90143",  "ZZ90081"),
 (1310,"2485C041", "4133L507"),  # 合并脏件精确 pid=1310
]

def c(v): return re.sub(r'[^A-Za-z0-9]',"",str(v)).upper() if v else ""
def ex(pn):
    cc=c(pn)
    r=conn.execute("SELECT p.id FROM parts p JOIN brands b ON b.id=p.brand_id WHERE b.name='PERKINS' AND (UPPER(p.part_number)=? OR UPPER(p.part_number_fmt)=?)",(cc,cc)).fetchone()
    return r[0] if r else None

conn=sqlite3.connect(DB)
if MODE=="real":
    bak=DB+f".bak_split_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy(DB,bak); print(f"✅ 备份: {bak}")

print(f"=== 拆分预览 ({MODE}) ===")
for m_pid,a,b in PLAN:
    # 解析 A/B 的现有 pid
    a_id=ex(a); b_id=ex(b)
    if m_pid is None:
        m_pid=ex(a) or ex(b)  # 合并件=其中一个
    mrow=conn.execute("SELECT id,part_number,name_en,models FROM parts WHERE id=?",(m_pid,)).fetchone() if m_pid else None
    print(f"\n• 合并件 pid={m_pid} {mrow[1] if mrow else '?'} | A={a}({'在库'+str(a_id) if a_id else '新建'}) B={b}({'在库'+str(b_id) if b_id else '新建'})")
    # A 处理
    if a_id:
        target=a_id; print(f"  A 已存在(pid={a_id})，合并件报价迁至 A；合并件将删除")
    else:
        conn.execute("UPDATE parts SET part_number=?, part_number_fmt=? WHERE id=?",(a,a,m_pid)) if MODE=="real" else None
        target=m_pid; print(f"  A 不存在→ 合并件(pid={m_pid})重命名为 A={a}，保留其报价")
    if MODE!="real": continue
    # 报价迁移
    for sid,price,qu,prio,src in conn.execute("SELECT supplier_id,price,quality,priority,src_row FROM part_suppliers WHERE part_id=?",(m_pid,)).fetchall():
        exist=conn.execute("SELECT id FROM part_suppliers WHERE part_id=? AND supplier_id=? AND quality=?",(target,sid,qu)).fetchone()
        if not exist:
            conn.execute("INSERT INTO part_suppliers(part_id,supplier_id,quality,price,priority,src_row) VALUES(?,?,?,?,?,?)",(target,sid,qu,price,prio,src))
    # B 作为通用号挂代替件
    if b_id and b_id!=target:
        link_to=b_id
    else:
        link_to=target
    have=conn.execute("SELECT 1 FROM part_alternates WHERE part_id=? AND UPPER(alt_part_number)=?",(target,c(b))).fetchone()
    if not have:
        conn.execute("INSERT INTO part_alternates(part_id,alt_part_number,alt_brand,alt_quality,src_row) VALUES(?,?,?,?,?)",(target,c(b),"PERKINS","",0))
        print(f"  已新增代替件 B={b} 挂到 A(pid={target})")
    # 删除合并脏件（仅当 A 已存在，合并件是冗余副本）
    if a_id:
        conn.execute("DELETE FROM part_alternates WHERE part_id=?",(m_pid,))
        conn.execute("DELETE FROM part_suppliers WHERE part_id=?",(m_pid,))
        conn.execute("DELETE FROM parts WHERE id=?",(m_pid,))
        print(f"  已删除合并脏件 pid={m_pid}")

if MODE=="real":
    conn.commit()
ok=conn.execute("PRAGMA integrity_check").fetchone()[0]
print(f"\nIntegrity: {ok}")
n=conn.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
print(f"当前零件总数: {n}")
conn.close()
