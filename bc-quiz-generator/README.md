# BC 10–12 出题助手（Open WebUI）

给 .75 服务器上的 Open WebUI（"CSEEC AI Tool" 模型，Qwen）用的出题 skill 和课程大纲知识库。

## 解决的问题

老师问"給我出一套10年級數學第一單元的單元測試題"时，旧的出题模块：

1. 让 Qwen 输出了一段 `<tool_call><function=ask_user_test>…` 想弹出选项，但 Open WebUI 没识别，原始代码直接显示给老师。
2. 列出的课程名是编的（BC 没有 "Pre-Calculus 10"、"Mathematics 10"）。
3. 没有中英双语解析。

新的 skill：

- 问中文回中文、问英文回英文（繁简也跟着老师）。
- 信息不够时，用**普通文字**的编号菜单让老师选课程、单元、试卷语言、难度、教材，回一行编号就行，回"默认"直接出题；明确禁止输出工具调用。
- 每道题附答案、中文解析、英文 Explanation、术语中英对照。
- 课程和单元来自 BC 官方课程大纲。

## 文件

| 文件 | 用途 |
|---|---|
| `SKILL.md` | 出题 skill，导入 Workspace → Skills |
| `knowledge/bc-math-10-12.md` | 数学各课内容与术语（中英） |
| `knowledge/bc-science-10-12.md` | 理科各课内容与术语（中英） |
| `knowledge/bc-english-social-10-12.md` | 英语、社会课程内容 |

## 安装到 .75

1. 备份 `/home/polo/school-ai/data/openwebui/webui.db`。
2. Workspace → Skills：新建（或替换旧的出题 skill）`bc-quiz-generator`，粘贴 `SKILL.md` 全文。旧的出题 skill 先停用，避免两个同时触发。
3. Workspace → Knowledge：新建知识库 "BC 10-12 课程大纲"，上传 `knowledge/` 下三个文件。
4. Workspace → Models → CSEEC AI Tool：把该知识库和 skill 关联到模型。
5. 测试：用中文、繁体、英文各问一次"出一套 10 年级数学第一单元测试题"，确认不再出现 `<tool_call>`，菜单课程名正确，解析是双语。

### 如果别的场景仍然出现 `<tool_call>` 原文

这是模型输出了 Qwen 格式的工具调用但没被解析。可以检查：

- Models → CSEEC AI Tool → Advanced Params → Function Calling：改成 `Default` 试试（`Native` 依赖推理服务把 Qwen 的工具调用解析出来）。
- 推理服务（strata 容器）是否开启了与该 Qwen 模型匹配的 tool-call parser。

## 题库来源与版权

查过的来源（2026-10）：

- **BC 官方课程大纲**（curriculum.gov.bc.ca）：本知识库只用自己的话整理了内容范围，没有复制原文。
- **BC 历年省考 / 毕业评估样题**：版权归 BC 省政府，官网写明未经书面许可不得复制或再分发，需向省政府申请许可才能批量放进服务器。
- **OpenStax**（高中物理等）：页面标注 CC BY-NC-SA，且声明未经书面许可不得用于训练大模型；学校是否算"非商业"需要确认。
- **BC ExamBank、Pearson、McGraw-Hill、THE KEY 等**：商业付费产品，不能放进服务器，除非学校已购买并获授权。

因此目前的做法是：知识库只放课程范围和术语，题目由模型原创；学校自己的试卷、已购教材的目录可以由老师上传到知识库补充。
