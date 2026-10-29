---
name: supplier-quote-db
description: 发动机零配件供应商报价数据库（SQLite）的查询、导入与维护。当用户要求查询零件号报价、把询价单与库中价格匹配、导入增量数据模板、新增/修改/删除某条报价、拆分合并脏件号、统一供应商名、或备份同步该数据库时使用。涉及 CATERPILLAR / PERKINS / CUMMINS / YANMAR / JOHN DEERE / KOMATSU 等品牌的零件询价与供应商报价管理。
agent_created: true
---

# 供应商报价数据库

维护一个发动机零配件多供应商报价库：按零件号查历史报价、把客户询价单匹配出成本价、把新报价批量导入、修正脏数据与报价。

## 环境

- 数据库：`~/.openclaw/workspace/supplier_db/supplier_db.sqlite`（可用 `--db` 或 `SUPPLIER_DB` 覆盖）
- Python：`/Users/zuomeica/.workbuddy/binaries/python/envs/default/bin/python`（已装 openpyxl）
- 用户维护的增量模板：`~/Documents/供应商数据库_导入模板_增量数据.xlsx`
- 技能目录内脚本可直接执行，无需复制到项目

## 铁律（详见 references/conventions.md）

任何操作前先确认这几条：

1. **无零件号一律拒绝入库**；无价格的行跳过。
2. **质量等级按原文入库，严禁归一化**（东亚/东康/重康/美康/博世等是有意义的细分标识）。
3. **同零件+同供应商+同质量多价格 → 取高价**。
4. **品牌必填且在 brands 表内（英文全大写）**；品牌列为空时必须先问用户，不得猜测。
5. **供应商名统一 = 只改名，不合并**；发现疑似重复供应商名只提醒、不动手。
6. **只在写库后同步云端**；纯查询结束不跑同步。
7. **批量写库前必打快照**，写完跑 `PRAGMA integrity_check` 并抽查关键件。

## 六类作业

流程细节、SQL 片段与命令见 `references/workflows.md`；表结构、约束、清洗规则见 `references/schema.md`。

### 1. 查价 / 询价单匹配

```bash
python scripts/query_parts.py 320-3060 CAT:7C3039 --out result.xlsx
python scripts/query_parts.py --xlsx inquiry.xlsx --sheet Caterpillar --out result.xlsx
python scripts/query_parts.py --file parts.txt --brand PERKINS --all
```

脚本内置 5 级兜底匹配（清洗号 → 原始号 → 品牌限定 → LIKE 模糊 → 代替件反查），避免「576/218 vs 576218」这类格式差异漏判。单价默认取库内最低报价，未命中行标红。

结果另存新文件，**绝不改动用户原询价文件**。同件两家价差悬殊时（如 207.13 vs 15）主动提示用户判断档次。

### 2. 增量导入

模板列序见 `assets/incremental_template.xlsx`（数据从第 7 行开始，14 列）。

```bash
python scripts/incremental_import.py dry-run "<模板>"
python scripts/incremental_import.py real    "<模板>" --backup
python scripts/incremental_import.py real    "<模板>" --override --backup   # 覆盖模式
```

默认规则是「同件同供同质量取高价、低价跳过」。只有用户明确说「本次价格为准 / 覆盖旧价」时才加 `--override`：
无条件用本次价格替换旧价（含降价），但仍只作用于**同零件+同供应商+同质量等级**的记录；质量等级不同的记录（如紫光「原厂」vs 紫光「重康」）视为两条，不会被覆盖，需另行确认是否删除。
dry-run 会打印「同件+同供+同质量 已存在 N 条」清单（旧价 → 新价）便于确认。

导入前必查：品牌列是否为空、有无价格行、第 12/13/14 列是否是真实代替件号（曾因填价差公式污染库）、同号多价情况。
导入后必查：计数核验（脚本「新增零件 +N」可能虚高）、抽查 3 件、代替件增量是否异常、integrity_check，然后同步云端。

用户手写的一行一条报价（如 `caterpillar |348-2379| ECU | 电脑版｜C12 ｜Genuine｜ 华达｜ 34908`）也走同一流程：先生成临时 xlsx 再 dry-run → real。

### 3. 单件增删改

先查 `SELECT id FROM parts WHERE part_number=?` 与供应商 id，再打快照、执行、核验、同步。
单件改价/删价、追加机型（追加不覆盖原值）的 SQL 模板见 workflows.md。

### 4. 拆分合并脏件号

识别两个号被粘成一个（如 `CH11304T436534`、`3T63526N9294`）。规则：主件号保留并带走报价，另一号挂入 `part_alternates` 作通用号。
若被拆出的号已独立存在且有自己报价，**保留两条独立记录 + 通用号关联**，不合并价格。

### 5. 供应商名处理

改名：`UPDATE suppliers SET name=? WHERE id=?`（默认）。
合并：仅在用户明确要求时用 `scripts/merge_suppliers.py`（会迁移报价并删除源供应商），先预览再 `--apply`；价差大的组（原厂/副厂两条线）不能合并。

### 6. 备份 / 回滚 / 同步

```bash
cp $DB $DB.bak_<动作>_$(date +%Y%m%d_%H%M%S)   # 打快照
cp $DB.bak_xxx $DB                              # 回滚
python scripts/backup_to_cloud.py               # 同步（cp 方式，勿用 rsync --delete）
```

完成后把「改了什么 / 影响行数 / 备份文件名 / 遗留问题」追加到 `~/.openclaw/workspace/memory/YYYY-MM-DD.md`，并复制到 `~/WorkBuddy/main/.workbuddy/memory/`。

## 汇报要求

- 给出明确的命中/未命中统计与价格表（供应商、质量、价格）。
- 主动指出发现的数据问题（脏件号、质量字段矛盾、价差异常、字段缺失）及已采取/建议的动作。
- 区分「本批改动」与「历史遗留」，不要混为一谈。
- 数据被改动后必须说明备份位置与云端同步状态。
