"""
title: CSEEC Trim Tool History
description: On follow-up questions, drop earlier turns' tool calls and tool results (keep each turn's final answer and file reads) so the model re-reads far less context.
author: CSEEC
version: 0.1.0
license: MIT
"""

from pydantic import BaseModel, Field


class Filter:
    class Valves(BaseModel):
        priority: int = Field(default=0, description="Filter order")
        keep_tools: str = Field(
            default="view_file,query_chat_files,grep_chat_files,list_chat_files",
            description="Comma-separated tool names whose earlier results are kept (uploaded-file reads, e.g. a transcript)",
        )

    def __init__(self):
        self.valves = self.Valves()

    def inlet(self, body: dict, __user__: dict = None) -> dict:
        messages = body.get("messages")
        if not isinstance(messages, list):
            return body
        last_user = max(
            (i for i, m in enumerate(messages) if isinstance(m, dict) and m.get("role") == "user"),
            default=None,
        )
        if last_user is None:
            return body
        keep = {name.strip() for name in self.valves.keep_tools.split(",") if name.strip()}

        # Map tool_call ids from finished turns to tool names so file reads can be kept.
        names = {}
        for message in messages[:last_user]:
            for call in message.get("tool_calls") or []:
                names[call.get("id")] = (call.get("function") or {}).get("name")

        trimmed = []
        for message in messages[:last_user]:
            role = message.get("role")
            if role == "tool":
                if names.get(message.get("tool_call_id")) in keep:
                    trimmed.append(message)
                continue
            if role == "assistant" and message.get("tool_calls"):
                calls = [
                    c for c in message["tool_calls"]
                    if (c.get("function") or {}).get("name") in keep
                ]
                message = dict(message)
                if calls:
                    message["tool_calls"] = calls
                else:
                    message.pop("tool_calls")
                    if not message.get("content"):
                        continue
            trimmed.append(message)

        # The current turn (last user message and anything after it) is left untouched.
        body["messages"] = trimmed + messages[last_user:]
        return body
