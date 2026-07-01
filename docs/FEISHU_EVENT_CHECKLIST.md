# 飞书事件订阅检查清单（被测 Bot 管理员）

适用于使用 **长连接** 接收飞书事件的 Bot。

## 为什么没有 Webhook 地址？

在 **开发配置 → 事件与回调 → 事件配置** 中，若订阅方式为：

> **使用长连接接收事件**

则页面上 **不会出现「请求地址」**，这是正常现象。

| 模式 | 是否需要 URL | Bot 如何收消息 |
|------|-------------|----------------|
| HTTP 回调（Webhook） | 需要填请求地址 | 飞书 POST 到你的服务器 |
| **长连接** | **不需要 URL** | Bot 服务器用 SDK 主动连飞书 |

`backend.health_url` / `callback_url` 用于探测**你的业务服务**是否在线，**不是**飞书事件推送地址。

---

## 必做：确认「接收消息」事件已订阅

长连接 Bot 要能 @ 回复，必须订阅 **接收消息** 事件。

### 操作步骤

1. 登录 [飞书开放平台](https://open.feishu.cn/app)
2. 进入**被测 Bot** 应用
3. **开发配置 → 事件与回调 → 事件配置**
4. 确认 **订阅方式** 为「长连接」
5. **已添加事件** 中须包含：

| 事件名称 | event_type | 是否必需 |
|----------|------------|----------|
| **接收消息** | `im.message.receive_v1` | **必需** |
| 机器人进群 | `im.chat.member.bot.added_v2` | 可选 |
| 机器人被移出群 | `im.chat.member.bot.deleted_v2` | 可选 |

6. **保存** 并 **发布版本**

### 验证

在测试群 @被测 Bot 发「你好」，应在数秒内收到回复。

---

## 建议开通的权限（被测 Bot）

| 权限 | 用途 |
|------|------|
| `im:message` | 收发消息 |
| `im:message:send_as_bot` | 以 Bot 身份发消息 |
| `im:chat` | 获取群信息 |
| `im:chat.members:read` | 读取群成员 |
| `contact:user.base:readonly` | 用户信息（越权测试） |
| `docx:document:readonly` / `wiki:wiki:readonly` | 文档测试 |

---

## 日志在哪里查

| 查什么 | 去哪里 |
|--------|--------|
| Bot 调用飞书 API | **运营监控 → 日志检索** |
| 业务逻辑 / 模型 | Bot **服务器日志** |
| 飞书 webhook 推送记录 | 长连接模式 **无此项** |

---

## 与巡检配置的对应关系

`config/bots.yaml` 中长连接 Bot 示例：

```yaml
feishu:
  event_mode: long_connection

backend:
  health_url: https://your-gateway.example.com/
  callback_url: https://your-gateway.example.com/
  log_query:
    type: skip
    trace_field: request_id
```

---

## 发布前自检

- [ ] 已订阅 `im.message.receive_v1`
- [ ] 已发布最新版本
- [ ] 被测 Bot 与 Inspector 均在测试群
- [ ] 测试群 `chat_id` 已填入 `bots.yaml`
