# cseec_assessment_export（Open WebUI Tool）

"CSEEC AI Tool" 用来把测验导出成三个 Word 文件：学生卷、教师答案、Forms 导入版。

## v0.2.0 提速改动（2026-10-29）
实测：老师点"下载"后又等了 137 秒。原因是模型必须把已经写好的测验逐字重抄成 JSON；第一遍还把阅读原文当成 0 分的题目，被拒绝，只拿到一句笼统的报错，于是整份重抄了第二遍。

- **新增 `export_last_answer`**：直接读取上一条回答里写好的测验（通过 Open WebUI 传进来的 `__messages__`），生成三个 Word 文件，模型不用再重抄。学生卷只取"答案 / 参考答案 / 评分 / Answer Key / Answers / Marking"这类标题之前的内容；教师卷是整篇回答。如果找不到答案标题，会提醒老师先从学生卷里删掉答案。
- **`create_assessment_files` 支持阅读原文**：新增可选字段 `passage` / `passage_title`；`type: "passage"` 或 0 分且没有选项的条目，会自动当作阅读原文处理，不再整份拒绝。
- **报错写清楚**：例如 "Question 2: Points must be an integer from 1 to 30"，模型能一次改对，不用整份重来。

安装后，在 "CSEEC AI Tool" 的系统提示词或出题技能里加一句："老师要下载 / 导出刚出的测验时，调用 export_last_answer，不要重抄。"
