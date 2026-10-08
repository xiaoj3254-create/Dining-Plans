// 认证 store：mock 授权登录（可切换测试账号，便于 IDE 演示多角色）
// 合规相关：登录/注册必须携带 consent（已同意协议），并在服务端留痕版本号。
import { defineStore } from "pinia";
import { get, post, patch, del, setToken, getToken, clearToken } from "../utils/request";
import { resetSocket } from "../utils/ws";

const DEVICE_KEY = "dp_device_id";
const USER_KEY = "dp_user";
const CONSENT_KEY = "dp_consent_version";

// 与服务端 settings.CONSENT_VERSION 对应；协议文本变更时递增
export const CONSENT_VERSION = "1.0";

function deviceId() {
  let id = uni.getStorageSync(DEVICE_KEY);
  if (!id) {
    id = "u_" + Math.random().toString(36).slice(2, 10);
    uni.setStorageSync(DEVICE_KEY, id);
  }
  return id;
}

export function hasAgreedConsent() {
  return uni.getStorageSync(CONSENT_KEY) === CONSENT_VERSION;
}

export function markConsentAgreed() {
  uni.setStorageSync(CONSENT_KEY, CONSENT_VERSION);
}

export const useAuthStore = defineStore("auth", {
  state: () => ({
    user: uni.getStorageSync(USER_KEY) || null,
    ready: false,
  }),
  getters: {
    isVerified: (s) => !!(s.user && s.user.real_name_verified),
    isLoggedIn: (s) => !!getToken(),
    isRestricted: (s) => !!(s.user && s.user.restricted),
  },
  actions: {
    /**
     * 静默登录。
     * @param {boolean} opts.force 本地有 token 也强制重新换取新 token
     *   （旧 token 指向已不存在的用户时，只打 /api/auth/me 会再次 401，必须 force 换新）
     */
    async silentLogin(opts = {}) {
      const { loading = false, force = false } = opts;
      if (force || !getToken()) {
        await this.loginAs(deviceId(), { loading });
      }
      await this.fetchMe(loading, true);
      this.ready = true;
      return this.user;
    },
    /**
     * 读取本人信息。
     * @param {boolean} allowForceRetry 撞 401 时是否强制换新 token 并重试一次
     */
    async fetchMe(loading = false, allowForceRetry = false) {
      try {
        this.user = await get("/api/auth/me", { loading });
        uni.setStorageSync(USER_KEY, this.user);
        return this.user;
      } catch (e) {
        const is401 = !!(e && e.statusCode === 401);
        if (is401 && allowForceRetry) {
          clearToken();
          try {
            await this.loginAs(deviceId(), { loading }); // 强制换新 token
            return await this.fetchMe(loading, false);
          } catch (e2) {
            /* 后端不可达：保持未登录状态 */
          }
        }
        this.user = null;
        return null;
      }
    },
    async loginAs(name, opts = {}) {
      const { loading = false, consent = hasAgreedConsent() } = opts;
      const res = await post("/api/auth/alipay", {
        code: "mock:" + name,
        nickname: name,
        age: 25 + Math.floor(Math.random() * 8),
        gender: Math.random() > 0.5 ? "male" : "female",
        // 未同意协议时后端会拒绝创建新用户（PIPL：须先取得同意）
        consent,
      }, { loading });
      setToken(res.access_token);
      this.user = res.user;
      uni.setStorageSync(USER_KEY, this.user);
      return this.user;
    },
    /** 记录协议同意（首启同意门通过后调用；服务端落版本号留痕） */
    async acceptConsent(version = CONSENT_VERSION) {
      markConsentAgreed();
      try {
        this.user = await post("/api/users/me/consent", { version }, { loading: false });
        uni.setStorageSync(USER_KEY, this.user);
      } catch (e) {
        /* 未登录或后端不可达时不阻塞使用，本地已记录 */
      }
      return this.user;
    },
    /** 演示用：切换为新的测试账号（多角色扮演） */
    async switchAccount(name) {
      clearToken();
      resetSocket();
      await this.loginAs(name || "guest_" + Math.random().toString(36).slice(2, 8), {
        consent: true,
      });
      this.ready = true;
    },
    /** 实名登记：必须显式同意（敏感个人信息单独同意） */
    async submitRealname(realName, idCard, consent = true) {
      this.user = await post("/api/users/me/realname", {
        real_name: realName,
        id_card: idCard,
        consent,
      });
      uni.setStorageSync(USER_KEY, this.user);
    },
    async updateProfile(payload) {
      this.user = await patch("/api/users/me", payload);
      uni.setStorageSync(USER_KEY, this.user);
    },
    /** 注销：匿名化个人信息并让全部 token 失效 */
    async deleteAccount() {
      const res = await del("/api/users/me");
      clearToken();
      resetSocket();
      uni.removeStorageSync(USER_KEY);
      this.user = null;
      return res;
    },
  },
});
