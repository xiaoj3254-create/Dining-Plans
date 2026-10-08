// 「选餐馆 → 选菜」跨页面选择桥。
// 小程序 navigateBack 不能带参，且这里是跨两层页面返回（选菜页 → 发起页），
// 用 store 暂存选择结果，发起页 onShow 时消费（比 getCurrentPages() 取页面实例稳）。
import { defineStore } from "pinia";

export const useMealStore = defineStore("meal", {
  state: () => ({
    restaurant: null, // 当前已选餐馆（含 dishes 时也存这里）
    dishes: [], // 当前已选菜品
    pending: null, // 待发起页消费的回填数据
  }),
  getters: {
    dishIds: (s) => s.dishes.map((d) => d.id),
    estimateTotal: (s) => s.dishes.reduce((sum, d) => sum + Number(d.price || 0), 0),
  },
  actions: {
    /** 选菜页「确定」与「暂不选菜」都走这里 */
    setSelection(restaurant, dishes) {
      this.restaurant = restaurant;
      this.dishes = dishes || [];
      this.pending = { restaurant, dishes: dishes || [] };
    },
    /** 发起页取走回填数据（取走即清空，避免重复回填） */
    takePending() {
      const p = this.pending;
      this.pending = null;
      return p;
    },
    reset() {
      this.restaurant = null;
      this.dishes = [];
      this.pending = null;
    },
  },
});
