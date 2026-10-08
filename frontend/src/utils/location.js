// 定位：用于广场/组队的「距离」展示与距离筛选。
// 设计取舍：坐标只在客户端使用 —— 传给后端仅用于本次请求算距离与排序，后端不落库。
// 定位失败（拒绝授权/超时）时必须优雅降级：不展示距离、禁用距离筛选，而不是阻塞页面。
import { toast } from "./ui";

const CACHE_MS = 5 * 60 * 1000; // 5 分钟内复用，避免频繁弹定位授权
let cache = { at: 0, coord: null, denied: false };

function getLocationOnce(timeout = 4000) {
  return new Promise((resolve) => {
    uni.getLocation({
      type: "gcj02",
      timeout,
      success: (res) => resolve({ latitude: res.latitude, longitude: res.longitude }),
      fail: () => resolve(null),
    });
  });
}

/**
 * 获取我的位置。
 * @returns {Promise<{latitude:number, longitude:number}|null>} null 表示不可用（未授权/失败）
 */
export async function getMyLocation({ force = false, silent = true } = {}) {
  if (!force && cache.coord && Date.now() - cache.at < CACHE_MS) return cache.coord;
  if (!force && cache.denied) return null;

  const coord = await getLocationOnce();
  if (!coord) {
    cache = { at: Date.now(), coord: null, denied: true };
    if (!silent) {
      toast("未获取到定位，距离信息暂不可用（可在设置中开启定位权限）");
    }
    return null;
  }
  cache = { at: Date.now(), coord, denied: false };
  return coord;
}

/** 定位是否已被拒绝（用于禁用"距离"筛选项并给出说明） */
export function isLocationDenied() {
  return !!cache.denied;
}

/** 清空缓存（切换账号 / 手动重试时用） */
export function resetLocationCache() {
  cache = { at: 0, coord: null, denied: false };
}
