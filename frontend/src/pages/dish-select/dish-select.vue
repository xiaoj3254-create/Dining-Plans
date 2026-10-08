<template>
  <view class="page">
    <!-- 已选餐馆 -->
    <view class="rest-bar" v-if="restaurant">
      <image class="rest-thumb" :src="restaurant.image" mode="aspectFill" />
      <view class="rest-info">
        <view class="rest-name">{{ restaurant.name }}</view>
        <view class="rest-sub">
          {{ restaurant.cuisine_type }} · {{ restaurant.district || "商圈待定" }}
          <text v-if="restaurant.avg_price"> · 人均 ¥{{ restaurant.avg_price }}</text>
        </view>
      </view>
    </view>

    <!-- 菜品分类 -->
    <scroll-view scroll-x class="cat-bar" :show-scrollbar="false" v-if="categories.length">
      <view class="chip" :class="{ active: !category }" hover-class="btn-pressed" @tap="category = ''">全部</view>
      <view
        v-for="c in categories"
        :key="c"
        class="chip"
        :class="{ active: category === c }"
        hover-class="btn-pressed"
        @tap="category = category === c ? '' : c"
      >{{ c }}</view>
    </scroll-view>

    <!-- 菜品网格（多选） -->
    <view class="grid">
      <dish-card
        v-for="d in shownDishes"
        :key="d.id"
        class="grid-item"
        :dish="d"
        :selected="selectedIds.indexOf(d.id) !== -1"
        @toggle="toggle"
      />
    </view>

    <empty-state
      v-if="!shownDishes.length && !loading"
      type="plate"
      title="该餐馆暂无菜品"
      desc="可以直接返回，预选菜品为选填"
    />
    <view class="muted center" v-if="loading">加载中…</view>

    <!-- 底部汇总 + 操作 -->
    <view class="footer">
      <view class="sum">
        <text class="sum-count">已选 {{ selected.length }} 道</text>
        <text class="sum-price">预估 ¥{{ total }}</text>
      </view>
      <view class="btn-ghost btn act" hover-class="btn-pressed" @tap="confirmSkip">暂不选菜</view>
      <view class="btn-primary btn act" hover-class="btn-pressed" @tap="confirmPick">确定</view>
    </view>
  </view>
</template>

<script>
import { get } from "../../utils/request";
import { toast } from "../../utils/ui";
import { useMealStore } from "../../stores/meal";
import DishCard from "../../components/dish-card/dish-card.vue";
import EmptyState from "../../components/empty-state/empty-state.vue";

export default {
  components: { DishCard, EmptyState },
  data() {
    return {
      rid: null, restaurant: null, dishes: [], selected: [],
      category: "", loading: false, committed: false,
    };
  },
  computed: {
    selectedIds() {
      return this.selected.map((d) => d.id);
    },
    total() {
      return this.selected.reduce((sum, d) => sum + Number(d.price || 0), 0);
    },
    categories() {
      const set = [];
      this.dishes.forEach((d) => {
        if (d.category && set.indexOf(d.category) === -1) set.push(d.category);
      });
      return set;
    },
    shownDishes() {
      if (!this.category) return this.dishes;
      return this.dishes.filter((d) => d.category === this.category);
    },
  },
  onLoad(options) {
    this.rid = Number(options.rid);
    // 已选过同一家餐馆的菜 → 回显勾选
    const meal = useMealStore();
    if (meal.restaurant && meal.restaurant.id === this.rid) {
      this.selected = meal.dishes.slice();
    }
    this.refresh();
  },
  onUnload() {
    // 系统返回键离开时兜底回填（避免"选了餐馆却没带回去"）
    if (!this.committed && this.restaurant) {
      useMealStore().setSelection(this.restaurant, this.selected);
    }
  },
  methods: {
    async refresh() {
      this.loading = true;
      try {
        const res = await get(`/api/restaurants/${this.rid}`);
        this.restaurant = res;
        this.dishes = res.dishes || [];
      } catch (e) {
        /* handled */
      } finally {
        this.loading = false;
      }
    },
    toggle(d) {
      const i = this.selectedIds.indexOf(d.id);
      if (i === -1) {
        if (this.selected.length >= 20) {
          toast("最多选 20 道菜");
          return;
        }
        this.selected.push(d);
      } else {
        this.selected.splice(i, 1);
      }
    },
    /** 写入选择桥并跨两层返回发起页 */
    commit(dishes) {
      const meal = useMealStore();
      this.committed = true;
      meal.setSelection(this.restaurant, dishes);
      uni.navigateBack({ delta: 2 });
    },
    confirmPick() {
      this.commit(this.selected);
    },
    confirmSkip() {
      this.commit([]);
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 200rpx; }

.rest-bar {
  display: flex; align-items: center; background: #fff;
  padding: 22rpx 24rpx; box-shadow: 0 4rpx 14rpx rgba(45, 52, 54, 0.04);
}
.rest-thumb { width: 96rpx; height: 96rpx; border-radius: 14rpx; flex-shrink: 0; background: #efeef6; }
.rest-info { margin-left: 18rpx; flex: 1; min-width: 0; }
.rest-name { font-size: 30rpx; font-weight: 700; }
.rest-sub { margin-top: 6rpx; font-size: 24rpx; color: #b2b2b2; }

.cat-bar { white-space: nowrap; padding: 20rpx 20rpx 4rpx; }
.cat-bar::-webkit-scrollbar { display: none; }
.chip {
  display: inline-block; padding: 8rpx 24rpx; margin-right: 14rpx;
  border-radius: 28rpx; background: #efeef6; color: #636e72; font-size: 24rpx;
}
.chip.active { background: #6c5ce7; color: #fff; }

/* 菜品网格：三列自适应 */
.grid { display: flex; flex-wrap: wrap; padding: 16rpx 14rpx 0; }
.grid-item { width: calc(33.33% - 16rpx); margin: 0 8rpx 16rpx; box-sizing: border-box; }

.center { text-align: center; padding: 40rpx 20rpx; }

.footer {
  position: fixed; left: 0; right: 0; bottom: 0;
  margin: 0 auto; max-width: 480px;
  display: flex; align-items: center; gap: 14rpx;
  padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #fff; box-shadow: 0 -4rpx 16rpx rgba(45, 52, 54, 0.05);
}
.sum { flex: 1; display: flex; flex-direction: column; }
.sum-count { font-size: 24rpx; color: #b2b2b2; }
.sum-price { font-size: 30rpx; font-weight: 700; color: #6c5ce7; }
.btn { margin-top: 0; }
.act { padding: 18rpx 30rpx; font-size: 26rpx; flex-shrink: 0; }
</style>
