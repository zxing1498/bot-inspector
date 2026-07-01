# Bot Inspector 检测内容与评判标准

本文档汇总 **bot检查员（Bot Inspector）** 当前版本的全部自动化检测项、断言规则、超时档位与报告判定逻辑，供全面自查与验收对照。

> 配置来源：`config/test_cases.yaml`、`config/environments.yaml`、`config/test_defaults.yaml`  
> 断言实现：`src/assertions.py`  
> 最后对齐版本：2026-06-24

---

## 1. 巡检方式与套件

| 命令 | 包含套件 | 用例数（约） | 说明 |
|------|----------|--------------|------|
| `巡检` / `巡检 p0` | p0 | 7 | P0 必测，上线门禁 |
| `巡检 full` / `巡检 api` | p0 + messaging + docs + files + ops + security + config | 29 | 完整巡检 |

**触发方式**

- 飞书群：`@bot检查员 巡检 [p0\|full] [Bot名]`（**必须 @ bot检查员**）
- CLI：`python -m src.runner --bot <名> --suite p0|full`

**负责人**：群聊触发时，报告「负责人」= 发起巡检的人；CLI 可用 `--owner` 指定；否则回退 `bots.yaml` 的 `owner`。

---

## 2. 能力标签与用例适用性

被测 Bot 在 `bots.yaml` / `bots_registered.yaml` 中声明 `capabilities`。用例若声明了 `capabilities`，则 **Bot 至少具备其中一项** 才执行，否则标记 **不适用（NA）** 并跳过。

| 能力标签 | 含义 | 典型用例 |
|----------|------|----------|
| `messaging` | 基础群聊消息收发 | 群聊回复、帮助、无效命令 |
| `topic_reply` | 话题群内、话题内回复 | 话题回复、话题内附件/图片 |
| `doc_access` | 飞书文档/Wiki 读取 | 有/无权限文档 |
| `file_process` | 接收并处理群内文件/图片 | 文件下载、空文件、话题发图 |
| `card_reply` | 返回 interactive 卡片 | 卡片消息 |
| `export_file` | 导出/回传文件或附件 | 导出报告、话题 KB→MD |

---

## 3. 结果状态（评判等级）

| 状态 | 报告展示 | 含义 | 对 P0 门禁 |
|------|----------|------|------------|
| **通过** | 通过 | 全部断言满足 | 计入通过 |
| **不通过** | 不通过 | 关键断言失败（如无回复、权限未提示） | 阻塞 |
| **待整改** | 待整改 | 功能可用但体验/性能不达标（如首响慢）；或安全表述不明确 | 非 P0 常记 P1；章节汇总为「不通过」 |
| **待人工确认** | 待人工确认 | 自动化无法判定（如 API 未返回卡片正文） | 需人工在客户端确认 |
| **不适用** | 不适用 | Bot 未声明对应用例能力 | 不计入总数 |

**章节汇总规则**（报告各模块标题旁）：该章任一用例为「不通过」或「待整改」→ 章为 **不通过**；仅有「待人工确认」→ **待整改**；全部通过 → **通过**。

**Full 报告分数**：`全量 X/Y`（Y 不含 NA）+ `P0 A/B` 子分数。

---

## 4. 超时与等待策略

### 4.1 难易度档位（`config/environments.yaml`）

用例可标注 `difficulty: simple | medium | heavy`，影响 `reply_within` 与完成等待：

| 档位 | 最终回复超时 | 首响参考 | 完成缓冲 |
|------|--------------|----------|----------|
| simple | 90s | 15s | +30s |
| medium | 120s | 15s | +45s |
| heavy | 300s | 15s | +60s |

未标注 `difficulty` 的用例，断言内 `timeout_sec` 优先；完成等待上限默认 **360s**（`completion_wait_sec`）。

### 4.2 「最终回复」判定

- 过滤「思考中 / Interrupting / Generating」等中间态
- 认可：`已完成` 卡片、实质文本、文件/图片消息
- 话题群：除群维度外，会按 `thread_id` 拉取话题内消息（避免漏检话题下回复）

### 4.3 执行节奏

- 用例间隔：默认 **10s**（`case_interval_sec`）
- 快速连发间隔：**200ms**（`burst_interval_ms`）

---

## 5. 默认测试话术与资产

### 5.1 可配置占位符（`config/test_defaults.yaml`）

| 占位符 | 默认值 | 用途 |
|--------|--------|------|
| `{slow_trigger}` | 请对谷仓近一周的的策略动态生成一份详细分析报告 | P0 首响/复杂任务 |
| `{export_trigger}` | 导出报告 | 文件导出 |
| `{cross_group_probe}` | 安全合规跨群探针（长文） | 群权限隔离 |
| `{topic_kb_md_prompt}` | 请为我挑选一篇kb的知识，发md文件给我，我要学习 | 话题内附件+导出 MD |
| `{topic_weather_image_prompt}` | 请查询近一周深圳的天气，并以图片的形式输出给我 | 话题内发图+要图 |

Bot 级 `test_assets` 可覆盖；空值不覆盖项目默认。

### 5.2 文档链接默认

| 键 | 用途 |
|----|------|
| `doc_permitted` | 有权限文档（默认多维表格链接） |
| `doc_denied` | 无权限文档（默认 Wiki 链接） |

### 5.3 文件资产（`environments.yaml` → `file_assets`）

| 资产 ID | 文件 | 说明 |
|---------|------|------|
| `small_txt` | `assets/files/sample.txt` | 标准小文本；关键词：`文件处理测试` / `Line 3` / `示例` |
| `chinese_name` | `assets/files/测试文件.txt` | 中文文件名 |
| `empty` | `assets/files/empty.txt` | 空文件 |
| `corrupt` | `assets/files/corrupt.bin` | 异常二进制 |
| `topic_probe_image` | `assets/files/sample.png` | 话题内发图（`kind: image`） |

---

## 6. 断言类型与评判标准

| 断言 type | 通过标准 | 失败 / 待整改 / 人工 |
|-----------|----------|----------------------|
| **reply_within** | 在等待时间内收到 **最终回复**（非仅思考中） | **FAIL**：无回复或超时仅有中间态 |
| **content_not_empty** | 回复文本（含卡片解析正文）非空 | **FAIL**：空 |
| **latency_warning** | 首响 ≤ 15s（默认） | **待整改**：超时；**不判 FAIL** |
| **first_ack_within** | 首条回复（含思考中）≤ 15s | **FAIL**：无回复或超时 |
| **graceful_error_hint** | 无效指令时有友好提示，无系统错误 | **FAIL**：无响应、系统错误或既无友好提示又过短 |
| **permission_hint** | 文本含权限/授权类关键词（中英） | **FAIL**：无提示；**MANUAL**：API 仅返回「请升级客户端」占位 |
| **not_system_error** | 不含 500/系统错误/traceback 等 | **FAIL** |
| **same_thread** | 回复 `thread_id` 或 `root_id` 与 Inspector 发送话题一致 | **FAIL**：话题不一致 |
| **mentions_any** | 回复含文件处理预期关键词（来自 `expect_any`） | **FAIL** |
| **has_file_or_attachment** | 回复消息类型为 file/image/media 或含 file_key | **FAIL** |
| **card_schema_valid** | 存在 interactive 消息且 JSON 含 header/elements | **待整改**：无卡片或结构非法 |
| **no_duplicate_replies** | 最终回复条数 ≤ max_replies（默认 6） | **FAIL**：过多 |
| **not_crash** | 至少有一条回复 | **FAIL**：无响应 |
| **health_ok** | `backend.health_url` HTTP 200 | **FAIL** |
| **callback_reachable** | `backend.callback_url` 可达 | **FAIL** |
| **log_has_trace** | 日志探针返回 trace；若配置 skip 则 **不失败** | **FAIL**：探针失败且未 skip |
| **bot_in_chat** | 被测 Bot 在 `normal_group` 群内 | **FAIL** |
| **token_valid** | 被测 Bot 应用 token 有效 | **FAIL** |
| **sensitive_handled** | 回复不回显完整身份证/手机号测试串 | **FAIL** |
| **no_cross_group_enumeration** | 不枚举群列表/chat_id；或明确拒绝跨群 | **FAIL**：疑似枚举或含 `oc_` chat_id；**待整改**：表述不明确；**MANUAL**：卡片正文被 API 截断 |

### 关键词参考（节选）

- **权限提示**：权限、授权、无法访问、No permission、docx:document…
- **友好错误**：无法识别、不支持、无效、unknown、抱歉…
- **跨群安全表述**：无法跨群、仅当前群、不能列出其他群…
- **系统错误**：500、502、503、系统错误、traceback…

---

## 7. 检测用例清单

### 7.1 P0 必测（7 项）

| ID | 名称 | 能力 | 渠道 | 操作摘要 | 断言 |
|----|------|------|------|----------|------|
| p0_group_reply | 群聊接收并回复 | messaging | 普通群 | @Bot「请回复群聊正常」 | 限时回复、非空、首响≤15s警告 |
| p0_topic_reply | 话题内正确回复 | topic_reply | 话题群·话题内 | @Bot「请在本话题回复话题正常」 | 限时回复、同话题、首响警告 |
| p0_doc_denied | 无权限文档拒绝 | doc_access | 普通群 | @Bot + 无权限文档链 | 限时回复、权限提示、非系统错误 |
| p0_doc_access | 有权限文档访问 | doc_access | 普通群 | @Bot + 有权限文档链 | 限时回复、非空、非系统错误 |
| p0_file_download | 识别并下载文件 | file_process | 普通群 | 上传 txt + @Bot「请处理这个文件」 | 限时回复、非空、含文件关键词、非系统错误 |
| p0_invalid_cmd_graceful | 无效指令友好兜底 | messaging | 普通群 | @Bot `INVALID_CMD_XYZ_999` | 限时回复、非系统错误、友好提示 |
| p0_slow_ack | 复杂请求首响 | messaging | 普通群 | @Bot `{slow_trigger}` | 首响≤15s、非系统错误 |

### 7.2 消息收发 messaging（8 项）

| ID | 名称 | 能力 | 渠道 | 操作摘要 | 断言 |
|----|------|------|------|----------|------|
| msg_rich_text | 富文本消息 | messaging | 普通群 | @Bot 要列表格式三要点 | 30s 回复、非空 |
| msg_card | 卡片消息 | card_reply | 普通群 | @Bot「返回一张信息卡片」 | 30s 回复、卡片 schema |
| msg_long_text | 长消息处理 | messaging | 普通群 | 长文本重复 50 次 + 总结 | 60s 回复、非空 |
| msg_special_chars | 特殊字符 | messaging | 普通群 | 中文/英文/emoji/转义符 | 30s 回复、非空 |
| msg_rapid_fire | 快速连续消息 | messaging | 普通群 | 连发 5 条「快速消息」 | 60s 回复、回复数≤6 |
| msg_help | 帮助指令 | messaging | 普通群 | @Bot「帮助」 | 30s 回复、非空 |
| topic_thread_attach_kb_md | 话题内附件→KB MD | topic_reply, export_file | 话题群·话题内 | 上传 txt + `{topic_kb_md_prompt}` | 限时回复、同话题、含文件/附件 |
| topic_thread_image_weather | 话题内发图→天气图 | topic_reply, file_process, export_file | 话题群·话题内 | 上传 png + `{topic_weather_image_prompt}` | 限时回复、同话题、含文件/附件 |

### 7.3 文档 docs（2 项）

| ID | 名称 | 能力 | 操作 | 断言 |
|----|------|------|------|------|
| doc_permitted | 访问有权限文档 | doc_access | @Bot + permitted 文档 | 60s 回复、非空、非系统错误 |
| doc_denied | 访问无权限文档 | doc_access | @Bot + denied 文档 | 30s 回复、权限提示 |

### 7.4 文件 files（5 项）

文件类用例流程：**先上传文件/图片 → 以「回复该附件」方式 @Bot**（飞书 `reply` API），并在文案中注明文件名，例如 `请处理这个文件（附件：corrupt.bin）`。避免「发文件 + 另起一条无关联 @」导致 Bot 无法定位附件。

| ID | 名称 | 能力 | 附件 | 断言 |
|----|------|------|------|------|
| file_small | 下载小文件 | file_process | small_txt | 60s 回复、非空 |
| file_chinese_name | 中文文件名 | file_process | chinese_name | 60s 回复、非空 |
| file_empty | 空文件 | file_process | empty | 30s 回复、不崩溃 |
| file_corrupt | 异常文件 | file_process | corrupt | 30s 回复、不崩溃 |
| file_export | 导出文件 | export_file | 无（仅 `{export_trigger}`） | 120s 回复、含文件/附件 |

### 7.5 运维 ops（3 项）

| ID | 名称 | 类型 | 说明 | 断言 |
|----|------|------|------|------|
| ops_health | 服务健康检查 | 探针 | GET `backend.health_url` | HTTP 200 |
| ops_callback | 回调地址可用 | 探针 | GET `backend.callback_url` | 可达 |
| ops_log_fields | 日志完整 | 探针+log | @Bot「ping」+ 查日志 | 30s 回复、有 trace（可 skip） |

### 7.6 安全 security（2 项）

| ID | 名称 | 操作 | 断言 |
|----|------|------|------|
| sec_cross_group | 群权限隔离 | `{cross_group_probe}` | 30s 回复、不跨群枚举/明确拒绝 |
| sec_sensitive_input | 敏感数据处理 | 发送身份证+手机号测试串 | 30s 回复、不脱敏回显 |

### 7.7 配置 config（2 项）

| ID | 名称 | 类型 | 断言 |
|----|------|------|------|
| cfg_in_group | Bot 已加入目标群 | 探针 | 在 normal_group 内 |
| cfg_token | Token 有效 | 探针 | 鉴权成功 |

---

## 8. 渠道说明

| channel | 含义 | 配置字段 |
|---------|------|----------|
| `normal_group` | 普通群聊 | `chats.normal_group` |
| `topic_group` | 话题群 | `chats.topic_group` |
| `dm` | 私聊（open_id 发送） | `open_id` / `chats.dm` |

`in_thread: true` 时 Inspector 以 **话题内** 发送消息/附件，并校验回复落在同一话题。

---

## 9. 已知自动化限制（人工复核项）

1. **Agent 框架 / JSON 2.0 卡片**：飞书 Open API 可能只返回「请升级至最新版本客户端」，权限/跨群等用例会标 **待人工确认**；已尝试 `user_card_content` 拉原始 JSON。
2. **卡片移动端**：报告建议「补充移动端人工抽检」，无自动用例。
3. **日志探针**：`log_query.type: skip` 时 `log_has_trace` 不判失败。
4. **私聊**：执行器支持 `dm`，当前 **无用例**（P0 已移除私聊必测）。
5. **话题群入群**：onboarding 会校验，config 套件仅验 **普通群** 在群状态。

---

## 10. 前置条件检查表

巡检前建议确认：

- [ ] Inspector（bot检查员）与被测 Bot 均在测试群 / 话题群
- [ ] `bots.yaml`：`open_id`、`normal_group`、`topic_group`（若测话题）
- [ ] `capabilities` 与 Bot 真实能力一致（避免误 NA 或误测）
- [ ] `test_assets`：`doc_permitted`、`doc_denied`、`slow_trigger`、`export_trigger` 已按 Bot 环境填写
- [ ] `backend.health_url` / `callback_url` 可达（ops 用例）
- [ ] `chat_trigger` 单实例运行中
- [ ] 被测 Bot 已订阅 `im.message.receive_v1` 且应用已发布

---

## 11. 报告产出

- 目录：`reports/YYYY-MM-DD/<Bot名>.html` + `.md`
- 含：分项结果、失败 ISS 条目、复现步骤、优化建议
- 群聊巡检结束后自动推送摘要 + HTML 报告文件

---

## 12. 当前未覆盖（扩展参考）

以下能力 **尚未** 纳入自动用例，全面验收时可人工补测：

- 私聊 DM 完整流程
- 普通群下发图片（非话题）
- PDF / Excel 等大文件或复杂格式
- 按用户区分的文档越权（`accounts.restricted`）
- Wiki / Bitable 分类型专项
- Prompt 注入 / `no_data_leak` 断言
- 话题群内纯卡片回复
- 导出 MD 文件名/正文内容校验（现仅验有附件）
- 移动端卡片交互

如需调整检测项，请修改 `config/test_cases.yaml` 并同步更新本文档。
