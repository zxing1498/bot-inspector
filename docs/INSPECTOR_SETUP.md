# 飞书 Inspector 检测应用配置指南

检测 Bot 是自动化测试的「操作员」，通过飞书 Open API 代你向被测 Bot 发消息、传文件、验回复。

## 1. 创建应用

1. 登录 [飞书开放平台](https://open.feishu.cn/app)
2. 创建企业自建应用，名称建议：`Bot巡检助手` 或 `Inspector`
3. 记录 **App ID** 和 **App Secret**

## 2. 所需权限（批量申请）

| 权限 | 用途 |
|---|---|
| `im:message` | 发送/接收消息 |
| `im:message:send_as_bot` | 以 Bot 身份发消息 |
| `im:chat` | 获取群信息 |
| `im:chat.members:read` | 验证 Bot 是否在群内 |
| `im:resource` | 上传/下载消息资源 |
| `contact:user.id:readonly` | 读取用户 open_id |
| `docx:document:readonly` | 文档访问测试（可选） |
| `wiki:wiki:readonly` | Wiki 访问测试（可选） |

## 3. 事件与回调（群内触发巡检必填）

进入 **开发配置 → 事件与回调**，需要配置**两块**（页签不同）：

### 3.1 事件配置（收 @ 消息）

- 页签：**事件配置**
- 订阅方式：**使用长连接接收事件**
- 添加事件：**接收消息** `im.message.receive_v1`
- 保存前须先运行 `python -m src.chat_trigger` 并保持在线

### 3.2 回调配置（配置卡片「提交」按钮，可选但推荐）

- 页签：**回调配置**（不是事件配置）
- 订阅方式：**使用长连接接收回调**
- 添加回调：**卡片回传交互**（新版 `card.action.trigger`）
- 搜索中文名「卡片回传交互」，不要搜 `card.action.trigger` 英文字符串
- 详见 [ONBOARDING.md](ONBOARDING.md)

不配回调时仍可用文字模板完成「测试 Bot」注册流程。

若仅 CLI 巡检、不用群内指令，可跳过事件订阅，改用消息列表轮询。

## 4. 发布与加群

1. 创建版本并发布到目标租户
2. 将 Inspector Bot 加入：
   - 普通测试群
   - 话题测试群
3. 将被测 Bot 也加入相同测试群

## 5. 获取 chat_id

在测试群中 @Inspector Bot 发消息后，通过开放平台 API 调试台或以下接口获取：

```
GET /open-apis/im/v1/chats
```

### 私聊（dm）特别注意

**不要**把「你与目标 Bot 私聊时问出来的 chat_id」填进 `bots.yaml` 的 `dm` 字段。

- 该 chat_id 属于 **用户 ↔ 被测 Bot** 的会话
- Inspector 是另一个 Bot，不在该会话里，发消息会报 `Bot/User can NOT be out of the chat`

私聊自动化已改为：Inspector 使用被测 Bot 的 **`open_id`** 发私聊（见 `bots.yaml` 的 `open_id` 字段）。  
`dm` 字段仅作 API 返回 chat_id 的回退，一般无需手动填写。

## 6. 配置环境变量

复制 `.env.example` 为 `.env` 并填写：

```env
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

## 7. 填写 Bot 台账

复制 `config/bots.yaml.example` 为 `config/bots.yaml` 并填写被测 Bot 信息。详见 [GETTING_STARTED.md](GETTING_STARTED.md)。

若被测 Bot 使用 **长连接**，请参阅 [FEISHU_EVENT_CHECKLIST.md](FEISHU_EVENT_CHECKLIST.md)。

## 9. 普适性接入（推荐）

在群里 @Inspector 发送 `测试 <Bot名>`，通过配置卡片完成注册与校验，详见 [ONBOARDING.md](ONBOARDING.md)。

## 8. 验证安装

```bash
pip install -r requirements.txt
python -m src.runner --bot all --suite p0 --dry-run
python -m src.runner --bot demo-bot --suite p0
```
