<template>
  <view class="page">
    <block v-if="data">
      <!-- 到场确认 -->
      <view class="card">
        <view class="section-head">
          <text class="card-title">到场确认</text>
          <view class="qmark" hover-class="btn-pressed" @tap="showRules = true">?</view>
        </view>
        <view class="muted tip">
          到店后点「确认到场」完成核销。全员确认（或超过用餐时间 {{ graceHours }} 小时）后账单生效，
          按实际到场人数均摊，未到场者不参与。
        </view>
        <view class="checkin-list" v-if="data.checkins">
          <view v-for="(c, i) in data.checkins.items" :key="i" class="checkin-item">
            <view class="avatar" :class="{ on: c.checked }">{{ c.user.nickname.slice(0, 1) }}</view>
            <text class="c-name">{{ c.user.nickname }}</text>
            <text class="c-state" :class="c.checked ? 'done' : 'undone'">
              {{ c.checked ? "已到场" : "未到场" }}
            </text>
          </view>
        </view>
        <view class="muted" v-else>{{ data.checkinHint }}</view>

        <!-- 核销码：放大 + 可复制，方便线下核验 -->
        <view class="my-code" v-if="myCode && !myChecked">
          <view class="code-box">
            <text class="muted">我的核销码</text>
            <text class="code">{{ myCode }}</text>
          </view>
          <view class="code-actions">
            <view class="btn btn-quiet btn-sm" hover-class="btn-pressed" @tap="copyCode">复制</view>
            <view class="btn btn-primary btn-sm" :class="{ 'is-loading': busy }"
                  hover-class="btn-pressed" @tap="doCheckin">确认到场</view>
          </view>
        </view>
        <view class="muted center" v-else-if="myChecked">你已完成到场确认。</view>
      </view>

      <!-- 规则弹窗 -->
      <view class="mask" v-if="showRules" @tap="showRules = false">
        <view class="sheet" @tap.stop>
          <view class="sheet-title">核销与分摊规则</view>
          <view class="rule">· 每人在小程序内出示自己的核销码并点「确认到场」，即视为已到场。</view>
          <view class="rule">· 全部成员确认到场，或超过用餐时间 {{ graceHours }} 小时，到场确认窗口关闭。</view>
          <view class="rule">· 窗口关闭后账单生效：总额由队长录入，按**实际到场人数**均摊。</view>
          <view class="rule">· 未到场者不参与分摊，也不会出现在结算名单中。</view>
          <view class="rule">· 各自独立结账，互不垫付；账单生效后不可再修改金额，也不可退出队伍。</view>
          <view class="btn btn-primary btn-block" hover-class="btn-pressed" @tap="showRules = false">我知道了</view>
        </view>
      </view>

      <!-- 账单 -->
      <view class="card">
        <view class="section-title">账单</view>

        <!-- 已生效：展示分摊明细 -->
        <template v-if="hasBill">
          <view class="bill-status">
            <text class="tag" :class="billClass(data.bill.status)">{{ billText(data.bill.status) }}</text>
            <text v-if="data.bill.per_capita" class="per">人均 ¥{{ data.bill.per_capita }}</text>
          </view>
          <view class="pay-list">
            <view v-for="(p, i) in data.bill.payments" :key="i" class="pay-item">
              <text>{{ p.user.nickname }}{{ p.is_me ? "（我）" : "" }}</text>
              <view class="right">
                <text class="amount">¥{{ p.amount }}</text>
                <text class="st" :class="p.status === 'paid' ? 'st-done' : 'st-notice'">
                  {{ p.status === "paid" ? "已支付" : "待支付" }}
                </text>
              </view>
            </view>
          </view>
          <view class="muted tip" v-if="!data.bill.i_am_payer">
            你未参与本次分摊（未完成到场确认），因此没有你的结算记录。
          </view>
          <view class="btn-primary btn" v-if="myUnpaid" :class="{ disabled: paying }"
                hover-class="btn-pressed" @tap="pay">{{ paying ? "支付中…" : "我 来 结 账" }}</view>
          <view class="muted center" v-if="paying">模拟支付处理中，请稍候…</view>
        </template>

        <!-- 未生效：队长录入 / 修改 -->
        <template v-else>
          <view class="muted">队长尚未录入账单总额。</view>
          <view class="form-row" v-if="isLeader">
            <input class="input" v-model="totalAmount" type="digit" placeholder="账单总额，如 300" />
            <view class="btn-primary btn-sm" :class="{ disabled: busy || !totalAmount }"
                  hover-class="btn-pressed" @tap="submitBill">录入</view>
          </view>
          <view class="muted tip" v-if="!isLeader">到店后由队长统一录入账单。</view>
        </template>

        <!-- 已录但未生效：修改（真编辑，不再是"赋值后立刻提交"） -->
        <view class="form-row" v-if="isLeader && isEditable">
          <text class="muted">当前总额 ¥{{ data.bill.total_amount }}，</text>
          <text class="edit" @tap="editBill">修改金额</text>
        </view>
        <view class="form-row" v-if="isLeader && editing">
          <input class="input" v-model="totalAmount" type="digit" focus placeholder="新的账单总额" />
          <view class="btn-primary btn-sm" :class="{ disabled: busy || !totalAmount }"
                hover-class="btn-pressed" @tap="submitBill">保存</view>
          <view class="btn-ghost btn-sm" hover-class="btn-pressed" @tap="cancelEdit">取消</view>
        </view>
        <view class="muted tip" v-if="isLeader && isEditable && !editing">
          账单生效后将不可再修改；如需调整请在全员到场或核销截止前完成。
        </view>
      </view>

      <view class="muted center" v-if="data.bill && data.bill.status === 'settled'">
        🎉 全员结清，本次约饭圆满完成！
      </view>
    </block>

    <!-- 空态：不再整页空白 -->
    <view class="card" v-else>
      <view class="section-title">暂时无法查看</view>
      <view class="muted">{{ emptyHint }}</view>
      <view class="btn-ghost btn" hover-class="btn-pressed" @tap="refresh">重新加载</view>
    </view>
  </view>
</template>

<script>
import { get, post } from "../../utils/request";
import { on, subscribe } from "../../utils/ws";

export default {
  data() {
    return {
      id: null,
      data: null,
      myCode: "",
      myChecked: false,
      totalAmount: "",
      paying: false,
      busy: false,
      editing: false,
      showRules: false,
      emptyHint: "正在加载…",
      graceHours: 2,
    };
  },
  computed: {
    isLeader() {
      return this.data && this.data.team && this.data.team.my_role === "leader";
    },
    hasBill() {
      return !!(this.data && this.data.bill && this.data.bill.status !== "none");
    },
    isEditable() {
      return !!(
        this.data &&
        this.data.bill &&
        this.data.bill.status === "pending" &&
        this.data.bill.total_amount
      );
    },
    myUnpaid() {
      return (
        this.data &&
        this.data.bill &&
        this.data.bill.status === "locked" &&
        this.data.bill.payments.some((p) => p.is_me && p.status === "unpaid")
      );
    },
  },
  onLoad(options) {
    this.id = Number(options.id);
    subscribe(["team:" + this.id]);
  },
  onShow() {
    this.refresh();
  },
  mounted() {
    on("checkin.updated", () => this.refresh());
    on("bill.updated", () => this.refresh());
    on("pay.updated", () => this.refresh());
  },
  methods: {
    billText(s) {
      return { pending: "待生效", locked: "已生效", settled: "已结清", void: "已作废" }[s] || s;
    },
    billClass(s) {
      // 状态色标准化：进行中=蓝，完成=绿，作废=灰
      return { pending: "st-notice", locked: "st-progress", settled: "st-done", void: "st-dead" }[s] || "";
    },
    async refresh() {
      try {
        const team = await get(`/api/teams/${this.id}`);
        const [checkins, bill, my] = await Promise.all([
          // 未成团时 /checkins 返回 404：这里降级为空态，避免整页空白
          get(`/api/teams/${this.id}/checkins`).catch(() => null),
          get(`/api/teams/${this.id}/bill`).catch(() => null),
          get(`/api/teams/${this.id}/checkins/me`).catch(() => null),
        ]);
        this.data = {
          team,
          checkins,
          checkinHint:
            team.status === "formed" || team.status === "completed"
              ? "暂时读不到到场名单，请下拉重试。"
              : "队伍尚未成团，成团后开放到场确认。",
          bill: bill ? { ...bill } : { status: "none", payments: [] },
        };
        this.myCode = my ? my.checkin_code : "";
        this.myChecked = !!(my && my.checked);
        this.emptyHint = "";
      } catch (e) {
        this.data = null;
        this.emptyHint = "读不到这局的信息：可能你已不在队内，或队伍已关闭。";
      }
    },
    copyCode() {
      if (!this.myCode) return;
      uni.setClipboardData({
        data: this.myCode,
        success: () => uni.showToast({ title: "核销码已复制", icon: "none" }),
      });
    },
    async doCheckin() {
      if (this.busy) return;
      this.busy = true;
      try {
        await post(`/api/teams/${this.id}/checkin`, { checkin_code: this.myCode });
        // 我的状态立刻置位（队友的到场状态以后端返回为准，不做本地推断）
        this.myChecked = true;
        uni.showToast({ title: "已确认到场", icon: "success" });
        await this.refresh();
      } catch (e) {
        this.myChecked = false;
      } finally {
        this.busy = false;
      }
    },
    /** 修改：进入编辑态并回填当前金额，由用户确认后再提交（原实现是赋值后立刻提交，改不了） */
    editBill() {
      this.totalAmount = String(this.data.bill.total_amount);
      this.editing = true;
    },
    cancelEdit() {
      this.editing = false;
      this.totalAmount = "";
    },
    async submitBill() {
      const amount = Number(this.totalAmount);
      if (!amount || amount <= 0) {
        uni.showToast({ title: "请输入大于 0 的金额", icon: "none" });
        return;
      }
      if (this.busy) return;
      this.busy = true;
      try {
        await post(`/api/teams/${this.id}/bill`, { total_amount: amount });
        uni.showToast({ title: this.editing ? "已更新" : "已录入", icon: "success" });
        this.totalAmount = "";
        this.editing = false;
        await this.refresh();
      } catch (e) {
        /* handled */
      } finally {
        this.busy = false;
      }
    },
    async pay() {
      if (this.paying) return;
      this.paying = true;
      // 模拟支付：前端 1s 支付动画 + 后端即时记账（带幂等键，重试不会二次扣款）
      setTimeout(async () => {
        try {
          await post(`/api/teams/${this.id}/bill/pay`);
          uni.showToast({ title: "支付成功", icon: "success" });
        } finally {
          this.paying = false;
          this.refresh();
        }
      }, 1000);
    },
  },
};
</script>

<style scoped>
.section-title { font-weight: 700; margin-bottom: 12rpx; font-size: 30rpx; }
.section-head { display: flex; align-items: center; margin-bottom: 12rpx; }
.section-head .card-title { margin-bottom: 0; flex: 1; }
.qmark {
  width: 44rpx; height: 44rpx; line-height: 44rpx; text-align: center;
  border-radius: 50%; background: #efeef6; color: #636e72; font-size: 24rpx;
}
.tip { margin-bottom: 20rpx; line-height: 1.6; }
.checkin-item { display: flex; align-items: center; padding: 12rpx 0; }
.avatar {
  width: 60rpx; height: 60rpx; border-radius: 50%;
  background: #efeef6; color: #b2b2b2; font-size: 26rpx;
  display: flex; align-items: center; justify-content: center;
}
.avatar.on { background: #f0eeff; color: #6c5ce7; }
.c-name { flex: 1; margin-left: 18rpx; }
.c-state { color: #b2b2b2; font-size: 24rpx; }
.c-state.done { color: #10b981; font-weight: 600; }   /* 已到场=绿 */
.c-state.undone { color: #9aa0a6; }                    /* 未到场=灰 */
/* 核销码放大，方便线下出示 */
.my-code { margin-top: 20rpx; }
.code-box {
  background: #f0eeff; border-radius: 16rpx; padding: 24rpx; text-align: center;
}
.code { display: block; margin-top: 8rpx; color: #6c5ce7; font-weight: 700; font-size: 52rpx; letter-spacing: 6rpx; }
.code-actions { display: flex; gap: 16rpx; justify-content: flex-end; margin-top: 16rpx; }
.btn-sm { padding: 10rpx 30rpx; font-size: 26rpx; border-radius: 30rpx; display: inline-block; }
.btn-block { width: 100%; box-sizing: border-box; margin-top: 24rpx; }
/* 规则弹窗 */
.mask {
  position: fixed; left: 0; top: 0; right: 0; bottom: 0;
  background: rgba(45, 52, 54, 0.45); z-index: 99;
  display: flex; align-items: center; justify-content: center;
}
.sheet { width: 620rpx; background: #fff; border-radius: 24rpx; padding: 36rpx; box-sizing: border-box; }
.sheet-title { font-size: 32rpx; font-weight: 700; margin-bottom: 20rpx; }
.rule { font-size: 25rpx; color: #636e72; line-height: 1.75; margin-bottom: 10rpx; }
.bill-status { display: flex; align-items: center; justify-content: space-between; margin-bottom: 16rpx; }
.per { color: #6c5ce7; font-size: 34rpx; font-weight: 700; }
.pay-item { display: flex; justify-content: space-between; align-items: center; padding: 14rpx 0; }
.right { display: flex; align-items: center; gap: 12rpx; }
.amount { font-weight: 600; }
.form-row { display: flex; align-items: center; gap: 14rpx; margin-top: 20rpx; }
.input { flex: 1; background: #efeef6; border-radius: 12rpx; padding: 16rpx 20rpx; font-size: 28rpx; }
.btn { margin-top: 24rpx; }
.center { text-align: center; padding: 20rpx; }
.edit { color: #6c5ce7; }
.btn.disabled { opacity: 0.45; pointer-events: none; }
</style>
