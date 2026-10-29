# 六类标准作业流程

数据库默认路径 $DB = `~/.openclaw/workspace/supplier_db/supplier_db.sqlite`
Python 解释器：`/Users/zuomeica/.workbuddy/binaries/python/envs/default/bin/python`（已装 openpyxl）

---

## 1. 批量查价（询价单 → 匹配结果）

```
python scripts/query_parts.py 320-3060 CAT:7C3039 --out result.xlsx
python scripts/query_parts.py --xlsx inquiry.xlsx --sheet Caterpillar --out result.xlsx
python scripts/query_parts.py --file parts.txt --brand PERKINS --all
```

输出规则：单价默认取**库内最低报价**，其余列入「其他可选报价」；未命中行标红。
原文件绝不改动，结果另存 `*_价格匹配结果.xlsx`。

未命中件必须做模糊兜底后再下结论（脚本已内置 5 级匹配），并主动提示用户可导出询价清单。

## 2. 增量导入（模板 → 数据库）

模板：`assets/incremental_template.xlsx`（14 列，数据从第 7 行开始）
用户通常在 `~/Documents/供应商数据库_导入模板_增量数据.xlsx` 维护，每次覆盖写入新一批。

```
cd ~/.openclaw/workspace/supplier_db
python <skill>/scripts/incremental_import.py dry-run "<模板文件>"
python <skill>/scripts/incremental_import.py real    "<模板文件>" --backup
```

导入前检查清单：
- 数据行统计、品牌列是否为空（空则**必须问用户**）
- 有无价格行（无价跳过）
- 第 12/13/14 列是否是真实代替件号（不是公式/价差）
- 同号多价 → 提前告知用户将取高价

导入后：核对 parts/ps 计数、抽查 3 件、`PRAGMA integrity_check`、检查代替件增量是否异常，然后同步云端。

**同一零件号多行（多供应商或多质量）是正常写法**，脚本会复用同一零件只追加报价。

## 3. 单件增删改

新增报价：
```sql
INSERT INTO part_suppliers (part_id,supplier_id,quality,price,unit,price_note,priority,src_row)
VALUES (?,?,?,'[480]','','',0,'manual_YYYYMMDD');
```
更新价格：`UPDATE part_suppliers SET price='[430]' WHERE id=?`
删除报价：`DELETE FROM part_suppliers WHERE id=?`
追加机型：`UPDATE parts SET models='3606 G3516 G3600' WHERE id=?`（追加不覆盖）

单件操作也要先 `cp` 打快照，写完核验 + 同步。

## 4. 拆分合并脏件号

识别：零件号明显由两个号拼接（如 `CH11304T436534`、`3T63526N9294`）。
规则：**主件号保留（带报价），另一号挂为通用号**。

```sql
UPDATE parts SET part_number='3T6352', part_number_fmt='3T-6352' WHERE id=?;
INSERT OR IGNORE INTO part_alternates (part_id,alt_part_number,alt_brand,alt_quality,src_row)
VALUES (?,'6N9294','CATERPILLAR','原厂',?);
```
若被拆出的号原本已独立存在（有自己的报价），**保留两条独立记录并用通用号关联**，不要合并价格——否则原厂高价会被副厂低价拉低。

## 5. 供应商名处理

改名（默认做法）：
```sql
UPDATE suppliers SET name='羁诚' WHERE id=?;
```
合并（**必须先确认用户意图**，脚本会迁移报价 + 删源 + 冲突取高价）：
```
python scripts/merge_suppliers.py "覊诚>羁诚"           # 预览
python scripts/merge_suppliers.py --apply "覊诚>羁诚"   # 执行
```
合并前必查冲突：`(part_id, quality)` 交集。价差大（如 11804 vs 850）说明是原厂/副厂两条独立报价线，**不能合并**。

## 6. 备份 / 回滚 / 同步

打快照：`cp $DB $DB.bak_<动作>_$(date +%Y%m%d_%H%M%S)`
回滚：`cp $DB.bak_xxx $DB`
同步：`python scripts/backup_to_cloud.py`（cp 方式，主文件 + 日期快照 + 工作日志）
校验：`PRAGMA integrity_check` + 抽查，云端副本也用只读模式打开核验一次。

写工作日志到 `~/.openclaw/workspace/memory/YYYY-MM-DD.md`（并复制到 `~/WorkBuddy/main/.workbuddy/memory/`），记录：改了什么、影响行数、备份文件名、遗留问题。
