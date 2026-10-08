// 请求封装：统一 baseURL / JWT / 错误分类 / 全局 loading / 401 自愈 / 幂等键
import { HOST, REQUEST_TIMEOUT } from "./config";

const TOKEN_KEY = "dp_token";

// 不自愈的端点白名单：登录/注册自身 401 说明凭据问题，重登会递归。
// 注意不能用 "/api/auth/" 前缀判断——/api/auth/me 是业务读取，必须参与自愈。
const AUTH_ENDPOINTS = ["/api/auth/alipay", "/api/auth/login", "/api/auth/register"];

// 变更类端点：自动附加 Idempotency-Key，使"401 自愈后重发"不会产生二次业务动作
// （报名 / 退队 / 支付 / 录账单 / 核销 / 补招 / 复制重开）。
// 这是修复"看似失败、实则已成功"的关键：非幂等请求也能被安全地自动重试。
const IDEMPOTENT_PATHS = [
  "/join", "/leave", "/kick", "/bill", "/checkin", "/recreate", "/members", "/messages",
];

// 422 字段名 → 中文，避免把 Pydantic 的 body.dining_time 直接甩给用户
const FIELD_LABELS = {
  dining_time: "就餐时间",
  target_size: "目标人数",
  restaurant_id: "餐馆",
  cuisine_type: "就餐品类",
  dish_ids: "预选菜品",
  total_amount: "账单金额",
  checkin_code: "核销码",
  content: "消息内容",
  real_name: "真实姓名",
  id_card: "证件号码",
  consent: "协议同意",
  age: "年龄",
  nickname: "昵称",
  gender: "性别",
  username: "用户名",
  password: "密码",
  name: "队伍名",
  mode: "组队模式",
  code: "邀请码",
  reason: "举报原因",
};

// 并发请求计数：全部结束才隐藏 loading
let loadingCount = 0;

function showLoading() {
  loadingCount += 1;
  if (loadingCount === 1) {
    uni.showLoading({ title: "加载中…", mask: true });
  }
}

function hideLoading() {
  loadingCount = Math.max(0, loadingCount - 1);
  if (loadingCount === 0) {
    uni.hideLoading();
  }
}

export function getToken() {
  return uni.getStorageSync(TOKEN_KEY) || "";
}

export function setToken(token) {
  uni.setStorageSync(TOKEN_KEY, token);
}

export function clearToken() {
  uni.removeStorageSync(TOKEN_KEY);
}

/** 生成幂等键（小程序无 crypto.randomUUID 的兼容写法） */
function makeIdemKey() {
  return "k-" + Date.now().toString(36) + "-" + Math.random().toString(36).slice(2, 12);
}

function needsIdemKey(method, path) {
  if (method === "GET") return false;
  return IDEMPOTENT_PATHS.some((p) => path.indexOf(p) !== -1);
}

// ---------- 401 自愈 ----------
// 重新登录能力由 App.vue 注入（若直接 import store 会形成 request ↔ store 循环引用）
let reloginHandler = null;
let reloginPromise = null;
let reloginInFlight = false; // 重登流程执行中：期间再撞 401 不再排队，避免自等待死锁

export function setReloginHandler(fn) {
  reloginHandler = fn;
}

/** 并发 401 共用同一次重登，避免打爆登录接口 */
function relogin() {
  if (!reloginHandler) return Promise.resolve(false);
  if (!reloginPromise) {
    reloginInFlight = true;
    reloginPromise = Promise.resolve()
      .then(() => reloginHandler())
      .then((user) => !!user)
      .catch(() => false)
      .finally(() => {
        reloginPromise = null;
        reloginInFlight = false;
      });
  }
  return reloginPromise;
}

/** 传输层失败分类：区分超时 / 连不上 / 其它，不再一律「网络异常」 */
function classifyFail(err) {
  const msg = (err && err.errMsg) || "";
  if (/timeout/i.test(msg)) return "请求超时，请检查后端服务";
  if (/fail|refus|network|connect/i.test(msg)) return "连不上后端服务（" + HOST + "）";
  return "请求失败：" + (msg || "未知错误");
}

/**
 * 发起请求。
 * @param {object} opts.loading 请求期间显示全局 loading（默认 true，静默刷新传 false）
 * @param {boolean} opts._retry 内部标记：401 重登后的自动重发（防止无限重试）
 * @param {string} opts._idemKey 内部标记：本次使用的幂等键（重发时复用同一个键）
 */
function request(path, method = "GET", data = null, opts = {}) {
  const { loading = true, _retry = false } = opts;
  const idemKey = opts._idemKey || (needsIdemKey(method, path) ? makeIdemKey() : "");
  if (loading) showLoading();
  return new Promise((resolve, reject) => {
    let settled = false;
    // 先收起 loading 再弹 toast：小程序里二者共用同一浮层，顺序反了 toast 会被立刻关掉
    const done = () => {
      if (settled) return;
      settled = true;
      if (loading) hideLoading();
    };
    const failOut = (title) => {
      done();
      uni.showToast({ title, icon: "none" });
    };

    const header = {
      Authorization: "Bearer " + getToken(),
      "Content-Type": "application/json",
    };
    if (idemKey) header["Idempotency-Key"] = idemKey;

    uni.request({
      url: HOST + path,
      method,
      data,
      timeout: REQUEST_TIMEOUT,
      header,
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          done();
          resolve(res.data);
          return;
        }

        if (res.statusCode === 401) {
          done();
          clearToken();
          // 仅登录/注册端点自身不自愈（避免递归）；/api/auth/me 等其他接口照常自愈
          if (AUTH_ENDPOINTS.indexOf(path) !== -1) {
            uni.showToast({ title: "登录失败，请重试", icon: "none" });
            reject(res);
            return;
          }
          if (reloginInFlight) {
            // 重登流程内部再撞 401：不再重登（否则会等待自己造成死锁）
            uni.showToast({ title: "登录已失效，请重新进入小程序", icon: "none" });
            reject(res);
            return;
          }
          // GET 天然幂等；变更类请求带幂等键时可安全重发（服务端回放首次结果）
          const canAutoRetry = !_retry && (method === "GET" || !!idemKey);
          relogin().then((ok) => {
            if (ok && canAutoRetry) {
              resolve(request(path, method, data, { loading: false, _retry: true, _idemKey: idemKey }));
            } else if (ok) {
              uni.showToast({ title: "登录已刷新，请重试刚才的操作", icon: "none" });
              reject(res);
            } else {
              uni.showToast({ title: "登录已失效，请重新进入小程序", icon: "none" });
              reject(res);
            }
          });
          return;
        }

        if (res.statusCode === 429) {
          failOut((res.data && res.data.detail) || "操作过于频繁，请稍后再试");
          reject(res);
          return;
        }

        if (res.statusCode === 403 && /实名/.test((res.data && res.data.detail) || "")) {
          done();
          uni.showModal({
            title: "需要实名认证",
            content: "完成实名后才能使用约饭功能",
            confirmText: "去实名",
            success: (r) => {
              if (r.confirm) uni.navigateTo({ url: "/pages/me/me" });
            },
          });
          reject(res);
          return;
        }

        failOut(readableError(res));
        reject(res);
      },
      fail(err) {
        failOut(classifyFail(err));
        reject(err);
      },
    });
  });
}

function readableError(res) {
  let detail = res.data && res.data.detail;
  if (Array.isArray(detail) && detail.length) {
    // FastAPI 422 校验错误：取第一条并翻译字段名，如 "就餐时间：时间必须晚于当前时间"
    const e = detail[0];
    const loc = (e.loc || []).filter((x) => x !== "body").join(".");
    const label = FIELD_LABELS[loc] || loc;
    return (label ? label + "：" : "") + (e.msg || "参数错误");
  }
  if (detail === undefined || detail === null) return "请求失败";
  if (typeof detail === "string") return detail;
  return JSON.stringify(detail);
}

export const get = (path, opts) => request(path, "GET", null, opts);
export const post = (path, data, opts) => request(path, "POST", data, opts);
export const patch = (path, data, opts) => request(path, "PATCH", data, opts);
export const del = (path, opts) => request(path, "DELETE", null, opts);

export default request;
