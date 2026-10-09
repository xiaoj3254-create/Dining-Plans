<template>
  <view class="page">
    <!-- 顶部 Hero -->
    <view class="hero">
      <text class="hero-kicker">消息中心</text>
      <view class="hero-title">消息通知</view>
      <view class="hero-sub">报名、成团、账单，Agent 自动推送到这里</view>
    </view>

    <!-- 类型筛选：全部 / 待办 / 系统通知 -->
    <view class="chips">
      <view v-for="c in filterChips" :key="c.key" class="chip"
            :class="{ active: filter === c.key }" hover-class="btn-pressed"
            @tap="filter = c.key">
        {{ c.label }}<text v-if="c.key === 'todo' && todoCount"> {{ todoCount }}</text>
      </view>
    </view>

    <!-- 顶部：待办汇总 -->
    <view class="summary" v-if="todoCount > 0 && filter !== 'system'">
      <text class="sum-title">{{ todoCount }} 项待处理</text>
      <text class="sum-sub">账单生效、到场提醒等需要你操作</text>
    </view>

    <!-- 按队伍聚合 -->
    <view v-for="g in groups" :key="g.key" class="group">
      <view class="group-head">
        <text class="g-name">{{ g.name }}</text>
        <text class="g-badge" v-if="g.unread">{{ g.unread }}</text>
      </view>

      <!-- 整条卡片可点击进入饭局详情；操作按钮收在卡片内右侧，不再用左滑（避免与文字重叠） -->
      <view
        v-for="n in g.items"
        :key="n.id"
        class="msg-card"
        :class="{ unread: !n.is_read }"
        hover-class="msg-pressed"
        :hover-stay-time="120"
        @tap="tapItem(n)"
      >
        <!-- 类型头像：一眼区分消息来源 -->
        <view class="avatar" :class="avatarOf(n).cls">{{ avatarOf(n).text }}</view>

        <view class="msg-body">
          <view class="row1">
            <text class="title">{{ typeText(n.type) }}</text>
            <view class="dot-red" v-if="!n.is_read"></view>
          </view>
          <view class="body">{{ bodyText(n) }}</view>

          <view class="row-bottom">
            <text class="time">{{ formatTime(n.created_at) }}</text>
            <view class="ops">
              <view class="op" v-if="actionPath(n)" hover-class="op-pressed" @tap.stop="goAction(n)">
                {{ n.category === "todo" ? "去处理" : "查看" }}
              </view>
              <view class="op del" hover-class="op-pressed" @tap.stop="remove(n)">删除</view>
            </view>
          </view>
        </view>
      </view>
    </view>

    <view class="loading-block" v-if="loading && !items.length">
      <view class="spinner"></view>
      <text>加载中…</text>
    </view>
    <view class="list-foot" v-else-if="loadError" @tap="refresh">
      <text class="retry">加载失败，点击重试</text>
    </view>
    <view class="list-foot" v-else-if="items.length && finished">没有更多了</view>

    <empty-state
      v-if="!shownItems.length && !loading && !loadError"
      type="bubble"
      :title="filter === 'todo' ? '暂无待办事项' : filter === 'system' ? '暂无系统通知' : '暂无消息通知'"
      :note="filter === 'todo'
        ? '账单生效、到场提醒等需要你操作的提醒会出现在这里'
        : '饭局报名、满员提醒、账单通知将由 Agent 自动推送至此处'"
    >
      <view slot="action" class="empty-action">
        <view class="btn btn-ghost" hover-class="btn-pressed" @tap="goPlaza">去广场看看</view>
      </view>
    </empty-state>
  </view>
</template>

<script>
import { get, post, del } from "../../utils/request";
import { on, subscribe } from "../../utils/ws";
import { useAuthStore } from "../../stores/auth";
import { toastOk } from "../../utils/ui";
import EmptyState from "../../components/empty-state/empty-state.vue";

// Agent 系统通知类型
const SYSTEM_TYPES = [
  "member_joined", "member_left", "team_updated", "kicked", "formed",
  "bill_submitted", "bill_effective", "team_failed", "team_completed",
  "checkin_reminder", "checkin_overdue", "checkin_escalated", "report_result",
];
const TAB_INDEX = 2; // 消息 Tab 在 tabBar 中的位置
const PAGE_SIZE = 20;

// 待办类通知的落地页：账单相关 → 账单页；其余 → 队伍详情
const BILL_ACTIONS = [
  "bill_submitted", "bill_effective",
  "checkin_reminder", "checkin_overdue", "checkin_escalated",
];

// 各类型通知的图标头像（emoji + 底色），避免"千篇一律的一行文字"
const AVATAR_MAP = {
  formed: { text: "🎉", cls: "a-done" },
  team_completed: { text: "✅", cls: "a-done" },
  team_failed: { text: "⛔", cls: "a-dead" },
  kicked: { text: "🚪", cls: "a-dead" },
  team_updated: { text: "✏️", cls: "a-brand" },
  bill_submitted: { text: "🧾", cls: "a-progress" },
  bill_effective: { text: "💰", cls: "a-progress" },
  checkin_reminder: { text: "⏰", cls: "a-warn" },
  checkin_overdue: { text: "⏰", cls: "a-warn" },
  checkin_escalated: { text: "⏰", cls: "a-warn" },
  report_result: { text: "📣", cls: "a-brand" },
};

export default {
  components: { EmptyState },
  data() {
    return {
      items: [],
      page: 1,
      total: 0,
      unread: 0,
      finished: false,
      loading: false,
      loadError: false,
      tabAnim: false,
      filter: "all",
      filterChips: [
        { key: "all", label: "全部" },
        { key: "todo", label: "待办" },
        { key: "system", label: "系统通知" },
      ],
    };
  },
  computed: {
    todoCount() {
      return this.items.filter((n) => n.category === "todo" && !n.is_read).length;
    },
    /** 按筛选条件过滤后的列表 */
    shownItems() {
      if (this.filter === "todo") return this.items.filter((n) => n.category === "todo");
      if (this.filter === "system") return this.items.filter((n) => this.isSystem(n.type));
      return this.items;
    },
    /** 按 team_id 聚合：一张卡片代表一局饭局 */
    groups() {
      const map = new Map();
      for (const n of this.shownItems) {
        const key = n.team_id ? "t" + n.team_id : "other";
        if (!map.has(key)) {
          map.set(key, {
            key,
            name: n.team_id ? (n.payload && n.payload.team_name) || "饭局" : "系统消息",
            items: [],
            unread: 0,
          });
        }
        const g = map.get(key);
        g.items.push(n);
        if (!n.is_read) g.unread += 1;
      }
      return Array.from(map.values());
    },
  },
  onShow() {
    this.refresh();
    const auth = useAuthStore();
    if (auth.user) subscribe(["user:" + auth.user.id]);
    this.playTabAnim();
  },
  onLoad() {
    on("notification.new", () => this.refresh());
  },
  onPullDownRefresh() {
    this.refresh().finally(() => uni.stopPullDownRefresh());
  },
  onReachBottom() {
    this.loadMore();
  },
  onUnload() {
    uni.removeTabBarBadge({ index: TAB_INDEX, fail: () => {} });
  },
  methods: {
    playTabAnim() {
      this.tabAnim = false;
      setTimeout(() => {
        this.tabAnim = true;
      }, 30);
    },
    isSystem(t) {
      return SYSTEM_TYPES.indexOf(t) !== -1;
    },
    /** 头像：成员相关显示参与人首字，其余按类型给图标 */
    avatarOf(n) {
      const p = n.payload || {};
      if (n.type === "member_joined" || n.type === "member_left") {
        const name = p.member_nickname || "";
        return { text: name ? name.slice(0, 1) : "👤", cls: "a-person" };
      }
      return AVATAR_MAP[n.type] || { text: "🔔", cls: "a-brand" };
    },
    typeText(t) {
      return {
        member_joined: "有人报名",
        member_left: "有人退出",
        team_updated: "队长修改了饭局",
        kicked: "被移出队伍",
        formed: "队伍已成团",
        bill_submitted: "队长已录入账单",
        bill_effective: "账单已生效",
        team_failed: "队伍已终止",
        team_completed: "约饭完成",
        checkin_reminder: "到场提醒",
        checkin_overdue: "仍未完成结算",
        checkin_escalated: "结算长时间未完成",
        report_result: "举报处理结果",
      }[t] || "通知";
    },
    bodyText(n) {
      const p = n.payload || {};
      const reasonText = {
        disbanded: "已被队长解散",
        checkin_aborted: "因核销异常已解散",
        expired: "招募超时未满员，已自动关闭",
        user_deleted: "队长已注销账号",
      }[p.reason] || "已终止";
      switch (n.type) {
        case "member_joined":
          return `${p.member_nickname || "有人"}报名了「${p.team_name}」（${p.current_size}/${p.target_size}）`;
        case "member_left":
          return `${p.member_nickname || "有人"}退出了「${p.team_name}」`;
        case "team_updated": {
          const bits = [];
          if (p.dining_time) bits.push(`时间改为 ${p.dining_time}`);
          if (p.restaurant_changed) bits.push("更换了餐馆");
          if (p.menu_changed) bits.push("更新了预选菜品");
          return `「${p.team_name}」${bits.length ? bits.join("，") : "信息有更新"}，请留意`;
        }
        case "kicked":
          return `你被移出了「${p.team_name}」`;
        case "formed":
          return `「${p.team_name}」已自动成团，专属群聊已创建`;
        case "bill_submitted":
          return `「${p.team_name}」账单已录入：总额 ¥${p.total_amount}（待联同到场情况生效）`;
        case "bill_effective":
          return `「${p.team_name}」账单生效，人均 ¥${p.per_capita}，请及时结账`;
        case "team_failed":
          return `「${p.team_name}」${reasonText}`;
        case "team_completed":
          return `「${p.team_name}」全员结清，本次约饭完成`;
        case "checkin_reminder":
          return `「${p.team_name}」仍有 ${p.unchecked} 人未确认到场`;
        case "checkin_overdue":
          return `「${p.team_name}」还有 ${p.unchecked} 人未确认到场，请与队友协商`;
        case "checkin_escalated":
          return `「${p.team_name}」长时间未完成结算，可协调后由队长解散重开`;
        default:
          return p.team_name ? `「${p.team_name}」有新动态` : JSON.stringify(p);
      }
    },
    formatTime(iso) {
      return iso ? iso.replace("T", " ").slice(5, 16) : "";
    },
    actionPath(n) {
      if (!n.team_id) return "";
      return BILL_ACTIONS.indexOf(n.type) !== -1
        ? "/pages/bill/bill?id=" + n.team_id
        : "/pages/team-detail/team-detail?id=" + n.team_id;
    },
    goAction(n) {
      const url = this.actionPath(n);
      if (url) uni.navigateTo({ url });
    },
    goPlaza() {
      uni.switchTab({ url: "/pages/plaza/plaza" });
    },
    /** 未读角标：以服务端返回的 unread 为准（原来只数当前页，超过一页就失真） */
    syncBadge() {
      const unread = this.unread;
      if (unread > 0) {
        uni.setTabBarBadge({ index: TAB_INDEX, text: unread > 99 ? "99+" : String(unread), fail: () => {} });
      } else {
        uni.removeTabBarBadge({ index: TAB_INDEX, fail: () => {} });
      }
    },
    async refresh() {
      this.loading = true;
      this.loadError = false;
      try {
        const res = await get(`/api/notifications?page=1&page_size=${PAGE_SIZE}`);
        this.items = res.items;
        this.unread = res.unread || 0;
        this.total = res.total || 0;
        this.page = 1;
        this.finished = !res.has_more;
        this.syncBadge();
      } catch (e) {
        this.loadError = true;
      } finally {
        this.loading = false;
      }
    },
    async loadMore() {
      if (this.finished || this.loading) return;
      this.loading = true;
      try {
        const res = await get(`/api/notifications?page=${this.page + 1}&page_size=${PAGE_SIZE}`);
        this.items = this.items.concat(res.items);
        this.unread = res.unread || this.unread;
        this.total = res.total || this.total;
        this.page += 1;
        this.finished = !res.has_more;
      } catch (e) {
        this.loadError = true;
      } finally {
        this.loading = false;
      }
    },
    async remove(n) {
      try {
        await del(`/api/notifications/${n.id}`);
        this.items = this.items.filter((x) => x.id !== n.id);
        if (!n.is_read) this.unread = Math.max(0, this.unread - 1);
        this.syncBadge();
        toastOk("已删除");
      } catch (e) {
        /* handled */
      }
    },
    async tapItem(n) {
      if (!n.is_read) {
        await post(`/api/notifications/${n.id}/read`);
        n.is_read = true;
        this.unread = Math.max(0, this.unread - 1);
        this.syncBadge();
      }
      if (n.team_id) {
        uni.navigateTo({ url: "/pages/team-detail/team-detail?id=" + n.team_id });
      }
    },
  },
};
</script>

<style scoped>
/* 底部安全区：tabBar 为原生组件已占位，这里只保证内容不被手势条压住 */
.page { padding-bottom: calc(40rpx + env(safe-area-inset-bottom)); }

/* 类型筛选 */
.chips {
  display: flex; gap: 16rpx;
  padding: 24rpx 24rpx 6rpx;
  /* 顶部安全区：原生导航栏下通常为 0；自定义导航栏时补出状态栏高度防遮挡 */
  padding-top: calc(24rpx + env(safe-area-inset-top));
}
.chip {
  padding: 10rpx 28rpx; border-radius: 32rpx; background: #f3f3f7;
  color: #636e72; font-size: 26rpx;
}
.chip.active { background: #6c5ce7; color: #fff; font-weight: 600; box-shadow: 0 4rpx 12rpx rgba(108, 92, 231, 0.25); }
.summary {
  margin: 20rpx 20rpx 0; padding: 24rpx; border-radius: 24rpx;
  background: linear-gradient(135deg, #f0eeff 0%, #e6e2ff 100%); display: flex; flex-direction: column; gap: 6rpx;
}
.sum-title { font-size: 30rpx; font-weight: 700; color: #6c5ce7; }
.sum-sub { font-size: 22rpx; color: #a29bfe; }

.group { margin-top: 24rpx; }
.group-head { display: flex; align-items: center; gap: 12rpx; padding: 0 28rpx 12rpx; }
.g-name { font-size: 26rpx; color: #636e72; font-weight: 600; }
.g-badge {
  min-width: 32rpx; height: 32rpx; line-height: 32rpx; text-align: center;
  border-radius: 16rpx; background: #6c5ce7; color: #fff; font-size: 20rpx; padding: 0 8rpx;
}

/* 消息卡片：整条可点，操作区在卡片内部右下 */
.msg-card {
  display: flex; align-items: flex-start;
  margin: 0 20rpx 16rpx; padding: 24rpx;
  background: #fff; border-radius: 24rpx;
  box-shadow: 0 8rpx 24rpx rgba(45, 52, 54, 0.05);
}
.msg-pressed { opacity: 0.92; }
/* 未读：左侧竖线突出；已读不整体降透明度（保持正常可读） */
.msg-card.unread { border-left: 6rpx solid #6c5ce7; }

/* 类型头像 */
.avatar {
  width: 72rpx; height: 72rpx; border-radius: 50%; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-size: 34rpx; margin-right: 20rpx;
}
.a-person { background: #f0eeff; color: #6c5ce7; font-weight: 700; }
.a-brand { background: #f0eeff; }
.a-progress { background: #e8f1ff; }
.a-done { background: #e6f8f2; }
.a-warn { background: #fdf1e3; }
.a-dead { background: #f1f2f4; }

.msg-body { flex: 1; min-width: 0; }
.row1 { display: flex; align-items: center; }
.title { font-weight: 700; font-size: 29rpx; color: #2d3436; flex: 1; }
.dot-red {
  width: 14rpx; height: 14rpx; border-radius: 50%; background: #ff7675; margin-left: 10rpx;
}
.body { margin-top: 10rpx; font-size: 25rpx; color: #8a9199; line-height: 1.6; }

.row-bottom {
  display: flex; align-items: center; justify-content: space-between;
  margin-top: 16rpx; gap: 20rpx;
}
.time { font-size: 22rpx; color: #b2b2b2; }
/* 操作区：查看/去处理 与 删除 并排，间距充足，不与文字重叠 */
.ops { display: flex; align-items: center; gap: 16rpx; flex-shrink: 0; }
.op {
  font-size: 24rpx; color: #6c5ce7; background: #f0eeff;
  padding: 10rpx 26rpx; border-radius: 26rpx; line-height: 1.3;
}
.op.del { color: #ff7675; background: #fff0f0; }
.op-pressed { opacity: 0.8; }
</style>
