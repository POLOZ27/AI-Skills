# cseec_official_admissions（Open WebUI Tool）

"CSEEC 升学分析" 模型用来读取大学官网录取信息的工具。安装在 .75 的 Open WebUI（Workspace → Tools）。

## v0.3.0 提速改动
- 成功读取的官网结果缓存 24 小时（内存 + `/app/backend/data/cache/cseec_admissions/`，容器重建也保留）。回答里会标明是多少分钟前读取的。读取不完整或失败的结果不缓存，下次重新读。
- 全局锁改成"每个网站一把锁"：不同大学可以同时读，同一个网站仍然不会被并发访问。
- robots.txt 缓存从 10 分钟改为 24 小时；超时从 8/12 秒降到 5/8 秒。
- 新增 `get_official_admissions_batch`：一次调用并行读取最多 6 所大学，减少模型的工具调用轮数。

隐私和来源规则不变：只接受公开的大学 ID，不传学生信息；仍遵守 robots.txt 和官网域名白名单。

## v0.4.0 缩短返回内容
实测（2026-10-29）：一次批量查 6 所大学返回约 5.4 万字符，后面每一轮模型都要重读，最后一轮输入 6.7 万 token。
- 每个页面返回给模型的摘录从最多 5000 字符缩到 1500 字符（缓存里仍保留完整摘录）。
- 不再返回"发现的链接"列表；未读 PDF 只列前 3 个。
- 批量查询时"限制说明"只在顶层出现一次，不再每所大学重复；NUS 的范围说明改为 `scope_note`。
模拟测试：3 所大学的返回从 36,481 字符降到 11,431 字符（约 -69%）。

## v0.5.0 只取正文、说清楚有没有读到要求（2026-11-04）
实测（2026-11-03）：UBC、SFU、UofT 返回给模型的摘录几乎全是网站导航菜单，真正的要求被 1500 字符上限截掉；状态永远是 `partial_evidence`，模型分不清"读到要求"和"只读到菜单"，仍给出"匹配偏上"这类结论。
- 解析网页时跳过 `header`、`nav`、`footer`、`aside`（以及 role 为 navigation/banner/contentinfo/search 的区块），优先用 `main`/`article` 里的正文；正文太少时才退回整页。
- 摘录关键词按主题（requirements / language / deadlines / history）分开，去掉 admission、grade、english、canadian 这类菜单里到处都有的宽泛词；不足 30 个字符且没有数字的短行（菜单项）不再触发摘录。含具体课程、分数、日期的段落排在最前面。
- 返回上限 1500 → 2500 字符。
- 新状态：`evidence_found`（正文里读到了具体课程 / 分数 / 日期）或 `no_requirement_text`（没读到，附 instruction：需人工核实，不得据常识判断冲刺/匹配/保底）。每个来源另有 `specific_evidence_found`。
- UBC 的课程要求是网页脚本按校区/省份/学位再加载的，本工具读不到；新增 `scope_note` 提示人工在 you.ubc.ca 核实。没有去调 UBC 的内部接口。
- 缓存键加了 `v5:` 前缀，旧版本的缓存结果不会被沿用。
- 2026-11-04 实测后补充：
  - UBC：改为调用 you.ubc.ca 选择器背后的公开接口（`/wp-admin/admin-ajax.php`，POST，robots.txt 允许），按 BC、温哥华校区和学位名称取要求（Science、Applied Science (Engineering)、Commerce、Arts；computing 对应 Science 并注明）。接口失败时退回读静态页面，状态会是 `no_requirement_text`。
  - SFU：program=science 时直接读理学院页面（`bc-yukon/science.html`）；挑专业链接时跳过写着其他方向的链接（例如 Computing Science、Engineering Science）。
  - "50% complete" 这类完成进度不再算作分数要求。
  - 离线测试：`python3 cseec-official-admissions/test_offline.py`。
- 2026-11-04 第三轮（实测 SFU 理学院、UofT 生命科学后）：
  - 摘录顺序：先放 "British Columbia" 省份段落（列出各省要求的页面），再放每条具体要求附近的小段，最后才是其他关键词上下文；纯链接文字的行（专业菜单）去掉。SFU 理学院的 Required Courses 原来在第 4439 字符、被 2500 上限截掉，现在排在最前。
  - 百分比必须挨着 average / grade / minimum / admission 等词才算分数要求（UofT 页面的 "95% of the universe" 曾被误判）。
  - UofT：要求页改为 `requirements-canadian-high-schools`（含 BC 课程对照），不再跟进学科介绍页；`scope_note` 说明专业先修和录取分数需人工核实。
  - 工具说明里写明：老师说了专业时，第一次调用就传对应 program（生命科学 / 健康 → science），不要先查 general 再按专业重查。
