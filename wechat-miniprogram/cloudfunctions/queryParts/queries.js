// 与本地 query_parts.py 保持一致的匹配逻辑（清洗号 / 模糊 / 代替件反查）
// 依赖 sql.js 的 Database 实例（db）

function clean(v) {
  return String(v).replace(/[^A-Za-z0-9]/g, '').toUpperCase();
}

function num(p) {
  const m = String(p).match(/[\d.]+/);
  return m ? parseFloat(m[0]) : null;
}

function stripPrice(p) {
  return String(p).replace(/^\[|\]$/g, '');
}

function buildSql(cond) {
  return `
    SELECT p.id, b.name brand, p.part_number, p.part_number_fmt,
           p.name_en, p.name_cn, p.models,
           ps.quality, s.name supplier, ps.price, ps.price_note
    FROM parts p
    JOIN brands b ON b.id = p.brand_id
    LEFT JOIN part_suppliers ps ON ps.part_id = p.id
    LEFT JOIN suppliers s ON s.id = ps.supplier_id
    WHERE ${cond}
  `;
}

// 用 sql.js 预备语句执行，返回对象数组
function run(db, cond, params) {
  const stmt = db.prepare(buildSql(cond));
  stmt.bind(params);
  const out = [];
  while (stmt.step()) out.push(stmt.getAsObject());
  stmt.free();
  return out;
}

function findPart(db, raw, brand) {
  const cl = clean(raw);
  const ru = String(raw).toUpperCase();

  let rows = run(db, 'p.part_number=? OR p.part_number_fmt=?', [cl, cl]);
  if (!rows.length) rows = run(db, 'p.part_number=? OR p.part_number_fmt=?', [ru, ru]);
  if (!rows.length && brand) {
    rows = run(db, 'b.name=? AND (p.part_number=? OR p.part_number_fmt=?)',
      [brand.toUpperCase(), cl, cl]);
  }
  if (!rows.length) {
    rows = run(db, 'p.part_number LIKE ? OR p.part_number_fmt LIKE ?',
      ['%' + cl + '%', '%' + cl + '%']);
  }
  if (!rows.length) {
    // 5) 代替件反查：该号作为通用号挂在哪个主件下（交叉号场景，如 1475088 → 3505417）
    const stmt = db.prepare(
      'SELECT pa.part_id FROM part_alternates pa WHERE pa.alt_part_number=? OR pa.alt_part_number=?'
    );
    stmt.bind([cl, ru]);
    let mainId = null;
    if (stmt.step()) mainId = stmt.getAsObject().part_id;
    stmt.free();
    if (mainId) rows = run(db, 'p.id=?', [mainId]);
  }
  if (!rows.length) return null;

  const pid = rows[0].id;
  const quotes = rows
    .filter(r => r.supplier)
    .map(r => ({
      quality: r.quality || '',
      supplier: r.supplier,
      price: num(r.price),
      price_text: stripPrice(r.price),
      price_note: r.price_note || ''
    }))
    .sort((a, b) => (a.price == null ? 1 : 0) - (b.price == null ? 1 : 0)
      || (a.price || 0) - (b.price || 0));

  // 代替件：列出该主件拥有的通用号（交叉号）
  let alt_of = [];
  const stmt = db.prepare(
    `SELECT pa.alt_part_number, pa.alt_brand, pa.alt_quality
     FROM part_alternates pa
     WHERE pa.part_id = ?`
  );
  stmt.bind([pid]);
  while (stmt.step()) alt_of.push(stmt.getAsObject());
  stmt.free();

  return {
    pid,
    brand: rows[0].brand,
    part_number: rows[0].part_number,
    name_en: rows[0].name_en || '',
    name_cn: rows[0].name_cn || '',
    models: rows[0].models || '',
    quotes,
    alt_of
  };
}

module.exports = { findPart };
