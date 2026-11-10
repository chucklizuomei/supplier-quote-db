#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
定期快照同步：把本地 supplier_db.sqlite 打包进云函数并重新部署。

设计（对应"定期快照"方案，且无需文件 ID）：
  本地改完库（导入/改价/拆脏件）后，跑一次本脚本：
    1. 先对本地库做 integrity_check（坏库不推）
    2. 把整个 SQLite 文件复制到 云函数目录 queryParts/supplier_db.sqlite
    3. 调用 `tcb fn deploy queryParts` 重新部署云函数
       —— 云函数优先读取目录内自带的 supplier_db.sqlite，因此：
         · 彻底不需要云存储文件 ID
         · 彻底不需要手工配置 DB_FILE_ID 环境变量
         · 每次重部署即自动用上最新快照

前置：
  1) 安装 CloudBase CLI 并登录：
       npm i -g @cloudbase/cli
       tcb login
  2) 环境 ID 已写入本文件 ENV 默认常量（也可 --env 覆盖 / 用 CLOUDBASE_ENV 环境变量）

用法：
  python sync_snapshot.py
  python sync_snapshot.py --db /path/to/supplier_db.sqlite
  python sync_snapshot.py --env xxxx-envid
"""
import argparse
import sqlite3
import subprocess
import sys
import shutil
import os
from pathlib import Path

# ---- 路径：本脚本在 wechat-miniprogram/scripts/ 下，据此推导项目根与函数目录 ----
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent                      # wechat-miniprogram/
FUNC_DIR = PROJECT_ROOT / "cloudfunctions" / "queryParts"

DEFAULT_DB = os.path.expanduser("~/.openclaw/workspace/supplier_db/supplier_db.sqlite")
DEFAULT_ENV = "cloud1-d3g6a4lna2b313d6d"             # 你的微信云开发环境 ID


def md5(p):
    import hashlib
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(8192), b""):
            h.update(b)
    return h.hexdigest()


def integrity_ok(p):
    try:
        c = sqlite3.connect(p)
        ok = c.execute("PRAGMA integrity_check").fetchone()[0]
        c.close()
        return ok == "ok"
    except Exception as e:
        print("校验出错:", e)
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", default=DEFAULT_DB, help="本地数据库路径")
    ap.add_argument("--env", default=os.environ.get("CLOUDBASE_ENV", DEFAULT_ENV), help="云开发环境 ID")
    args = ap.parse_args()

    if not os.path.exists(args.db):
        sys.exit(f"数据库不存在: {args.db}")

    if not integrity_ok(args.db):
        sys.exit("❌ 库完整性校验未通过，已中止（避免推送损坏的库到云端）")
    print("✅ 完整性校验 ok；本地 md5:", md5(args.db))

    if not FUNC_DIR.is_dir():
        sys.exit(f"❌ 未找到云函数目录: {FUNC_DIR}\n请确认本脚本位于 wechat-miniprogram/scripts/ 下。")

    # 1) 复制最新库进云函数目录
    dest = FUNC_DIR / "supplier_db.sqlite"
    shutil.copyfile(args.db, dest)
    print(f"✅ 已复制数据库到云函数目录: {dest} ({os.path.getsize(dest)} bytes)")

    # 2) 重新部署云函数（会自动打包该目录内的 supplier_db.sqlite + 本地 node_modules）
    #    --force 跳过"同名函数覆盖"交互确认，便于全自动定时运行
    #    --install-dependency false 表示依赖已随包上传，云端不再自动 npm install
    #      （保持函数包精简，冷启动快，避免触发小程序端 3 秒网关超时）
    cmd = ["tcb", "fn", "deploy", "queryParts", "--force",
           "--install-dependency", "false", "--cwd", str(PROJECT_ROOT)]
    print("\n执行部署:", " ".join(cmd))
    r = subprocess.run(cmd)
    if r.returncode == 0:
        print("✅ 云函数已重新部署，最新快照已生效。小程序查询将使用新库。")
        print("   若函数仍返回旧数据，可在小程序调用时传 {refresh:true}，或等待实例回收。")
    else:
        print("❌ 部署失败。请确认：tcb 已 `tcb login`；envId 正确；且 FUNC_DIR 下有 package.json。")


if __name__ == "__main__":
    main()
