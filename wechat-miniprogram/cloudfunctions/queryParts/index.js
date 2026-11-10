// 供应商报价查询云函数（精简版）
// 数据库已随函数打包进目录（sync_snapshot.py 每次同步都会更新 supplier_db.sqlite），
// 因此直接读本地文件即可，无需 wx-server-sdk / 云存储下载，冷启动更轻更快。
const initSqlJs = require('sql.js');
const fs = require('fs');
const path = require('path');
const { findPart } = require('./queries');

let SQL = null;
let dbCache = null; // 同实例冷启动期间缓存，避免每次请求都重新读盘

async function getSqlJs() {
  if (!SQL) SQL = await initSqlJs();
  return SQL;
}

function loadDb() {
  const SQL = SQL_SYNC();
  const local = path.join(__dirname, 'supplier_db.sqlite');
  if (!fs.existsSync(local)) {
    throw new Error('未找到数据库：函数目录缺少 supplier_db.sqlite，请重新运行 sync_snapshot.py 同步');
  }
  console.log('[queryParts] 从本地文件加载数据库:', local, fs.statSync(local).size, 'bytes');
  return new SQL.Database(fs.readFileSync(local));
}

// initSqlJs 是异步的，但只初始化一次；用闭包缓存同步句柄
let _sqlReady = null;
function SQL_SYNC() {
  if (!_sqlReady) throw new Error('SQL 引擎尚未初始化');
  return _sqlReady;
}

exports.main = async (event = {}) => {
  // 首次调用时初始化 sql.js（仅需一次，后续复用）
  if (!_sqlReady) {
    _sqlReady = await getSqlJs();
  }

  const parts = event.parts || [];
  const brand = event.brand || null;
  const refresh = !!event.refresh; // 强制重新加载快照

  if (!parts.length) {
    return { hit: 0, miss: 0, total: 0, results: [] };
  }

  if (!dbCache || refresh) {
    dbCache = loadDb();
  }

  const results = [];
  let hit = 0;
  let miss = 0;

  for (const raw of parts) {
    const r = findPart(dbCache, raw, brand);
    if (r) hit++;
    else miss++;
    results.push({ query: raw, result: r });
  }

  return { hit, miss, total: parts.length, results };
};
