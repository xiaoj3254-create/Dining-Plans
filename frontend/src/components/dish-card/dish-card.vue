<template>
  <view
    class="dish-card"
    :class="{ on: selected }"
    hover-class="btn-pressed"
    :hover-stay-time="100"
    @tap="$emit('toggle', dish)"
  >
    <view class="img-wrap">
      <image class="dish-img" :src="dish.image" mode="aspectFill" />
      <view class="check" v-if="selected">✓</view>
    </view>
    <view class="dish-name">{{ dish.name }}</view>
    <view class="dish-price">
      <text class="rmb">¥</text>{{ dish.price }}
    </view>
    <view class="dish-tags" v-if="tagList.length">
      <text class="dtag" v-for="t in tagList" :key="t">{{ t }}</text>
    </view>
  </view>
</template>

<script>
export default {
  name: "dish-card",
  props: {
    dish: { type: Object, required: true },
    selected: { type: Boolean, default: false },
  },
  computed: {
    tagList() {
      const t = this.dish.tags;
      if (!t) return [];
      return String(t).split(",").filter(Boolean).slice(0, 2);
    },
  },
};
</script>

<style scoped>
.dish-card {
  background: #fff; border-radius: 16rpx; padding: 14rpx;
  border: 2rpx solid transparent;
  box-shadow: 0 4rpx 14rpx rgba(45, 52, 54, 0.05);
  transition: border-color 0.15s, transform 0.12s;
}
.dish-card.on { border-color: #6c5ce7; background: #fbfaff; }
.img-wrap { position: relative; width: 100%; height: 150rpx; border-radius: 12rpx; overflow: hidden; }
.dish-img { width: 100%; height: 150rpx; background: #efeef6; }
/* 选中角标 */
.check {
  position: absolute; right: 8rpx; top: 8rpx;
  width: 36rpx; height: 36rpx; border-radius: 50%;
  background: #6c5ce7; color: #fff; font-size: 22rpx;
  display: flex; align-items: center; justify-content: center;
}
.dish-name {
  margin-top: 10rpx; font-size: 26rpx; color: #2d3436;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.dish-price { margin-top: 4rpx; color: #6c5ce7; font-size: 28rpx; font-weight: 700; }
.rmb { font-size: 20rpx; margin-right: 2rpx; }
.dish-tags { margin-top: 6rpx; display: flex; flex-wrap: wrap; }
.dtag {
  font-size: 18rpx; color: #a29bfe; background: #f0eeff;
  padding: 2rpx 8rpx; border-radius: 6rpx; margin-right: 6rpx;
}
</style>
