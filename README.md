# AI-Skills

本地 AI（Claude Code）使用的 skill 集合。每个子文件夹是一个 skill，复制到 `C:\Users\<用户名>\.claude\skills\` 下，新开对话即可生效。

| Skill | 用途 |
|---|---|
| [ai-homework-detector](ai-homework-detector/SKILL.md) | 帮老师检测学生作业是否可能由 AI 生成（中英文，本地离线） |

## 安装

```
git clone https://github.com/POLOZ27/AI-Skills
xcopy /E /I AI-Skills\ai-homework-detector %USERPROFILE%\.claude\skills\ai-homework-detector
pip install -r %USERPROFILE%\.claude\skills\ai-homework-detector\requirements.txt
python %USERPROFILE%\.claude\skills\ai-homework-detector\scripts\detect.py --download
```
