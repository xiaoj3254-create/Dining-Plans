<template>
  <view class="empty">
    <!-- 饭碗 + 筷子（广场无饭局） -->
    <view v-if="type === 'bowl'" class="illus">
      <view class="chopstick c1"></view>
      <view class="chopstick c2"></view>
      <view class="steam s1"></view>
      <view class="steam s2"></view>
      <view class="steam s3"></view>
      <view class="bowl"></view>
      <view class="dish"></view>
      <view class="shadow"></view>
    </view>

    <!-- 空餐盘 + 刀叉（我的组队空） -->
    <view v-else-if="type === 'plate'" class="illus plate-wrap">
      <view class="fork">
        <view class="fork-tine t1"></view>
        <view class="fork-tine t2"></view>
        <view class="fork-tine t3"></view>
        <view class="fork-body"></view>
      </view>
      <view class="plate"></view>
      <view class="knife"></view>
      <view class="shadow"></view>
    </view>

    <!-- 消息气泡（消息通知空） -->
    <view v-else-if="type === 'bubble'" class="illus">
      <view class="bb bb1">
        <view class="dot o"></view>
        <view class="dot o d2"></view>
        <view class="dot o d3"></view>
      </view>
      <view class="bb bb2">
        <view class="dot g"></view>
        <view class="dot g d2"></view>
        <view class="dot g d3"></view>
      </view>
    </view>

    <!-- 放大镜（筛选/搜索无结果） -->
    <view v-else class="illus">
      <view class="mag"><view class="mag-handle"></view></view>
    </view>

    <view class="e-title">{{ title }}</view>
    <view v-if="desc" class="e-desc">
      <view v-for="(line, i) in descLines" :key="i" class="e-line">{{ line }}</view>
    </view>
    <view v-if="note" class="e-note">{{ note }}</view>
    <slot name="action"></slot>
  </view>
</template>

<script>
export default {
  name: "empty-state",
  props: {
    type: { type: String, default: "bowl" }, // bowl | plate | bubble | mag
    title: { type: String, default: "" },
    desc: { type: String, default: "" },
    note: { type: String, default: "" },
  },
  computed: {
    descLines() {
      // 支持 "/" 分行，避免模板里出现转义 \n
      return this.desc ? this.desc.split("|") : [];
    },
  },
};
</script>

<style scoped>
.empty { text-align: center; padding: 60rpx 0 80rpx; }
.illus { position: relative; width: 220rpx; height: 210rpx; margin: 50rpx auto 20rpx; }

/* ---------- 饭碗 ---------- */
.bowl {
  position: absolute; left: 30rpx; top: 100rpx; width: 160rpx; height: 80rpx;
  background: #c5bfff; border-radius: 0 0 160rpx 160rpx;
}
.bowl::before {
  content: ""; position: absolute; top: -14rpx; left: -18rpx; right: -18rpx;
  height: 26rpx; background: #a29bfe; border-radius: 14rpx;
}
.chopstick { position: absolute; width: 12rpx; height: 92rpx; background: #a29bfe; border-radius: 6rpx; }
.chopstick.c1 { left: 118rpx; top: 0; transform: rotate(22deg); }
.chopstick.c2 { left: 158rpx; top: -10rpx; transform: rotate(38deg); }
.steam {
  position: absolute; width: 10rpx; height: 32rpx;
  background: #e0e3e8; border-radius: 6rpx;
  animation: steam 2.2s ease-in-out infinite alternate;
}
.steam.s1 { left: 66rpx; top: 26rpx; }
.steam.s2 { left: 100rpx; top: 12rpx; animation-delay: 0.4s; }
.steam.s3 { left: 134rpx; top: 30rpx; animation-delay: 0.8s; }
@keyframes steam {
  from { transform: translateY(0); opacity: 0.4; }
  to { transform: translateY(-10rpx); opacity: 1; }
}
.dish {
  position: absolute; left: 8rpx; top: 168rpx; width: 56rpx; height: 20rpx;
  background: #f0eeff; border-radius: 10rpx;
}
.dish::after {
  content: ""; position: absolute; right: -96rpx; top: -6rpx;
  width: 64rpx; height: 44rpx; background: #f0eeff; border-radius: 0 0 64rpx 64rpx;
}
.shadow {
  position: absolute; left: 20rpx; right: 20rpx; top: 196rpx; height: 16rpx;
  background: #e9ebee; border-radius: 50%;
}

/* ---------- 空餐盘 ---------- */
.plate-wrap { width: 260rpx; height: 210rpx; }
.plate {
  position: absolute; left: 50rpx; top: 30rpx;
  width: 160rpx; height: 160rpx; border-radius: 50%;
  background: #fff; border: 12rpx solid #c5bfff; box-sizing: border-box;
}
.plate::after {
  content: ""; position: absolute; left: 18rpx; top: 18rpx;
  width: 92rpx; height: 92rpx; border-radius: 50%;
  border: 6rpx solid #f0eeff; box-sizing: border-box;
}
.fork { position: absolute; left: 22rpx; top: 34rpx; width: 16rpx; height: 150rpx; }
.fork-tine {
  position: absolute; top: 0; width: 6rpx; height: 36rpx;
  background: #d6dae0; border-radius: 4rpx;
}
.fork-tine.t1 { left: 0; }
.fork-tine.t2 { left: 5rpx; }
.fork-tine.t3 { left: 10rpx; }
.fork-body {
  position: absolute; top: 30rpx; left: 3rpx; width: 10rpx; height: 120rpx;
  background: #d6dae0; border-radius: 6rpx;
}
.knife {
  position: absolute; right: 22rpx; top: 34rpx;
  width: 18rpx; height: 150rpx;
  background: #d6dae0; border-radius: 10rpx 10rpx 8rpx 8rpx;
}
.knife::before {
  content: ""; position: absolute; top: -2rpx; left: 0;
  width: 18rpx; height: 62rpx;
  background: #e8ebee; border-radius: 10rpx 10rpx 4rpx 4rpx;
}
.plate-wrap .shadow { left: 30rpx; right: 30rpx; top: 196rpx; }

/* ---------- 消息气泡 ---------- */
.bb {
  position: absolute; display: flex; align-items: center; justify-content: center;
  gap: 10rpx; height: 90rpx; border-radius: 34rpx;
}
.bb1 {
  left: 10rpx; top: 30rpx; width: 170rpx; background: #f0eeff;
}
.bb1::after {
  content: ""; position: absolute; left: 36rpx; bottom: -14rpx;
  width: 0; height: 0;
  border-left: 16rpx solid transparent; border-right: 16rpx solid transparent;
  border-top: 18rpx solid #f0eeff;
}
.bb2 {
  left: 70rpx; top: 140rpx; width: 130rpx; height: 74rpx; background: #f2f3f5;
}
.bb2::after {
  content: ""; position: absolute; right: 32rpx; top: -14rpx;
  width: 0; height: 0;
  border-left: 14rpx solid transparent; border-right: 14rpx solid transparent;
  border-bottom: 16rpx solid #f2f3f5;
}
.dot { width: 14rpx; height: 14rpx; border-radius: 50%; }
.dot.o { background: #a29bfe; }
.dot.g { background: #c0c4cc; }
.dot.d2 { animation: blink 1.6s ease-in-out infinite alternate; }
.dot.d3 { animation: blink 1.6s ease-in-out 0.5s infinite alternate; }
@keyframes blink {
  from { opacity: 0.35; }
  to { opacity: 1; }
}

/* ---------- 放大镜 ---------- */
.mag {
  position: relative; width: 110rpx; height: 110rpx;
  border: 12rpx solid #d6dae0; border-radius: 50%;
  margin: 60rpx auto 30rpx;
}
.mag-handle {
  position: absolute; right: -34rpx; bottom: -30rpx;
  width: 52rpx; height: 12rpx; background: #d6dae0;
  border-radius: 8rpx; transform: rotate(45deg);
}

/* ---------- 文案 ---------- */
.e-title { font-size: 32rpx; font-weight: 700; color: #636e72; }
.e-desc { margin-top: 16rpx; color: #b2b2b2; font-size: 26rpx; line-height: 1.7; }
.e-note { margin-top: 12rpx; color: #b2b2b2; font-size: 24rpx; line-height: 1.6; padding: 0 80rpx; }
</style>
