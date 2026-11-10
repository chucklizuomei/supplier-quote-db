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
│   ├── node_modules/sql.js/   # 已随包提交（精简版），克隆后可直接部署
│   └── supplier_db.sqlite     # ★ 由 sync_snapshot.py 自动复制进来（.gitignore 已忽略，不入库）
├── cloudbaserc.json           # tcb 部署配置（envId / runtime / timeout）
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

---

## 🚀 部署步骤（详细版）

### 第 0 步：本机一次性环境准备

1. **安装 Node.js（LTS）**
   微信云开发 CLI（`tcb`）依赖 Node.js。已装可跳过，建议版本 ≥ 18。
   ```bash
   node -v
   ```

2. **安装并登录 CloudBase CLI**
   ```bash
   npm i -g @cloudbase/cli
   tcb login          # 浏览器弹出微信扫码授权，按提示完成
   tcb env list       # 确认能看到你的环境（记下 envId）
   ```

3. **安装微信开发者工具（稳定版）**
   从 https://developers.weixin.qq.com/miniprogram/dev/devtools/download.html 下载安装。

---

### 第 1 步：获取 AppID 与环境 ID

- **AppID（小程序 ID）**：登录 [mp.weixin.qq.com](https://mp.weixin.qq.com) → 开发管理 → 开发设置 → 找到「AppID（小程序 ID）」。
  没有账号需先注册一个「小程序」类型账号。
- **环境 ID（envId）**：打开微信开发者工具 → 顶部「云开发」→ 在云开发控制台左上角环境名称下拉旁有「复制环境 ID」。
  本仓库默认填好的 envId 是 `cloud1-d3g6a4lna2b313d6d`，如不是你的环境，请替换。

> 这两个值要分别写进两个文件：
> - `app.js` 里的 `wx.cloud.init({ env: '你的envId' })`
> - `project.config.json` 里的 `"appid": "你的AppID"`
> `cloudbaserc.json` 里的 `envId` 也要一致（供 `tcb` 命令行部署识别）。

---

### 第 2 步：导入工程到开发者工具

1. 微信开发者工具 → 「导入项目」。
2. 目录选择本仓库的 `wechat-miniprogram/`。
3. AppID 填你的（或先用测试号，但不能调云函数，建议填真实 AppID）。
4. 导入后确认：
   - `project.config.json` 中 `miniprogramRoot` 为 `./`、`cloudfunctionRoot` 为 `cloudfunctions/`。
   - 左侧文件树能看到 `cloudfunctions/queryParts` 和 `pages/index`。

---

### 第 3 步：首次同步数据库 + 部署云函数

在终端进入小程序目录的脚本目录，运行一键同步脚本：

```bash
cd wechat-miniprogram/scripts
python sync_snapshot.py
# 可用参数：
#   --db /path/to/supplier_db.sqlite   指定本地库（默认 ~/.openclaw/workspace/supplier_db/supplier_db.sqlite）
#   --env xxxx-envId                   覆盖环境 ID
```

脚本会自动完成：
1. 对本地库跑 `PRAGMA integrity_check`（坏库直接中止，避免推送损坏数据）；
2. 把 `supplier_db.sqlite` 复制到 `cloudfunctions/queryParts/supplier_db.sqlite`；
3. 执行 `tcb fn deploy queryParts --force --install-dependency false` 重新部署。

看到终端输出 `✔ [queryParts] Cloud function deployed successfully!` 即部署成功。
此时云函数目录里已自带最新数据库，**无需任何手动配置**。

> ⚠️ `--install-dependency false` 表示依赖（精简后的 `sql.js`）已随包上传，云端不再重装，
> 这样函数包体只有约 1.45MB、冷启动约 0.8s，可规避小程序端的 3 秒网关超时（见下方「常见问题」）。

---

### 第 4 步：（备选）在开发者工具里手动上传云函数

如果你更习惯用 GUI 上传，也可以：

1. **先**在终端跑一次 `python sync_snapshot.py`（目的只为了把库复制进函数目录，可忽略其部署结果）；
2. 在开发者工具左侧 `cloudfunctions/queryParts` 上右键 → 「上传并部署：云端安装依赖」；
3. 上传完成后，到云开发控制台 → 云函数 → `queryParts` → 配置，确认：
   - **超时时间 = 30 秒**（默认可能是 3 秒，必须改大，否则大包冷启动会超时）；
   - 内存 256MB、运行环境 Nodejs16.13 即可。

> 注意：通过 GUI「上传并部署」时，云端会按 `package.json` 重新安装依赖；本仓库已移除
> `wx-server-sdk`，只剩 `sql.js`，所以即使云端安装也只有几 MB，不会影响速度。

---

### 第 5 步：调试与真机预览

1. **模拟器调试**：点「编译」，在页面输入框输入 `4W5698` 或 `CAT:3590908`，点「查价」。
   应返回供应商、质量、价格；`1475088` 这类交叉号也应能解析到 `3505417`。
2. **真机预览**：点顶部「预览」→ 用微信扫码，在手机上同样查价。
3. 若查不到但本地能查到，见下方「常见问题」。

---

### 第 6 步：日常同步（定期快照）

本地库有任何改动（导入新报价、改价、拆脏件）后，只需：

```bash
cd wechat-miniprogram/scripts
python sync_snapshot.py
```

脚本先校验库完整性，通过才复制并重新部署。云函数有实例缓存，若想立即生效，
调用时带 `{refresh:true}`（或在小程序前端临时加个参数），或等待实例回收。

---

## 🔧 常见问题

- **改完本地库小程序还是旧的**：重跑 `sync_snapshot.py` 重新部署；或调用时带 `refresh:true`。
- **报 `errCode -504003 / timed out after 3 seconds`**：
  这是函数包体过大、经小程序网关预置超时所致。本仓库已通过「移除 wx-server-sdk + 精简 sql.js」
  把包体压到 1.45MB、冷启动约 0.8s 解决。若你重新上传后再次出现，请确认：
  ① 云函数控制台超时已设为 **30 秒**；② 依赖是随包上传（`--install-dependency false`）而非云端重装大依赖。
- **部署提示覆盖确认**：`sync_snapshot.py` 已带 `--force` 自动跳过；手动部署时选「覆盖」。
- **查不到但本地能查到**：确认 `sync_snapshot.py` 已成功部署（看终端 `deployed successfully`）。
- **想改用云存储而非打包**：在云函数控制台给 `queryParts` 加环境变量 `DB_FILE_ID`，
  并把库上传到云存储即可（本地打包文件缺失时函数会自动回退云存储）。

---

## 📜 铁律与边界（与本地一致）

- 小程序**仅只读查询**，所有写入/导入/改价/拆脏件仍在你本机完成，再靠打包同步上来。
- 写库操作（incremental_import、改价、拆脏件）**不要在小程序端做**，保持单一数据源。
- 云函数查询逻辑刻意与本地 `query_parts.py` 对齐（清洗号匹配 / 模糊 LIKE / 代替件反查），
  保证两端结果一致。

## 💰 费用与限制

- 云开发有免费额度（云函数调用、出网流量），小团队查价通常够用。
- sql.js 每次冷启动会把整库（约 1.2MB）载入内存；量级很小，无压力。
- 部署包 = 代码 + 1.2MB 库，远小于云函数包体上限，无需担心体积。
- 用云开发自带域名，**无需 ICP 备案**即可在开发者工具和真机调试；正式发布仍要走小程序常规审核。
