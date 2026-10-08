# 状态机规格（state-machine.md）

> 2026-10-08 随全量审查整改更新：新增 `expire` / `fill_seat` / 成团后 `leave` 与补位流转，
> 账单生效条件由"全员到场"改为"核销窗口关闭"，核销语义明确为"本人确认到场"。

## 状态

```
draft ──publish──▶ recruiting ──AUTO_FORM(满员链式)──▶ formed ──AUTO_COMPLETE(全付清链式)──▶ completed
   │                    │                                 │
   │                    ├──(disband)──▶ failed            ├──(abort / 核销异常)──▶ failed
   │                    └──(expire / 招募超时)──▶ failed  │
   └──(disband)──▶ failed                                 └──(leave / fill_seat / join_by_link：原地流转)
```

`failed` 会写入归因字段 `fail_reason`：`disbanded` / `checkin_aborted` / `expired` / `user_deleted`。

## 事件

CREATE（服务层直建）/ UPDATE_DRAFT / PUBLISH / JOIN / JOIN_BY_LINK / LEAVE / KICK /
FILL_SEAT / DISBAND / CLOSE_INVITE / AUTO_FORM / CHECKIN / SUBMIT_BILL / AUTO_BILL_LOCK /
PAY / AUTO_COMPLETE / ABORT / EXPIRE

## 流转表（实现于 `backend/app/agent/transitions.py`）

| # | 当前态 | 事件 | 守卫 | 目标态 | 副作用 |
|---|--------|------|------|--------|--------|
| 1 | draft | UPDATE_DRAFT | g_is_leader | draft | 更新字段 |
| 2 | draft | PUBLISH | g_is_leader, g_publish_fields（显式 None 判定 + 时间未来 + 人数≥2） | recruiting | invite 模式生成 12 位 code；广播 plaza.changed |
| 3 | recruiting | JOIN | g_not_member★, g_not_blocked, g_slot_available★ | recruiting | 复活/插入成员行 + 成员事件流水；通知队长；满员→链式 AUTO_FORM |
| 4 | recruiting | JOIN_BY_LINK | g_invite_entry, g_not_member★, g_not_blocked, g_slot_available★ | recruiting | 同上 |
| 5 | recruiting | LEAVE | g_member_not_leader | recruiting | status=left；size-1；通知队长；广场补空位 |
| 6 | recruiting | KICK | g_is_leader, g_kick_target | recruiting | status=kicked（进入该队冷却）；通知被踢者 |
| 7 | recruiting | DISBAND | g_is_leader | failed | fail_reason=disbanded；通知全员；广场下架 |
| 8 | recruiting | CLOSE_INVITE | g_is_leader | recruiting | invite_open=false |
| 9 | recruiting | AUTO_FORM | g_is_full | formed | formed_at；预生成全员到场码；建群欢迎 system 消息；通知全员；广播 team.formed |
| 10 | recruiting | **EXPIRE** | g_expired（就餐时间 + 宽限期已过） | failed | fail_reason=expired；通知全员；广场下架 |
| 11 | formed | CHECKIN | g_checkin_code（码匹配 + 未确认 + 账单未生效） | formed | checked_at=now；广播；窗口关闭→链式 AUTO_BILL_LOCK |
| 12 | formed | **LEAVE** | g_member_not_leader, g_leave_window_open（账单未生效） | formed | 释放名额；通知队长；允许留空席 |
| 13 | formed | **FILL_SEAT** | g_is_leader, g_fill_seat_target, g_slot_available_formed★ | formed | 补招指定用户：成员行 + 到场码 + 系统消息 + 通知本人 |
| 14 | formed | **JOIN_BY_LINK** | g_invite_entry, g_not_member★, g_not_blocked, g_slot_available_formed★ | formed | 邀请码补位（持码者本人入队） |
| 15 | formed | SUBMIT_BILL | g_is_leader, g_bill_editable, g_bill_amount | formed | upsert bill(pending)；窗口已关→链式 AUTO_BILL_LOCK |
| 16 | formed | AUTO_BILL_LOCK | g_bill_lockable（账单已录 + **核销窗口已关闭**） | formed | bill=locked；per_capita 快照；**按实际到场者**生成 payments（队长补差）；通知并推送 |
| 17 | formed | PAY | g_unpaid_payment | formed | payment=paid；广播；全付清→链式 AUTO_COMPLETE |
| 18 | formed | AUTO_COMPLETE | g_all_paid | completed | completed_at；bill=settled；通知全员 |
| 19 | formed | ABORT | g_is_leader, g_abort_allowed（无成功支付） | failed | bill=void；fail_reason=checkin_aborted；通知全员；recreate 可复制重开 |
| 20 | formed | DISBAND | **不在表内** → TransitionForbidden → 409 | — | 成团后禁止解散（防恶意跑路） |

★ 带写副作用的守卫（原子抢名额）必须位于守卫列表最后。

## 链式触发

`JOIN/JOIN_BY_LINK → AUTO_FORM`、`CHECKIN/SUBMIT_BILL → AUTO_BILL_LOCK`、
`PAY → AUTO_COMPLETE`。链式调用在同一事务内递归 `dispatch()`，保证原子性；
链式守卫失败被吞掉不阻断主事件（如账单未录时确认到场仍成功）。

## 账单生效条件（整改要点）

原实现要求"**全员到场**才锁账"——只要有一人不确认到场，账单永远停在 `pending`，
全队无法支付，队伍彻底卡死。现改为：

```
核销窗口关闭 = 全员已确认到场  或  now >= dining_time + CHECKIN_GRACE_HOURS(默认 2h)
```

窗口关闭后按 **实际到场人数** 均摊，缺席者不参与分账（不出现在 payments 中）。
窗口关闭有两个触发点：链式（最后一次确认到场 / 队长录账单）+ 巡检
`notify_service.scan_bill_lock`（没人再操作时的兜底收口）。

账单生效后核销窗口关闭（`g_checkin_code` 拒绝），防止"锁账后补确认到场白吃"。

## 并发安全（SQLite）

1. WAL 模式 + busy_timeout=5000（`db.py` 连接事件注入 PRAGMA）
2. 原子条件 UPDATE 抢名额：`UPDATE teams SET current_size=current_size+1 WHERE id=? AND status=? AND current_size<target_size`，
   rowcount==1 才算抢到；报名用 `status='recruiting'`，补位用 `status='formed'`（`concurrency.py`）
3. 复活式重加入：`UNIQUE(team_id,user_id)` 冲突时将旧行 UPDATE 回 active（**被踢者除外**）
4. 乐观锁 `version` 字段兜底非状态机路径更新
5. `autoflush=True`：保证链式副作用内 SELECT 能看到同事务未 flush 的插入
6. **DB 层 CHECK 约束**兜底不变量：`current_size <= target_size`、`target_size >= 2`、`current_size >= 0`
7. 唯一索引：`uq_checkin_code`、`uq_payment_bill_user`、`uq_member_team_user`、`uq_block_pair`、`uq_idem_user_key`

## 定时器（每 5 分钟一轮，`notify_service.run_all_scans`）

| 巡检 | 作用 |
|---|---|
| `scan_checkin_timeout` | 到场超时**阶梯提醒**：T+2h 提醒队长 → T+12h 提醒全员 → T+24h 升级提示可协调解散 |
| `scan_bill_lock` | 账单锁定收口：窗口已关且已录账单 → 触发 AUTO_BILL_LOCK |
| `expire_overdue` | 招募超时收口：就餐时间 + 宽限期仍未满员 → failed(expired) 并下架 |
| `deliver_push_outbox` | 订阅消息出队（未接正式 AppID 时标记 skipped，保留"该发什么"的证据链） |

幂等判定一律走结构化 `notifications.team_id` 列，不再解析 payload 文本
（原实现用子串匹配，`team 5` 会被 `team 55` 的历史通知误屏蔽）。

## 时间语义

全项目统一经 `app/core/timeutil.py`：

- 内部一律使用配置时区（`DP_TIMEZONE_OFFSET_HOURS`，默认 +08:00）下的 **naive 本地时间**；
- 入站时间统一 `to_local_naive()` 归一（带偏移则换算，裸时间按配置时区解释）；
- 出站统一 `iso()` 输出**带偏移**的 ISO 8601（`2026-10-07T20:00:00+08:00`）。

这样服务器 TZ 被设为 UTC 也不会让"就餐时间必须晚于当前"和核销窗口整体偏移 8 小时。

## 权限口径（整改要点）

原实现把权限判断散落在三处（状态机守卫 / 服务层断言 / 路由依赖），且没有矩阵测试——
`GET /teams/{id}/checkins` 就是漏网案例（非成员可读全员名单）。

统一约定：**凡涉及队伍资源读写的端点，必须先过 `assert_active_member` 或状态机守卫**。
`assert_active_member` 位于 `services/common.py`；`tests/test_audit_fixes.py::test_p1_authz_matrix_team_endpoints`
把"非成员 / 队员 / 队长"对全部资源端点的期望状态码钉死，防止再次漂移。
