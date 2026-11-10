# 供应商报价查询 · 微信小程序（云开发版）

发动机零配件供应商报价数据库的移动端查询入口。基于**微信云开发（CloudBase）+ 定期打包快照**，
无需自建服务器。小程序只读查询，数据来自你本地库的云端副本。

## 目录结构

```
wechat-miniprogram/
├── project.config.json        # 开发者工具项目配置（已填 AppID / envId）
├── app.js / app.json / app.wxss
├── pages/index/               # 查价页面（输入零件号 → 结果列表）
├── cloudfunctions/queryParts/ # 云函数：用 sql.js 打开 SQLite 并查询
│   ├── index.js
│   ├── queries.js             # 匹配逻辑（与本地 query_parts.py 一致）
│   ├── package.json
│   └── supplier_db.sqlite     # ★ 由 sync_snapshot.py 自动复制进来（.gitignore 已忽略，不入库）
├── cloudbaserc.json           # tcb 部署配置（envId / runtime）
├── scripts/sync_snapshot.py   # 本地改完库后，一键复制库 + 重新部署云函数
└── README.md
```

## 数据流

```
微信小程序  ──callFunction──▶  queryParts 云函数  ──读取目录内自带的──▶  supplier_db.sqlite
   （前端）                      （sql.js 查 SQLite）        supplier_db.sqlite
```

**数据库直接打包进云函数目录**，随函数一起部署，因此：
- 不需要云存储；
- 不需要「文件 ID / DB_FILE_ID 环境变量」；
- 同步只需「复制库 + 重新部署函数」，全程自动化、零手工复制。

> 云函数仍保留云存储下载作为兜底（若设置了 `DB_FILE_ID` 且本地文件缺失），但默认走本地打包库。

## 部署步骤（需你本人在微信开发者工具操作）

### 1. 准备
- 注册微信小程序，拿到 **AppID**（mp.weixin.qq.com）。
- 安装 **微信开发者工具**（稳定版）。
- 本机安装 Node.js + CloudBase CLI：`npm i -g @cloudbase/cli`，然后 `tcb login`。

### 2. 导入工程
- 微信开发者工具 → 导入项目 → 目录选本 `wechat-miniprogram/` → 填你的 AppID。
- `project.config.json` 已填好 `appid` 与 `cloudfunctionsRoot`；`app.js` 已填好 `env`；
  如需改环境，改这两个文件即可。

### 3. 首次同步（复制库 + 部署函数）
```bash
cd wechat-miniprogram/scripts
python sync_snapshot.py          # 自动读默认 envId，复制库并 tcb fn deploy
```
脚本会：① integrity_check 校验本地库 → ② 复制 supplier_db.sqlite 进云函数目录 →
③ `tcb fn deploy queryParts --force` 重新部署（云端按 package.json 安装 sql.js 依赖）。
完成后函数即自带最新库，**无需任何手动配置**。

> 首次也可在开发者工具里右键 `cloudfunctions/queryParts` → 上传并部署：云端安装依赖，
> 但务必先把库放进该目录（跑一次 `sync_snapshot.py` 即可）。

### 4. 预览
- 编译 → 模拟器输入 `4W5698` 或 `CAT:3590908` 查价。
- 真机预览：点「预览」用微信扫码。

## 日常同步（定期快照）

本地库有任何改动（导入新报价、改价、拆脏件）后，只需：

```bash
python sync_snapshot.py          # 默认环境；或 --env <你的envId> 覆盖
```

脚本先校验库完整性，通过才复制并重新部署。云函数有实例缓存，若想立即生效，
调用时带 `{refresh:true}`（或等待实例回收）。

## 铁律与边界（与本地一致）

- 小程序**仅只读查询**，所有写入/导入/改价仍在你本机完成，再靠打包同步上来。
- 写库操作（incremental_import、改价、拆脏件）**不要在小程序端做**，保持单一数据源。
- 云函数查询逻辑刻意与本地 `query_parts.py` 对齐（清洗号匹配 / 模糊 LIKE / 代替件反查），
  保证两端结果一致。

## 费用与限制

- 云开发有免费额度（云函数调用、出网流量），小团队查价通常够用。
- sql.js 每次冷启动会把整库（约 1.2MB）载入内存；量级很小，无压力。
- 部署包 = 代码 + 1.2MB 库，远小于云函数包体上限，无需担心体积。
- 用云开发自带域名，**无需 ICP 备案**即可在开发者工具和真机调试；正式发布仍要走小程序常规审核。

## 常见问题

- **改完本地库小程序还是旧的**：重跑 `sync_snapshot.py` 重新部署；或调用时带 `refresh:true`。
- **部署提示覆盖确认**：脚本已带 `--force` 自动跳过；手动部署时选「覆盖」。
- **查不到但本地能查到**：确认 `sync_snapshot.py` 已成功部署（看终端 `deployed successfully`）。
- **想改用云存储而非打包**：在云函数控制台给 queryParts 加环境变量 `DB_FILE_ID`，
  并把库上传到云存储即可（本地打包文件缺失时函数会自动回退云存储）。
