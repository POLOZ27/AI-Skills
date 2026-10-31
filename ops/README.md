# .75 服务器的定时任务（2026-10-31 起）

都在用户 `polo` 的 crontab 里，脚本会自己换算温哥华时间（服务器时钟是 UTC）。

## 每晚备份：`/home/polo/school-ai/backups/backup-nightly.sh`（温哥华 02:30）
- 用 SQLite backup API 备份 webui.db，存成 `webui-YYYYMMDD.db`，保留最近 14 份。
- 书库 `source_library/library.db` 每周日备份一次，保留 4 份。
- 改动前手动做的 `webui.db.bak-*` 不会被自动删除。
- 待办：复制到 NAS（//192.168.1.220/svc-backup）。现在 NAS 挂载只有 root 能写，需要用 sudo 调整挂载权限，或者给 polo 单独开一个目录。

## 每天自检：`/home/polo/school-ai/selfcheck/selfcheck.sh`（温哥华 06:30，只读）
结果写在 `latest.json`，另外按日期留一份，保留 30 天。检查项：
- 容器 school-ai-openwebui、strata、docling、ja-mail 是否在运行
- Open WebUI `/health` 和 strata 健康接口
- 各模型的组授权：
  - 基础模型 → CSEEC Teachers / JA Teachers / Service: ja-mail
  - CSEEC AI Tool → CSEEC Teachers
  - 升学分析 → CSEEC Teachers / JA Teachers
- 4 个工具是否存在并挂在对应模型上
- 24 小时内的 403、5xx 和 Traceback。聊天请求被 403 拒绝一律算失败；"频道"页面的 403 是界面请求，可以忽略
- 默认路由走的网卡（目前是 2.5G USB 网卡）
- 磁盘剩余空间，低于 15% 报警

发现老师用不了时，按 POLO 定的规矩立即修：先备份，修完再告诉 POLO。
