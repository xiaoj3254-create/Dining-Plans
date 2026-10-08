<template>
  <view class="page">
    <view
      v-for="t in list"
      :key="t.id"
      class="card item"
      hover-class="btn-pressed"
      @tap="goDetail(t)"
    >
      <view class="row1">
        <text class="t-h2 name">{{ t.name }}</text>
        <text class="st" :class="statusMeta(t).cls">{{ statusMeta(t).text }}</text>
      </view>
      <view class="muted line">{{ restaurantName(t) }} · {{ diningText(t) }}</view>
      <view class="bottom">
        <text class="seat">{{ t.current_size }}/{{ t.target_size || "?" }} 人</text>
        <text class="st st-brand">{{ t.my_role === "leader" ? "队长" : "队员" }}</text>
        <text class="muted mode">{{ t.mode === "anonymous" ? "匿名拼桌" : "链接邀请" }}</text>
        <text class="muted fail" v-if="t.status === 'failed'">{{ failReasonText(t.fail_reason) }}</text>
      </view>
    </view>

    <empty-state
      v-if="!loading && list.length === 0"
      type="plate"
      title="还没有历史饭局"
      desc="完成的约饭会归档到这里"
    >
      <view slot="action" class="empty-action">
        <view class="btn btn-primary" hover-class="btn-pressed" @tap="goPlaza">去广场看看</view>
      </view>
    </empty-state>

    <view class="muted center" v-if="loading">加载中…</view>
  </view>
</template>

<script>
import { get } from "../../utils/request";
import {
  diningTimeText, failReasonText, teamStatusMeta,
} from "../../utils/format";
import EmptyState from "../../components/empty-state/empty-state.vue";

export default {
  components: { EmptyState },
  data() {
    return { list: [], loading: false };
  },
  onShow() {
    this.refresh();
  },
  methods: {
    failReasonText,
    statusMeta(t) {
      return teamStatusMeta(t.status);
    },
    restaurantName(t) {
      return (t.restaurant && t.restaurant.name) || t.location_hint || "地点待定";
    },
    diningText(t) {
      return diningTimeText(t.dining_time) || "时间待定";
    },
    async refresh() {
      this.loading = true;
      try {
        const res = await get("/api/users/me/teams");
        const g = res.groups || {};
        this.list = (g.completed || []).concat(g.failed || []);
      } catch (e) {
        this.list = [];
      } finally {
        this.loading = false;
      }
    },
    goDetail(t) {
      uni.navigateTo({ url: "/pages/team-detail/team-detail?id=" + t.id });
    },
    goPlaza() {
      uni.switchTab({ url: "/pages/plaza/plaza" });
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 60rpx; }
.item { margin-bottom: 20rpx; }
.item.card { margin: 20rpx; }
.row1 { display: flex; align-items: center; }
.name { flex: 1; }
.line { margin-top: 12rpx; }
.bottom { display: flex; align-items: center; gap: 14rpx; margin-top: 16rpx; flex-wrap: wrap; }
.seat { font-size: 26rpx; font-weight: 600; color: #6c5ce7; }
.mode { font-size: 22rpx; }
.fail { font-size: 22rpx; }
.center { text-align: center; padding: 24rpx; }
</style>
