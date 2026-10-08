<template>
  <view class="page">
    <view class="tabs">
      <view
        v-for="t in tabs"
        :key="t.key"
        class="tab"
        :class="{ on: active === t.key }"
        @tap="active = t.key"
      >{{ t.label }}</view>
    </view>

    <view class="card doc">
      <block v-for="sec in sections" :key="sec.title">
        <view class="doc-h2">{{ sec.title }}</view>
        <view class="doc-p" v-for="(p, i) in sec.paras" :key="i">{{ p }}</view>
        <view class="doc-li" v-for="(li, i) in sec.list || []" :key="'l' + i">· {{ li }}</view>
      </block>
      <view class="doc-note">
        版本 {{ version }}　生效日期 2026-10-08
      </view>
    </view>

    <view class="footer" v-if="needAgree">
      <view class="btn-primary btn" hover-class="btn-pressed" @tap="agree">我已阅读并同意</view>
      <view class="btn-ghost btn" hover-class="btn-pressed" @tap="reject">不同意</view>
    </view>
  </view>
</template>

<script>
// 协议与政策全文页。
// 之前项目里没有任何协议入口，实名表单直接提交身份证号——属于合规硬缺失。
// 本页同时承担「首启同意门」的展示（needAgree 由跳转参数决定）。
import { useAuthStore, CONSENT_VERSION } from "../../stores/auth";

const DOCS = {
  terms: {
    label: "用户服务协议",
    version: CONSENT_VERSION,
    sections: [
      {
        title: "一、服务内容",
        paras: [
          "本服务提供「约饭组队」功能：发布饭局、陌生人拼桌或链接邀请好友、自动成团、群聊协商、到店确认与人均分账。",
        ],
      },
      {
        title: "二、使用条件",
        paras: ["使用本服务须同时满足："],
        list: [
          "年满 18 周岁（未满 18 周岁不得参与任何线下拼桌活动）；",
          "完成身份信息登记（见《实名登记与个人信息处理规则》）；",
          "不以骚扰、诈骗、引流、营销或任何违法目的使用本服务。",
        ],
      },
      {
        title: "三、线下活动的风险与责任",
        paras: [
          "约饭属于线下社交活动。平台提供信息撮合与流程工具，不对参与者线下会面中的行为承担担保责任。请务必自行核实对方信息、选择公共场所、告知亲友行程。",
          "如遇骚扰、诈骗或人身威胁，请立即使用消息页或队伍详情页的举报功能，必要时报警。",
        ],
      },
      {
        title: "四、行为规范",
        paras: ["以下行为将被限制或封停账号："],
        list: [
          "发布虚假饭局、恶意占位后失联、组织跑单；",
          "在群聊中发送诈骗、色情、赌博、涉毒、人身威胁等违规内容；",
          "多次被其他用户举报并经核实；",
          "恶意滥用举报功能。",
        ],
      },
      {
        title: "五、费用与结算",
        paras: [
          "账单由队长在到店后录入，系统按实际到场人数均摊并生成各自独立的结算记录，互不垫付。",
          "当前版本为演示环境，支付为模拟流程，不产生真实资金流转。",
        ],
      },
    ],
  },
  privacy: {
    label: "隐私政策",
    version: CONSENT_VERSION,
    sections: [
      {
        title: "一、我们收集哪些信息",
        paras: ["为提供服务，我们会处理以下信息："],
        list: [
          "账号信息：昵称、年龄、性别（用于拼桌匹配展示）；",
          "身份信息：姓名、证件号码（仅用于成年核验与安全兜底，见下节）；",
          "组队信息：你发布或参与饭局的记录、群聊消息、到店确认与结算状态；",
          "设备信息：为在小程序内保持登录而生成的设备标识。",
        ],
      },
      {
        title: "二、对外展示范围",
        paras: [
          "其他用户在任何情况下只能看到你的昵称、年龄、性别三项；姓名、证件号码、账号名、联系方式一律不对外展示。",
          "匿名拼桌模式下，非队伍成员只能看到人数与性别/年龄构成，看不到成员名单；报名入队后才可查看队友的上述三项信息。",
        ],
      },
      {
        title: "三、你的权利",
        paras: ["你可以随时在「我的」页面："],
        list: [
          "查看与修改自己的对外资料；",
          "撤回同意并注销账号——注销后姓名与证件信息立即清除，历史队伍中的昵称会被匿名化；",
          "删除站内通知记录。",
        ],
      },
      {
        title: "四、安全措施",
        paras: [
          "证件号码不以明文存储，仅保存加盐摘要用于核验留痕；账号登录凭证使用带随机盐的慢哈希存储。",
        ],
      },
      {
        title: "五、保存期限",
        paras: [
          "账号信息保存至你注销为止；注销后仅保留去标识化的交易与结算记录以维持其他人的账目完整性。",
        ],
      },
    ],
  },
  realname: {
    label: "实名登记规则",
    version: CONSENT_VERSION,
    sections: [
      {
        title: "一、为什么需要登记",
        paras: [
          "约饭是线下陌生人社交，身份与年龄门槛是参与者的基本安全保障。登记后你的姓名与证件号不会展示给任何人，仅用于成年核验与纠纷追溯。",
        ],
      },
      {
        title: "二、如何处理你的证件信息",
        paras: ["提交后我们仅做以下处理："],
        list: [
          "校验证件号格式与校验位是否合法；",
          "从证件号推算出生日期，用于判断是否年满 18 周岁，并将你的年龄修正为证件推算值（此后不可再修改年龄）；",
          "保存加盐摘要（HMAC-SHA256 + 服务端密钥）用于留痕；不保存明文姓名与证件号。",
        ],
      },
      {
        title: "三、当前版本的能力边界（重要）",
        paras: [
          "本演示版本尚未接入公安/运营商等权威核验渠道，「登记」不等于「权威核验」：系统只能确认你填写的证件号在格式上是合法的。",
          "请勿把本版本用于真实的线下约见。正式版本接入权威核验后，我们会在本页与「我的」页面明确标注。",
        ],
      },
      {
        title: "四、单独同意",
        paras: [
          "姓名与证件号属于敏感个人信息。请在「我的 → 实名登记」页面勾选同意后再提交；你可以随时撤回同意并注销账号。",
        ],
      },
    ],
  },
};

export default {
  data() {
    return {
      tabs: Object.keys(DOCS).map((k) => ({ key: k, label: DOCS[k].label })),
      active: "terms",
      needAgree: false,
      version: CONSENT_VERSION,
    };
  },
  computed: {
    sections() {
      return DOCS[this.active].sections;
    },
  },
  onLoad(options) {
    if (options && options.needAgree === "1") this.needAgree = true;
    if (options && options.doc && DOCS[options.doc]) this.active = options.doc;
    uni.setNavigationBarTitle({ title: DOCS[this.active].label });
  },
  methods: {
    async agree() {
      const auth = useAuthStore();
      await auth.acceptConsent(CONSENT_VERSION);
      uni.$emit("consent:agreed");
      uni.navigateBack();
    },
    reject() {
      uni.showModal({
        title: "无法继续使用",
        content: "不同意协议时我们无法处理你的个人信息，因此无法提供约饭服务。你可以稍后再决定。",
        showCancel: false,
        success: () => uni.navigateBack(),
      });
    },
  },
};
</script>

<style scoped>
.page { padding-bottom: 200rpx; }
.tabs { display: flex; background: #fff; border-bottom: 2rpx solid #efeef6; position: sticky; top: 0; z-index: 5; }
.tab { flex: 1; text-align: center; padding: 24rpx 0; font-size: 28rpx; color: #636e72; }
.tab.on { color: #6c5ce7; font-weight: 700; border-bottom: 4rpx solid #6c5ce7; }
.doc { margin-top: 20rpx; }
.doc-h2 { font-size: 30rpx; font-weight: 700; margin: 24rpx 0 12rpx; }
.doc-h2:first-child { margin-top: 0; }
.doc-p { font-size: 26rpx; color: #2d3436; line-height: 1.75; margin-bottom: 10rpx; }
.doc-li { font-size: 26rpx; color: #636e72; line-height: 1.75; padding-left: 16rpx; }
.doc-note { margin-top: 28rpx; padding-top: 20rpx; border-top: 2rpx solid #efeef6; font-size: 22rpx; color: #b2b2b2; }
.footer {
  position: fixed; left: 0; right: 0; bottom: 0; margin: 0 auto; max-width: 480px;
  display: flex; gap: 20rpx; padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #fff; box-shadow: 0 -4rpx 16rpx rgba(45, 52, 54, 0.05);
}
.btn { flex: 1; }
</style>
