// 环境配置：真机预览 / 真机调试时只需改这里
// - 模拟器：可用 127.0.0.1
// - 真机：必须换成开发机局域网 IP（如 http://192.168.1.5:8000）或 HTTPS 合法域名
export const HOST = "http://127.0.0.1:8000";
export const WS_URL = "ws://127.0.0.1:8000/ws";

// 请求超时（毫秒）。不设会走默认值，超时后只会得到笼统的「网络异常」
export const REQUEST_TIMEOUT = 15000;
