# 飞书群内触发巡检

启动监听后，在测试群里 **@bot检查员**（或你在 `.env` 中配置的 `INSPECTOR_AT_NAME`）并发送指令即可。

## 用法

```
@bot检查员 巡检 p0 demo-bot
@bot检查员 帮助
```

| 指令 | 效果 |
|------|------|
| `巡检` | P0 巡检全部 Bot |
| `巡检 p0` | P0 巡检 |
| `巡检 full` | 完整 API 巡检 |
| `巡检 demo-bot` | 只巡检指定 Bot |
| `巡检 p0 demo-bot` | 指定套件 + Bot |
| `帮助` | 显示指令帮助 |

也支持 `/inspect` 前缀。对话解读见 [CONVERSATION.md](CONVERSATION.md)。

## 启动

```bash
python -m src.chat_trigger
```

看到 `connected to wss` 即表示长连接就绪。**保持窗口运行。**

## 前置条件

1. Inspector 应用已订阅 **接收消息** + **长连接**（见 [INSPECTOR_SETUP.md](INSPECTOR_SETUP.md)）
2. Inspector Bot 已加入测试群
3. `.env` 中 `TRIGGER_CHAT_IDS` 填写正确群 chat_id
4. `python -m src.chat_trigger` 正在运行

## 执行流程

1. 发送 `@bot检查员 巡检 p0 demo-bot`
2. Bot 回复「已收到巡检指令，开始执行…」
3. 后台跑完用例，生成 `reports/` 报告
4. Bot 把摘要发回群里

## 命令行（定时任务）

```bash
python -m src.runner --bot demo-bot --suite p0 --notify
```
