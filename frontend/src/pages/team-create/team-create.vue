<template>
  <view class="page">
    <!-- ========== 区块：基本信息 ========== -->
    <view class="block">
      <view class="block-head">基本信息</view>
      <view class="card">
        <!-- 队伍名 -->
        <view class="form-row">
          <text class="label">队伍名 <text class="req">*</text></text>
          <input class="input" :class="{ bad: errors.name }" v-model="form.name" maxlength="50"
                 placeholder="如：周五晚火锅局" @blur="attempted = true" />
        </view>
        <view class="field-error" v-if="errors.name">{{ errors.name }}</view>

        <!-- 目标人数 -->
        <view class="form-row">
          <text class="label">目标人数 <text class="req">*</text></text>
          <view class="slider-row">
            <slider
              class="slider"
              :min="2"
              :max="20"
              :value="form.target_size"
              activeColor="#6c5ce7"
              block-color="#6c5ce7"
              :block-size="20"
              @changing="onSizeChange"
              @change="onSizeChange"
            />
            <view class="num-box">{{ form.target_size }}<text class="unit">人</text></view>
          </view>
        </view>
        <view class="slider-hint">最少 2 人（含你自己，招募 1 位以上队友）</view>

        <!-- 餐馆 -->
        <view class="form-row">
          <text class="label">餐馆 <text class="req">*</text></text>
          <view class="pick-row" :class="{ bad: errors.restaurant }" hover-class="btn-pressed" @tap="goRestaurant">
            <view class="pick-main" v-if="form.restaurant">
              <image class="pick-thumb" :src="form.restaurant.image" mode="aspectFill" />
              <view class="pick-text">
                <text class="pick-name">{{ form.restaurant.name }}</text>
                <text class="pick-sub">
                  {{ form.restaurant.cuisine_type }} · {{ form.restaurant.district || "商圈待定" }}
                </text>
              </view>
            </view>
            <text class="pick-hint" v-else>选择就餐餐馆</text>
            <text class="pick-arrow">›</text>
          </view>
        </view>
        <view class="field-error" v-if="errors.restaurant">{{ errors.restaurant }}</view>
        <!-- 菜品与商圈由餐馆自动带出，无需手动填写 -->
        <view class="auto-fill" v-if="form.restaurant">
          已自动带出：{{ form.cuisine_type || "菜系待定" }} · {{ form.location_hint || "商圈待定" }}
        </view>

        <!-- 菜系兜底：仅当餐馆未带出菜系时才需要手填 -->
        <view class="form-row" v-if="form.restaurant && !form.restaurant.cuisine_type">
          <text class="label">就餐品类 <text class="req">*</text></text>
          <input class="input" :class="{ bad: errors.cuisine }" v-model="form.cuisine_type" maxlength="30"
                 placeholder="该餐馆未标注菜系，请补充" @blur="attempted = true" />
        </view>
        <view class="field-error" v-if="errors.cuisine">{{ errors.cuisine }}</view>

        <!-- 预选菜品 + 菜品备注（合并为一个模块，减少填写负担） -->
        <view class="form-row column">
          <text class="label">预选菜品</text>
          <view class="pick-row" :class="{ disabled: !form.restaurant_id }" hover-class="btn-pressed" @tap="goDishes">
            <text class="pick-hint" v-if="!form.dishes.length">选填，可提前定好菜单</text>
            <view class="dish-summary" v-else>
              <image
                v-for="d in form.dishes.slice(0, 3)"
                :key="d.id"
                class="mini-thumb"
                :src="d.image"
                mode="aspectFill"
              />
              <text class="dish-count">已选 {{ form.dishes.length }} 道 · 预估 ¥{{ dishTotal }}</text>
            </view>
            <text class="pick-arrow">›</text>
          </view>
          <input class="input note-input" v-model="form.menu_summary" maxlength="500"
                 placeholder="菜品备注，如：毛肚必点、有人忌辣（选填）" />
        </view>

        <!-- 就餐时间：日期 + 时间（支付宝原生选择器） -->
        <view class="form-row">
          <text class="label">就餐时间 <text class="req">*</text></text>
          <view class="time-row">
            <picker mode="date" :start="minDate" @change="(e) => (form.date = e.detail.value)">
              <view class="input picker" :class="{ bad: errors.time }">{{ form.date || "选择日期" }}</view>
            </picker>
            <picker mode="time" @change="(e) => (form.time = e.detail.value)">
              <view class="input picker" :class="{ bad: errors.time }">{{ form.time || "选择时间" }}</view>
            </picker>
          </view>
        </view>
        <view class="field-error" v-if="errors.time">{{ errors.time }}</view>
      </view>
    </view>

    <!-- ========== 区块：组队模式 ========== -->
    <view class="block">
      <view class="block-head">组队模式</view>
      <view class="card">
        <radio-group @change="onModeChange" class="mode-row">
          <label class="mode-item" :class="{ on: form.mode === 'anonymous', locked: editMode }">
            <radio value="anonymous" :checked="form.mode === 'anonymous'" :disabled="editMode" color="#6c5ce7" />
            <view class="mode-text">
              <text class="mode-name">匿名拼桌</text>
              <text class="mode-sub">广场公开报名，队员互相仅可见年龄性别</text>
            </view>
          </label>
          <label class="mode-item" :class="{ on: form.mode === 'invite', locked: editMode }">
            <radio value="invite" :checked="form.mode === 'invite'" :disabled="editMode" color="#6c5ce7" />
            <view class="mode-text">
              <text class="mode-name">链接邀请</text>
              <text class="mode-sub">可分享链接邀请好友，成团后也能补位</text>
            </view>
          </label>
        </radio-group>
        <view class="mode-tip" v-if="editMode">
          饭局已发布，组队模式不可更改（避免已发出去的邀请码语义混乱）。
        </view>
        <view class="mode-tip">
          {{ form.mode === "anonymous"
            ? "匿名模式：仅广场报名，队内互相只能看到年龄性别，禁止查看主页。"
            : "链接邀请模式：广场报名 + 分享链接邀请好友补位，仅队长可关闭邀请。" }}
        </view>
      </view>
    </view>

    <!-- 底部操作：固定底栏 + 安全边距，防手势条遮挡 -->
    <view class="footer">
      <view
        class="btn-ghost btn flex1"
        v-if="draftId && !editMode"
        hover-class="btn-pressed"
        @tap="saveDraft"
      >仅保存草稿</view>
      <view
        class="btn-primary btn flex1"
        :class="{ disabled: !canSubmit || submitting }"
        hover-class="btn-pressed"
        @tap="submit"
      >{{ submitting ? "提交中…" : submitLabel }}</view>
    </view>
  </view>
</template>

<script>
import { get, post, patch } from "../../utils/request";
import { toast, toastOk } from "../../utils/ui";
import { useMealStore } from "../../stores/meal";

function buildPayload(form) {
  if (!form.date || !form.time) return null;
  return {
    name: form.name,
    mode: form.mode,
    target_size: form.target_size,
    cuisine_type: form.cuisine_type,
    menu_summary: form.menu_summary,
    location_hint: form.location_hint,
    restaurant_id: form.restaurant_id,
    dish_ids: form.dishes.map((d) => d.id),
    dining_time: `${form.date}T${form.time}:00`,
  };
}

export default {
  data() {
    return {
      draftId: null,
      editMode: false,
      submitting: false,
      // attempted：用户已尝试提交过 → 空值字段也标红（避免一进页面就飘红）
      attempted: false,
      form: {
        name: "",
        mode: "invite",
        target_size: 4,
        cuisine_type: "",
        menu_summary: "",
        location_hint: "",
        date: "",
        time: "",
        restaurant_id: null,
        restaurant: null,
        dishes: [],
      },
    };
  },
  computed: {
    /** 日期选择下限：今天（避免用户选出过去时间，提交后才被后端 422 驳回） */
    minDate() {
      const d = new Date();
      const p = (n) => String(n).padStart(2, "0");
      return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}`;
    },
    /** 本地即可给出的时间校验，错误文案与后端一致 */
    timeError() {
      if (!this.form.date || !this.form.time) return "";
      const ts = new Date(`${this.form.date}T${this.form.time}:00`).getTime();
      if (Number.isNaN(ts)) return "就餐时间格式不正确";
      if (ts <= Date.now()) return "计划就餐时间必须晚于当前时间";
      return "";
    },
    /** 字段级错误：有输入但非法 → 实时提示；空值 → 提交后再提示 */
    errors() {
      const e = {};
      const name = (this.form.name || "").trim();
      if (name && name.length < 2) e.name = "队伍名至少 2 个字";
      else if (this.attempted && !name) e.name = "请填写队伍名";

      if (this.attempted && !this.form.restaurant_id) e.restaurant = "请选择就餐餐馆";

      const needCuisine = !!this.form.restaurant && !this.form.restaurant.cuisine_type;
      if (needCuisine && this.attempted && !(this.form.cuisine_type || "").trim()) {
        e.cuisine = "请补充就餐品类";
      }

      if (this.timeError) e.time = this.timeError;
      else if (this.attempted && (!this.form.date || !this.form.time)) e.time = "请选择就餐日期与时间";
      return e;
    },
    submitLabel() {
      if (this.editMode) return "保存修改";
      return this.draftId ? "保存并发布" : "创建并发布";
    },
    /** 必填项校验：队伍名 / 目标人数 / 餐馆 / 就餐品类 / 就餐时间，全满足才可提交 */
    canSubmit() {
      return !!(
        this.form.name.trim().length >= 2 &&
        this.form.target_size >= 2 &&
        this.form.restaurant_id &&
        this.form.cuisine_type.trim() &&
        this.form.date &&
        this.form.time &&
        !this.timeError
      );
    },
    dishTotal() {
      return this.form.dishes.reduce((sum, d) => sum + Number(d.price || 0), 0);
    },
    firstError() {
      const e = this.errors;
      return e.name || e.restaurant || e.cuisine || e.time || "";
    },
  },
  onLoad(options) {
    if (options.draftId) {
      this.draftId = Number(options.draftId);
      if (options.edit === "1") this.editMode = true;
      this.loadDraft();
    }
  },
  onShow() {
    // 从「选餐馆 → 选菜」返回：消费选择桥回填
    const meal = useMealStore();
    const sel = meal.takePending();
    if (sel) this.applySelection(sel);
    if (this.editMode) uni.setNavigationBarTitle({ title: "修改饭局" });
  },
  methods: {
    /** 回填餐馆与预选菜品，并自动带出品类/商圈（不再需要用户手动填） */
    applySelection(sel) {
      this.form.restaurant = sel.restaurant;
      this.form.restaurant_id = sel.restaurant.id;
      this.form.dishes = sel.dishes || [];
      if (sel.restaurant.cuisine_type) this.form.cuisine_type = sel.restaurant.cuisine_type;
      if (sel.restaurant.district) this.form.location_hint = sel.restaurant.district;
    },
    goRestaurant() {
      uni.navigateTo({ url: "/pages/restaurant-select/restaurant-select" });
    },
    goDishes() {
      if (!this.form.restaurant_id) {
        toast("请先选择餐馆");
        return;
      }
      uni.navigateTo({ url: "/pages/dish-select/dish-select?rid=" + this.form.restaurant_id });
    },
    onSizeChange(e) {
      this.form.target_size = e.detail.value;
    },
    onModeChange(e) {
      this.form.mode = e.detail.value;
    },
    async loadDraft() {
      const d = await get("/api/teams/" + this.draftId);
      // 已是「招募中」的饭局 → 按"修改模式"处理：保存后不重新发布，组队模式也不可改
      if (d.status === "recruiting") this.editMode = true;
      this.form = {
        name: d.name,
        mode: d.mode,
        target_size: d.target_size || 4,
        cuisine_type: d.cuisine_type || "",
        menu_summary: d.menu_summary || "",
        location_hint: d.location_hint || "",
        date: d.dining_time ? d.dining_time.slice(0, 10) : "",
        time: d.dining_time ? d.dining_time.slice(11, 16) : "",
        restaurant_id: d.restaurant ? d.restaurant.id : null,
        restaurant: d.restaurant || null,
        dishes: (d.dishes || []).map((x) => ({
          id: x.dish_id, name: x.name, price: x.price, image: x.image,
        })),
      };
    },
    /** 后端会把已下架的菜品从预选菜单里剔除并回报，这里如实提示用户 */
    warnRemoved(res) {
      if (res && res.removed_dishes && res.removed_dishes.length) {
        uni.showModal({
          title: "部分菜品已下架",
          content: `已自动移除：${res.removed_dishes.join("、")}。其余设置已保存。`,
          showCancel: false,
        });
      }
    },
    async saveDraft() {
      if (this.submitting || !this.draftId) return;
      this.submitting = true;
      try {
        const p = buildPayload(this.form);
        const res = await patch("/api/teams/" + this.draftId, p || { name: this.form.name });
        this.warnRemoved(res);
        toastOk("草稿已保存");
      } catch (e) {
        /* handled */
      } finally {
        this.submitting = false;
      }
    },
    async submit() {
      if (this.submitting) return; // 防重复点击
      this.attempted = true; // 触发空值字段的标红提示
      const p = buildPayload(this.form);
      if (!p) {
        toast("请选择就餐日期与时间");
        return;
      }
      if (this.firstError || !this.canSubmit) {
        toast(this.firstError || "请完善必填信息");
        return;
      }
      this.submitting = true;
      try {
        if (this.editMode) {
          // 修改已发布的饭局：只保存，不重新发布；队友会收到变更通知
          const res = await patch("/api/teams/" + this.draftId, p);
          this.warnRemoved(res);
          toastOk("修改已保存，队友已收到通知");
          setTimeout(() => uni.navigateBack(), 600);
          return;
        }
        let teamId;
        if (this.draftId) {
          const res = await patch("/api/teams/" + this.draftId, p);
          this.warnRemoved(res);
          teamId = this.draftId;
          await post(`/api/teams/${teamId}/publish`);
        } else {
          const created = await post("/api/teams", p);
          this.warnRemoved(created);
          teamId = created.id;
          await post(`/api/teams/${teamId}/publish`);
        }
        uni.redirectTo({ url: "/pages/team-detail/team-detail?id=" + teamId });
      } catch (e) {
        /* handled */
      } finally {
        this.submitting = false;
      }
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 200rpx; }

/* 两大区块之间留白，区分感更强 */
.block { margin-bottom: 36rpx; }
.block:last-of-type { margin-bottom: 0; }
.block-head {
  font-size: 32rpx; font-weight: 700; color: #2d3436;
  padding: 26rpx 24rpx 0;
}

.form-row { display: flex; align-items: center; margin-bottom: 26rpx; flex-wrap: wrap; }
.form-row:last-child { margin-bottom: 0; }
.form-row.column { flex-direction: column; align-items: stretch; }
.form-row.column .label { width: auto; margin-bottom: 14rpx; }
.label { width: 150rpx; color: #636e72; flex-shrink: 0; }
.req { color: #ff7675; }
.input {
  flex: 1; background: #efeef6; border-radius: 12rpx;
  padding: 16rpx 20rpx; font-size: 28rpx;
}
.input.bad, .pick-row.bad { background: #fff0f0; }
.picker { color: #636e72; margin-right: 12rpx; min-width: 180rpx; }
.time-row { flex: 1; display: flex; align-items: center; }

/* 关键字段错误：紧跟字段下方的红字提示 */
.field-error {
  width: 100%; color: #ff7675; font-size: 23rpx; line-height: 1.5;
  padding-left: 150rpx; margin: -16rpx 0 20rpx;
}
.form-row.column + .field-error { padding-left: 0; }

.pick-row {
  flex: 1; display: flex; align-items: center;
  background: #efeef6; border-radius: 12rpx; padding: 12rpx 16rpx;
  min-height: 72rpx; transition: background 0.15s;
}
.pick-row.disabled { opacity: 0.5; }
.pick-main { flex: 1; display: flex; align-items: center; min-width: 0; }
.pick-thumb { width: 64rpx; height: 64rpx; border-radius: 10rpx; flex-shrink: 0; background: #e4e3f0; }
.pick-text { margin-left: 14rpx; display: flex; flex-direction: column; min-width: 0; }
.pick-name {
  font-size: 28rpx; color: #2d3436;
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.pick-sub { font-size: 22rpx; color: #b2b2b2; margin-top: 4rpx; }
.pick-hint { flex: 1; font-size: 26rpx; color: #b2b2b2; }
.pick-arrow { color: #b2b2b2; font-size: 34rpx; margin-left: 10rpx; }

.auto-fill {
  width: 100%; font-size: 22rpx; color: #6c5ce7; background: #f0eeff;
  border-radius: 10rpx; padding: 10rpx 16rpx; margin: -12rpx 0 22rpx;
}
.dish-summary { flex: 1; display: flex; align-items: center; }
.mini-thumb {
  width: 56rpx; height: 56rpx; border-radius: 10rpx;
  margin-right: 8rpx; background: #e4e3f0; flex-shrink: 0;
}
.dish-count { font-size: 24rpx; color: #6c5ce7; font-weight: 600; margin-left: 6rpx; }
.note-input { margin-top: 14rpx; }

/* 滑块与人数框对齐；数字加大更醒目 */
.slider-row { flex: 1; display: flex; align-items: center; }
.slider { flex: 1; margin: 0 8rpx 0 0; }
.num-box {
  min-width: 116rpx; text-align: center; flex-shrink: 0;
  background: #f0eeff; color: #6c5ce7; font-size: 36rpx; font-weight: 700;
  padding: 6rpx 0; border-radius: 12rpx;
}
.num-box .unit { font-size: 22rpx; font-weight: 400; margin-left: 4rpx; }
.slider-hint { color: #b2b2b2; font-size: 22rpx; padding-left: 150rpx; margin: -14rpx 0 24rpx; }

/* 组队模式卡片（说明文字字号缩小，避免拥挤） */
.mode-row { display: flex; flex-direction: column; gap: 18rpx; }
.mode-item {
  display: flex; align-items: center;
  background: #f7f7fc; border: 2rpx solid #efeef6; border-radius: 16rpx;
  padding: 20rpx 18rpx; transition: border-color 0.15s, background 0.15s;
}
.mode-item.on { border-color: #6c5ce7; background: #f0eeff; }
.mode-item.locked { opacity: 0.7; }
.mode-text { display: flex; flex-direction: column; margin-left: 8rpx; }
.mode-name { font-size: 28rpx; color: #2d3436; }
.mode-sub { font-size: 21rpx; color: #b2b2b2; margin-top: 4rpx; line-height: 1.5; }
.mode-tip { margin-top: 18rpx; font-size: 22rpx; color: #b2b2b2; line-height: 1.7; }

/* 底部固定操作栏：预留安全边距 */
.footer {
  position: fixed; left: 0; right: 0; bottom: 0;
  margin: 0 auto; max-width: 480px;
  display: flex; gap: 20rpx;
  padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #fff; box-shadow: 0 -4rpx 16rpx rgba(45, 52, 54, 0.05);
}
.btn { margin-top: 0; }
.flex1 { flex: 1; }
/* 必填未满足 / 提交中：置灰禁用 */
.btn.disabled { opacity: 0.45; pointer-events: none; }
</style>
