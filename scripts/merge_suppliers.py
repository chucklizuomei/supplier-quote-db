#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
供应商合并工具 - 把重复的供应商名统一到一个正名

用法:
  python3 merge_suppliers.py "旧名1>新名1" "旧名2>新名2" ... [--apply]

不带 --apply 时只预览（不写库）。

冲突处理：若同一零件 + 同一质量下两家都有报价，按既定规则【取高价】，
         低价那条删除，高价保留在正名供应商名下。
"""

import sys, sqlite3, shutil, os
from datetime import datetime

DB = "/Users/zuomeica/.openclaw/workspace/supplier_db/supplier_db.sqlite"

def num(p):
    import re
    m = re.search(r'[\d.]+', str(p))
    return float(m.group()) if m else 0.0

def main(pairs, apply=False):
    conn = sqlite3.connect(DB)
    if apply:
        bak = DB + f".bak_merge_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        shutil.copy(DB, bak)
        print(f"✅ 已备份: {os.path.basename(bak)}\n")

    total_moved = total_conflict = total_del = 0
    for old, new in pairs:
        o = conn.execute("SELECT id FROM suppliers WHERE name=?", (old,)).fetchone()
        n = conn.execute("SELECT id FROM suppliers WHERE name=?", (new,)).fetchone()
        if not o:
            print(f"⚠️  跳过 {old}: 库中不存在"); continue
        if not n:
            print(f"⚠️  跳过 {old}>{new}: 目标供应商不存在"); continue
        oid, nid = o[0], n[0]
        if oid == nid:
            print(f"⚠️  跳过 {old}: 与 {new} 是同一条记录"); continue

        src = conn.execute("SELECT id,part_id,quality,price FROM part_suppliers WHERE supplier_id=?", (oid,)).fetchall()
        dst = {(r[1], r[2]): (r[0], r[3]) for r in
               conn.execute("SELECT id,part_id,quality,price FROM part_suppliers WHERE supplier_id=?", (nid,))}
        moved = conflict = 0
        for sid, pid, q, price in src:
            key = (pid, q)
            if key in dst:
                # 冲突：取高价
                did, dprice = dst[key]
                if num(price) > num(dprice):
                    if apply:
                        conn.execute("UPDATE part_suppliers SET price=? WHERE id=?", (price, did))
                        conn.execute("DELETE FROM part_suppliers WHERE id=?", (sid,))
                    print(f"    ⚔️ 冲突 {pid}/{q}: {dprice} → {price}（取高价）")
                else:
                    if apply:
                        conn.execute("DELETE FROM part_suppliers WHERE id=?", (sid,))
                    print(f"    ⚔️ 冲突 {pid}/{q}: 保留已有 {dprice}（高于 {price}）")
                conflict += 1
            else:
                if apply:
                    conn.execute("UPDATE part_suppliers SET supplier_id=? WHERE id=?", (nid, sid))
                moved += 1
        if apply:
            conn.execute("DELETE FROM suppliers WHERE id=?", (oid,))
        print(f"  {old}({oid}) → {new}({nid}): 迁移 {moved} 条, 冲突合并 {conflict} 条")
        total_moved += moved; total_conflict += conflict

    if apply:
        conn.commit()
    print(f"\n合计: 迁移 {total_moved} 条, 冲突合并 {total_conflict} 条")
    print(f"供应商总数: {conn.execute('SELECT COUNT(*) FROM suppliers').fetchone()[0]}")
    print(f"报价总数: {conn.execute('SELECT COUNT(*) FROM part_suppliers').fetchone()[0]}")
    print(f"完整性: {conn.execute('PRAGMA integrity_check').fetchone()[0]}")
    conn.close()

if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    pairs = []
    for a in args:
        if ">" not in a:
            print(f"❌ 参数格式应为 旧名>新名，收到: {a}"); sys.exit(1)
        o, n = a.split(">", 1)
        pairs.append((o.strip(), n.strip()))
    print("=" * 60)
    print(f"  模式: {'APPLY（写入）' if apply else 'DRY-RUN（预览）'}")
    print(f"  合并: {len(pairs)} 组")
    print("=" * 60)
    main(pairs, apply)
