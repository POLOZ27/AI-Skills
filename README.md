# AI-Skills

学校本地 AI（Open WebUI + Qwen，服务器 jamainserver）使用的 skill 集合。每个子文件夹是一个 skill：

- `openwebui/`：Open WebUI 版本。`*_tool.py` 导入到 工作空间 → 工具，`SKILL.md` 导入到 工作空间 → Skills。
- 其余文件：Claude Code 版本，可复制到 `~/.claude/skills/` 使用。

| Skill | 用途 |
|---|---|
| [ai-homework-detector](ai-homework-detector/SKILL.md) | 帮老师检测学生作业是否可能由 AI 生成（中英文，本地离线） |

## 安装到 Open WebUI

1. 备份 `webui.db`。
2. 工作空间 → 工具 → 新建，粘贴 `ai-homework-detector/openwebui/ai_homework_detector_tool.py`，保存。
3. 工作空间 → Skills → 新建，粘贴 `ai-homework-detector/openwebui/SKILL.md`。
4. 在要用的模型上勾选这个工具和 skill。
5. 第一次调用时会把约 1.7GB 模型下载到 `/app/backend/data/cache/aigc_detector`（在数据卷里，容器重建不丢）。

## 安装到 Claude Code

```
git clone https://github.com/POLOZ27/AI-Skills
cp -r AI-Skills/ai-homework-detector ~/.claude/skills/
pip install -r ~/.claude/skills/ai-homework-detector/requirements.txt
python ~/.claude/skills/ai-homework-detector/scripts/detect.py --download
```
