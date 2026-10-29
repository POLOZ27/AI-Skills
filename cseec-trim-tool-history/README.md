# cseec_trim_tool_history（Open WebUI Filter）

挂在 "CSEEC 升学分析" 模型上的 inlet 过滤器，用来让追问变快。

**问题**：Open WebUI v0.12.4 每次追问时，都会把之前每一轮的全部工具调用和完整返回结果原样重发给模型（`utils/middleware.py` 的 `process_messages_with_output` → `convert_output_to_messages`）。2026-10-29 实测，一句"给我中文"要先读 65,816 token，单是读入就花了 100 秒。

**做法**：对已经结束的轮次，删掉工具调用和工具返回，只保留每轮的最终回答。读取上传文件（如成绩单）的工具结果默认保留，见 `keep_tools`。当前这一轮不做任何改动。

**代价**：追问时，模型看不到上一轮官网工具返回的原文，只能看到它自己写的总结。需要原文时，它会重新查一次（官网结果有 24 小时缓存，基本不花时间）。

安装：在 Workspace → Functions 新建 Filter，粘贴代码，然后只挂到 "CSEEC 升学分析" 模型上（不要设成全局）。
