# 首次使用指南（从零到第一次巡检）

本指南假设你**从未用过飞书开放平台**，按步骤操作即可。若你把本仓库交给 AI Agent 部署，可同时阅读根目录 [AGENTS.md](../AGENTS.md)。

---

## 你将准备什么

| 角色 | 说明 |
|------|------|
| **Inspector（巡检员）** | 本项目对应的飞书自建应用，负责发消息、收指令、生成报告 |
| **被测 Bot** | 你要验收的另一个飞书应用 |
| **测试群** | 普通群即可；两个 Bot 都必须在群里 |

预计耗时：**30–60 分钟**（含开放平台审核等待）。

---

## 第 1 步：安装项目

```bash
git clone <你的仓库地址>
cd bot-inspector

python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS/Linux:
source .venv/bin/activate

pip install -r requirements.txt
```

---

## 第 2 步：创建 Inspector 应用并找到 App ID / Secret

### 2.1 创建应用

1. 浏览器打开 [飞书开放平台](https://open.feishu.cn/app)（国际版用 [open.larksuite.com](https://open.larksuite.com/app)）
2. 点击 **创建企业自建应用**
3. 名称建议：`Bot巡检助手` 或 `bot检查员`
4. 创建完成后进入应用详情

### 2.2 App ID 在哪？

1. 左侧 **凭证与基础信息**
2. 页面中部 **应用凭证** 区域
3. **App ID** 是一串以 `cli_` 开头的字符，例如 `cli_a1b2c3d4e5f67890`
4. 点击复制

### 2.3 App Secret 在哪？

1. 仍在 **凭证与基础信息**
2. **App Secret** 在 App ID 下方
3. 点击 **显示** 或 **重置** 后复制（只显示一次，请立即保存到密码管理器）

### 2.4 填入 `.env`

```bash
copy .env.example .env    # Windows
cp .env.example .env      # macOS/Linux
```

编辑 `.env`：

```env
FEISHU_APP_ID=cli_你的Inspector应用ID
FEISHU_APP_SECRET=你的AppSecret
INSPECTOR_AT_NAME=bot检查员

# 巡检结果发到这个群（与 TRIGGER_CHAT_IDS 通常相同）
NOTIFY_CHAT_ID=oc_稍后填写
TRIGGER_CHAT_IDS=oc_稍后填写
CHAT_TRIGGER_MODE=ws
```

> **注意**：`.env` 不要提交到 Git，已在 `.gitignore` 中。

### 2.5 申请权限

进入 **权限管理**，开通至少：

| 权限 | 用途 |
|------|------|
| 获取与发送单聊、群组消息 (`im:message`) | 发巡检消息 |
| 以应用身份发消息 (`im:message:send_as_bot`) | 群内播报 |
| 获取群组信息 (`im:chat`) | 读群信息 |
| 获取群成员列表 (`im:chat.members:read`) | 解析负责人姓名 |
| 上传与下载图片、文件 (`im:resource`) | 文件类用例 |
| 以应用身份读取通讯录 (`contact:user.base:readonly`) | 可选，负责人显示名 |

文档类用例还需：`docx:document:readonly`、`wiki:wiki:readonly` 等（见 [INSPECTOR_SETUP.md](INSPECTOR_SETUP.md)）。

### 2.6 配置事件（群内 @ 触发必填）

1. **开发配置 → 事件与回调 → 事件配置**
2. 订阅方式选 **使用长连接接收事件**
3. 添加 **接收消息** `im.message.receive_v1`
4. **先在本机运行**（下一步会讲）`python -m src.chat_trigger`，保持窗口不关
5. 回到开放平台点击 **保存**（长连接要求客户端在线）

可选：在 **回调配置** 添加 **卡片回传交互**，用于群内「测试 Bot」配置卡片。见 [ONBOARDING.md](ONBOARDING.md)。

### 2.7 发布应用

**版本管理与发布** → 创建版本 → 申请发布 → 在目标企业启用。

---

## 第 3 步：建测试群并获取 chat_id

1. 在飞书里新建群，例如「Bot 巡检测试群」
2. 把 **Inspector** 和 **被测 Bot** 都拉进群
3. 获取群 `chat_id`（`oc_` 开头），任选一种方法：

**方法 A — 看 Inspector 日志（推荐）**

```bash
python -m src.chat_trigger
```

在群里 @Inspector 发任意消息，终端会出现类似：

```
ws event chat=oc_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx type=text
```

`oc_` 后面整段即为 `chat_id`。

**方法 B — 开放平台 API 调试台**

调用 `GET /open-apis/im/v1/chats`，在返回列表中找到群名对应的 `chat_id`。

4. 把 `chat_id` 填入 `.env` 的 `NOTIFY_CHAT_ID` 和 `TRIGGER_CHAT_IDS`（多个群用英文逗号分隔）。

---

## 第 4 步：配置被测 Bot

### 4.1 复制台账模板

```bash
copy config\bots.yaml.example config\bots.yaml
copy config\bots_registered.yaml.example config\bots_registered.yaml
```

### 4.2 填写 `config/bots.yaml`

打开 `config/bots.yaml`，至少修改：

| 字段 | 说明 | 示例 |
|------|------|------|
| `name` | 台账里的 Bot 名称，巡检命令用这个名字 | `my-agent` |
| `app_id` | **被测 Bot** 的 App ID（不是 Inspector 的） | `cli_xxxx` |
| `open_id` | 被测 Bot 的 open_id | `ou_xxxx` |
| `chats.normal_group` | 测试群 chat_id | `oc_xxxx` |
| `capabilities` | 该 Bot 具备的能力标签 | 见 example 文件 |
| `test_assets.doc_permitted` | Bot **有权限**阅读的文档链接 | 你企业的飞书文档 URL |
| `test_assets.doc_denied` | Bot **无权限**阅读的文档链接 | 另一篇无权限文档 URL |

### 4.3 如何获取被测 Bot 的 open_id？

**方法 1 — 群内注册（推荐）**

```text
@bot检查员 测试 @被测Bot名称 my-agent
```

按卡片指引完成配置，系统会自动探测并写入 `bots_registered.yaml`。

**方法 2 — 开放平台**

对被测 Bot 调用 `GET /open-apis/bot/v3/info`（仅能查**当前应用自身**；查别的 Bot 需用群成员列表或注册流程）。

**方法 3 — 群成员 API**

`GET /im/v1/chats/{chat_id}/members`，在返回列表中找到 Bot 对应项的 `member_id`（`open_id`）。

### 4.4 准备测试文档

文档类用例需要两篇链接：

- **doc_permitted**：确认被测 Bot 的应用有阅读权限
- **doc_denied**：确认被测 Bot **没有**权限（用于测拒绝提示）

可在 `config/test_defaults.yaml` 改全局默认，或在 `bots.yaml` 的 `test_assets` 里按 Bot 覆盖。

---

## 第 5 步：验证安装（dry-run）

不调用飞书 API，检查用例与配置能否加载：

```bash
python -m src.runner --bot demo-bot --suite p0 --dry-run
```

若提示「未找到 Bot」，请确认 `bots.yaml` 里 `name` 与 `--bot` 参数一致。

---

## 第 6 步：第一次真实巡检

**终端 1 — 启动监听（保持运行）**

```bash
python -m src.chat_trigger
```

看到 `connected to wss://` 表示长连接成功。

**终端 2 — 可选 CLI 巡检**

```bash
python -m src.runner --bot my-agent --suite p0
```

**或在群里触发**

```text
@bot检查员 巡检 p0 my-agent
```

### 成功标志

1. 回复「已收到巡检指令…」
2. 陆续出现 `【巡检 R260701-xxx 1/7】` 进度（注意 **R 编号** 同一轮一致）
3. 结束后出现 `【巡检结束】`、摘要卡片、HTML 报告文件
4. 本地 `reports/日期/my-agent.html`

---

## 第 7 步：可选 — LLM 解释失败原因

在 `.env` 中配置（支持 OpenAI 兼容 API）：

```env
INSPECTOR_LLM_API_KEY=sk-...
INSPECTOR_LLM_BASE_URL=https://api.openai.com/v1
INSPECTOR_LLM_MODEL=gpt-4o-mini
```

不配也能完成巡检，只是无法使用 `@bot检查员 解释 p0_xxx`。

---

## 常见问题

| 现象 | 处理 |
|------|------|
| 只收到「开始执行」无进度 | 检查 `.env`、是否复制了 `bots.yaml`、终端是否有报错 |
| 进度 1/7、4/7 乱跳 | 两轮巡检同时在跑；等一轮结束或 `@bot检查员 暂停 Bot名` |
| 负责人显示 `ou_…` | 给 Inspector 开通通讯录或群成员读权限 |
| 文档用例全失败 | 检查 `doc_permitted` / `doc_denied` 链接与 Bot 文档权限 |
| 保存长连接失败 | 必须先 `python -m src.chat_trigger` 再点开放平台保存 |
| `该巡检任务正在进行中` | 同一 Bot 互斥锁生效，等待上一轮结束 |

更多细节：

- [INSPECTOR_SETUP.md](INSPECTOR_SETUP.md) — Inspector 权限与事件
- [CHAT_TRIGGER.md](CHAT_TRIGGER.md) — 群内指令说明
- [ONBOARDING.md](ONBOARDING.md) — 群内注册被测 Bot
- [FEISHU_EVENT_CHECKLIST.md](FEISHU_EVENT_CHECKLIST.md) — 被测 Bot 使用长连接时

---

## 安全提醒

- 巡检会在测试群**真实 @ 被测 Bot**、发送文件与文档链接，请勿在生产大群直接跑 `full` 套件
- 勿将 `.env`、`bots.yaml` 提交到公开仓库
- 若 App Secret 曾泄露，请在开放平台立即重置
