# supplier-quote-db

发动机零配件供应商报价数据库（SQLite）的 **WorkBuddy 技能**：用于查询零件号报价、把询价单与库中价格匹配、导入增量数据模板、清洗脏合并件号、统一供应商名、以及备份同步。

覆盖品牌：CATERPILLAR / PERKINS / SCANIA / CUMMINS / YANMAR / JOHN DEERE / KOMATSU 等。

> 本仓库只含**技能代码与说明**，不含任何报价数据库本体（`*.sqlite`）与含商业数据的报价结果。数据库需由使用者自行提供，并放在脚本配置的 `DEFAULT_DB` 路径（默认 `~/.openclaw/workspace/supplier_db/supplier_db.sqlite`）。

## 目录结构

```
supplier-quote-db/
├── SKILL.md                      # 技能入口（WorkBuddy 加载）
├── README.md                     # 本文件
├── references/
│   ├── schema.md                 # 数据库表结构（5 表）
│   ├── conventions.md            # 命名/清洗/铁律约定
│   └── workflows.md              # 标准操作流程
├── scripts/
│   ├── query_parts.py            # 单号/批量/询价单(xlsx)查价匹配
│   ├── incremental_import.py     # 增量模板导入（dry-run/real/--override/--backup）
│   ├── clean_split_merged.py     # 拆分脏合并件号（Perkins 专用示例）
│   ├── merge_suppliers.py        # 统一供应商名（只改名不合并）
│   └── backup_to_cloud.py        # 整库同步到云端（Google Drive）
└── assets/
    └── incremental_template.xlsx # 增量导入模板
```

## 安装为 WorkBuddy 技能

将本目录复制到用户级技能目录即可：

```bash
cp -r supplier-quote-db ~/.workbuddy/skills/
```

重启/刷新 WorkBuddy 后，对"查报价 / 匹配询价单 / 导入增量数据"等请求即会自动触发本技能。

## 常用命令

```bash
# 单号查价（列出全部报价）
python scripts/query_parts.py CAT:4W-7018 --all

# 批量查价
python scripts/query_parts.py CAT:4W5698 CAT:3590908 --all

# 询价单(xlsx)匹配，结果写出到桌面
python scripts/query_parts.py --xlsx "/path/to/询价单.xlsx" --all --out "~/Desktop/匹配结果.xlsx"

# 增量导入（先 dry-run 检查，再 real 写库并自动备份）
python scripts/incremental_import.py "/path/to/增量数据.xlsx" --dry-run
python scripts/incremental_import.py "/path/to/增量数据.xlsx" --real --backup
```

> 查询类操作**不会写库、不同步**；写库类操作遵循铁律（见 `references/conventions.md`），且写前自动打快照、跑 `PRAGMA integrity_check`、再同步云端。

## 铁律（摘要）

- 无零件号不入库；质量不归一化（原厂/副厂等按原样保留）。
- 同供应商同质量取高价；代替件禁公式、挂 `part_alternates`。
- 纯查询不写库、不同步；写库后 `cp` 同步云端（不用 `rsync --delete`）。
- 品牌必填；供应商只改名、不合并。
- 脏合并件号：主件改名 + 交叉号挂代替件，**不拆成两个独立件**。
