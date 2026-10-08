<template>
  <view class="page">
    <!-- 顶部固定公告：饭局名称 / 餐馆 / 用餐时间，免翻聊天记录 -->
    <view class="notice" v-if="team">
      <view class="notice-line">
        <text class="notice-name">{{ team.name }}</text>
        <text class="st" :class="statusMeta.cls">{{ statusMeta.text }}</text>
      </view>
      <view class="notice-sub">{{ noticeSub }}</view>
    </view>

    <scroll-view scroll-y class="msg-list" :scroll-top="scrollTop" scroll-with-animation>
      <view
        v-for="m in messages"
        :key="m.id"
        :class="['bubble-row', m.msg_type === 'system' ? 'sys' : m.is_me ? 'me' : '']"
      >
        <!-- 系统消息：浅灰气泡 -->
        <view v-if="m.msg_type === 'system'" class="sys-text">{{ m.content }}</view>
        <template v-else>
          <view class="bubble" :class="{ recalled: m.recalled, image: m.msg_type === 'image' }"
                @longpress="onLongPress(m)">
            <view class="sender" v-if="!m.is_me">
              {{ m.sender ? m.sender.nickname : "成员" }}
            </view>
            <!-- @全体成员 高亮 -->
            <view class="mention" v-if="m.mentions_all">@全体成员</view>
            <image
              v-if="m.msg_type === 'image' && !m.recalled"
              class="msg-img"
              :src="mediaUrl(m.content)"
              mode="widthFix"
              lazy-load
              @tap="previewImage(m.content)"
            />
            <view v-else class="content">{{ m.content }}</view>
          </view>
        </template>
      </view>
      <view class="muted center" v-if="!messages.length">还没有消息，和队友打个招呼吧</view>
      <view class="list-pad"></view>
    </scroll-view>

    <!-- 快捷功能 + 输入栏 -->
    <view class="input-bar">
      <view class="quick" hover-class="btn-pressed" @tap="sendLocation">📍</view>
      <view class="quick" :class="{ off: !isLeader }" hover-class="btn-pressed" @tap="toggleMentionAll">
        @全体
      </view>
      <input
        class="input"
        v-model="draft"
        :adjust-position="true"
        :cursor-spacing="20"
        :confirm-hold="true"
        confirm-type="send"
        :placeholder="mentionAll ? '将 @全体成员：输入内容…' : '和队友协商到店时间…'"
        @confirm="send"
      />
      <view class="send-btn" :class="{ disabled: busy }" hover-class="btn-pressed" @tap="send">
        {{ busy ? "…" : "发送" }}
      </view>
    </view>
  </view>
</template>

<script>
import { get, post, getToken } from "../../utils/request";
import { HOST } from "../../utils/config";
import { on, subscribe } from "../../utils/ws";
import { useAuthStore } from "../../stores/auth";
import { toastOk, toast, confirm } from "../../utils/ui";
import { diningTimeText, teamStatusMeta } from "../../utils/format";

export default {
  data() {
    return {
      id: null,
      messages: [],
      draft: "",
      scrollTop: 0,
      busy: false,
      uploading: false,
      mentionAll: false,
      team: null,
    };
  },
  computed: {
    isLeader() {
      return !!(this.team && this.team.my_role === "leader");
    },
    statusMeta() {
      return teamStatusMeta(this.team && this.team.status);
    },
    noticeSub() {
      if (!this.team) return "";
      const r = this.team.restaurant ? this.team.restaurant.name : this.team.location_hint || "地点待定";
      return `${r} · ${diningTimeText(this.team.dining_time) || "时间待定"}`;
    },
  },
  onLoad(options) {
    this.id = Number(options.id);
    subscribe(["team:" + this.id]);
  },
  onShow() {
    this.refresh();
    this.loadTeam();
  },
  mounted() {
    on("chat.message", (e) => {
      if (e.data && e.data.team_id === this.id && e.data.message) {
        this.appendMessage(e.data.message);
      }
    });
  },
  methods: {
    /** 图片是站内相对路径，渲染时需要补上服务地址 */
    mediaUrl(path) {
      if (!path) return "";
      return /^https?:\/\//.test(path) ? path : HOST + path;
    },
    async loadTeam() {
      try {
        this.team = await get(`/api/teams/${this.id}`);
      } catch (e) {
        /* handled */
      }
    },
    async refresh() {
      try {
        const res = await get(`/api/teams/${this.id}/messages?limit=50`);
        // is_me 由服务端按 user_id 判定（原实现用昵称比对，同名用户会串位）
        this.messages = res.messages.map((m) => ({ ...m, recalled: !!m.recalled }));
        this.scrollToBottom();
      } catch (e) {
        toast("群聊在成团后开放");
      }
    },
    appendMessage(m) {
      const idx = this.messages.findIndex((x) => x.id === m.id);
      if (idx >= 0) {
        // 撤回等状态变更会以同一 id 重播，这里原地替换
        this.messages.splice(idx, 1, { ...m, recalled: !!m.recalled });
        return;
      }
      this.messages.push({ ...m, recalled: !!m.recalled });
      this.scrollToBottom();
    },
    scrollToBottom() {
      this.$nextTick(() => {
        this.scrollTop = this.messages.length * 600;
      });
    },
    toggleMentionAll() {
      if (!this.isLeader) {
        toast("只有队长可以 @全体成员");
        return;
      }
      this.mentionAll = !this.mentionAll;
    },
    async send() {
      const content = (this.draft || "").trim();
      if (!content || this.busy || this.uploading) return;
      this.busy = true;
      const mentionsAll = this.mentionAll;
      try {
        const msg = await post(`/api/teams/${this.id}/messages`, {
          content,
          msg_type: "text",
          mentions_all: mentionsAll,
        });
        this.draft = "";
        this.mentionAll = false;
        this.appendMessage(msg);
      } catch (e) {
        /* 命中内容安全策略时由请求层提示，保留草稿便于修改 */
      } finally {
        this.busy = false;
      }
    },
    /** 发送图片（可用来发餐馆定位截图） */
    sendLocation() {
      if (this.uploading) return;
      uni.chooseImage({
        count: 1,
        sizeType: ["compressed"],
        success: async (res) => {
          const path = res.tempFilePaths && res.tempFilePaths[0];
          if (!path) return;
          this.uploading = true;
          try {
            const url = await this.upload(path);
            const msg = await post(`/api/teams/${this.id}/messages`, {
              content: url,
              msg_type: "image",
            });
            this.appendMessage(msg);
          } catch (e) {
            /* 上传层已给出提示 */
          } finally {
            this.uploading = false;
          }
        },
        fail: () => {},
      });
    },
    upload(filePath) {
      return new Promise((resolve, reject) => {
        uni.uploadFile({
          url: `${HOST}/api/teams/${this.id}/uploads`,
          filePath,
          name: "file",
          header: { Authorization: "Bearer " + getToken() },
          success: (res) => {
            let body = {};
            try {
              body = JSON.parse(res.data || "{}");
            } catch (e) {
              body = {};
            }
            if (res.statusCode >= 200 && res.statusCode < 300 && body.url) {
              resolve(body.url);
            } else {
              toast(body.detail || "图片上传失败，请重试");
              reject(res);
            }
          },
          fail: () => {
            toast("图片上传失败，请检查网络");
            reject();
          },
        });
      });
    },
    previewImage(path) {
      const url = this.mediaUrl(path);
      if (uni.previewImage) uni.previewImage({ urls: [url], current: url });
    },
    /** 长按消息：本人消息可撤回（2 分钟内），他人消息可举报 */
    onLongPress(m) {
      if (m.msg_type === "system" || m.recalled) return;
      const items = m.is_me ? ["撤回消息"] : ["举报该消息"];
      uni.showActionSheet({
        itemList: items,
        success: (res) => {
          if (m.is_me && res.tapIndex === 0) this.recall(m);
          else if (!m.is_me) this.reportMessage(m);
        },
        fail: () => {},
      });
    },
    async recall(m) {
      const ok = await confirm({
        title: "撤回消息",
        content: "撤回后所有人将看不到这条内容。确定吗？",
        confirmText: "撤回",
      });
      if (!ok) return;
      try {
        const out = await post(`/api/teams/${this.id}/messages/${m.id}/recall`);
        this.appendMessage(out);
        toastOk("已撤回");
      } catch (e) {
        /* handled */
      }
    },
    reportMessage(m) {
      if (!m.sender_id) {
        toast("无法定位发送者，请在队伍详情页举报该成员");
        return;
      }
      const reasons = ["骚扰或言语冒犯", "疑似诈骗引流", "人身威胁", "其他违规"];
      const codes = ["harassment", "fraud", "abuse", "other"];
      uni.showActionSheet({
        itemList: reasons,
        success: async (res) => {
          try {
            await post("/api/reports", {
              target_user_id: m.sender_id,
              team_id: this.id,
              message_id: m.id,
              reason: codes[res.tapIndex],
            });
            toastOk("举报已受理");
          } catch (e) {
            /* handled */
          }
        },
        fail: () => {},
      });
    },
  },
};
</script>

<style scoped>
.page { display: flex; flex-direction: column; height: 100vh; }

/* 顶部固定公告 */
.notice {
  background: #fafafd; border-bottom: 2rpx solid #efeef6;
  padding: 16rpx 24rpx; flex-shrink: 0;
}
.notice-line { display: flex; align-items: center; gap: 12rpx; }
.notice-name { font-size: 30rpx; font-weight: 700; color: #2d3436; }
.notice-sub { margin-top: 6rpx; font-size: 23rpx; color: #636e72; }

.msg-list { flex: 1; padding: 20rpx; box-sizing: border-box; }
.bubble-row { display: flex; margin-bottom: 20rpx; }
.bubble-row.me { justify-content: flex-end; }
.sys { justify-content: center; }
/* 系统消息用浅灰气泡 */
.sys-text {
  background: #f2f3f5; color: #9aa0a6; font-size: 22rpx;
  padding: 10rpx 22rpx; border-radius: 20rpx; line-height: 1.6; max-width: 78%;
}
.bubble { max-width: 70%; background: #fff; border-radius: 16rpx; padding: 16rpx 20rpx; }
.bubble.recalled { opacity: 0.6; }
.bubble.image { padding: 10rpx; }
.me .bubble { background: #f0eeff; }
.sender { color: #b2b2b2; font-size: 22rpx; margin-bottom: 6rpx; }
.mention { font-size: 22rpx; color: #ff7675; font-weight: 600; margin-bottom: 6rpx; }
.content { font-size: 28rpx; word-break: break-all; }
.msg-img { width: 360rpx; border-radius: 12rpx; display: block; }
.center { text-align: center; padding: 40rpx 20rpx; }
.list-pad { height: 20rpx; }

/* 输入栏：适配键盘弹出（adjust-position + cursor-spacing）与底部手势条 */
.input-bar {
  display: flex; align-items: center; gap: 14rpx;
  padding: 16rpx 24rpx calc(16rpx + env(safe-area-inset-bottom));
  background: #fff; border-top: 2rpx solid #f0f0f0;
  max-width: 480px; margin: 0 auto; width: 100%; box-sizing: border-box;
  flex-shrink: 0;
}
.quick {
  flex-shrink: 0; padding: 8rpx 16rpx; border-radius: 24rpx;
  background: #f0eeff; color: #6c5ce7; font-size: 24rpx; line-height: 1.5;
}
.quick.off { background: #f2f3f5; color: #b2b2b2; }
.input { flex: 1; background: #efeef6; border-radius: 36rpx; padding: 16rpx 24rpx; font-size: 28rpx; }
.send-btn { color: #6c5ce7; font-size: 30rpx; font-weight: 600; flex-shrink: 0; }
.send-btn.disabled { opacity: 0.5; }
</style>
