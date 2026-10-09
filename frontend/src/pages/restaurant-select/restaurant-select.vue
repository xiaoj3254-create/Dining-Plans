<template>
  <view class="page">
    <!-- 搜索 + 菜系筛选 -->
    <view class="filters">
      <view class="search-row">
        <input
          class="s-input"
          v-model="keyword"
          confirm-type="search"
          placeholder="搜索餐馆名 / 菜系 / 商圈"
          @confirm="refresh"
        />
        <view class="s-btn" hover-class="btn-pressed" @tap="refresh">搜索</view>
        <view class="s-cancel" v-if="keyword" hover-class="btn-pressed" @tap="clearKeyword">清除</view>
      </view>
      <scroll-view scroll-x class="fscroll" :show-scrollbar="false">
        <view class="chip" :class="{ active: !cuisine }" hover-class="btn-pressed" @tap="setCuisine('')">全部菜系</view>
        <view
          v-for="c in cuisines"
          :key="c"
          class="chip"
          :class="{ active: cuisine === c }"
          hover-class="btn-pressed"
          @tap="setCuisine(c)"
        >{{ c }}</view>
      </scroll-view>
    </view>

    <!-- 餐馆列表 -->
    <view
      v-for="r in restaurants"
      :key="r.id"
      class="rest-card"
      hover-class="card-hover"
      :hover-stay-time="120"
      @tap="choose(r)"
    >
      <image class="rest-img" :src="r.image" mode="aspectFill" />
      <view class="rest-info">
        <view class="rest-top">
          <text class="rest-name">{{ r.name }}</text>
          <text class="tag tag-orange">{{ r.cuisine_type }}</text>
        </view>
        <view class="rest-desc" v-if="r.description">{{ r.description }}</view>
        <view class="rest-meta">
          <text class="meta-item">{{ r.district || "商圈待定" }}</text>
          <text class="meta-item">{{ r.dish_count }} 道菜</text>
          <text class="meta-item price" v-if="r.avg_price">人均 ¥{{ r.avg_price }}</text>
        </view>
      </view>
    </view>

    <empty-state
      v-if="!restaurants.length && !loading"
      type="plate"
      title="没有找到餐馆"
      desc="换个菜系或关键词试试"
    />
    <view class="muted center" v-if="loading">加载中…</view>
  </view>
</template>

<script>
import { get } from "../../utils/request";
import { CUISINES } from "../../utils/constants";
import EmptyState from "../../components/empty-state/empty-state.vue";

export default {
  components: { EmptyState },
  data() {
    return { restaurants: [], cuisines: CUISINES, cuisine: "", keyword: "", loading: false };
  },
  onLoad() {
    this.refresh();
  },
  methods: {
    setCuisine(c) {
      this.cuisine = this.cuisine === c ? "" : c;
      this.refresh();
    },
    clearKeyword() {
      this.keyword = "";
      this.refresh();
    },
    async refresh() {
      this.loading = true;
      try {
        let qs = `?page=1&page_size=50`;
        if (this.cuisine) qs += `&cuisine=${encodeURIComponent(this.cuisine)}`;
        if (this.keyword) qs += `&keyword=${encodeURIComponent(this.keyword)}`;
        const res = await get("/api/restaurants" + qs);
        this.restaurants = res.restaurants;
      } catch (e) {
        /* handled */
      } finally {
        this.loading = false;
      }
    },
    /** 选中餐馆 → 进入选菜页（选完一并回填发起页） */
    choose(r) {
      uni.navigateTo({ url: "/pages/dish-select/dish-select?rid=" + r.id });
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 40rpx; }
.filters { background: #fff; padding: 16rpx 0 16rpx; }
.search-row { display: flex; align-items: center; gap: 14rpx; padding: 4rpx 20rpx 14rpx; }
.s-input { flex: 1; background: #f3f3f7; border-radius: 32rpx; padding: 12rpx 24rpx; font-size: 26rpx; }
.s-btn { color: #6c5ce7; font-size: 26rpx; font-weight: 600; }
.s-cancel { color: #b2b2b2; font-size: 26rpx; }
.fscroll { white-space: nowrap; padding: 0 20rpx; }
.fscroll::-webkit-scrollbar { display: none; }
.chip {
  display: inline-block; padding: 10rpx 28rpx; margin-right: 16rpx;
  border-radius: 32rpx; background: #f3f3f7; color: #636e72; font-size: 26rpx;
}
.chip.active { background: #6c5ce7; color: #fff; font-weight: 600; box-shadow: 0 4rpx 12rpx rgba(108, 92, 231, 0.25); }

.rest-card {
  display: flex; background: #fff; border-radius: 24rpx; padding: 22rpx;
  margin: 20rpx 20rpx 0; box-shadow: 0 8rpx 24rpx rgba(45, 52, 54, 0.05);
  transition: transform 0.15s ease, box-shadow 0.15s ease;
}
.card-hover { transform: translateY(-6rpx); box-shadow: 0 14rpx 30rpx rgba(108, 92, 231, 0.16); }
.rest-img { width: 150rpx; height: 150rpx; border-radius: 18rpx; flex-shrink: 0; background: #efeef6; }
.rest-info { flex: 1; margin-left: 20rpx; min-width: 0; }
.rest-top { display: flex; align-items: center; }
.rest-name {
  flex: 1; font-size: 30rpx; font-weight: 600;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rest-desc {
  margin-top: 8rpx; font-size: 24rpx; color: #b2b2b2;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.rest-meta { margin-top: 14rpx; display: flex; flex-wrap: wrap; }
.meta-item { font-size: 24rpx; color: #636e72; margin-right: 20rpx; }
.meta-item.price { color: #6c5ce7; font-weight: 600; }
.center { text-align: center; padding: 40rpx 20rpx; }
</style>
