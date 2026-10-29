# 数据库结构（SQLite，5 张表）

默认路径：`~/.openclaw/workspace/supplier_db/supplier_db.sqlite`
可用 `--db` 或环境变量 `SUPPLIER_DB` 覆盖。

## brands（品牌，50 个）

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL UNIQUE | **英文全大写**，如 CATERPILLAR / PERKINS / YANMAR |
| name_cn | TEXT | |
| notes | TEXT | |

现有品牌：ATLAS, AUDI, BAUDOUIN, BMW, BOBCAT, BOSCH, CASE, CATERPILLAR, CHERY, CHEVEROLET, CUMMINS, DAF, DELPHI, DENSO, DETROIT, DEUTZ, DOOSAN, FG WILSON, FLEETGUARD, FORD, HINO, HITACHI, HUIER, HYUNDAI, INGERSOLL RAND, ISUZU, IVECO, JCB, JOHN DEERE, KOMATSU, KUBOTA, LIEBHERR, MAN, MERCEDES-BENZ, MITSUBISHI, MTU, NEW HOLLAND, NISSAN, PERKINS, RENAULT, SCANIA, SIEMENS, STANADYNE, TDI, TOYOTA, VOLVO, WEICHAI, XCMG, YANMAR, ZEXEL

（品牌表会随导入增长，导入前用 `SELECT name FROM brands` 复核。）

## suppliers（供应商，303 家）

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| name | TEXT NOT NULL **UNIQUE** | 中文/英文原名，如 广州信昌、侯平CAT、佛山帕金斯 |
| notes | TEXT | |

⚠️ UNIQUE 约束意味着**不能存在两个同名供应商**。若要把 A 改名为已存在的 B，必须先合并报价再删除，不能只改名字。

主要供应商（报价条数）：广州信昌 544、优豪 514、JSD 319、正野 311、华达 254、楚锦晨 251、姚娜 214、侯平CAT 186、Morida 168、浩瀚 167、佛山帕金斯 159、紫光 155、湖南信昌 148、吕光辉 147、联盛 127、三和 123、菲越 101。

## parts（零件）

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| brand_id | INTEGER | → brands.id |
| part_number | TEXT NOT NULL | **清洗后的号**：仅保留 A-Z 0-9，转大写 |
| part_number_fmt | TEXT NOT NULL | 原始可读格式，如 `320-3060`（历史上多数与 part_number 相同） |
| name_en / name_cn | TEXT | 英文/中文名称（中文填充率 98%+，新件应一并填） |
| models | TEXT | 适用机型，空格分隔，如 `3516B 3512B 3508B` |
| quality | TEXT | 零件级质量（多为历史遗留值，真实质量以 part_suppliers.quality 为准） |
| quality_raw / params / src_row / src_file | | 原文与来源追溯 |

UNIQUE(brand_id, part_number) —— **一个零件号只属于一个品牌**。

## part_suppliers（报价，核心表）

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| part_id | INTEGER NOT NULL | → parts.id |
| supplier_id | INTEGER NOT NULL | → suppliers.id |
| quality | TEXT | 质量等级，**按原文保留** |
| price | TEXT NOT NULL | **字符串**，常见格式 `[550]`、`[150/套]`、`[400|480]` |
| unit / price_note / priority / src_row | | 单位、价格备注、优先级、来源行号 |

UNIQUE(part_id, supplier_id, quality) —— 同零件+同供应商+同质量只能有一条，冲突时取高价。

价格解析：`re.search(r'[\d.]+', price)` 取第一个数字比较大小；展示时 `str(price).strip('[]')`。
SQL 排序技巧：`ORDER BY CAST(REPLACE(REPLACE(ps.price,'[',''),']','') AS REAL)`。

## part_alternates（代替件 / 通用号）

| 列 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | |
| part_id | INTEGER NOT NULL | 主件 |
| alt_part_number | TEXT | 通用号（清洗值） |
| alt_brand / alt_quality / src_row | | |

UNIQUE(part_id, alt_part_number)。查询时要**双向查**：既查主件号，也反查该号是否被挂成别人的通用号。

## 零件号清洗规则

```python
clean = re.sub(r'[^A-Za-z0-9]', '', str(v)).upper()
```

- `320-3060` → `3203060`；`278/399` → `278399`；`740695-01600-C` → `74069501600C`
- 查询必须同时匹配 `part_number` 与 `part_number_fmt`，并兼容原始带符号写法
- 兜底顺序：精确清洗号 → 原始大写号 → 指定品牌 → LIKE 模糊 → 代替件反查
