// 统一交互反馈：toast / 确认弹窗。全项目只用这里的封装，保证样式与文案口径一致。
const BRAND = "#6c5ce7";

/** 轻提示（默认无图标，1.8s） */
export function toast(title, icon = "none") {
  uni.showToast({ title, icon, duration: 1800 });
}

/** 成功提示 */
export function toastOk(title) {
  toast(title, "success");
}

/**
 * 二次确认弹窗，resolve(true/false)
 * @param {object} opts { title, content, confirmText }
 */
export function confirm(opts = {}) {
  return new Promise((resolve) => {
    uni.showModal({
      title: opts.title || "确认操作",
      content: opts.content || "",
      confirmText: opts.confirmText || "确定",
      confirmColor: BRAND,
      cancelColor: "#636e72",
      success: (res) => resolve(!!res.confirm),
      fail: () => resolve(false),
    });
  });
}
