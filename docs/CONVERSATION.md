# 对话解读（阶段 2）

巡检助手除「巡检 / 测试 / 暂停」等指令外，支持在巡检完成后**用自然语言追问**结果与判据。

## 你能说什么

| 类型 | 示例 |
|---|---|
| 解释失败 | `@bot检查员 解释 p0_doc_denied` |
| 按问题编号 | `@bot检查员 为什么 ISS-001 判失败` |
| 自然追问 | `@bot检查员 无权限文档这项为什么失败？` |
| 讨论判据 | `@bot检查员 建议文件检测应该回复附件而不是另起一条` |
| 寒暄 | `@bot检查员 你好` |

## 工作原理

1. **会话上下文**：你触发的最近一次巡检会缓存在内存中（约 1 小时），追问时自动关联 Bot 名与失败项。
2. **事实材料**：从 `BotRunReport` 读取 expected / actual / 判定说明，**不会编造**未出现在报告中的内容。
3. **RAG**：从 `docs/INSPECTION_CHECKLIST.md` 检索相关断言说明与用例定义。
4. **LLM 润色**（可选）：配置 API Key 后，由模型组织语言；未配置时使用规则模板回复。

> 重要：**对话不会改变巡检结果**。要改判据请改代码/配置后重新跑巡检。

## 配置 LLM（你需要做的）

在 `.env` 中增加：

```env
INSPECTOR_LLM_API_KEY=sk-...
INSPECTOR_LLM_BASE_URL=https://api.openai.com/v1
INSPECTOR_LLM_MODEL=gpt-4o-mini
```

国内或企业环境可使用 **OpenAI 兼容** 中转/私有部署，只需保证：

- `POST {BASE_URL}/chat/completions`
- 请求体含 `model`、`messages`
- 响应含 `choices[0].message.content`

配置后**重启** `python -m src.chat_trigger`。

未配置 Key 时仍可追问，回复为结构化事实 + 清单摘录，末尾会提示未启用 LLM。

## 架构

```
用户 @ Inspector
    → 意图识别（解释 / 建议 / 闲聊）
    → 加载会话内最近报告（或 reports/ 目录最新 md）
    → RAG 检索 INSPECTION_CHECKLIST
    → [可选] LLM 组织回复
    → 飞书回复
```

执行类指令（`巡检`、`测试`、`暂停`）仍走原有确定性逻辑，优先级高于对话。

## 限制

- 会话仅存于当前 `chat_trigger` 进程内存，重启后需重新巡检或依赖 `reports/` 历史文件。
- 历史报告从 Markdown 解析 ISS 表，细节不如内存快照完整。
- LLM 回复仅供参考，以 HTML/Markdown 报告为准。

## 相关文件

| 模块 | 路径 |
|---|---|
| 意图 | `src/conversation/intent.py` |
| 会话 | `src/conversation/session.py` |
| 报告 | `src/conversation/report_store.py` |
| RAG | `src/conversation/rag.py` |
| 解读 | `src/conversation/explainer.py` |
| LLM | `src/conversation/llm.py` |
| 编排 | `src/conversation/service.py` |
