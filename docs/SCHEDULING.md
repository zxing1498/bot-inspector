# 定时巡检配置

## Windows 任务计划程序

1. 打开「任务计划程序」→ 创建基本任务
2. 触发器：每周一 09:00（核心 Bot）或每月 1 日（普通 Bot）
3. 操作：启动程序
   - 程序：`powershell.exe`
   - 参数：`-ExecutionPolicy Bypass -File "d:\bot检测\scripts\run_inspection.ps1"`

## Linux cron

```cron
# 每周一 9:00 P0 巡检
0 9 * * 1 cd /path/to/bot检测 && python -m src.runner --bot all --suite p0 --notify

# 每月 1 日完整 API 巡检
0 9 1 * * cd /path/to/bot检测 && python -m src.runner --bot all --suite full --notify
```

## 变更后即时复测

```bash
python -m src.runner --bot 知识库助手 --suite p0
python -m src.runner --bot 知识库助手 --suite full --notify
```

## 套件与频率对照

| 场景 | 命令 |
|---|---|
| 核心生产 Bot 每周 | `--suite p0` |
| 普通业务 Bot 每月 | `--suite full` |
| 权限/配置变更后 | `--suite p0` |
| 代码/模型变更后 | `--suite full` |
