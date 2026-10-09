<template>
  <view class="page" :class="{ 'tab-in': tabAnim }">
    <!-- Hero：渐变头 + 大头像 + 昵称 + 实名状态 -->
    <view class="hero me-hero">
      <view class="me-row">
        <view class="me-avatar">{{ user && user.nickname ? user.nickname.slice(0, 1) : "?" }}</view>
        <view class="me-info">
          <view class="me-name">{{ user ? user.nickname : "未登录" }}</view>
          <view class="me-sub" v-if="user">
            {{ genderText(user.gender) }} · {{ user.age }}岁
            <text class="me-verified" v-if="verified">已实名</text>
          </view>
          <view class="me-sub" v-else>连接后端后自动登录</view>
        </view>
        <view class="me-set" hover-class="btn-pressed" @tap="openDoc('terms')">⚙️</view>
      </view>
      <view class="me-banner" v-if="isRestricted">
        账号已被限制使用组队功能（{{ user.restricted_reason || "存在违规行为" }}）。
      </view>
    </view>

    <!-- 统计条：招募中 / 已成团 / 已结束 -->
    <view class="stats hero-overlap">
      <view class="stat" hover-class="btn-pressed" @tap="goMyTeams('recruiting')">
        <text class="stat-num">{{ statRecruiting }}</text>
        <text class="stat-label">招募中</text>
      </view>
      <view class="stat" hover-class="btn-pressed" @tap="goMyTeams('formed')">
        <text class="stat-num">{{ statFormed }}</text>
        <text class="stat-label">已成团</text>
      </view>
      <view class="stat" hover-class="btn-pressed" @tap="goHistory">
        <text class="stat-num">{{ statClosed }}</text>
        <text class="stat-label">已结束</text>
      </view>
    </view>

    <!-- 快捷菜单：图标色块 + 红点角标 -->
    <view class="card menu-card">
      <view class="menu-item" hover-class="btn-pressed" @tap="goNotifications">
        <view class="mi-icon mi-blue">🔔</view>
        <text class="mi-title">消息通知</text>
        <text class="mi-badge" v-if="unread">{{ unread > 99 ? "99+" : unread }}</text>
        <text class="mi-chev">›</text>
      </view>
      <view class="menu-item" hover-class="btn-pressed" @tap="goHistory">
        <view class="mi-icon mi-orange">🍜</view>
        <text class="mi-title">我的历史饭局</text>
        <text class="mi-value">查看消费记录</text>
        <text class="mi-chev">›</text>
      </view>
    </view>

    <!-- 卡片：对外资料 -->
    <view class="card">
      <view class="card-head"><text class="ch-title">对外资料</text></view>
      <view class="tip-small">其他用户仅能看到你的昵称、年龄、性别。</view>
      <view class="form-row">
        <text class="label">昵称</text>
        <input class="input" v-model="form.nickname" maxlength="30" placeholder="昵称"
               :adjust-position="true" :cursor-spacing="24" />
      </view>
      <view class="form-row">
        <text class="label">年龄</text>
        <input class="input" :class="{ locked: verified }" v-model="form.age" type="number"
               :disabled="verified" maxlength="3" placeholder="年龄"
               :adjust-position="true" :cursor-spacing="24" />
      </view>
      <view class="hint" v-if="verified">已完成实名登记，年龄以证件为准，不可修改。</view>
      <view class="form-row">
        <text class="label">性别</text>
        <radio-group @change="onGender" class="radio-row">
          <label class="radio"><radio value="male" :checked="form.gender === 'male'" color="#6c5ce7" />男</label>
          <label class="radio"><radio value="female" :checked="form.gender === 'female'" color="#6c5ce7" />女</label>
          <label class="radio"><radio value="other" :checked="form.gender === 'other'" color="#6c5ce7" />保密</label>
        </radio-group>
      </view>
      <view class="hint">选择保密，其他用户无法查看你的性别</view>
      <view class="btn-row">
        <view class="btn btn-ghost flex1" hover-class="btn-pressed" @tap="showPreview = true">预览我的资料</view>
        <view class="btn btn-primary flex1" :class="{ 'is-disabled': !profileValid }"
              hover-class="btn-pressed" @tap="saveProfile">保存资料</view>
      </view>
    </view>

    <!-- 卡片：实名登记（说明精简） -->
    <view class="card">
      <view class="card-head">
        <text class="ch-title">
          实名登记
          <text v-if="verified" class="st st-done inline-tag">已登记</text>
        </text>
        <view class="qmark" hover-class="btn-pressed" @tap="showRealnameTip = true">?</view>
      </view>
      <template v-if="!verified">
        <view class="tip-small">
          仅用于确认你已年满 18 周岁。姓名与证件号不会展示给任何人，也不保存明文。
        </view>
        <view class="warn">
          当前版本未接入权威核验渠道，「登记」不等于「权威核验」。
        </view>
        <view class="form-row">
          <text class="label">姓名</text>
          <input class="input" v-model="rn.real_name" maxlength="30" placeholder="真实姓名"
                 :adjust-position="true" :cursor-spacing="24" />
        </view>
        <view class="form-row">
          <text class="label">证件号</text>
          <input class="input" v-model="rn.id_card" maxlength="18" placeholder="18 位身份证号"
                 :adjust-position="true" :cursor-spacing="24" />
        </view>
        <label class="consent-row">
          <checkbox :checked="rn.consent" color="#6c5ce7" @tap="toggleConsent" />
          <text class="consent-text">
            我已阅读并同意
            <text class="link" @tap.stop="openDoc('realname')">《实名登记与个人信息处理规则》</text>
          </text>
        </label>
        <view class="btn btn-primary btn-block"
              :class="{ 'is-disabled': !realnameValid || !rn.consent }"
              hover-class="btn-pressed" @tap="doRealname">提交登记</view>
      </template>
      <view class="muted" v-else>
        证件信息已按加盐摘要留存，明文不落库。无需重复提交。
      </view>
    </view>

    <!-- 卡片：协议与政策 -->
    <view class="card">
      <view class="card-head">
        <text class="ch-title"><text class="head-ico mi-purple">📄</text>协议与政策</text>
      </view>
      <view class="link-row" hover-class="btn-pressed" @tap="openDoc('terms')">
        <text>用户服务协议</text><text class="arrow">›</text>
      </view>
      <view class="link-row" hover-class="btn-pressed" @tap="openDoc('privacy')">
        <text>隐私政策</text><text class="arrow">›</text>
      </view>
      <view class="link-row" hover-class="btn-pressed" @tap="openDoc('realname')">
        <text>实名登记与个人信息处理规则</text><text class="arrow">›</text>
      </view>
      <view class="tip-small">已同意版本：{{ user && user.consent_version ? user.consent_version : "—" }}</view>
    </view>

    <!-- 卡片：演示工具 -->
    <view class="card">
      <view class="card-head"><text class="ch-title"><text class="head-ico mi-gray">🧪</text>演示工具</text></view>
      <view class="tip-small">多账号模拟，模拟器切换身份，扮演队长/队员，验证组队、踢人、报名完整业务流程。</view>
      <input class="input input-block" v-model="switchName" placeholder="输入账号名，如 leader / a1 / a2"
             :adjust-position="true" :cursor-spacing="24" />
      <view class="btn-ghost btn btn-block" :class="{ disabled: !switchName.trim() || switching }"
            hover-class="btn-pressed" @tap="switchAccount">
        {{ switching ? "切换中…" : "切换到该账号" }}
      </view>
    </view>

    <!-- 卡片：注销（PIPL 删除权） -->
    <view class="card danger-card">
      <view class="card-head"><text class="ch-title"><text class="head-ico mi-warn-ico">⚠️</text>注销账号</text></view>
      <view class="tip-small">
        注销后姓名与证件信息立即清除、登录凭证失效，历史队伍中的昵称将被匿名化；进行中的饭局会被关闭。不可恢复。
      </view>
      <view class="btn btn-danger btn-block" hover-class="btn-pressed" @tap="confirmDelete">
        注销我的账号
      </view>
    </view>

    <!-- 实名说明弹窗 -->
    <view class="mask" v-if="showRealnameTip" @tap="showRealnameTip = false">
      <view class="sheet" @tap.stop>
        <view class="sheet-title">实名信息怎么用？</view>
        <view class="rule">· 仅用于确认你已年满 18 周岁，以及纠纷时的身份追溯。</view>
        <view class="rule">· 不会展示给任何人：其他用户只能看到你的昵称、年龄、性别。</view>
        <view class="rule">· 证件号不保存明文，只保存加盐摘要，无法反推原始号码。</view>
        <view class="rule">· 你可以随时撤回同意并注销账号，注销后信息立即清除。</view>
        <view class="rule">· 当前版本尚未接入权威核验渠道，「登记」不等于「权威核验」。</view>
        <view class="btn btn-primary btn-block" hover-class="btn-pressed" @tap="showRealnameTip = false">我知道了</view>
      </view>
    </view>

    <!-- 对外资料预览弹窗 -->
    <view class="mask" v-if="showPreview" @tap="showPreview = false">
      <view class="sheet" @tap.stop>
        <view class="sheet-title">别人看到的你</view>
        <view class="preview">
          <view class="avatar big">{{ (form.nickname || "?").slice(0, 1) }}</view>
          <view class="pv-info">
            <text class="pv-name">{{ form.nickname || "未填写" }}</text>
            <text class="muted">{{ genderText(form.gender) }} · {{ form.age || "—" }}岁</text>
          </view>
        </view>
        <view class="rule">队友在队伍里只能看到以上信息。</view>
        <view class="rule" v-if="form.gender === 'other'">你选择了「保密」，其他用户看不到你的性别。</view>
        <view class="rule">真实姓名、证件号、账号名、联系方式都不会出现在这里。</view>
        <view class="btn btn-primary btn-block" hover-class="btn-pressed" @tap="showPreview = false">知道了</view>
      </view>
    </view>
  </view>
</template>

<script>
import { useAuthStore } from "../../stores/auth";
import { subscribe } from "../../utils/ws";
import { get } from "../../utils/request";
import { toastOk, confirm } from "../../utils/ui";

export default {
  data() {
    return {
      form: { nickname: "", age: "", gender: "other" },
      rn: { real_name: "", id_card: "", consent: false },
      switchName: "",
      switching: false,
      tabAnim: false,
      showRealnameTip: false,
      showPreview: false,
      teamGroups: {}, // 我的饭局分组（统计条用）
      unread: 0,      // 未读消息数（菜单角标用）
    };
  },
  computed: {
    user() {
      return this.$pinia.state.value.auth ? useAuthStore().user : null;
    },
    verified() {
      return !!(this.user && this.user.real_name_verified);
    },
    isRestricted() {
      return !!(this.user && this.user.restricted);
    },
    statusText() {
      if (!this.user) return "未登录";
      if (this.user.restricted) return "受限";
      return this.verified ? "已登记" : "未实名";
    },
    statusCls() {
      if (!this.user) return "st-notice";
      if (this.user.restricted) return "st-warn";
      return this.verified ? "st-done" : "st-notice";
    },
    statRecruiting() {
      const g = this.teamGroups || {};
      return (g.draft || []).length + (g.recruiting || []).length;
    },
    statFormed() {
      return (this.teamGroups.formed || []).length;
    },
    statClosed() {
      const g = this.teamGroups || {};
      return (g.completed || []).length + (g.failed || []).length;
    },
    profileValid() {
      return !!(this.form.nickname && this.form.nickname.trim() && Number(this.form.age) >= 18);
    },
    realnameValid() {
      const n = (this.rn.real_name || "").trim();
      const c = (this.rn.id_card || "").trim();
      return !!(n.length >= 2 && c.length === 18);
    },
  },
  onShow() {
    const auth = useAuthStore();
    auth.silentLogin().then(() => {
      if (auth.user) this.fillForm(auth);
    });
    this.loadSummary();
    this.playTabAnim();
  },
  methods: {
    /** 统计条 + 未读角标：静默拉取，失败不影响页面 */
    async loadSummary() {
      try {
        const res = await get("/api/users/me/teams");
        this.teamGroups = res.groups || {};
      } catch (e) { /* 忽略，统计条保持 0 */ }
      try {
        const res = await get("/api/notifications?page=1&page_size=1");
        this.unread = res.unread || 0;
      } catch (e) { /* 忽略 */ }
    },
    goNotifications() {
      uni.switchTab({ url: "/pages/notifications/notifications" });
    },
    goMyTeams() {
      uni.switchTab({ url: "/pages/my-teams/my-teams" });
    },
    playTabAnim() {
      this.tabAnim = false;
      setTimeout(() => {
        this.tabAnim = true;
      }, 30);
    },
    genderText(g) {
      return g === "male" ? "男" : g === "female" ? "女" : "保密";
    },
    fillForm(auth) {
      this.form.nickname = auth.user.nickname;
      this.form.age = String(auth.user.age);
      this.form.gender = auth.user.gender;
    },
    onGender(e) {
      this.form.gender = e.detail.value;
    },
    toggleConsent() {
      this.rn.consent = !this.rn.consent;
    },
    openDoc(doc) {
      uni.navigateTo({ url: "/pages/agreement/agreement?doc=" + doc });
    },
    goHistory() {
      uni.navigateTo({ url: "/pages/history/history" });
    },
    async saveProfile() {
      if (!this.profileValid) {
        if (Number(this.form.age) < 18) {
          uni.showToast({ title: "仅限 18 周岁以上用户使用", icon: "none" });
        }
        return;
      }
      const auth = useAuthStore();
      const payload = { nickname: this.form.nickname, gender: this.form.gender };
      // 已实名时年龄锁定，不再提交（后端也会拒绝）
      if (!this.verified) payload.age = Number(this.form.age);
      await auth.updateProfile(payload);
      toastOk("资料已保存");
    },
    async doRealname() {
      if (!this.realnameValid || !this.rn.consent) return;
      const auth = useAuthStore();
      await auth.submitRealname(
        this.rn.real_name.trim(),
        this.rn.id_card.trim().toUpperCase(),
        true
      );
      toastOk("登记完成");
      this.fillForm(auth);
    },
    async confirmDelete() {
      const ok = await confirm({
        title: "注销账号",
        content: "将清除你的姓名与证件信息并关闭进行中的饭局，且不可恢复。确定注销吗？",
        confirmText: "注销",
      });
      if (!ok) return;
      const auth = useAuthStore();
      await auth.deleteAccount();
      uni.showToast({ title: "账号已注销", icon: "none" });
      this.form = { nickname: "", age: "", gender: "other" };
      this.rn = { real_name: "", id_card: "", consent: false };
      setTimeout(() => uni.switchTab({ url: "/pages/plaza/plaza" }), 600);
    },
    async switchAccount() {
      if (!this.switchName.trim() || this.switching) return;
      this.switching = true;
      const auth = useAuthStore();
      try {
        const name = this.switchName.trim();
        await auth.switchAccount(name);
        this.fillForm(auth);
        this.rn = { real_name: "", id_card: "", consent: false };
        this.switchName = "";
        subscribe(["plaza", "user:" + auth.user.id]);
        uni.$emit("auth:changed");
        toastOk("已切换为 " + name);
      } catch (e) {
        /* handled */
      } finally {
        this.switching = false;
      }
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: calc(40rpx + env(safe-area-inset-bottom)); }

/* ---------- Hero 头部 ---------- */
.me-hero { padding-bottom: 56rpx; }
.me-row { display: flex; align-items: center; gap: 24rpx; }
/* 淡绿圆底大头像（参考主流 App 的 Profile 头部） */
.me-avatar {
  width: 128rpx; height: 128rpx; border-radius: 50%; flex-shrink: 0;
  background: #a7f3d0; color: #065f46; font-size: 56rpx; font-weight: 700;
  display: flex; align-items: center; justify-content: center;
  box-shadow: 0 6rpx 18rpx rgba(0, 0, 0, 0.15);
}
.me-info { flex: 1; min-width: 0; }
.me-name { font-size: 42rpx; font-weight: 700; color: #fff; }
.me-sub {
  font-size: 26rpx; color: rgba(255, 255, 255, 0.82); margin-top: 10rpx;
  display: flex; align-items: center; gap: 12rpx;
}
.me-verified {
  font-size: 20rpx; padding: 2rpx 14rpx; border-radius: 14rpx;
  background: rgba(255, 255, 255, 0.22); color: #fff; line-height: 1.7;
}
.me-set {
  width: 64rpx; height: 64rpx; border-radius: 50%; flex-shrink: 0;
  background: rgba(255, 255, 255, 0.16); font-size: 32rpx;
  display: flex; align-items: center; justify-content: center;
}
.me-banner {
  margin-top: 24rpx; padding: 16rpx 20rpx; border-radius: 16rpx;
  background: rgba(255, 255, 255, 0.14); color: #ffd5d5; font-size: 24rpx; line-height: 1.6;
}

/* 卡片头部图标（小号色块） */
.head-ico {
  display: inline-flex; align-items: center; justify-content: center;
  width: 48rpx; height: 48rpx; border-radius: 14rpx; font-size: 26rpx;
  margin-right: 14rpx; vertical-align: -8rpx;
}
.mi-warn-ico { background: #fff0f0; }

/* 注销卡片弱化：它不是常规功能，视觉降权 */
.danger-card { background: #fffafa; }

/* 卡片头部：标题左、状态/问号右，位置统一 */
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 18rpx;
}
.ch-title {
  font-size: 30rpx; font-weight: 700; color: #2d3436;
  display: flex; align-items: center; gap: 12rpx;
}
.inline-tag { font-weight: 400; }

.avatar.big { width: 112rpx; height: 112rpx; font-size: 48rpx; }

.qmark {
  width: 40rpx; height: 40rpx; line-height: 40rpx; text-align: center;
  border-radius: 50%; background: #efeef6; color: #636e72; font-size: 24rpx;
}

/* 统一的小号说明文字（缩小，不抢主信息） */
.tip-small { font-size: 22rpx; color: #b2b2b2; line-height: 1.6; margin-bottom: 18rpx; }

.btn-row { display: flex; gap: 16rpx; margin-top: 8rpx; }
.btn-row .btn { margin-top: 0; }
.flex1 { flex: 1; }

.link-row {
  display: flex; align-items: center; justify-content: space-between;
  padding: 22rpx 0; border-bottom: 2rpx solid #efeef6; font-size: 28rpx;
}
.link-row:last-of-type { border-bottom: none; }
.arrow { color: #b2b2b2; font-size: 34rpx; }

.preview { display: flex; align-items: center; margin: 20rpx 0 24rpx; }
.pv-info { margin-left: 24rpx; display: flex; flex-direction: column; gap: 6rpx; }
.pv-name { font-size: 34rpx; font-weight: 700; }
.mask {
  position: fixed; left: 0; top: 0; right: 0; bottom: 0;
  background: rgba(45, 52, 54, 0.45); z-index: 99;
  display: flex; align-items: center; justify-content: center;
}
.sheet { width: 620rpx; background: #fff; border-radius: 24rpx; padding: 36rpx; box-sizing: border-box; }
.sheet-title { font-size: 32rpx; font-weight: 700; margin-bottom: 20rpx; }
.rule { font-size: 25rpx; color: #636e72; line-height: 1.75; margin-bottom: 10rpx; }
.btn-block { width: 100%; box-sizing: border-box; margin-top: 24rpx; }
.warn {
  margin-bottom: 20rpx; padding: 14rpx 18rpx; border-radius: 12rpx;
  background: #fdf1e3; color: #d98b26; font-size: 23rpx; line-height: 1.6;
}
.form-row { display: flex; align-items: center; margin-bottom: 22rpx; }
.label { width: 120rpx; color: #636e72; flex-shrink: 0; }
.input { flex: 1; background: #f3f3f7; border-radius: 16rpx; padding: 16rpx 20rpx; font-size: 28rpx; }
.input.locked { color: #b2b2b2; }
.input-block { width: 100%; box-sizing: border-box; margin-bottom: 20rpx; }
.radio-row { flex: 1; display: flex; align-items: center; }
.radio { flex: 1; font-size: 26rpx; display: flex; align-items: center; justify-content: center; }
.hint { color: #b2b2b2; font-size: 23rpx; margin: -8rpx 0 16rpx; padding-left: 120rpx; line-height: 1.5; }
.consent-row { display: flex; align-items: flex-start; margin: 8rpx 0 24rpx; }
.consent-text { font-size: 24rpx; color: #636e72; line-height: 1.6; }
.link { color: #6c5ce7; }
.btn { margin-top: 8rpx; }
.btn-danger {
  background: #fff; color: #ff7675; border: 2rpx solid #ff7675;
  border-radius: 44rpx; font-size: 30rpx; padding: 18rpx 0; text-align: center;
}
.btn.disabled { opacity: 0.45; pointer-events: none; }

/* 弹窗里复用的头像 */
.preview .avatar {
  width: 112rpx; height: 112rpx; border-radius: 50%; flex-shrink: 0;
  background: #6c5ce7; color: #fff; font-size: 48rpx;
  display: flex; align-items: center; justify-content: center;
}
</style>
