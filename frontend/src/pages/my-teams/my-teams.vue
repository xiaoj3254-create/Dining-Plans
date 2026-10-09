<template>
  <view class="page page-tab">
    <!-- 顶部 Hero -->
    <view class="hero">
      <text class="hero-kicker">我的饭局</text>
      <view class="hero-title">我的组队</view>
      <view class="hero-sub">招募、成团、聚餐动态，一站式掌握</view>
    </view>

    <!-- 分组 Tab：招募中 / 已成团 / 已结束 -->
    <view class="tabs">
      <view
        v-for="t in tabs"
        :key="t.key"
        class="tab"
        :class="{ on: activeTab === t.key }"
        hover-class="btn-pressed"
        @tap="switchTab(t.key)"
      >
        <view class="tab-label">
          <text>{{ t.label }}</text>
          <text class="tab-badge" v-if="countOf(t.key)">{{ countOf(t.key) }}</text>
        </view>
      </view>
    </view>

    <!-- 列表：与广场共用同一张卡片，保持全站视觉统一 -->
    <view :class="{ 'tab-in': tabAnim }">
      <team-card
        v-for="t in currentList"
        :key="t.id"
        :team="t"
        :me="me"
        :show-action="false"
        :show-share="canShare(t)"
        :role="t.my_role"
        :gray-when-unavailable="false"
        @click="goDetail(t)"
        @share="prepareShare(t)"
      />
    </view>

    <!-- 加载态 -->
    <view class="loading-block" v-if="loading && !currentList.length">
      <view class="spinner"></view>
      <text>加载中…</text>
    </view>

    <!-- 分 Tab 空状态 -->
    <empty-state
      v-else-if="!loading && currentList.length === 0"
      type="plate"
      :title="emptyMeta.title"
      :desc="emptyMeta.desc"
    >
      <view slot="action" class="empty-action">
        <view class="btn btn-primary" hover-class="btn-pressed" @tap="goCreate">＋ 发起饭局</view>
      </view>
    </empty-state>

    <view class="list-foot" v-if="loadError" @tap="refresh">
      <text class="retry">加载失败，点击重试</text>
    </view>
  </view>
</template>

<script>
import { get } from "../../utils/request";
import { on, subscribe } from "../../utils/ws";
import { useAuthStore } from "../../stores/auth";
import { getMyLocation } from "../../utils/location";
import EmptyState from "../../components/empty-state/empty-state.vue";
import TeamCard from "../../components/team-card/team-card.vue";

// Tab 定义：草稿归入「招募中」组（待发布、需要用户继续操作），已终止与已完成归入「已结束」
const TAB_STATUS = {
  recruiting: ["draft", "recruiting"],
  formed: ["formed"],
  closed: ["completed", "failed"],
};

export default {
  components: { EmptyState, TeamCard },
  data() {
    return {
      groups: {},
      loading: false,
      loadError: false,
      tabAnim: false,
      activeTab: "recruiting",
      shareTarget: null,
      me: null,
      tabs: [
        { key: "recruiting", label: "招募中" },
        { key: "formed", label: "已成团" },
        { key: "closed", label: "已结束" },
      ],
    };
  },
  computed: {
    currentList() {
      const statuses = TAB_STATUS[this.activeTab] || [];
      return statuses.reduce((acc, s) => acc.concat(this.groups[s] || []), []);
    },
    emptyMeta() {
      const map = {
        recruiting: { title: "暂无正在招募的饭局", desc: "发起一场饭局|等大家来报名" },
        formed: { title: "暂无已成团的饭局", desc: "满员后会自动成团|可在群聊里协商细节" },
        closed: { title: "还没有历史饭局", desc: "完成的约饭会归档到这里" },
      };
      return map[this.activeTab] || map.recruiting;
    },
    /** 兜底分享目标：第一个可邀请的队伍（未指定具体卡片时用） */
    firstShareable() {
      const all = Object.values(this.groups).reduce((a, l) => a.concat(l), []);
      return all.find((t) => t.status === "recruiting" && t.mode === "invite" && t.code) || null;
    },
  },
  onLoad() {
    on("plaza.changed", () => this.scheduleRefresh());
    this.initLocation();
  },
  onShow() {
    this.refresh();
    const auth = useAuthStore();
    if (auth.isVerified) subscribe(["plaza"]);
  },
  onPullDownRefresh() {
    this.refresh().finally(() => uni.stopPullDownRefresh());
  },
  onShareAppMessage() {
    const t = this.shareTarget;
    if (t && t.code) {
      return {
        title: `约饭啦：${t.name}，一起来！`,
        path: `/pages/team-detail/team-detail?id=${t.id}&code=${t.code}`,
      };
    }
    const first = this.firstShareable;
    return {
      title: first ? `约饭啦：${first.name}，一起来！` : "约饭组队，找人一起吃饭",
      path: first
        ? `/pages/team-detail/team-detail?id=${first.id}&code=${first.code}`
        : "/pages/plaza/plaza",
    };
  },
  methods: {
    async initLocation() {
      this.me = await getMyLocation({ silent: true });
    },
    scheduleRefresh() {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = setTimeout(() => this.refresh(), 300);
    },
    /** Tab 切换：重放入场动画，形成"平滑刷新"的观感（数据已在本地，无需重新请求） */
    switchTab(key) {
      if (this.activeTab === key) return;
      this.activeTab = key;
      this.tabAnim = false;
      setTimeout(() => {
        this.tabAnim = true;
      }, 30);
    },
    countOf(tabKey) {
      const statuses = TAB_STATUS[tabKey] || [];
      return statuses.reduce((n, s) => n + ((this.groups[s] || []).length), 0);
    },
    canShare(t) {
      return t.my_role === "leader" && t.status === "recruiting" && t.mode === "invite" && t.code;
    },
    prepareShare(t) {
      this.shareTarget = t;
    },
    async refresh() {
      this.loading = true;
      this.loadError = false;
      try {
        const res = await get("/api/users/me/teams");
        this.groups = res.groups || {};
      } catch (e) {
        this.loadError = true;
      } finally {
        this.loading = false;
      }
    },
    goDetail(t) {
      // 整卡任意区域都可点击进详情；草稿进入编辑页继续完善
      if (t.status === "draft") {
        uni.navigateTo({ url: "/pages/team-create/team-create?draftId=" + t.id });
      } else {
        uni.navigateTo({ url: "/pages/team-detail/team-detail?id=" + t.id });
      }
    },
    goCreate() {
      uni.navigateTo({ url: "/pages/team-create/team-create" });
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 60rpx; }

/* ---------- 分组 Tab ---------- */
.tabs {
  display: flex; background: #fff; padding: 0 20rpx;
  /* 顶部安全区：原生导航栏下通常为 0；若改为自定义导航栏（navigationStyle: custom）
     这里会自动补出状态栏高度，避免 Tab 被手机顶部状态栏遮挡 */
  padding-top: env(safe-area-inset-top);
  position: sticky; top: 0; z-index: 6;
  border-bottom: 2rpx solid #efeef6;
  box-shadow: 0 4rpx 12rpx rgba(45, 52, 54, 0.04);
}
.tab {
  flex: 1; text-align: center; padding: 24rpx 0; font-size: 30rpx; color: #9aa0a6;
  display: flex; align-items: center; justify-content: center;
  position: relative;
}
.tab.on { color: #2d3436; font-weight: 700; }
/* 选中下划线：独占一条，粗细适中，视觉更利落 */
.tab.on::after {
  content: ""; position: absolute; left: 50%; bottom: 0;
  transform: translateX(-50%);
  width: 64rpx; height: 8rpx; border-radius: 4rpx; background: #6c5ce7;
}
/* 角标移到文字右上角（上标形式），不再挤在同一行 */
.tab-label { position: relative; display: inline-block; }
.tab-badge {
  position: absolute; top: -14rpx; right: -32rpx;
  min-width: 28rpx; height: 28rpx; line-height: 28rpx; text-align: center;
  border-radius: 14rpx; background: #e9eaee; color: #9aa0a6;
  font-size: 18rpx; padding: 0 6rpx;
}
.tab.on .tab-badge { background: #6c5ce7; color: #fff; }
</style>
