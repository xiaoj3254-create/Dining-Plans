// 展示层格式化工具：距离 / 倒计时 / 用餐时间 / 状态文案与配色。
// 各页面统一从这里取，避免"同一个字段在不同页面显示不一致"。

/** 两点球面距离（km）。与后端 plaza_service.haversine_km 同一算法 */
export function haversineKm(lat1, lng1, lat2, lng2) {
  const r = 6371;
  const toRad = (d) => (d * Math.PI) / 180;
  const p1 = toRad(lat1);
  const p2 = toRad(lat2);
  const dp = p2 - p1;
  const dl = toRad(lng2 - lng1);
  const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
  return 2 * r * Math.asin(Math.sqrt(a));
}

/**
 * 餐馆 → 我的距离文本。
 * @param {object} restaurant 含 latitude/longitude
 * @param {object} me {latitude, longitude} 可为 null（未授权定位）
 */
export function distanceText(restaurant, me) {
  if (!restaurant || !me || restaurant.latitude == null || restaurant.longitude == null) return "";
  if (me.latitude == null || me.longitude == null) return "";
  const km = haversineKm(me.latitude, me.longitude, restaurant.latitude, restaurant.longitude);
  return formatDistance(km);
}

export function formatDistance(km) {
  if (km == null || Number.isNaN(km)) return "";
  if (km < 1) return `${Math.max(50, Math.round((km * 1000) / 50) * 50)}m`;
  if (km < 10) return `${km.toFixed(1)}km`;
  return "10km+";
}

/** 解析后端返回的带偏移 ISO（部分环境 Date 解析差异，这里做兜底） */
export function parseTime(iso) {
  if (!iso) return null;
  const t = Date.parse(iso.replace(" ", "T"));
  return Number.isNaN(t) ? null : t;
}

/** 剩余时间文案，如「还剩 2 小时 15 分」「还剩 12 分钟」「已结束」 */
export function countdownText(iso, { expired = "已结束" } = {}) {
  const t = parseTime(iso);
  if (t == null) return "";
  const diff = t - Date.now();
  if (diff <= 0) return expired;
  const mins = Math.floor(diff / 60000);
  if (mins < 60) return `还剩 ${Math.max(1, mins)} 分钟`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) {
    const rest = mins % 60;
    return rest ? `还剩 ${hours} 小时 ${rest} 分` : `还剩 ${hours} 小时`;
  }
  return `还剩 ${Math.floor(hours / 24)} 天`;
}

/** 是否已过期 */
export function isPast(iso) {
  const t = parseTime(iso);
  return t != null && t <= Date.now();
}

/** 用餐时间展示：10-09 20:06 */
export function diningTimeText(iso) {
  return iso ? iso.replace("T", " ").slice(5, 16) : "";
}

/** 用餐时段：午市 / 晚市 / 其他（与后端 MEAL_PERIODS 口径一致） */
export function mealPeriodOf(iso) {
  const t = parseTime(iso);
  if (t == null) return "";
  const h = new Date(t).getHours();
  if (h >= 11 && h < 15) return "午市";
  if (h >= 16 && h < 22) return "晚市";
  return "";
}

/**
 * 队伍状态 → 展示文案与配色类。
 * 状态色标准：蓝=进行中 / 绿=完成 / 灰=失效 / 红=警告
 */
export function teamStatusMeta(status, { isFull = false } = {}) {
  switch (status) {
    case "draft":
      return { text: "草稿", cls: "st-dead" };
    case "recruiting":
      return isFull
        ? { text: "已满员", cls: "st-done" }
        : { text: "招募中", cls: "st-progress" };
    case "formed":
      return { text: "已成团", cls: "st-done" };
    case "completed":
      return { text: "已完成", cls: "st-done" };
    case "failed":
      return { text: "已终止", cls: "st-dead" };
    default:
      return { text: status || "", cls: "st-dead" };
  }
}

/** 队伍终止原因文案（failed 时展示） */
export function failReasonText(reason) {
  return (
    {
      disbanded: "队长解散",
      checkin_aborted: "核销异常，已解散重开",
      expired: "招募超时未满员",
      user_deleted: "队长已注销",
    }[reason] || "已终止"
  );
}
