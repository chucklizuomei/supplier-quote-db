#!/usr/bin/env python3
"""
供应商报价数据库 —— 云端备份（复制整库文件，非增量同步）。

用法：
  python backup_to_cloud.py                       # 用默认路径
  python backup_to_cloud.py --db /path/db.sqlite --dest "/Users/.../My Drive/Supplier Database Backup"
  python backup_to_cloud.py --no-snapshot         # 只覆盖主文件，不额外存日期快照

说明：
  - 采用整文件复制：云端任何时刻都是一份可直接打开使用的完整库。
  - 默认同时写两份：supplier_db.sqlite（主，覆盖）+ supplier_db_YYYYMMDD_HHMM.sqlite（日期快照）。
  - 不使用 rsync 删除：rsync 的 --delete 会触发权限拦截，故一律用 cp。
  - 会顺带同步工作日志（memory/*.md）。
"""
import argparse
import datetime
import os
import shutil
import sqlite3
import sys

DEFAULT_DB = os.path.expanduser("~/.openclaw/workspace/supplier_db/supplier_db.sqlite")
DEFAULT_DEST = os.path.expanduser(
    "~/Library/CloudStorage/GoogleDrive-motorpartshub@gmail.com"
    "/My Drive/Supplier Database Backup"
)
MEMORY_DIRS = [
    os.path.expanduser("~/.openclaw/workspace/memory"),
    os.path.expanduser("~/WorkBuddy/main/.workbuddy/memory"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=os.environ.get("SUPPLIER_DB", DEFAULT_DB))
    ap.add_argument("--dest", default=DEFAULT_DEST)
    ap.add_argument("--no-snapshot", action="store_true")
    ap.add_argument("--no-memory", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit("数据库不存在: %s" % args.db)
    # 落盘前先自检，避免把坏库推上去
    c = sqlite3.connect(args.db)
    ok = c.execute("PRAGMA integrity_check").fetchone()[0]
    parts = c.execute("SELECT COUNT(*) FROM parts").fetchone()[0]
    ps = c.execute("SELECT COUNT(*) FROM part_suppliers").fetchone()[0]
    c.close()
    if ok != "ok":
        sys.exit("数据库完整性检查失败(%s)，已中止备份" % ok)

    dstdir = os.path.join(args.dest, "supplier_db")
    os.makedirs(dstdir, exist_ok=True)

    main_copy = os.path.join(dstdir, "supplier_db.sqlite")
    shutil.copy2(args.db, main_copy)
    print("✅ 主文件已更新:", main_copy)

    if not args.no_snapshot:
        snap = os.path.join(
            dstdir,
            "supplier_db_%s.sqlite" % datetime.datetime.now().strftime("%Y%m%d_%H%M"),
        )
        shutil.copy2(args.db, snap)
        print("✅ 日期快照:", snap)

    if not args.no_memory:
        memdst = os.path.join(args.dest, "memory")
        os.makedirs(memdst, exist_ok=True)
        n = 0
        for d in MEMORY_DIRS:
            if not os.path.isdir(d):
                continue
            for fn in os.listdir(d):
                if fn.endswith(".md"):
                    shutil.copy2(os.path.join(d, fn), memdst)
                    n += 1
        print(f"✅ 工作日志同步: {n} 个文件")

    print(f"📦 本次备份内容: {parts} 零件 / {ps} 报价 | integrity ok")


if __name__ == "__main__":
    main()
