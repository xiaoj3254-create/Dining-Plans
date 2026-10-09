<template>
  <view class="page page-tab" :class="{ 'tab-in': tabAnim }">
    <!-- 顶部 Hero：品牌感头部 -->
    <view class="hero">
      <text class="hero-kicker">{{ locationDenied ? "定位未开启" : "正在你身边" }}</text>
      <view class="hero-title">约饭广场</view>
      <view class="hero-sub">找到同频的人，把一顿饭约成一次相遇</view>
    </view>

    <!-- 筛选区（两行：模式单选 / 菜系·时段·距离多选横滑），卡片压在 Hero 圆角上 -->
    <view class="filters hero-overlap">
      <!-- 第一行：组队模式（单选） + 说明 + 搜索 -->
      <view class="frow">
        <scroll-view scroll-x class="fscroll" :show-scrollbar="false">
          <view class="chip" :class="{ active: !mode }" hover-class="btn-pressed" @tap="setMode('')">全部</view>
          <view class="chip" :class="{ active: mode === 'anonymous' }" hover-class="btn-pressed" @tap="setMode('anonymous')">匿名拼桌</view>
          <view class="chip" :class="{ active: mode === 'invite' }" hover-class="btn-pressed" @tap="setMode('invite')">链接邀请</view>
        </scroll-view>
        <view class="qmark" @tap="showTip = true">?</view>
        <view class="qmark search" @tap="toggleSearch">
          <image class="s-ico" src="/static/icons/search.png" mode="aspectFit" />
        </view>
      </view>

      <!-- 第二行：菜系（多选）+ 用餐时段（多选）+ 距离（单选）+ 排序 -->
      <scroll-view scroll-x class="fscroll second" :show-scrollbar="false">
        <view class="chip" :class="{ active: !pickedCuisines.length }" hover-class="btn-pressed" @tap="clearCuisines">全部菜系</view>
        <view
          v-for="c in cuisines"
          :key="c"
          class="chip"
          :class="{ active: pickedCuisines.indexOf(c) !== -1 }"
          hover-class="btn-pressed"
          @tap="toggleCuisine(c)"
        >{{ c }}</view>

        <view class="vline"></view>

        <view
          v-for="p in periodOptions"
          :key="p.key"
          class="chip"
          :class="{ active: pickedPeriods.indexOf(p.key) !== -1 }"
          hover-class="btn-pressed"
          @tap="togglePeriod(p.key)"
        >{{ p.label }}</view>

        <view class="vline"></view>

        <view class="chip" :class="{ active: maxDistance == null }" hover-class="btn-pressed" @tap="setDistance(null)">不限距离</view>
        <view
          v-for="d in distanceOptions"
          :key="d"
          class="chip"
          :class="{ active: maxDistance === d }"
          hover-class="btn-pressed"
          @tap="setDistance(d)"
        >{{ d }}km 内</view>

        <view class="vline"></view>

        <view class="chip" :class="{ active: sort === 'time' }" hover-class="btn-pressed" @tap="setSort('time')">按时间</view>
        <view class="chip" :class="{ active: sort === 'distance' }" hover-class="btn-pressed" @tap="setSort('distance')">按距离</view>
      </scroll-view>

      <!-- 已选条件回执：多选后可一眼看清筛了什么，并可一键清空 -->
      <view class="picked" v-if="hasFilter">
        <text class="picked-text">已筛选 {{ pickedCount }} 项</text>
        <text class="picked-clear" hover-class="btn-pressed" @tap="clearAllFilters">清空筛选</text>
      </view>

      <!-- 搜索框 -->
      <view class="search-row" v-if="searchOpen">
        <input class="s-input" v-model="keyword" confirm-type="search" @confirm="doSearch"
               placeholder="搜索餐馆/饭局名称" />
        <view class="s-btn" hover-class="btn-pressed" @tap="doSearch">搜索</view>
        <view class="s-cancel" v-if="keyword" hover-class="btn-pressed" @tap="clearSearch">清除</view>
      </view>

      <!-- 定位状态提示 -->
      <view class="loc-tip" v-if="locationDenied" @tap="retryLocation">
        未获取到定位，「距离」相关筛选暂不可用，点击重试
      </view>

      <!-- 模式说明浮层 -->
      <view class="tip-mask" v-if="showTip" @tap="showTip = false">
        <view class="tip-card" @tap.stop>
          <view class="tip-title">两种组队模式的区别？</view>
          <view class="tip-item">
            <text class="tip-tag anon">匿名拼桌</text>
            <text>组队内成员互相不可查看身份，仅展示年龄、性别；非成员看不到成员名单。</text>
          </view>
          <view class="tip-item">
            <text class="tip-tag invite">链接邀请</text>
            <text>生成分享链接，邀请好友加入组队，成团后也可用链接补位。</text>
          </view>
          <view class="tip-close" @tap="showTip = false">我知道了</view>
        </view>
      </view>
    </view>

    <!-- 饭局卡片流 -->
    <team-card
      v-for="t in teams"
      :key="t.id"
      :team="t"
      :me="me"
      :joining-id="joiningId"
      @click="goDetail(t.id)"
      @join="onJoin(t)"
    />

    <!-- 空状态 1：筛选/搜索无结果 -->
    <empty-state
      v-if="!loading && teams.length === 0 && hasFilter"
      type="mag"
      title="没有找到匹配的饭局"
      desc="换个筛选条件|或清空筛选查看全部饭局"
    >
      <view slot="action" class="empty-action">
        <view class="btn btn-ghost" hover-class="btn-pressed" @tap="clearAllFilters">清空筛选</view>
      </view>
    </empty-state>

    <!-- 空状态 2：广场无饭局 → 给出发起引导，减少流失 -->
    <empty-state
      v-else-if="!loading && teams.length === 0"
      type="bowl"
      title="还没有饭局在招募"
      desc="当今天的饭桌发起人|等大家来报名"
    >
      <view slot="action" class="empty-action">
        <view class="btn btn-primary" hover-class="btn-pressed" @tap="goCreate">＋ 发起饭局</view>
      </view>
    </empty-state>

    <view class="loading-block" v-if="loading && !teams.length">
      <view class="spinner"></view>
      <text>正在找附近的饭局…</text>
    </view>
    <view class="list-foot" v-else-if="loading">加载中…</view>
    <view class="list-foot" v-else-if="loadMoreError" @tap="loadMore">
      <text class="retry">加载失败，点击重试</text>
    </view>
    <!-- 到底收尾：轻量插画 + 短文案，避免一行干文字 -->
    <view class="list-end" v-else-if="teams.length && finished">
      <view class="le-dots"><view class="d"></view><view class="d"></view><view class="d"></view></view>
      <text class="le-text">没有更多饭局了，去发起一场吧</text>
    </view>

    <!-- 悬浮发起按钮 -->
    <view class="fab" hover-class="fab-pressed" :hover-stay-time="120" @tap="goCreate">＋ 发起饭局</view>
  </view>
</template>

<script>
import { get, post } from "../../utils/request";
import { on, subscribe } from "../../utils/ws";
import { useAuthStore } from "../../stores/auth";
import { CUISINES } from "../../utils/constants";
import { getMyLocation } from "../../utils/location";
import { toast } from "../../utils/ui";
import TeamCard from "../../components/team-card/team-card.vue";
import EmptyState from "../../components/empty-state/empty-state.vue";

export default {
  components: { TeamCard, EmptyState },
  data() {
    return {
      teams: [],
      page: 1,
      pageSize: 10,
      total: 0,
      loading: false,
      finished: false,
      loadMoreError: false,
      cuisines: CUISINES,
      periodOptions: [
        { key: "lunch", label: "午市" },
        { key: "dinner", label: "晚市" },
      ],
      mode: "",
      pickedCuisines: [],
      pickedPeriods: [],
      maxDistance: null,
      sort: "time",
      distanceOptions: [1, 3, 5, 10],
      searchOpen: false,
      keyword: "",
      showTip: false,
      tabAnim: false,
      me: null, // 我的坐标（距离展示与排序用）
      locationDenied: false,
      joiningId: null, // 正在报名的队伍 id（按钮 loading + 防重复提交）
      visible: false,
    };
  },
  computed: {
    hasFilter() {
      return !!(this.mode || this.pickedCuisines.length || this.pickedPeriods.length
        || this.maxDistance || this.keyword);
    },
    pickedCount() {
      return this.pickedCuisines.length + this.pickedPeriods.length
        + (this.maxDistance ? 1 : 0) + (this.mode ? 1 : 0) + (this.keyword ? 1 : 0);
    },
  },
  onLoad() {
    // plaza.changed 是 at-least-once 广播（worker 重试会重发），这里做 300ms 合并
    on("plaza.changed", () => this.scheduleRefresh());
    uni.$on("auth:changed", () => this.reload());
    this.initLocation();
  },
  onShow() {
    this.visible = true;
    const auth = useAuthStore();
    if (auth.isVerified) {
      this.refresh();
      subscribe(["plaza"]);
    }
    this.playTabAnim();
  },
  onHide() {
    this.visible = false;
  },
  onPullDownRefresh() {
    this.refresh().finally(() => uni.stopPullDownRefresh());
  },
  onReachBottom() {
    this.loadMore();
  },
  methods: {
    /** 定位只在进入页面时请求一次；失败不阻塞任何功能 */
    async initLocation() {
      const coord = await getMyLocation({ silent: true });
      this.me = coord;
      this.locationDenied = !coord;
    },
    async retryLocation() {
      const coord = await getMyLocation({ force: true, silent: false });
      this.me = coord;
      this.locationDenied = !coord;
      if (coord) this.reload();
    },
    scheduleRefresh() {
      clearTimeout(this._refreshTimer);
      this._refreshTimer = setTimeout(() => this.refresh(), 300);
    },
    playTabAnim() {
      this.tabAnim = false;
      setTimeout(() => {
        this.tabAnim = true;
      }, 30);
    },
    setMode(m) {
      this.mode = m;
      this.reload();
    },
    /** 菜系多选：选中集合内切换，"全部菜系"清空 */
    toggleCuisine(c) {
      const i = this.pickedCuisines.indexOf(c);
      if (i === -1) this.pickedCuisines.push(c);
      else this.pickedCuisines.splice(i, 1);
      this.reload();
    },
    clearCuisines() {
      if (!this.pickedCuisines.length) return;
      this.pickedCuisines = [];
      this.reload();
    },
    /** 用餐时段多选：午市 + 晚市可同时选 */
    togglePeriod(p) {
      const i = this.pickedPeriods.indexOf(p);
      if (i === -1) this.pickedPeriods.push(p);
      else this.pickedPeriods.splice(i, 1);
      this.reload();
    },
    async setDistance(d) {
      if (d != null && !this.me) {
        const coord = await getMyLocation({ force: true, silent: false });
        this.me = coord;
        this.locationDenied = !coord;
        if (!coord) return; // 拿不到定位就不启用距离筛选
      }
      // 距离是"上限值"，多选无意义，保持单选
      this.maxDistance = d;
      if (d != null) this.sort = "distance";
      this.reload();
    },
    async setSort(s) {
      if (s === "distance" && !this.me) {
        const coord = await getMyLocation({ force: true, silent: false });
        this.me = coord;
        this.locationDenied = !coord;
        if (!coord) return;
      }
      this.sort = s;
      this.reload();
    },
    toggleSearch() {
      this.searchOpen = !this.searchOpen;
      if (!this.searchOpen && this.keyword) {
        this.keyword = "";
        this.reload();
      }
    },
    doSearch() {
      this.reload();
    },
    clearSearch() {
      this.keyword = "";
      this.reload();
    },
    clearAllFilters() {
      this.mode = "";
      this.pickedCuisines = [];
      this.pickedPeriods = [];
      this.maxDistance = null;
      this.sort = "time";
      this.keyword = "";
      this.reload();
    },
    buildQs(page) {
      let qs = `?page=${page}&page_size=${this.pageSize}&sort=${this.sort}`;
      if (this.mode) qs += `&mode=${this.mode}`;
      if (this.pickedCuisines.length) {
        qs += `&cuisine=${encodeURIComponent(this.pickedCuisines.join(","))}`;
      }
      if (this.pickedPeriods.length) qs += `&meal_period=${this.pickedPeriods.join(",")}`;
      if (this.maxDistance) qs += `&max_distance_km=${this.maxDistance}`;
      if (this.keyword) qs += `&keyword=${encodeURIComponent(this.keyword)}`;
      if (this.me) qs += `&lat=${this.me.latitude}&lng=${this.me.longitude}`;
      return qs;
    },
    reload() {
      this.page = 1;
      this.finished = false;
      return this.refresh();
    },
    async refresh() {
      this.loading = true;
      this.loadMoreError = false;
      try {
        const res = await get("/api/plaza/teams" + this.buildQs(1));
        this.teams = res.teams;
        this.total = res.total;
        this.page = 1;
        this.finished = !res.has_more;
      } catch (e) {
        this.teams = [];
        this.loadMoreError = true;
      } finally {
        this.loading = false;
      }
    },
    async loadMore() {
      if (this.finished || this.loading) return;
      this.loading = true;
      this.loadMoreError = false;
      try {
        const res = await get("/api/plaza/teams" + this.buildQs(this.page + 1));
        this.teams = this.teams.concat(res.teams);
        this.page += 1;
        this.finished = !res.has_more;
      } catch (e) {
        this.loadMoreError = true;
      } finally {
        this.loading = false;
      }
    },
    /** 报名：按钮 loading + 成功后进详情 */
    async onJoin(team) {
      if (this.joiningId != null) return;
      this.joiningId = team.id;
      try {
        await post(`/api/teams/${team.id}/join`);
        toast("报名成功");
        setTimeout(() => {
          uni.navigateTo({ url: "/pages/team-detail/team-detail?id=" + team.id });
        }, 500);
      } catch (e) {
        /* 错误提示已由请求层处理 */
      } finally {
        this.joiningId = null;
      }
    },
    goDetail(id) {
      uni.navigateTo({ url: "/pages/team-detail/team-detail?id=" + id });
    },
    goCreate() {
      uni.navigateTo({ url: "/pages/team-create/team-create" });
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 160rpx; }

/* ---------- 筛选区：白色圆角卡压在 Hero 上 ---------- */
.filters {
  background: #fff; padding: 20rpx 0 14rpx;
  margin: 0 20rpx 8rpx; border-radius: 24rpx;
  box-shadow: 0 8rpx 24rpx rgba(45, 52, 54, 0.05);
}
.frow { display: flex; align-items: center; padding: 0 20rpx; margin-bottom: 12rpx; }
.fscroll { flex: 1; white-space: nowrap; }
.second { padding: 0 20rpx; }
.fscroll ::-webkit-scrollbar,
.fscroll::-webkit-scrollbar { display: none; width: 0; height: 0; background: transparent; }
.chip {
  display: inline-block; padding: 10rpx 28rpx; margin-right: 16rpx;
  border-radius: 32rpx; background: #f3f3f7; color: #636e72; font-size: 25rpx;
}
.chip.active { background: #6c5ce7; color: #fff; font-weight: 600; box-shadow: 0 4rpx 12rpx rgba(108, 92, 231, 0.25); }
.vline {
  display: inline-block; width: 2rpx; height: 26rpx; background: #e6e6ef;
  margin: 0 16rpx 0 2rpx; vertical-align: middle;
}

.qmark {
  width: 52rpx; height: 52rpx; line-height: 52rpx; text-align: center; flex-shrink: 0;
  margin-left: 10rpx; border-radius: 50%; background: #efeef6; color: #636e72; font-size: 26rpx;
}
.qmark.search { display: flex; align-items: center; justify-content: center; }
.s-ico { width: 30rpx; height: 30rpx; }

/* 已选条件回执 */
.picked {
  display: flex; align-items: center; justify-content: space-between;
  padding: 4rpx 24rpx 8rpx;
}
.picked-text { font-size: 22rpx; color: #b2b2b2; }
.picked-clear { font-size: 22rpx; color: #6c5ce7; padding: 4rpx 12rpx; }

.search-row { display: flex; align-items: center; padding: 0 20rpx 12rpx; gap: 14rpx; }
.s-input { flex: 1; background: #efeef6; border-radius: 30rpx; padding: 14rpx 24rpx; font-size: 26rpx; }
.s-btn { color: #6c5ce7; font-size: 28rpx; font-weight: 600; }
.s-cancel { color: #b2b2b2; font-size: 26rpx; }

.loc-tip {
  margin: 0 20rpx 12rpx; padding: 12rpx 18rpx; border-radius: 12rpx;
  background: #fdf1e3; color: #d98b26; font-size: 22rpx; line-height: 1.5;
}

/* 模式说明浮层 */
.tip-mask {
  position: fixed; left: 0; top: 0; right: 0; bottom: 0;
  background: rgba(45, 52, 54, 0.45); z-index: 99;
  display: flex; align-items: center; justify-content: center;
}
.tip-card { width: 600rpx; background: #fff; border-radius: 20rpx; padding: 36rpx; box-sizing: border-box; }
.tip-title { font-size: 32rpx; font-weight: 700; margin-bottom: 24rpx; }
.tip-item { display: flex; margin-bottom: 20rpx; font-size: 26rpx; color: #636e72; line-height: 1.65; }
.tip-tag { flex-shrink: 0; height: 40rpx; line-height: 40rpx; padding: 0 16rpx; border-radius: 8rpx; font-size: 22rpx; margin-right: 16rpx; }
.tip-tag.anon { background: #e6f8f2; color: #10b981; }
.tip-tag.invite { background: #fdf1e3; color: #d98b26; }
.tip-close {
  margin-top: 12rpx; text-align: center; padding: 18rpx 0;
  background: #6c5ce7; color: #fff; border-radius: 40rpx; font-size: 28rpx;
}

/* 悬浮发起按钮：阴影收紧，避免视觉过重 */
.fab {
  position: fixed; right: 32rpx; bottom: calc(60rpx + env(safe-area-inset-bottom));
  background: #6c5ce7; color: #fff; font-size: 28rpx; font-weight: 600;
  padding: 20rpx 32rpx; border-radius: 48rpx;
  box-shadow: 0 6rpx 16rpx rgba(108, 92, 231, 0.28); z-index: 20;
}
.fab-pressed { background: #5a4bd1; transform: scale(0.96); }
</style>
