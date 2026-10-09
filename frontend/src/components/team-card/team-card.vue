<template>
  <view class="tc" :class="{ dimmed }" hover-class="tc-pressed" @tap="$emit('click', team)">
    <!-- 第一行：状态 + 距离 + 剩余招募时长（信息归一行，便于快速扫读） -->
    <view class="tc-top">
      <text class="st" :class="status.cls">{{ status.text }}</text>
      <text class="tc-dist" v-if="distText">📍 {{ distText }}</text>
      <text class="tc-countdown" :class="{ urgent: urgent }" v-if="countdown">{{ countdown }}</text>
      <button
        v-if="showShare"
        class="share-mini"
        open-type="share"
        @tap.stop="$emit('share', team)"
      >分享</button>
    </view>

    <!-- 第二行：饭局名（卡片标题，加粗） -->
    <view class="tc-name">{{ team.name }}</view>

    <!-- 核心信息：餐馆（门店） + 用餐时间 -->
    <view class="tc-main">
      <view class="tc-row">
        <image class="ico" src="/static/icons/location.png" mode="aspectFit" />
        <text class="txt txt-rest">{{ restaurantName }}</text>
        <text class="tc-period" v-if="period">{{ period }}</text>
      </view>
      <view class="tc-row">
        <image class="ico" src="/static/icons/clock.png" mode="aspectFit" />
        <text class="txt txt-time">{{ diningText }}</text>
      </view>
    </view>

    <view class="tc-menu" v-if="team.menu_summary">{{ team.menu_summary }}</view>

    <!-- 底部：人数进度 + 标签 + 操作 -->
    <view class="tc-bottom">
      <view class="tc-seat">
        <view class="seat-line">
          <text class="seat-num">{{ team.current_size }}/{{ team.target_size || "?" }}</text>
          <text class="seat-label">已入队</text>
        </view>
        <view class="seat-bar" v-if="team.target_size">
          <view class="seat-fill" :class="{ full: isFull }" :style="{ width: seatPercent + '%' }"></view>
        </view>
      </view>
      <view class="tc-tags">
        <text class="tc-role" v-if="role">{{ role === "leader" ? "队长" : "队员" }}</text>
        <text class="tc-mode" :class="team.mode === 'anonymous' ? 'anon' : 'invite'">
          {{ team.mode === "anonymous" ? "匿名拼桌" : "链接邀请" }}
        </text>
        <text class="tc-cuisine" v-if="team.cuisine_type">{{ team.cuisine_type }}</text>
      </view>
      <view
        v-if="showAction"
        class="join-btn"
        :class="{ grayed: !joinable, loading: joining }"
        hover-class="jb-pressed"
        :hover-stay-time="120"
        @tap.stop="onJoin"
      >{{ joinText }}</view>
    </view>

    <!-- 匿名模式的信息可见性说明（固定在卡片底部） -->
    <view class="tc-risk" v-if="team.mode === 'anonymous'">
      匿名模式：队友仅可见你的年龄与性别
    </view>
  </view>
</template>

<script>
import {
  countdownText, distanceText, diningTimeText, mealPeriodOf, parseTime, teamStatusMeta,
} from "../../utils/format";

export default {
  name: "team-card",
  props: {
    team: { type: Object, required: true },
    /** 我的坐标（未授权定位时为 null） */
    me: { type: Object, default: null },
    /** 正在报名的队伍 id（用于按钮 loading 与防重复提交） */
    joiningId: { type: [Number, null], default: null },
    /** 是否展示报名按钮（「我的组队」里不需要） */
    showAction: { type: Boolean, default: true },
    /** 是否展示分享按钮（「我的组队」里队长可分享） */
    showShare: { type: Boolean, default: false },
    /** 我的角色（'leader' | 'member' | null）：传了就在标签区展示角色 */
    role: { type: String, default: "" },
    /**
     * 「满员 / 招募已截止」时是否整卡弱化。
     * - 广场（默认 true）：满员即无位可报，整卡弱化并禁用"报名"是符合预期的；
     * - 我的组队（传 false）：**已成团但未核销 = 有效进行中**，必须保持白底可点，
     *   只有已结束 / 已取消才弱化。
     */
    grayWhenUnavailable: { type: Boolean, default: true },
  },
  computed: {
    restaurantName() {
      if (this.team.restaurant && this.team.restaurant.name) return this.team.restaurant.name;
      return this.team.location_hint || "地点待定";
    },
    diningText() {
      return diningTimeText(this.team.dining_time) || "时间待定";
    },
    period() {
      return mealPeriodOf(this.team.dining_time);
    },
    distText() {
      // 后端已算好则直接用（带坐标请求时），否则用本地坐标兜底
      const fromServer = this.team.distance_km;
      if (fromServer != null) {
        if (fromServer < 1) return `${Math.max(50, Math.round((fromServer * 1000) / 50) * 50)}m`;
        return fromServer < 10 ? `${fromServer.toFixed(1)}km` : "10km+";
      }
      return distanceText(this.team.restaurant, this.me);
    },
    /** 剩余招募时长：以招募截止（就餐时间 + 宽限期）为准 */
    countdown() {
      if (this.team.status !== "recruiting") return "";
      const deadline = this.team.recruit_deadline || this.team.dining_time;
      if (!deadline) return "";
      return countdownText(deadline, { expired: "招募已截止" });
    },
    urgent() {
      const t = parseTime(this.team.recruit_deadline || this.team.dining_time);
      return t != null && t - Date.now() < 3 * 3600 * 1000;
    },
    isFull() {
      // target_size 在草稿期可能为空（不再用 0 冒充），这里必须防 NaN
      if (!this.team.target_size) return false;
      return this.team.target_size - this.team.current_size <= 0;
    },
    seatPercent() {
      if (!this.team.target_size) return 0;
      return Math.min(100, Math.round((this.team.current_size / this.team.target_size) * 100));
    },
    /** 已结束 / 已取消 —— 这两种才代表"该条目已失效" */
    isClosed() {
      return this.team.status === "completed" || this.team.status === "failed";
    },
    /** 招募已过截止时间（即便巡检还没把它收口） */
    isExpired() {
      const t = parseTime(this.team.recruit_deadline || this.team.dining_time);
      return t != null && t <= Date.now();
    },
    /** 报名不可用：满员 / 已截止 / 已取消 */
    joinable() {
      return !this.isFull && !this.isClosed && !this.isExpired;
    },
    /** 整卡弱化：仅"失效条目"；广场语境下满员/已截止也弱化 */
    dimmed() {
      if (this.isClosed) return true;
      return this.grayWhenUnavailable && (this.isFull || this.isExpired);
    },
    status() {
      if (this.isExpired && this.team.status === "recruiting") {
        return { text: "招募已截止", cls: "st-dead" };
      }
      return teamStatusMeta(this.team.status, { isFull: this.isFull });
    },
    joining() {
      return this.joiningId != null && this.joiningId === this.team.id;
    },
    joinText() {
      if (this.joining) return "报名中…";
      if (this.isFull) return "已满";
      if (this.isClosed || this.isExpired) return "已结束";
      return "报名";
    },
  },
  methods: {
    onJoin() {
      if (!this.joinable || this.joining) return; // 防重复提交
      this.$emit("join", this.team);
    },
  },
};
</script>

<style scoped>
/* 卡片规格与全局 .card 对齐（圆角/阴影统一） */
.tc {
  background: #fff; border-radius: 24rpx; padding: 28rpx;
  margin: 20rpx; box-shadow: 0 8rpx 24rpx rgba(45, 52, 54, 0.05);
  transition: opacity 0.15s;
}
.tc-pressed { opacity: 0.94; }
/* 仅"失效条目"（已结束 / 已取消）弱化 */
.tc.dimmed { filter: grayscale(0.85); opacity: 0.72; }

.tc-top { display: flex; align-items: center; gap: 12rpx; }
.tc-dist { font-size: 22rpx; color: #3b82f6; background: #e8f1ff; padding: 4rpx 12rpx; border-radius: 8rpx; }
.tc-countdown { font-size: 22rpx; color: #9aa0a6; margin-left: auto; }
.tc-countdown.urgent { color: #ff7675; font-weight: 600; }
.share-mini {
  margin: 0 0 0 auto; padding: 4rpx 20rpx; line-height: 1.9;
  background: #f0eeff; color: #6c5ce7; font-size: 22rpx; border-radius: 30rpx;
}
.share-mini::after { border: none; }
.tc-top .share-mini + .tc-countdown,
.tc-top .tc-countdown + .share-mini { margin-left: 0; }

/* 层级：饭局名(标题) > 门店(次标题) > 时间(次要) */
.tc-name { font-size: 34rpx; font-weight: 700; color: #2d3436; margin: 16rpx 0 12rpx; }

.tc-main { display: flex; flex-direction: column; gap: 8rpx; }
.tc-row { display: flex; align-items: center; }
.ico { width: 26rpx; height: 26rpx; margin-right: 10rpx; flex-shrink: 0; }
.txt { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.txt-rest { font-size: 28rpx; font-weight: 600; color: #2d3436; }
.txt-time { font-size: 24rpx; color: #636e72; }
.tc-period { font-size: 20rpx; color: #6c5ce7; background: #f0eeff; padding: 2rpx 10rpx; border-radius: 6rpx; margin-left: 12rpx; flex-shrink: 0; }

.tc-menu { margin-top: 12rpx; font-size: 23rpx; color: #b2b2b2; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.tc-bottom { display: flex; align-items: center; margin-top: 18rpx; padding-top: 18rpx; border-top: 2rpx solid #efeef6; }
/* 人数进度：数字 + 进度条 */
.tc-seat { flex-shrink: 0; width: 156rpx; }
.seat-line { display: flex; align-items: baseline; }
.seat-num { font-size: 36rpx; font-weight: 700; color: #6c5ce7; }
.seat-label { font-size: 21rpx; color: #b2b2b2; margin-left: 6rpx; }
.seat-bar { height: 8rpx; background: #efeef6; border-radius: 4rpx; margin-top: 10rpx; overflow: hidden; }
.seat-fill { height: 100%; background: #6c5ce7; border-radius: 4rpx; transition: width 0.3s; }
.seat-fill.full { background: #10b981; }

.tc-tags { flex: 1; display: flex; align-items: center; gap: 10rpx; margin-left: 20rpx; flex-wrap: wrap; }
/* 模式标签用浅色系，与菜系标签分组区分 */
.tc-mode { font-size: 20rpx; padding: 4rpx 12rpx; border-radius: 8rpx; }
.tc-mode.anon { background: #e6f8f2; color: #10b981; }
.tc-mode.invite { background: #fdf1e3; color: #d98b26; }
.tc-role { font-size: 20rpx; padding: 4rpx 12rpx; border-radius: 8rpx; background: #f0eeff; color: #6c5ce7; }
.tc-cuisine { font-size: 20rpx; padding: 4rpx 12rpx; border-radius: 8rpx; background: #f3f3f7; color: #636e72; }

.join-btn {
  flex-shrink: 0; min-width: 140rpx; text-align: center;
  background: #6c5ce7; color: #fff; font-size: 28rpx; font-weight: 600;
  padding: 14rpx 0; border-radius: 40rpx;
}
.join-btn.grayed { background: #f1f2f4; color: #9aa0a6; }
.join-btn.loading { opacity: 0.7; }
.jb-pressed { opacity: 0.85; }

.tc-risk { margin-top: 14rpx; font-size: 21rpx; color: #b2b2b2; line-height: 1.5; }
</style>
