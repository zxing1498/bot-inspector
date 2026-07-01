# bot-inspector

飞书 Bot 自动化验收工具：由 **Inspector（巡检员）** 应用代你向被测 Bot 发消息、传文件、验回复，自动生成 HTML/Markdown 报告与群内摘要。

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

## 快速开始

**第一次使用请阅读 → [docs/GETTING_STARTED.md](docs/GETTING_STARTED.md)**（含 App ID 在哪、chat_id 怎么填等逐步说明）

使用 AI 部署 → [AGENTS.md](AGENTS.md)

```bash
git clone <repo-url>
cd bot-inspector
python -m venv .venv && .venv\Scripts\activate   # Windows
pip install -r requirements.txt

copy .env.example .env
copy config\bots.yaml.example config\bots.yaml
# 编辑 .env 与 config/bots.yaml

python -m src.runner --bot demo-bot --suite p0 --dry-run
python -m src.chat_trigger
# 群里：@bot检查员 巡检 p0 demo-bot
```

## 两种触发方式

| 方式 | 说明 |
|------|------|
| **飞书群聊** | `python -m src.chat_trigger`，详见 [docs/CHAT_TRIGGER.md](docs/CHAT_TRIGGER.md) |
| **命令行** | `python -m src.runner --bot <名> --suite p0`，适合 CI / 定时任务 |

## 项目结构

```
config/           用例定义、环境配置；bots.yaml 为本地台账（见 *.example）
assets/           测试附件
src/feishu/       飞书 API 客户端
src/tests/        用例执行器
src/report/       报告生成与评分
docs/             配置与使用文档
reports/          巡检输出（本地，不提交 Git）
```

## CLI 参数

| 参数 | 说明 |
|------|------|
| `--bot` | Bot 名称或 `all` |
| `--suite` | `p0` / `full` / `api` 或逗号分隔套件 |
| `--dry-run` | 不调用飞书 API |
| `--parallel N` | 并行 Bot 数 |
| `--notify` | 完成后发摘要到 `NOTIFY_CHAT_ID` |
| `--output DIR` | 自定义报告目录 |

## 套件说明

| 套件 | 覆盖 |
|------|------|
| `p0` | P0 必测 7 项 |
| `messaging` | 消息收发 |
| `docs` | 文档访问 |
| `files` | 文件处理 |
| `ops` | 运维探针 |
| `security` | 安全合规 |
| `config` | 基础配置 |
| `full` | 以上全部 |

## 文档索引

| 文档 | 内容 |
|------|------|
| [GETTING_STARTED.md](docs/GETTING_STARTED.md) | **首次使用完整指引** |
| [INSPECTOR_SETUP.md](docs/INSPECTOR_SETUP.md) | Inspector 应用权限与事件 |
| [ONBOARDING.md](docs/ONBOARDING.md) | 群内注册被测 Bot |
| [CHAT_TRIGGER.md](docs/CHAT_TRIGGER.md) | 群内指令 |
| [FEISHU_EVENT_CHECKLIST.md](docs/FEISHU_EVENT_CHECKLIST.md) | 被测 Bot 长连接检查 |
| [CONVERSATION.md](docs/CONVERSATION.md) | 巡检后「解释」对话 |
| [SCHEDULING.md](docs/SCHEDULING.md) | 定时巡检 |

## 开发

```bash
python -m pytest -q
```

## 许可证

[MIT](LICENSE)

## 商标

「飞书」「Lark」为字节跳动商标。本项目与飞书官方无隶属关系。
