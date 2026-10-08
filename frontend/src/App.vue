<script>
import { useAuthStore, hasAgreedConsent } from "./stores/auth";
import { subscribe, resume, on } from "./utils/ws";
import { setReloginHandler } from "./utils/request";

export default {
  data() {
    return { booted: false, consentPrompted: false };
  },
  onLaunch() {
    const auth = useAuthStore();
    // 把「重新登录」能力注入请求层：任何请求撞 401 都走这里自愈（force 强制换新 token）
    setReloginHandler(() => auth.silentLogin({ force: true }));
    // 同意协议后继续启动流程
    uni.$on("consent:agreed", () => this.boot());
    // 小程序前台恢复：重连 WS 并重放订阅
    on("connected", () => resume());
  },
  onShow() {
    // 切后台回来时 WS 可能被回收，这里触发重连/重放订阅
    resume();
    // 首启同意门：未同意协议前不发起任何个人信息处理（包括登录本身）
    if (!hasAgreedConsent()) {
      if (!this.consentPrompted) {
        this.consentPrompted = true;
        uni.navigateTo({ url: "/pages/agreement/agreement?needAgree=1" });
      }
      return;
    }
    this.boot();
  },
  methods: {
    boot() {
      if (this.booted) return;
      this.booted = true;
      const auth = useAuthStore();
      auth.silentLogin().then(() => {
        if (auth.isVerified) {
          subscribe(["plaza", "user:" + auth.user.id]);
        }
      });
    },
  },
};
</script>

<style>
/* ============================================================
   全局样式规范（2026-10-08 统一）
   说明：支付宝小程序的 CSS 自定义属性支持不一致，因此这里用**字面量工具类**
   而不是 CSS 变量来实现设计令牌 —— 换色时全项目搜索替换这几个类即可，
   不依赖运行时的变量解析，避免"某些机型上变量没生效"的静默失败。

   状态色标准：蓝 = 进行中（招募中） / 绿 = 完成（已成团、已完成）
               灰 = 失效（已终止、已作废） / 红 = 警告（危险操作、异常）
   ============================================================ */
page {
  background-color: #f7f7fc;
  font-size: 28rpx;      /* 正文基准 */
  color: #2d3436;
}

/* ---------- 字号层级 ---------- */
.t-title { font-size: 36rpx; font-weight: 700; color: #2d3436; }
.t-h2 { font-size: 30rpx; font-weight: 700; color: #2d3436; }
.t-body { font-size: 28rpx; color: #2d3436; }
.t-sub { font-size: 24rpx; color: #636e72; }
.t-tiny { font-size: 22rpx; color: #b2b2b2; }
.muted { color: #b2b2b2; font-size: 24rpx; }

/* ---------- 卡片与分割 ---------- */
.card {
  background: #fff;
  border-radius: 20rpx;
  padding: 24rpx;
  margin: 20rpx;
  box-shadow: 0 6rpx 20rpx rgba(45, 52, 54, 0.06);
}
/* 卡片内的区块分割：菜品/成员/餐馆等模块之间拉开层级 */
.section {
  padding-top: 22rpx;
  margin-top: 22rpx;
  border-top: 2rpx solid #efeef6;
}
.section:first-child { padding-top: 0; margin-top: 0; border-top: none; }
.section-title { font-size: 28rpx; font-weight: 600; color: #2d3436; margin-bottom: 16rpx; }
.card-title { font-size: 30rpx; font-weight: 700; color: #2d3436; margin-bottom: 20rpx; }
.tile { background: #fafafd; border-radius: 16rpx; padding: 20rpx; }
.divider { height: 2rpx; background: #efeef6; margin: 20rpx 0; }
.spacer { height: 20rpx; }

/* ---------- 状态标签（标准化配色） ---------- */
.st { display: inline-block; font-size: 22rpx; padding: 4rpx 14rpx; border-radius: 8rpx; line-height: 1.6; }
.st-progress { background: #e8f1ff; color: #3b82f6; }   /* 进行中（招募中） */
.st-done { background: #e6f8f2; color: #10b981; }       /* 完成（已成团、已完成） */
.st-dead { background: #f1f2f4; color: #9aa0a6; }       /* 失效（已终止、已作废） */
.st-warn { background: #fff0f0; color: #ff7675; }       /* 危险（错误、需立即处理） */
.st-notice { background: #fdf1e3; color: #d98b26; }     /* 提示（非危险的注意事项） */
.st-brand { background: #f0eeff; color: #6c5ce7; }      /* 主色（中性强调） */
/* 兼容旧类名（页面逐步迁移到 .st-*） */
.tag { display: inline-block; font-size: 22rpx; padding: 4rpx 14rpx; border-radius: 8rpx; margin-right: 12rpx; background: #efeef6; color: #636e72; }
.tag-orange { background: #f0eeff; color: #6c5ce7; }
.tag-blue { background: #e8f1ff; color: #3b82f6; }
.tag-yellow { background: #fdcb6e; color: #2d3436; }
.tag-green { background: #e6f8f2; color: #10b981; }

/* ---------- 按钮（统一尺寸与反馈） ---------- */
.btn {
  border-radius: 44rpx; font-size: 30rpx; text-align: center;
  padding: 20rpx 0; box-sizing: border-box;
}
.btn-primary { background: #6c5ce7; color: #fff; }
.btn-ghost { background: #fff; color: #6c5ce7; border: 2rpx solid #6c5ce7; padding: 18rpx 0; }
.btn-quiet { background: #f0eeff; color: #6c5ce7; }
.btn-danger { background: #fff; color: #ff7675; border: 2rpx solid #ff7675; padding: 18rpx 0; }
.btn-sm { font-size: 26rpx; padding: 10rpx 28rpx; border-radius: 30rpx; display: inline-block; }
.btn-block { width: 100%; box-sizing: border-box; }
/* 所有按钮的按压反馈 */
.btn-pressed { opacity: 0.85; }
.btn-primary.btn-pressed { background: #5a4bd1; }
.btn-quiet.btn-pressed { background: #e6e2ff; }
.btn-ghost.btn-pressed, .btn-danger.btn-pressed { opacity: 0.75; }
.tap-pressed { opacity: 0.92; transform: scale(0.99); }
/* 禁用 / 请求中：统一置灰并屏蔽点击，杜绝重复提交 */
.is-disabled { opacity: 0.45; pointer-events: none; }
.is-loading { opacity: 0.7; pointer-events: none; }

/* ---------- 空状态 ---------- */
.empty { padding: 60rpx 40rpx; text-align: center; }
.empty-title { font-size: 28rpx; color: #636e72; margin-bottom: 10rpx; }
.empty-desc { font-size: 24rpx; color: #b2b2b2; line-height: 1.6; }
.empty-action { margin-top: 28rpx; display: flex; justify-content: center; }
.empty-action .btn { min-width: 280rpx; padding-left: 40rpx; padding-right: 40rpx; }

/* ---------- 加载态（统一占位，避免"空白页无反馈"） ---------- */
.loading-block {
  display: flex; align-items: center; justify-content: center;
  gap: 14rpx; padding: 56rpx 20rpx; color: #b2b2b2; font-size: 26rpx;
}
.spinner {
  width: 30rpx; height: 30rpx; border-radius: 50%;
  border: 4rpx solid #e6e3f7; border-top-color: #6c5ce7;
  animation: spin 0.7s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
/* 列表底部（加载中 / 没有更多 / 加载失败）统一留白与字号 */
.list-foot { text-align: center; padding: 28rpx 20rpx; color: #b2b2b2; font-size: 24rpx; }
.list-foot .retry { color: #6c5ce7; }

/* 列表到底的轻量收尾插画（"没有更多了"不再是一行干文字） */
.list-end { display: flex; flex-direction: column; align-items: center; padding: 30rpx 0 10rpx; }
.list-end .le-dots { display: flex; gap: 10rpx; margin-bottom: 14rpx; }
.list-end .le-dots .d { width: 12rpx; height: 12rpx; border-radius: 50%; background: #ded9f5; }
.list-end .le-dots .d:nth-child(2) { background: #c5bfff; }
.list-end .le-dots .d:nth-child(3) { background: #a29bfe; }
.list-end .le-text { font-size: 24rpx; color: #b2b2b2; }

/* ---------- 横向滚动的溢出提示箭头 ---------- */
.scroll-hint {
  display: flex; align-items: center; justify-content: flex-end;
  gap: 8rpx; font-size: 22rpx; color: #a29bfe; margin-top: 8rpx;
}
.scroll-hint .arw { font-size: 26rpx; animation: nudge 1.4s ease-in-out infinite; }
@keyframes nudge {
  0%, 100% { transform: translateX(0); }
  50% { transform: translateX(8rpx); }
}

/* ---------- 页面左右边距统一 ---------- */
.pad-x { padding-left: 20rpx; padding-right: 20rpx; }

/* ---------- 安全区（底部固定栏 / 页面留白） ---------- */
.safe-bottom { padding-bottom: calc(24rpx + env(safe-area-inset-bottom)); }
.safe-fixed-bottom {
  position: fixed; left: 0; right: 0; bottom: 0;
  margin: 0 auto; max-width: 480px;
  padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #fff; box-shadow: 0 -4rpx 16rpx rgba(45, 52, 54, 0.05);
  display: flex; gap: 20rpx; box-sizing: border-box;
}
/* 底部有固定栏的页面统一留出空间（含手势条） */
.page-with-footer { padding-bottom: calc(180rpx + env(safe-area-inset-bottom)) !important; }
/* Tab 页底部留白：tabBar 为原生组件，这里只保证内容不被手势条压住 */
.page-tab { padding-bottom: calc(40rpx + env(safe-area-inset-bottom)); }

/* ---------- Tab 切换入场动画 ---------- */
.tab-in { animation: tabIn 0.26s ease-out; }
@keyframes tabIn {
  from { opacity: 0; transform: translateY(12rpx); }
  to { opacity: 1; transform: none; }
}

/* ---------- 桌面浏览器：约束为手机宽度居中 ---------- */
@media (min-width: 768px) {
  body { background: #e9ebee; }
  uni-app, uni-page, uni-page-wrapper, uni-page-body {
    max-width: 480px;
    margin: 0 auto !important;
    min-height: 100vh;
    background: #f7f7fc;
    box-shadow: 0 0 32rpx rgba(0, 0, 0, 0.12);
  }
  uni-tabbar, .uni-tabbar {
    max-width: 480px;
    left: 0; right: 0; margin: 0 auto;
  }
}
</style>
