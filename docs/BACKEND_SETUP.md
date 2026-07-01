# Backend 与日志探针配置说明

你 **不需要自己搭 Elasticsearch** 也能跑巡检。将 `log_query.type` 设为 `skip` 时，日志相关项会标「待人工确认」，其他测试可正常进行。

## 三种日志模式（选一种）

### 模式 A：skip（默认推荐，零配置）

```yaml
backend:
  log_query:
    type: skip
    trace_field: request_id
```

- **优点**：零配置，立刻能跑
- **缺点**：「错误日志可追踪」需人工查日志
- **报告结果**：该项显示「待人工确认」

### 模式 B：Elasticsearch

```yaml
log_query:
  type: elasticsearch
  url: ${ES_URL}
  index: bot-logs
  trace_field: request_id
```

在 `.env` 中设置 `ES_URL=http://your-es-host:9200`。

### 模式 C：HTTP 日志 API

```yaml
log_query:
  type: http
  url: https://your-service.example.com/api/logs/recent?limit=5
  trace_field: request_id
```

响应需为 JSON 列表，包含 `request_id` 字段。

## health / callback 说明

| 配置项 | 含义 |
|--------|------|
| `health_url` | 被测 Bot 后端健康检查地址（返回 HTTP 200） |
| `callback_url` | 网关/服务可达性探针（**不是**飞书 webhook 专用路径） |

### 长连接 Bot

若被测 Bot 使用 **长连接** 收飞书事件，开放平台 **没有 webhook 地址**，这是正常现象。`callback_url` 仅用于探测你的业务网关是否在线。详见 [FEISHU_EVENT_CHECKLIST.md](FEISHU_EVENT_CHECKLIST.md)。

### Webhook Bot

```yaml
backend:
  health_url: https://your-service.example.com/health
  callback_url: https://your-service.example.com/feishu/event
```

## 自动探测后端

```bash
python -m src.tools.probe_backend --bot <Bot名>
python -m src.tools.probe_backend --bot <Bot名> --base https://your-service.example.com
```

## 人工查日志（skip 模式）

1. 在测试群 @Bot 发送 `INVALID_CMD_XYZ_999`
2. 飞书开放平台 → **运营监控 → 日志检索**
3. 按时间筛选，确认能找到 `requestId`

## 验证

```bash
python -m src.runner --bot <Bot名> --suite p0 --dry-run
```
