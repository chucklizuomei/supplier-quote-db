Page({
  data: {
    input: '',
    brand: '',
    results: [],
    loading: false,
    error: '',
    summary: ''
  },

  onInput(e) {
    this.setData({ input: e.detail.value });
  },

  onBrand(e) {
    this.setData({ brand: e.detail.value.trim().toUpperCase() });
  },

  async onQuery() {
    const lines = this.data.input
      .split(/[\n,，\s]+/)
      .map(s => s.trim())
      .filter(Boolean);

    if (!lines.length) {
      this.setData({ error: '请输入至少一个零件号' });
      return;
    }

    this.setData({ loading: true, error: '', results: [], summary: '' });

    try {
      const res = await wx.cloud.callFunction({
        name: 'queryParts',
        data: {
          parts: lines,
          brand: this.data.brand || null,
          all: true
        }
      });

      const r = res.result || {};
      this.setData({
        results: r.results || [],
        summary: `命中 ${r.hit || 0} / 未命中 ${r.miss || 0} / 共 ${r.total || lines.length}`
      });
    } catch (err) {
      this.setData({
        error: '查询失败：' + (err.errMsg || err.message || err)
      });
    } finally {
      this.setData({ loading: false });
    }
  }
});
