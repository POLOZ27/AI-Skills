# 邮件系统（ja-mail）接入本地 AI

邮件系统用本地 AI 把学校写给家长的邮件翻译成家长的语言（`src/lib/ai.ts` 的 `translate`，OpenAI 兼容的 `/v1/chat/completions`）。2026-10-29 起，它通过 Open WebUI 使用自己独立的 API 密钥，不再直连 strata（strata 只支持一个密钥）。

## .env 里的三行
```
LOCAL_AI_BASE_URL=http://school-ai-openwebui:8080/api
LOCAL_AI_MODEL=qwen3.8-flash-next-unsloth-ud-iq4_xs
LOCAL_AI_API_KEY=<"ja-mail (service)" 账号的 Open WebUI 密钥，只放在服务器 /home/polo/ja-mail/.env，不要提交>
```
`.env` 权限设为 600。

## 每次用 docker run 重建 ja-mail 之后
ja-mail 是用 `docker run --env-file` 建的，改了 `.env` 必须重建容器才会生效（只 `docker restart` 不会重新读取）。重建以后还要接上 AI 所在的网络，否则连不上 Open WebUI：
```
docker network connect llm_llm-network ja-mail
```
原来的 `ja-internal` 网络保留不动。

## 账号和权限
- Open WebUI 用户 "ja-mail (service)"（ja-mail@local.invalid，普通用户，只通过 API 密钥使用）
- 组 "Service: ja-mail"：允许使用 API 密钥，只能读取基础模型，访问不到 CSEEC 模型
- API 密钥接口白名单里加了 `/api/v1/chat/completions` 和 `/api/models`

## 停用
在 Open WebUI 管理后台停用 "ja-mail (service)" 账号即可，不影响老师使用。

---
English summary: ja-mail reaches the local AI through Open WebUI with its own API key (service user "ja-mail (service)", base model only). After any `docker run` rebuild, run `docker network connect llm_llm-network ja-mail`; `.env` changes need a rebuild, not a restart. Disable by deactivating that user.
