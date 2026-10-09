<template>
  <view class="page page-with-footer" v-if="rest">
    <!-- 头图 -->
    <view class="hero">
      <image class="hero-img" :src="rest.image" mode="aspectFill" lazy-load />
      <view class="hero-mask"></view>
      <view class="hero-info">
        <text class="hero-name">{{ rest.name }}</text>
        <view class="hero-tags">
          <text class="tag light" v-if="rest.cuisine_type">{{ rest.cuisine_type }}</text>
          <text class="tag light" v-if="rest.district">{{ rest.district }}</text>
          <text class="tag light" v-if="rest.avg_price">人均 ¥{{ rest.avg_price }}</text>
        </view>
      </view>
    </view>

    <!-- 简介 -->
    <view class="card">
      <view class="card-title">餐馆简介</view>
      <view class="desc">{{ rest.description || "这家餐馆还没有填写简介。" }}</view>
      <view class="stat-row">
        <view class="stat">
          <text class="stat-num">{{ rest.dish_count || (rest.dishes || []).length }}</text>
          <text class="stat-label">菜品</text>
        </view>
        <view class="stat">
          <text class="stat-num">{{ rest.avg_price ? "¥" + rest.avg_price : "—" }}</text>
          <text class="stat-label">人均</text>
        </view>
        <view class="stat">
          <text class="stat-num">{{ rest.cuisine_type || "—" }}</text>
          <text class="stat-label">菜系</text>
        </view>
      </view>
    </view>

    <!-- 菜品清单 -->
    <view class="card">
      <view class="card-title">菜品清单<text class="muted sub" v-if="dishes.length">（{{ dishes.length }} 道）</text></view>
      <view class="dish-list" v-if="dishes.length">
        <view class="dish" v-for="d in dishes" :key="d.id">
          <image class="dish-img" :src="d.image" mode="aspectFill" lazy-load />
          <view class="dish-body">
            <view class="dish-name">{{ d.name }}</view>
            <view class="dish-tags">
              <text class="muted tiny" v-if="d.category">{{ d.category }}</text>
              <text class="muted tiny" v-for="(t, i) in (d.tags || [])" :key="i">{{ t }}</text>
            </view>
          </view>
          <text class="dish-price">¥{{ d.price }}</text>
        </view>
      </view>
      <view class="muted" v-else>该餐馆暂未录入菜品。</view>
    </view>

    <!-- 底部：以该餐馆发起饭局 -->
    <view class="safe-fixed-bottom">
      <view class="btn btn-primary flex1" hover-class="btn-pressed" @tap="startTeam">＋ 以此餐馆发起饭局</view>
    </view>
  </view>

  <view class="card" v-else>
    <view class="section-title">暂时无法查看</view>
    <view class="muted">{{ emptyHint }}</view>
    <view class="btn-ghost btn" hover-class="btn-pressed" @tap="refresh">重新加载</view>
  </view>
</template>

<script>
import { get } from "../../utils/request";
import { useMealStore } from "../../stores/meal";
import { toast } from "../../utils/ui";

export default {
  data() {
    return {
      id: null,
      rest: null,
      emptyHint: "正在加载…",
    };
  },
  computed: {
    dishes() {
      return (this.rest && this.rest.dishes) || [];
    },
  },
  onLoad(options) {
    this.id = Number(options.id);
  },
  onShow() {
    this.refresh();
  },
  methods: {
    async refresh() {
      try {
        const res = await get("/api/restaurants/" + this.id);
        this.rest = res;
        this.emptyHint = "";
        uni.setNavigationBarTitle({ title: res.name || "餐馆简介" });
      } catch (e) {
        this.rest = null;
        this.emptyHint = "读不到这家餐馆的信息，可能已下架。";
      }
    },
    /** 带着餐馆信息去发起饭局（team-create 会在 onShow 消费选择桥回填） */
    startTeam() {
      if (!this.rest) return;
      const meal = useMealStore();
      meal.setSelection(
        {
          id: this.rest.id,
          name: this.rest.name,
          cuisine_type: this.rest.cuisine_type,
          district: this.rest.district,
          image: this.rest.image,
          avg_price: this.rest.avg_price,
        },
        []
      );
      toast("已带入餐馆，继续填写饭局信息");
      setTimeout(() => {
        uni.navigateTo({ url: "/pages/team-create/team-create" });
      }, 300);
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 180rpx; }

.hero { position: relative; height: 360rpx; background: #efeef6; border-radius: 0 0 36rpx 36rpx; overflow: hidden; }
.hero-img { width: 100%; height: 100%; }
.hero-mask {
  position: absolute; left: 0; right: 0; bottom: 0; height: 200rpx;
  background: linear-gradient(to top, rgba(20, 16, 40, 0.65), rgba(20, 16, 40, 0));
}
.hero-info { position: absolute; left: 24rpx; right: 24rpx; bottom: 24rpx; }
.hero-name { color: #fff; font-size: 40rpx; font-weight: 700; }
.hero-tags { display: flex; gap: 12rpx; margin-top: 12rpx; flex-wrap: wrap; }
.tag.light { background: rgba(255, 255, 255, 0.22); color: #fff; margin: 0; }

.desc { font-size: 26rpx; color: #636e72; line-height: 1.7; }
.stat-row { display: flex; margin-top: 22rpx; padding-top: 22rpx; border-top: 2rpx solid #efeef6; }
.stat { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 6rpx; }
.stat-num { font-size: 30rpx; font-weight: 700; color: #6c5ce7; }
.stat-label { font-size: 22rpx; color: #b2b2b2; }

.sub { font-weight: 400; }
.dish-list { display: flex; flex-direction: column; }
.dish { display: flex; align-items: center; padding: 18rpx 0; border-bottom: 2rpx solid #f2f2f7; }
.dish:last-child { border-bottom: none; }
.dish-img { width: 110rpx; height: 110rpx; border-radius: 12rpx; flex-shrink: 0; background: #efeef6; }
.dish-body { flex: 1; margin-left: 20rpx; min-width: 0; }
.dish-name { font-size: 28rpx; color: #2d3436; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dish-tags { display: flex; gap: 12rpx; margin-top: 8rpx; flex-wrap: wrap; }
.tiny { font-size: 21rpx; }
.dish-price { font-size: 30rpx; font-weight: 700; color: #ff7675; flex-shrink: 0; margin-left: 12rpx; }

.flex1 { flex: 1; }
.section-title { font-weight: 700; margin-bottom: 12rpx; font-size: 30rpx; }
.btn { margin-top: 20rpx; }
</style>
