# Agent 部署说明

本文档供 **Cursor / Copilot / 其他 AI Agent** 在用户要求「帮我部署 bot-inspector」时遵循。请严格按顺序执行，不要跳过验证步骤。

## 目标

让用户能在飞书测试群里通过 `@bot检查员 巡检 p0 <Bot名>` 完成第一次 P0 巡检并收到 HTML 报告。

## 必读文件

1. [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md) — 完整人工步骤（截图级说明）
2. [docs/INSPECTOR_SETUP.md](docs/INSPECTOR_SETUP.md) — Inspector 权限与事件
3. [config/bots.yaml.example](config/bots.yaml.example) — 台账字段含义

## 执行清单

### 1. 环境

```bash
python -m venv .venv
# 激活 venv 后：
pip install -r requirements.txt
```

### 2. 向用户索取（不要猜、不要用仓库里的占位符）

| 变量 | 说明 |
|------|------|
| Inspector `FEISHU_APP_ID` | `cli_` 开头，来自用户自建 Inspector 应用 |
| Inspector `FEISHU_APP_SECRET` | 同上应用密钥 |
| 测试群 `chat_id` | `oc_` 开头 |
| 被测 Bot 名称 | 用户起的台账名 |
| 被测 Bot `app_id` / `open_id` | 可选；可通过群内「测试」流程自动发现 |

### 3. 创建本地配置（勿提交 Git）

```bash
cp .env.example .env
cp config/bots.yaml.example config/bots.yaml
cp config/bots_registered.yaml.example config/bots_registered.yaml
```

编辑 `.env` 填入凭证与 `TRIGGER_CHAT_IDS`。

编辑 `config/bots.yaml` 填入被测 Bot 与测试群。

**禁止**：将 `.env` 或 `bots.yaml` 写入代码、提交 commit、或出现在对话截图中。

### 4. 验证

```bash
python -m pytest -q
python -m src.runner --bot <Bot名> --suite p0 --dry-run
```

### 5. 启动与触发

终端 A（常驻）：

```bash
python -m src.chat_trigger
```

确认日志含 `connected to wss://` 后，用户在群里发送：

```text
@bot检查员 巡检 p0 <Bot名>
```

### 6. 成功判定

- 群内有 `【巡检 R… 1/7】` 进度
- 结束有 `【巡检结束】` 与报告文件
- 本地 `reports/<日期>/<Bot名>.html` 存在

### 7. 失败时

- 读 `chat_trigger` 终端日志与 `errors` 文案
- 常见：未复制 `bots.yaml`、App Secret 错误、长连接未保存、两轮巡检并发
- 参考 [docs/GETTING_STARTED.md#常见问题](docs/GETTING_STARTED.md)

## 不要做的事

- 不要使用仓库历史中可能存在的真实 `cli_` / `oc_` / `ou_` 作为用户配置
- 不要在没有用户许可时向生产群发巡检消息
- 不要删除用户已有的 `config/bots.yaml`（已在 .gitignore，仅本地有效）

## 可选功能

- LLM 解释：需 `INSPECTOR_LLM_API_KEY`，见 `.env.example`
- 定时巡检：见 [docs/SCHEDULING.md](docs/SCHEDULING.md)
