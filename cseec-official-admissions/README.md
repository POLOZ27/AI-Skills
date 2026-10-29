# cseec_official_admissions（Open WebUI Tool）

"CSEEC 升学分析" 模型用来读取大学官网录取信息的工具。安装在 .75 的 Open WebUI（Workspace → Tools）。

## v0.3.0 提速改动
- 成功读取的官网结果缓存 24 小时（内存 + `/app/backend/data/cache/cseec_admissions/`，容器重建也保留）。回答里会标明是多少分钟前读取的。读取不完整或失败的结果不缓存，下次重新读。
- 全局锁改成"每个网站一把锁"：不同大学可以同时读，同一个网站仍然不会被并发访问。
- robots.txt 缓存从 10 分钟改为 24 小时；超时从 8/12 秒降到 5/8 秒。
- 新增 `get_official_admissions_batch`：一次调用并行读取最多 6 所大学，减少模型的工具调用轮数。

隐私和来源规则不变：只接受公开的大学 ID，不传学生信息；仍遵守 robots.txt 和官网域名白名单。
