# API 一览（api.md）

Base URL：`http://127.0.0.1:8000`。除注册/登录/支付宝登录外，均需 `Authorization: Bearer <JWT>`；
核心业务端点额外要求实名（未实名 403）；变更类端点还会校验账号是否被限制（`restricted` → 403）。

## 通用约定（2026-10-08 整改新增）

| 约定 | 说明 |
|---|---|
| **幂等键** | 变更类端点支持 `Idempotency-Key: <uuid>` 请求头，重复提交直接**回放首次响应**，不会二次执行业务动作。前端已对 `/join`、`/leave`、`/kick`、`/bill`、`/checkin`、`/recreate`、`/members`、`/messages` 自动附加 |
| **限流** | 滑动窗口（60s），超限返回 **429**。维度：认证（按 IP）、邀请码尝试 / 变更类 / 发消息 / 举报（按用户）。阈值见 `app/core/config.py` |
| **时间格式** | 所有时间字段出站为**带偏移**的 ISO 8601（`2026-10-07T20:00:00+08:00`）；入站可带偏移，裸时间按服务端配置时区解释 |
| **协议同意** | 注册与新用户授权登录必须携带 `consent: true`；实名登记必须携带 `consent: true`（敏感个人信息单独同意） |
| **JWT 版本** | 注销后 `token_version` 递增，旧 token 立即 401 |

## 认证

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/auth/register | 注册 `{username,password,nickname,age(≥18),gender,consent}` → `{access_token,user}` |
| POST | /api/auth/login | 登录 → `{access_token,user}` |
| POST | /api/auth/alipay | 小程序授权登录，MVP mock：`{code:"mock:用户名", consent:true}`；**新用户未同意 → 422** |
| GET | /api/auth/me | 本人信息（含 username / consent_version / restricted，仅自己可见） |

## 用户

| 方法 | 路径 | 说明 |
|---|---|---|
| PATCH | /api/users/me | 补填 `{nickname,age,gender}`；**实名后改 age → 409**（年龄以证件为准） |
| POST | /api/users/me/consent | 记录协议同意版本 `{version}` |
| POST | /api/users/me/realname | 实名登记 `{real_name,id_card,consent}`；校验姓名汉字格式 + 身份证 GB 11643 校验位；从证件推算年龄（<18 → 422）并锁定 |
| **DELETE** | **/api/users/me** | **注销账号**：匿名化个人信息、关闭进行中的队伍、全部 token 失效 |
| GET | /api/users/me/teams | 我的组队（按状态分组，含 `fail_reason`、invite 模式的 `code`） |
| **GET** | **/api/users/me/blocks** | 我的黑名单 id 列表 |

## 举报与拉黑

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/reports | `{target_user_id,team_id?,message_id?,reason,detail?}`；reason ∈ harassment/fraud/abuse/illegal/other；累计达阈值自动限制（`DP_REPORT_AUTO_RESTRICT_THRESHOLD`） |
| POST | /api/blocks | 拉黑 `{target_user_id,reason?}`：跨队生效（互相看不到对方队伍、无法入队） |
| DELETE | /api/blocks/{target_user_id} | 解除拉黑 |

## 餐馆与菜品（参考数据，只读）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/restaurants?cuisine=&keyword=&page=&page_size= | 餐馆列表；keyword 命中 名称/菜系/商圈；含 dish_count |
| GET | /api/restaurants/{id} | 餐馆详情（含全部 dishes） |
| GET | /api/restaurants/{id}/dishes?category=&keyword= | 该店菜品（可按分类/关键词过滤） |

字段：餐馆 `{id,name,cuisine_type,district,avg_price,description,image,latitude,longitude,dish_count}`；
菜品 `{id,name,price,category,tags,image}`。
`image` 恒为小程序包内路径 `/static/food/<文件名>`（缺图回退 `_default.png`）。
坐标用于客户端计算"距离"，为演示用近似值（单一数据源 `scripts/menu_catalog.json`）。

## 静态托管

`GET /uploads/chat/<32位随机名>.<jpg|png|webp|gif>`：群聊图片。
文件名由服务端生成，目录内不存在可执行内容。

## 组队

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | /api/teams | 创建草稿 `{name,mode,target_size?,cuisine_type?,dining_time?,menu_summary?,location_hint?,restaurant_id?,dish_ids?}`；`removed_dishes` 回报被下架剔除的菜品 |
| PATCH | /api/teams/{id} | 改草稿（队长+draft）；**招募期队长也可修改**（改后通知全部队员，见 `team_updated`）；传 dish_ids 覆盖预选菜单；换 restaurant_id 且不带 dish_ids 则清空旧快照 |

招募期修改的额外守卫：目标人数不得小于已入队人数、组队模式不可更改、用餐时间必须仍在未来
（均 422）；若改后刚好满员则立即成团，不留"剩余 0 人却仍在招募"的僵尸状态。
| POST | /api/teams/{id}/publish | 发布（**必填校验 422**：队伍名/目标人数≥2/就餐品类/餐馆/就餐时间，且时间须晚于当前） |
| GET | /api/teams/{id} | 详情。**非成员**只返回 `profile` 概况（`members: []` + `members_hidden: true`）；成员可见名单（含 `user_id`）；含 `bill_status` / `can_leave` / `fail_reason` |
| POST | /api/teams/{id}/join | 广场报名 |
| POST | /api/teams/join/{code} | 链接报名 / **成团后补位**（有空缺席位时可用） |
| POST | /api/teams/{id}/leave | 退出。招募中任何人可退（队长除外）；**成团后账单生效前队员可退** |
| POST | /api/teams/{id}/members | **队长补招**（query `target_user_id`） |
| POST | /api/teams/{id}/members/{uid}/kick | 踢人（仅队长）；被踢者进入该队冷却，不可再报 |
| POST | /api/teams/{id}/disband | 解散（成团后 409） |
| POST | /api/teams/{id}/invite/close | 关闭链接邀请（仅队长） |
| POST | /api/teams/{id}/abort | 核销异常解散（有成功支付则 409） |
| POST | /api/teams/{id}/recreate | 复制配置重开（仅 failed）；过期就餐时间置空由用户重选 |

## 广场

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/plaza/teams?page=&page_size=&cuisine=&mode=&keyword=&meal_period=&lat=&lng=&max_distance_km=&sort= | 仅 `recruiting` 且**用餐时间仍在未来**；过滤与我有拉黑关系的队长 |

查询参数（2026-10-08 体验优化新增）：

| 参数 | 取值 | 说明 |
|---|---|---|
| `cuisine` | 菜系名，**支持逗号分隔多选** | 如 `火锅,烧烤` → 维度内取并集（命中任一即可） |
| `meal_period` | `lunch` / `dinner`，**支持逗号分隔多选** | 午市 11:00–14:59 / 晚市 16:00–21:59；`lunch,dinner` 合并两段 |
| `lat` / `lng` | 数值 | 客户端自身坐标。**只在本次请求内用于算距离与排序，服务端不落库** |
| `max_distance_km` | 0–50 | 半径筛选（上限语义，单选），需同时传 `lat`/`lng` |
| `sort` | `time`（默认）/ `distance` | 按时间升序 / 按距离升序（无坐标的队伍排在最后） |

多选筛选的边界约定：同一维度内取并集（OR），跨维度取交集（AND）；
若 `meal_period` 提供了多个值，全部非法才返回 422，部分非法时忽略非法值（宽进）。
单值写法与多选写法走同一代码路径，保持向后兼容。

卡片字段：`remaining` / `profile` / `restaurant{...,latitude,longitude}` /
`recruit_deadline`（招募截止 = 用餐时间 + 宽限期，前端据此显示"剩余招募时长"）/
`distance_km`（仅在传了坐标时返回）。keyword 亦命中餐馆名与商圈。

## 群聊（成团后开放）

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/teams/{id}/messages?before_id=&limit= | 历史（游标分页）；每项含 `is_me`（服务端按 user_id 判定）、`sender_id`、`mentions_all`、`recalled` |
| POST | /api/teams/{id}/messages | 发消息 `{content, msg_type, mentions_all}`；文本命中内容安全策略 → 422 |
| **POST** | **/api/teams/{id}/uploads** | **上传群聊图片**（multipart，字段名 `file`）→ `{url,size,content_type}` |
| POST | /api/teams/{id}/messages/{mid}/recall | 撤回本人消息（2 分钟内，文本与图片均可） |

图片消息：先调上传接口拿到 `url`，再以 `msg_type="image"` 发送；`content` 必须是
本站上传路径（外链一律 422，防盗图/防钓鱼）。上传限制：白名单 jpg/png/webp/gif、
默认单张 ≤2MB（`DP_UPLOAD_MAX_BYTES`）、服务端随机文件名（不使用客户端文件名）、
每用户每分钟 `DP_UPLOAD_PER_MIN` 次。

`@全体成员`：`mentions_all=true`，**仅队长**可置位（其他角色 403）。

## 到场确认 / 账单

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/teams/{id}/checkins | 全员到场进度（**仅成员**，非成员 403） |
| GET | /api/teams/{id}/checkins/me | 本人核销码（**仅成员本人**） |
| POST | /api/teams/{id}/checkin | 确认到场 `{checkin_code}`；账单生效后 → 409 |
| POST | /api/teams/{id}/bill | 队长录账单 `{total_amount}`（Decimal，>0） |
| GET | /api/teams/{id}/bill | 账单 + 各成员支付状态 + `i_am_payer`（缺席者不参与分摊） |
| POST | /api/teams/{id}/bill/pay | 本人独立结账（模拟，即时到账） |

## 通知

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | /api/notifications?unread_only=&page=&page_size= | 列表 + `unread` 总数 + `has_more`；每项含 `team_id` 与 `category`（`todo`/`info`） |
| POST | /api/notifications/{id}/read | 标已读 |
| POST | /api/notifications/read-all | 全部已读 |
| DELETE | /api/notifications/{id} | 删除本人通知（左滑删除；他人通知 404） |

通知类型：`member_joined` / `member_left` / `team_updated`（队长修改了饭局）/
`kicked` / `formed` / `bill_submitted`（队长已录入账单）/ `bill_effective` /
`team_failed` / `team_completed` / `checkin_reminder` / `checkin_overdue` /
`checkin_escalated` / `report_result`。

`category` 为 `todo` 表示需要用户处理（前端置顶并给"去处理"直达按钮）。

## WebSocket `/ws`

**首帧鉴权**（推荐）：连接后发送 `{"action":"auth","token":"<JWT>"}`，服务端回 `connected` 后再订阅。
兼容旧的 `?token=` query 方式（会写入访问日志，建议尽快迁移）。

订阅：`{"action":"subscribe","channels":["team:1","user:5","plaza"]}`
- team:* 仅活跃成员；user:* 仅本人；plaza 任何实名用户

下行事件：
`team.member_joined / team.member_left / team.formed / team.status_changed / chat.message / checkin.updated / bill.updated / pay.updated / plaza.changed / notification.new`

心跳：客户端发 `{"action":"ping"}` → `{"event":"pong"}`

## 错误约定

- 401 未登录/过期/已注销（token_version 不匹配）
- 403 权限不足（非成员）/ 未实名 / 账号被限制 / 被踢出后重报 / 拉黑关系
- 404 不存在
- 409 状态冲突（满员/已成团/账单已生效/资源并发修改）
- 422 参数校验失败（Pydantic / 发布守卫 / 内容安全 / 未同意协议）
- **429 触发限流**
- 500 内部异常（DB 约束冲突已统一映射为 409，业务规则路径不应出现 500）

## 运维端点

`GET /health` → `{status, env, tz, realname_mode, push_provider, consent_version}`
