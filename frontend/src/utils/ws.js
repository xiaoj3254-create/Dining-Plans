// WebSocket 封装：首帧鉴权 / 订阅 / 心跳 / 断线重连 / 前台恢复重放订阅
import { getToken, get } from "./request";
import { WS_URL } from "./config";

const listeners = {}; // event -> [fn]
let socketTask = null;
let subscribedChannels = [];
let reconnectTimer = null;
let heartbeatTimer = null;
let closedByUser = false;

function emit(event, data) {
  (listeners[event] || []).forEach((fn) => {
    try {
      fn(data);
    } catch (e) {
      console.error("ws listener error", e);
    }
  });
}

export function on(event, fn) {
  (listeners[event] = listeners[event] || []).push(fn);
}

export function off(event, fn) {
  listeners[event] = (listeners[event] || []).filter((f) => f !== fn);
}

function _connect() {
  if (socketTask || !getToken()) return;
  closedByUser = false;
  // 不在 URL 上带 token：避免写进服务器/网关访问日志，改为连上后的首帧鉴权
  socketTask = uni.connectSocket({
    url: WS_URL,
    success: () => {},
  });
  socketTask.onOpen(() => {
    socketTask.send({
      data: JSON.stringify({ action: "auth", token: getToken() }),
      fail: () => {},
    });
    _heartbeat();
  });
  socketTask.onMessage((res) => {
    try {
      const msg = JSON.parse(res.data);
      // 鉴权成功后服务端回 connected，此刻才重放订阅（顺序不能反）
      if (msg.event === "connected") {
        _subscribe(subscribedChannels);
      }
      if (msg.event && msg.event !== "pong") {
        emit(msg.event, { channel: msg.channel, data: msg.data });
      }
    } catch (e) {
      /* ignore */
    }
  });
  socketTask.onClose(() => {
    socketTask = null;
    clearInterval(heartbeatTimer);
    if (!closedByUser) _scheduleReconnect();
  });
  socketTask.onError(() => {
    try {
      socketTask && socketTask.close({});
    } catch (e) {
      /* noop */
    }
  });
}

function _subscribe(channels) {
  if (!socketTask || !channels.length) return;
  socketTask.send({
    data: JSON.stringify({ action: "subscribe", channels }),
    fail: () => {},
  });
}

function _heartbeat() {
  clearInterval(heartbeatTimer);
  heartbeatTimer = setInterval(() => {
    if (socketTask) {
      socketTask.send({ data: JSON.stringify({ action: "ping" }), fail: () => {} });
    }
  }, 25000);
}

function _scheduleReconnect() {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(() => _connect(), 3000);
}

/** 订阅频道（增量）。team 频道需为队伍成员 */
export function subscribe(channels) {
  const fresh = channels.filter((c) => !subscribedChannels.includes(c));
  if (!fresh.length) return;
  subscribedChannels = subscribedChannels.concat(fresh);
  if (socketTask) {
    _subscribe(fresh);
  } else {
    _connect();
  }
}

/** 取消订阅（例如退出/被踢出队伍后，避免继续收到该队事件） */
export function unsubscribe(channels) {
  subscribedChannels = subscribedChannels.filter((c) => channels.indexOf(c) === -1);
}

/** 前台恢复：重连并重放订阅（小程序切后台 WS 可能被系统回收） */
export function resume() {
  if (socketTask) {
    _subscribe(subscribedChannels);
  } else if (getToken()) {
    _connect();
  }
}

export function resetSocket() {
  closedByUser = true;
  subscribedChannels = [];
  clearInterval(heartbeatTimer);
  clearTimeout(reconnectTimer);
  if (socketTask) {
    try {
      socketTask.close({});
    } catch (e) {
      /* noop */
    }
    socketTask = null;
  }
}
