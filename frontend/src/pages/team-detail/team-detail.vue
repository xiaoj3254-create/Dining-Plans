<template>
  <view class="page page-with-footer" v-if="team">
    <!-- 卡片 1：队伍概况 -->
    <view class="card">
      <view class="row1">
        <text class="t-title name">{{ team.name }}</text>
        <text class="st status-tag" :class="status.cls">{{ status.text }}</text>
      </view>
      <view class="meta-row">
        <text class="tag">{{ team.mode === "anonymous" ? "匿名拼桌" : "链接邀请" }}</text>
        <text class="tag" v-if="team.cuisine_type">{{ team.cuisine_type }}</text>
        <text class="st st-progress" v-if="distText">📍 {{ distText }}</text>
      </view>
      <view class="meta muted">时间：{{ diningText }}{{ period ? "（" + period + "）" : "" }}</view>
      <view class="meta muted" v-if="team.location_hint">位置：{{ team.location_hint }}</view>
      <view class="meta muted" v-if="team.failed_at">终止原因：{{ failReasonText(team.fail_reason) }}</view>

      <!-- 进度：进度条 + 右侧人数；下一行放倒计时（分行更整齐） -->
      <view class="progress-row">
        <view class="progress-bg">
          <view class="progress-fg" :class="{ full: isFull }" :style="{ width: seatPercent + '%' }" />
        </view>
        <text class="seat-text">{{ team.current_size }}/{{ team.target_size || "?" }} 人</text>
      </view>
      <view class="progress-hint">
        <text class="muted">已入队 {{ team.current_size }} 人{{ seatHint }}</text>
        <text class="countdown" :class="{ urgent: urgent }" v-if="recruitCountdown">{{ recruitCountdown }}</text>
      </view>
    </view>

    <!-- 补位提示 -->
    <view class="card notice" v-if="team.status === 'formed' && hasSeat">
      <view class="notice-title">有 {{ team.remaining }} 个空缺席位</view>
      <view class="muted">
        有队友退出，账单生效前都可补位。{{ isLeader ? "把队伍分享出去，对方点开即可补位。" : "" }}
      </view>
    </view>

    <!-- 卡片 2：就餐餐馆（可点击查看简介） -->
    <view class="card" v-if="team.restaurant">
      <view class="card-title">就餐餐馆</view>
      <view class="rest-row" hover-class="btn-pressed" @tap="goRestaurant">
        <image class="rest-thumb" :src="team.restaurant.image" mode="aspectFill" lazy-load />
        <view class="rest-info">
          <view class="rest-name">{{ team.restaurant.name }}</view>
          <view class="rest-sub">
            {{ team.restaurant.cuisine_type }} · {{ team.restaurant.district || "商圈待定" }}
            <text v-if="team.restaurant.avg_price"> · 人均 ¥{{ team.restaurant.avg_price }}</text>
          </view>
          <view class="rest-more">查看餐馆简介 ›</view>
        </view>
        <view class="copy-btn" v-if="team.location_hint" hover-class="btn-pressed" @tap.stop="copyAddress">复制地址</view>
      </view>
    </view>

    <!-- 卡片 3：预选菜品（横向滚动 + 溢出提示） -->
    <view class="card">
      <view class="card-title" v-if="team.dishes && team.dishes.length">
        预选菜品（{{ team.dishes.length }} 道）
      </view>
      <template v-if="team.dishes && team.dishes.length">
        <scroll-view scroll-x class="dish-scroll" :show-scrollbar="false">
          <view class="dish-item" v-for="d in team.dishes" :key="d.dish_id">
            <image class="dish-img" :src="d.image" mode="aspectFill" lazy-load />
            <view class="dish-name">{{ d.name }}</view>
            <view class="dish-price">¥{{ d.price }}</view>
          </view>
        </scroll-view>
        <view class="scroll-hint" v-if="dishOverflow">左右滑动查看全部菜品 <text class="arw">›</text></view>
        <view class="section estimate">
          <view class="est-row">
            <text class="est-label">预估总价</text>
            <text class="est-total">¥{{ team.estimate.total }}</text>
          </view>
          <view class="est-row">
            <text class="est-label">按 {{ team.target_size }} 人分摊</text>
            <text class="est-per">约 ¥{{ team.estimate.per_capita }}/人</text>
          </view>
          <view class="est-note">
            预估逻辑：按所选菜品标价合计，以满员人数均摊。仅作参考，实际以队长到店录入的账单为准。
          </view>
        </view>
      </template>
      <view class="muted" v-else>队长未预选菜品，可到店后现场点单。</view>
    </view>

    <!-- 卡片 4：成员 -->
    <view class="card">
      <view class="card-title">
        成员概况
        <text class="muted sub">（{{ team.profile.male }}男{{ team.profile.female }}女 · 平均{{ team.profile.avg_age }}岁）</text>
      </view>
      <view class="muted tip" v-if="team.members_hidden">
        {{ team.mode === "anonymous"
          ? "匿名拼桌：报名入队后才能看到队友昵称，非成员只看到年龄与性别的整体概况。"
          : "报名入队后才能查看队友昵称。" }}
      </view>
      <view class="member-list">
        <view class="member" v-for="(m, i) in team.members" :key="i" hover-class="btn-pressed" @tap="showMember(m)">
          <view class="avatar" :class="{ lead: m.role === 'leader' }">{{ m.user.nickname.slice(0, 1) }}</view>
          <view class="m-info">
            <text class="m-name">{{ m.user.nickname }}</text>
            <text class="muted">{{ genderText(m.user.gender) }} · {{ m.user.age }}岁</text>
          </view>
          <text class="st" :class="m.role === 'leader' ? 'st-brand' : 'st-progress'">
            {{ m.role === "leader" ? "队长" : "队员" }}
          </text>
          <text
            class="kick"
            v-if="isLeader && m.role !== 'leader' && team.status === 'recruiting'"
            @tap.stop="kickMember(m)"
          >移出</text>
        </view>
      </view>
    </view>

    <!-- 卡片 5：邀请（仅链接邀请 + 可见成员） -->
    <view class="card" v-if="team.code && isMember">
      <view class="card-title">{{ team.status === "recruiting" ? "邀请好友" : "补位邀请" }}</view>
      <view class="muted">邀请码：<text class="code">{{ team.code }}</text></view>
      <view class="btn-row">
        <button class="share-btn" open-type="share">分享邀请</button>
        <view class="btn btn-quiet btn-sm flex1" hover-class="btn-pressed" @tap="copyLink">复制邀请码</view>
        <view
          class="btn btn-ghost btn-sm flex1"
          v-if="isLeader && team.mode === 'invite' && team.invite_open"
          hover-class="btn-pressed"
          @tap="closeInvite"
        >关闭邀请</view>
      </view>
      <view class="muted tip">关闭后邀请码立即失效，广场报名不受影响。</view>
    </view>

    <!-- 底部操作：招募中 -->
    <view class="safe-fixed-bottom" v-if="team.status === 'recruiting'">
      <template v-if="!isMember">
        <view class="btn btn-primary flex1" :class="{ 'is-disabled': !canJoin }"
              hover-class="btn-pressed" @tap="askJoin">{{ joinText }}</view>
      </template>
      <template v-else-if="isLeader">
        <view class="btn btn-ghost flex1" hover-class="btn-pressed" @tap="goEdit">修改饭局</view>
        <view class="btn btn-danger flex1" :class="{ 'is-disabled': busy }"
              hover-class="btn-pressed" @tap="disband">撤销饭局</view>
      </template>
      <template v-else>
        <view class="btn btn-ghost flex1" :class="{ 'is-disabled': busy }"
              hover-class="btn-pressed" @tap="leave">退出报名</view>
      </template>
    </view>

    <!-- 底部操作：已成团（两个主按钮 + 更多菜单收纳退出/解散，防误点） -->
    <view class="safe-fixed-bottom" v-if="team.status === 'formed' || team.status === 'completed'">
      <template v-if="isMember">
        <view class="btn btn-quiet flex1 icon-btn" hover-class="btn-pressed" @tap="goChat">
          <text class="ic">💬</text> 进入群聊
        </view>
        <view class="btn btn-primary flex1 icon-btn" hover-class="btn-pressed" @tap="goBill">
          <text class="ic">✅</text> 确认到场 / 账单
        </view>
        <view class="btn btn-more" hover-class="btn-pressed" @tap="moreActions">⋯</view>
      </template>
      <template v-else>
        <view class="btn btn-primary flex1"
              :class="{ 'is-disabled': busy || !hasSeat || !joinReady }"
              hover-class="btn-pressed" @tap="joinByCode">
          {{ hasSeat ? (joinReady ? "补位加入本队" : "名额已满") : "名额已满" }}
        </view>
      </template>
    </view>

    <!-- 报名前规则确认 -->
    <view class="mask" v-if="showRules" @tap="showRules = false">
      <view class="sheet" @tap.stop>
        <view class="sheet-title">确认报名本次饭局</view>
        <view class="rule" v-for="(r, i) in rules" :key="i">· {{ r }}</view>
        <view class="sheet-actions">
          <view class="btn btn-ghost flex1" hover-class="btn-pressed" @tap="showRules = false">再看看</view>
          <view class="btn btn-primary flex1" :class="{ 'is-loading': busy }"
                hover-class="btn-pressed" @tap="doJoin">确认报名</view>
        </view>
      </view>
    </view>

    <!-- 成员信息卡片 -->
    <view class="mask" v-if="memberCard" @tap="memberCard = null">
      <view class="sheet info-card" @tap.stop>
        <view class="ic-head">
          <view class="avatar big">{{ memberCard.user.nickname.slice(0, 1) }}</view>
          <view class="ic-name">
            {{ memberCard.user.nickname }}
            <text class="st" :class="memberCard.role === 'leader' ? 'st-brand' : 'st-progress'">
              {{ memberCard.role === "leader" ? "队长" : "队员" }}
            </text>
          </view>
        </view>
        <view class="ic-row"><text class="ic-label">年龄</text><text>{{ memberCard.user.age }} 岁</text></view>
        <view class="ic-row"><text class="ic-label">性别</text><text>{{ genderText(memberCard.user.gender) }}</text></view>
        <view class="ic-note">平台仅展示以上信息，匿名拼桌不提供成员主页与真实身份。</view>
        <view class="ic-actions" v-if="memberCard.user_id && !isSelf(memberCard)">
          <view class="btn btn-danger btn-sm flex1" hover-class="btn-pressed" @tap="reportMember(memberCard)">举报</view>
          <view class="btn btn-ghost btn-sm flex1" hover-class="btn-pressed" @tap="blockMember(memberCard)">加入黑名单</view>
        </view>
        <view class="btn btn-primary btn-block" hover-class="btn-pressed" @tap="memberCard = null">知道了</view>
      </view>
    </view>
  </view>
</template>

<script>
import { get, post } from "../../utils/request";
import { on, subscribe, unsubscribe } from "../../utils/ws";
import { useAuthStore } from "../../stores/auth";
import { getMyLocation } from "../../utils/location";
import {
  countdownText, diningTimeText, distanceText, failReasonText, isPast, mealPeriodOf,
  parseTime, teamStatusMeta,
} from "../../utils/format";
import { toastOk, toast, confirm } from "../../utils/ui";

export default {
  data() {
    return {
      id: null,
      team: null,
      memberCard: null,
      busy: false,
      inviteCode: "",
      showRules: false,
      meCoord: null, // 我的坐标（距离展示用）
      rules: [
        "报名即占用一个名额，成团后请按时到店；无法赴约请在账单生效前退出。",
        "到店后在小程序内「确认到场」，全员（或超过用餐时间 2 小时）后账单生效。",
        "账单由队长录入，按实际到场人数均摊，未到场者不参与分摊。",
        "群聊内禁止骚扰、诈骗、引流等行为，违者将被限制并可能被移交处理。",
      ],
    };
  },
  computed: {
    isLeader() {
      return this.team && this.team.my_role === "leader";
    },
    isMember() {
      return !!(this.team && this.team.is_member);
    },
    seatPercent() {
      if (!this.team || !this.team.target_size) return 0;
      return Math.min(100, Math.round((this.team.current_size / this.team.target_size) * 100));
    },
    /** 进度条下方的文字提示：还需几人 / 已满 */
    seatHint() {
      if (!this.team || !this.team.target_size) return "";
      const left = this.team.target_size - this.team.current_size;
      return left > 0 ? `，还需 ${left} 人满员` : "，已满员";
    },
    isFull() {
      return !!(this.team && this.team.target_size && this.team.current_size >= this.team.target_size);
    },
    hasSeat() {
      return !!(this.team && this.team.remaining !== null && this.team.remaining > 0);
    },
    joinReady() {
      return !!this.inviteCode;
    },
    /** 菜品是否溢出需提示可横滑（约 3 张占满一屏） */
    dishOverflow() {
      return !!(this.team && this.team.dishes && this.team.dishes.length > 3);
    },
    expired() {
      return isPast(this.team && this.team.dining_time);
    },
    canJoin() {
      return !this.expired && !this.busy;
    },
    joinText() {
      if (this.expired) return "已过用餐时间，报名已关闭";
      return "立即报名";
    },
    status() {
      return teamStatusMeta(this.team && this.team.status, { isFull: this.isFull });
    },
    diningText() {
      return diningTimeText(this.team && this.team.dining_time) || "待定";
    },
    period() {
      return mealPeriodOf(this.team && this.team.dining_time);
    },
    distText() {
      return distanceText(this.team && this.team.restaurant, this.meCoord);
    },
    recruitCountdown() {
      if (!this.team || this.team.status !== "recruiting") return "";
      return countdownText(this.team.recruit_deadline || this.team.dining_time, { expired: "招募已截止" });
    },
    urgent() {
      const ts = parseTime((this.team && (this.team.recruit_deadline || this.team.dining_time)) || null);
      return ts != null && ts - Date.now() < 3 * 3600 * 1000;
    },
    me() {
      return useAuthStore().user;
    },
  },
  onLoad(options) {
    this.id = Number(options.id);
    // 分享卡片进入：只记录邀请码，由用户点击确认后才报名
    this.inviteCode = options.code || "";
    getMyLocation({ silent: true }).then((c) => { this.meCoord = c; });
  },
  onShow() {
    this.refresh();
    subscribe(["team:" + this.id]);
  },
  onUnload() {
    unsubscribe(["team:" + this.id]);
  },
  mounted() {
    on("team.member_joined", () => this.refresh());
    on("team.member_left", () => this.refresh());
    on("team.updated", () => this.refresh());
    on("team.formed", (e) => {
      if (e.data && e.data.team_id === this.id) {
        toastOk("队伍已满员自动成团");
        this.refresh();
      }
    });
    on("team.status_changed", () => this.refresh());
  },
  onShareAppMessage() {
    const canInvite = this.team && this.team.mode === "invite" && this.team.code;
    return {
      title: `约饭啦：${this.team ? this.team.name : "饭局"}，一起来！`,
      path: canInvite
        ? `/pages/team-detail/team-detail?id=${this.id}&code=${this.team.code}`
        : `/pages/team-detail/team-detail?id=${this.id}`,
    };
  },
  methods: {
    failReasonText,
    genderText(g) {
      return g === "male" ? "男" : g === "female" ? "女" : "保密";
    },
    isSelf(m) {
      return !!(m.user && this.me && m.user.nickname === this.me.nickname);
    },
    async refresh() {
      try {
        this.team = await get("/api/teams/" + this.id);
        if (this.team.is_member) {
          const auth = useAuthStore();
          subscribe(["user:" + (auth.user ? auth.user.id : 0)]);
        }
      } catch (e) {
        /* handled */
      }
    },
    showMember(m) {
      this.memberCard = m;
    },
    copyLink() {
      uni.setClipboardData({ data: this.team.code });
    },
    copyAddress() {
      uni.setClipboardData({ data: this.team.location_hint });
    },
    /** 变更类操作统一防抖：连点两次会产生重复请求与误导性的错误提示 */
    async run(fn) {
      if (this.busy) return;
      this.busy = true;
      try {
        await fn();
      } catch (e) {
        /* 错误提示已由请求层处理 */
      } finally {
        this.busy = false;
      }
    },
    askJoin() {
      if (!this.canJoin) {
        if (this.expired) toast("该饭局的用餐时间已过，无法报名");
        return;
      }
      this.showRules = true; // 二次确认 + 规则阅读
    },
    async doJoin() {
      await this.run(async () => {
        await post(`/api/teams/${this.id}/join`);
        this.showRules = false;
        toastOk("报名成功");
        await this.refresh();
      });
    },
    async joinByCode() {
      if (!this.inviteCode) {
        toast("请通过队长分享的链接进入才能补位");
        return;
      }
      await this.run(async () => {
        await post("/api/teams/join/" + this.inviteCode);
        toastOk("补位成功");
        await this.refresh();
      });
    },
    async leave() {
      const formed = this.team.status === "formed";
      const ok = await confirm({
        title: formed ? "退出已成团的饭局" : "退出报名",
        content: formed
          ? "退出后你不再参与本次账单分摊，名额将释放给其他用户。确定退出吗？"
          : "确定退出该饭局吗？退出后名额将释放给其他用户。",
        confirmText: "退出",
      });
      if (!ok) return;
      await this.run(async () => {
        await post(`/api/teams/${this.id}/leave`);
        toastOk("已退出");
        await this.refresh();
      });
    },
    async kickMember(m) {
      const name = m.user.nickname;
      const ok = await confirm({
        title: "移出队员",
        content: `确定将「${name}」移出队伍吗？移出后对方无法再次加入本队。`,
        confirmText: "移出",
      });
      if (!ok) return;
      await this.run(async () => {
        await post(`/api/teams/${this.id}/members/${m.user_id}/kick`);
        toastOk(`已移出「${name}」`);
        this.memberCard = null;
        await this.refresh();
      });
    },
    async disband() {
      const joined = this.team.current_size > 1;
      const ok = await confirm({
        title: "撤销饭局",
        content: joined
          ? `撤销后饭局立即下架，已报名的 ${this.team.current_size - 1} 位队友会收到通知。确定撤销吗？`
          : "确定撤销这场饭局吗？撤销后不可恢复。",
        confirmText: "撤销",
      });
      if (!ok) return;
      await this.run(async () => {
        await post(`/api/teams/${this.id}/disband`);
        toastOk("已撤销");
        setTimeout(() => uni.navigateBack(), 600);
      });
    },
    async closeInvite() {
      const ok = await confirm({
        title: "关闭邀请",
        content: "关闭后链接与邀请码将失效，确定吗？",
        confirmText: "关闭",
      });
      if (!ok) return;
      await this.run(async () => {
        await post(`/api/teams/${this.id}/invite/close`);
        toastOk("已关闭邀请");
        await this.refresh();
      });
    },
    async abort() {
      const ok = await confirm({
        title: "解散重开",
        content: "账单将作废，稍后可一键复制配置重开新局。确定？",
        confirmText: "确定",
      });
      if (!ok) return;
      await this.run(async () => {
        await post(`/api/teams/${this.id}/abort`);
        await this.refresh();
        const created = await post(`/api/teams/${this.id}/recreate`);
        uni.navigateTo({ url: "/pages/team-create/team-create?draftId=" + created.id });
      });
    },
    /** 更多菜单：把退出/解散等破坏性操作收进来，避免底部误点 */
    moreActions() {
      const items = [];
      const handlers = [];
      if (this.isLeader) {
        if (this.team.mode === "invite" && this.team.invite_open) {
          items.push("关闭邀请");
          handlers.push(this.closeInvite);
        }
        items.push("核销异常？解散重开");
        handlers.push(this.abort);
      } else if (this.team.can_leave) {
        items.push("退出队伍");
        handlers.push(this.leave);
      }
      if (!items.length) {
        toast("暂无可执行的操作");
        return;
      }
      items.push("取消");
      uni.showActionSheet({
        itemList: items,
        success: (res) => {
          const fn = handlers[res.tapIndex];
          if (fn) fn.call(this);
        },
        fail: () => {},
      });
    },
    reportMember(m) {
      const reasons = ["骚扰或言语冒犯", "疑似诈骗引流", "人身威胁", "其他违规"];
      const codes = ["harassment", "fraud", "abuse", "other"];
      uni.showActionSheet({
        itemList: reasons,
        success: async (res) => {
          try {
            await post("/api/reports", {
              target_user_id: m.user_id, team_id: this.id, reason: codes[res.tapIndex],
            });
            this.memberCard = null;
            toastOk("举报已受理");
          } catch (e) {
            /* handled */
          }
        },
        fail: () => {},
      });
    },
    async blockMember(m) {
      const ok = await confirm({
        title: "加入黑名单",
        content: "加入后你们互相看不到对方的饭局，对方也无法加入你的队伍。确定吗？",
        confirmText: "拉黑",
      });
      if (!ok) return;
      await this.run(async () => {
        await post("/api/blocks", { target_user_id: m.user_id, reason: "成员页拉黑" });
        this.memberCard = null;
        toastOk("已加入黑名单");
      });
    },
    goEdit() {
      uni.navigateTo({ url: "/pages/team-create/team-create?draftId=" + this.id + "&edit=1" });
    },
    goChat() {
      uni.navigateTo({ url: "/pages/chat/chat?id=" + this.id });
    },
    goBill() {
      uni.navigateTo({ url: "/pages/bill/bill?id=" + this.id });
    },
    goRestaurant() {
      if (!this.team || !this.team.restaurant) return;
      uni.navigateTo({ url: "/pages/restaurant-detail/restaurant-detail?id=" + this.team.restaurant.id });
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 200rpx; }
.row1 { display: flex; align-items: flex-start; }
.name { flex: 1; margin-right: 14rpx; }
.status-tag { flex-shrink: 0; margin-left: auto; }
.meta-row { display: flex; align-items: center; flex-wrap: wrap; gap: 10rpx; margin-top: 14rpx; }
.meta { margin-top: 12rpx; }

.progress-row { display: flex; align-items: center; margin-top: 22rpx; }
.progress-bg { flex: 1; height: 14rpx; background: #efeef6; border-radius: 7rpx; overflow: hidden; }
.progress-fg { height: 100%; background: #6c5ce7; border-radius: 7rpx; transition: width 0.3s; }
.progress-fg.full { background: #10b981; }
.seat-text { margin-left: 16rpx; color: #2d3436; font-size: 26rpx; font-weight: 700; min-width: 120rpx; text-align: right; }
/* 人数与倒计时分行：阅读更整齐 */
.progress-hint { display: flex; align-items: center; justify-content: space-between; margin-top: 10rpx; }
.progress-hint .muted { font-size: 22rpx; }
.countdown { font-size: 22rpx; color: #9aa0a6; }
.countdown.urgent { color: #ff7675; font-weight: 600; }

.notice { background: #f0eeff; }
.notice-title { font-weight: 700; color: #6c5ce7; margin-bottom: 8rpx; }

.rest-row { display: flex; align-items: center; }
.rest-thumb { width: 120rpx; height: 120rpx; border-radius: 14rpx; flex-shrink: 0; background: #efeef6; }
.rest-info { margin-left: 20rpx; flex: 1; min-width: 0; }
.rest-name { font-size: 30rpx; font-weight: 600; }
.rest-sub { margin-top: 8rpx; font-size: 24rpx; color: #b2b2b2; }
.rest-more { margin-top: 10rpx; font-size: 22rpx; color: #6c5ce7; }
.copy-btn {
  flex-shrink: 0; font-size: 22rpx; color: #6c5ce7; background: #f0eeff;
  padding: 8rpx 18rpx; border-radius: 24rpx; margin-left: 16rpx;
}

/* 菜品：横向滚动，尺寸统一，价格突出 */
.dish-scroll { white-space: nowrap; margin: 0 -8rpx; }
.dish-item { display: inline-block; width: 200rpx; margin: 0 8rpx; vertical-align: top; }
.dish-img { width: 200rpx; height: 150rpx; border-radius: 12rpx; background: #efeef6; display: block; }
.dish-name {
  margin-top: 10rpx; height: 34rpx; line-height: 34rpx; font-size: 24rpx; color: #2d3436;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dish-price { font-size: 28rpx; color: #ff7675; font-weight: 700; margin-top: 4rpx; height: 40rpx; line-height: 40rpx; }

.estimate { display: flex; flex-direction: column; gap: 8rpx; }
.est-row { display: flex; align-items: baseline; }
.est-label { font-size: 24rpx; color: #b2b2b2; flex: 1; }
.est-total { font-size: 36rpx; font-weight: 700; color: #6c5ce7; }
.est-per { font-size: 28rpx; font-weight: 600; color: #636e72; }
.est-note { margin-top: 4rpx; font-size: 22rpx; color: #b2b2b2; line-height: 1.6; }

.sub { font-weight: 400; }
.tip { margin-top: 8rpx; line-height: 1.6; }

.member-list { background: #fafafd; border-radius: 16rpx; padding: 6rpx 20rpx; }
.member { display: flex; align-items: center; padding: 18rpx 0; border-bottom: 2rpx solid #f0f0f5; }
.member:last-child { border-bottom: none; }
.avatar {
  width: 68rpx; height: 68rpx; border-radius: 50%; flex-shrink: 0;
  background: #f0eeff; color: #6c5ce7; font-size: 30rpx;
  display: flex; align-items: center; justify-content: center;
}
/* 队长头像高亮，与队员区分 */
.avatar.lead { background: #6c5ce7; color: #fff; }
.avatar.big { width: 88rpx; height: 88rpx; font-size: 38rpx; }
.m-info { flex: 1; margin-left: 20rpx; display: flex; flex-direction: column; }
.m-name { font-size: 28rpx; color: #2d3436; }
.m-info .muted { font-size: 22rpx; }
.kick { color: #ff7675; font-size: 26rpx; padding: 6rpx 12rpx; flex-shrink: 0; margin-left: 8rpx; }

.code { color: #6c5ce7; font-weight: 700; font-size: 32rpx; }
.btn-row { display: flex; gap: 16rpx; margin-top: 16rpx; flex-wrap: wrap; }
.flex1 { flex: 1; }
.icon-btn { display: flex; align-items: center; justify-content: center; gap: 10rpx; }
.ic { font-size: 30rpx; }
.btn-more {
  flex-shrink: 0; width: 88rpx; padding: 20rpx 0;
  background: #efeef6; color: #636e72; font-size: 34rpx; font-weight: 700;
}
.share-btn {
  flex: 1; background: #f0eeff; color: #6c5ce7; margin: 0;
  border-radius: 44rpx; font-size: 28rpx; line-height: 2.2;
}
.share-btn::after { border: none; }

.mask {
  position: fixed; left: 0; top: 0; right: 0; bottom: 0;
  background: rgba(45, 52, 54, 0.45); z-index: 99;
  display: flex; align-items: center; justify-content: center;
}
.sheet {
  width: 620rpx; background: #fff; border-radius: 24rpx; padding: 36rpx;
  box-sizing: border-box;
}
.sheet-title { font-size: 32rpx; font-weight: 700; margin-bottom: 20rpx; }
.rule { font-size: 25rpx; color: #636e72; line-height: 1.7; margin-bottom: 10rpx; }
.sheet-actions { display: flex; gap: 20rpx; margin-top: 28rpx; }

.info-card { width: 580rpx; }
.ic-head { display: flex; align-items: center; margin-bottom: 28rpx; }
.ic-name { margin-left: 20rpx; font-size: 32rpx; font-weight: 700; display: flex; align-items: center; gap: 12rpx; }
.ic-row { display: flex; align-items: center; margin-bottom: 16rpx; font-size: 28rpx; color: #2d3436; }
.ic-label { width: 120rpx; color: #b2b2b2; font-size: 26rpx; }
.ic-note { margin-top: 12rpx; font-size: 22rpx; color: #b2b2b2; line-height: 1.6; }
.ic-actions { display: flex; gap: 16rpx; margin: 24rpx 0 0; }
.ic-actions .btn { margin: 0; }
</style>
