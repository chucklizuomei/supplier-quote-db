// 小程序入口：初始化微信云开发
App({
  onLaunch() {
    if (!wx.cloud) {
      console.error('当前基础库不支持云开发，请使用 2.2.3 或以上版本');
      return;
    }
    wx.cloud.init({
      // 云开发环境 ID（微信开发者工具 → 云开发控制台左上角复制）
      env: 'cloud1-d3g6a4lna2b313d6d',
      traceUser: true
    });
  }
});
