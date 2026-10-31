# cseec_source_texts（Open WebUI Tool）

让 "CSEEC AI Tool" 出题时能读到公版作品的**真实原文**，不再凭记忆编。起因：2026-10-30 老师要求按国会图书馆版本给 *The Mother and the Wolf* 出题，AI 不能上网，凭记忆写成了另一则寓言，还编了出处。

## 本地书库
书库在服务器 `/app/backend/data/source_library/library.db`（SQLite），容器重建也保留。
- **国会图书馆《The Aesop for Children》**（read.gov/aesop）：146 则寓言全部存在本地，约 1 MB。
- **Project Gutenberg（古登堡计划）**：本地只存书目（书名、作者、语言，约 7 万条），用来按书名秒查。书的正文在老师第一次用到时才从 gutenberg.org 下载，下载后存进书库，下次直接用。
- 维基文库（Wikisource）暂不接：它的 robots.txt 不允许自动调用搜索接口。

查找顺序：先查本地书库；本地没有正文时，只去白名单网址读一次（`read.gov/aesop/`、`www.gutenberg.org/cache/epub/`），遵守 robots.txt，只用 HTTPS，不带任何学生信息。

## 工具函数
- `find_source_text(title, author, source)`：按书名在书库里找。找到的若是寓言，直接返回全文和出处；若是书，返回候选和 `text_id`。
- `read_source_text(text_id, part)`：按 12,000 字符一段读正文，附出处（链接和读取日期）。
- `search_in_source_text(text_id, phrase)`：在长篇里找章节名、诗名或句子在第几段，只读需要的那段。

函数说明里写明：**只有老师明确要求查某篇作品或某个版本时才调用**，不会主动检索。

## 安装
1. 备份 webui.db。
2. Workspace → Tools 新建工具，粘贴 `cseec_source_texts.py`，挂到 "CSEEC AI Tool"。
3. 建书库（只需一次，约 3 分钟）：
   ```
   docker cp cseec-source-texts school-ai-openwebui:/tmp/
   docker exec school-ai-openwebui python /tmp/cseec-source-texts/seed_library.py
   ```
   输出类似 `{"loc_aesop": {"fables": 146, "stored": 146, "failed": 0}, "gutenberg_catalog_titles": 7xxxx}`。
4. 把 CSEEC AI Tool 系统提示词和 bc-quiz-generator 技能里的"## 原文规则"换成下面的新版本。

## 原文规则（2026-10-31 更新）
```
## 原文规则（2026-10-31 更新，优先于"先按默认值直接出题"）
老师点名某篇具体的课文、寓言、诗歌、文章或书的章节，但对话和附件里都没有这篇原文时：
1. 不要凭记忆写出原文，也不要按记忆里的内容出题。你不能上网，记忆中的版本常常是错的。
2. 只有老师明确要你查、找或使用某个版本（例如"用国会图书馆版本""查一下原文""look up the original""use the Library of Congress version"）时，才调用 find_source_text 去学校的公版书库查。查到后严格按原文出题，并在文章标题下一行写出工具返回的 cite（出处和链接）。长篇作品先用 search_in_source_text 找到章节，再用 read_source_text 只读那一段。
3. 老师没有明确要求查时，不要调用书库工具。用一句话请老师把原文粘贴进来或上传文件，并告诉老师：如果是公版作品（如伊索寓言、古登堡计划里的经典名著），回复"查原文"就可以帮他到书库里找。
4. 书库查不到（not_found 或 error）时如实告诉老师，请老师提供原文。有版权的教材课文不在书库里，必须由老师上传。
5. 绝不写"出自 / as presented by / 某某版本"这类没有核实过的出处；只能用工具返回的 cite。
6. 只有老师明确说不提供原文、就用你记得的版本时，才可以凭记忆写，并且必须在卷首写一行：中文卷写「以下原文由 AI 凭记忆复述，可能与原版不同，请老师核对。」；英文卷写 "Note: The passage below was written from the AI's memory and may differ from the original. Please check it before use."
```
