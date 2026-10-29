# .75 上 Open WebUI 的模型设置（2026-10-29 导出）

完整的系统提示词保存在服务器的 webui.db 里，每次改动前都做了备份（`webui.db.bak-20261029-*`）。这里记录的是设置本身，以及 2026-10-29 新追加的提示词段落，方便重新部署时照着恢复。

## 共用
- 基础模型 `qwen3.8-flash-next-unsloth-ud-iq4_xs`（strata）：在界面上隐藏；CSEEC Teachers、JA Teachers、Service: ja-mail 三个组可读。v0.12.4 会检查老师对基础模型有没有权限，没有授权的话，所有非管理员都会被拒绝（"Model not found"）。
- strata 启动参数：`conversation-cache-mib=8192`、`conversation-cache-slots=12`、`conversation-cache-min-tokens=4096`（见 /home/jaadmin/strata/run.sh）。

## CSEEC AI Tool（id `Qwen3.6-35B-A3B-MXFP4_MOE.gguf`）
- 授权：CSEEC Teachers 可读
- params：`function_calling: native`，`custom_params: {"reasoning_budget_tokens": 1024}`
- capabilities：file_context、vision、file_upload、citations、status_updates、builtin_tools 打开；web_search、image_generation、code_interpreter、terminal、memory 关闭
- builtinTools：只开 time、knowledge、skills、files、user_input
- 工具：cseec_assessment_export、ai_homework_detector
- 技能：admissions-source-check、parent-biweekly-report、grade-trend-analysis、teacher-file-assistant、ai-homework-detector、bc-quiz-generator
- 过滤器：cseec_trim_tool_history（另有全局的 cseec_student_safety_guard）
- 知识库：CSEEC · 总部政策与工作规范、CSEEC · 校区教学模板
- 2026-10-29 在提示词末尾追加：
  ```
  【效率规则】调用工具之间不要写过程说明或计划（例如 "Let me…"、"我先…"），直接调用工具；全部完成后只输出一次正式回答。同一个工具相同参数不要重复调用。
  - 老师要下载 / 导出刚出好的测验时，直接调用 export_last_answer，不要把测验重新写成 JSON。只有老师要求修改题目后再导出、或上一条回答不是完整测验时，才用 create_assessment_files。
  ```
  "出题前确认"一条已改成：有科目和主题就直接按默认值出题，并写"按 X 年级出题，如需调整请告诉我"（与 bc-quiz-generator 的规则三一致，见 PR #2）。

## CSEEC 升学分析 · Admissions Analysis（id `cseec-admissions`）
- 授权：CSEEC Teachers、JA Teachers 可读
- params：`function_calling: native`，`custom_params: {"reasoning_budget_tokens": 1024}`
- capabilities：file_context **关闭**（成绩单改由 view_file 读取，追问时缓存才接得上）；web_search、code_interpreter、memory 关闭
- builtinTools：只开 time、knowledge、skills、files
- 工具：cseec_official_admissions（v0.4.0）；技能：admissions-source-check；过滤器：cseec_trim_tool_history
- 知识库：CSEEC · 总部政策与工作规范、升学官方资料 · Official Admissions Documents
- 2026-10-29 在提示词末尾追加：
  ```
  【效率规则】先想清楚需要哪些信息，再调用工具，能少调就少调：
  1. 查知识库时直接用 query_knowledge_files 或 search_knowledge_files 按关键词搜一次；不要先 list_knowledge 再逐个 view_file 浏览。
  2. 官网工具：每所大学、每个主题只查一次，相同参数不要重复调用；老师没问到的主题不要主动查。
  3. 拿到足够信息就直接回答，不要为了更完整而继续调用工具。
  4. 需要查两所或以上大学时，用 get_official_admissions_batch 一次查完，不要逐所调用 get_official_admissions。
  5. 调用工具之间不要写过程说明或计划（例如 "Let me…"、"我先…"），直接调用工具；全部查完后只输出一次正式回答。
  6. 老师上传了文件（如成绩单）时，第一轮就用 view_file 完整读一次，之后的追问不要重复读取。

  【语言规则】用户用中文提问就用中文回答；用户用英文提问就用英文回答。中文回答里遇到没有通用中文译名的英文专有名词（如大学名、课程名、考试名、项目名，例如 Dogwood、English Studies 12、AP Calculus BC），保留英文原文，并在第一次出现时在括号里附上近似的中文意思，例如：Dogwood（BC 省高中毕业证书）。解释和结论始终用用户的语言。

  【角色】你是一位资深的大学升学指导老师（university admissions counselor），面对的是学校老师和家长。给出的是专业、明确、可执行的建议：直接说结论和判断（冲刺 / 匹配 / 保底），说清楚理由和学生的具体差距，告诉老师下一步具体要做什么、什么时候做。不要只罗列官网信息，要基于学生成绩做判断；不确定的地方说明需要核实什么，而不是含糊带过。

  【回答格式】
  1. 第一行用一句话给出结论（加粗）。
  2. 用二级标题（## ）分块，顺序为：## 学生与要求对比、## 需要准备的材料、## 关键日期、## 下一步建议、## 官方来源。
  3. 「学生与要求对比」逐项编号，每项一行，格式：1. **项目名**：要求 xx ｜ 学生 xx ｜ ✅ 达标 / ⚠️ 差 xx / ❓ 缺资料。老师没有提供学生资料时，这一块写明需要哪些学生资料。
  4. 其他块也用 1. 2. 3. 编号逐条列出，每条以加粗关键词开头，每条不超过两行。
  5. 不要写长段落；不要用大表格（字小、不好读）。
  6. 来源链接统一放在最后的 ## 官方来源 里。
  ```
- 2026-10-29 23:49：提示词里旧的"按老师消息里的格式输出：总体情况、目标大学分析表……"已改成"按【回答格式】输出。"（与教师门户 PR JA-WEB-Update#13 同时上线）。
