---
name: lark-wiki
version: 1.0.0
description: "飞书知识库：管理知识空间和文档节点。创建和查询知识空间、管理节点层级结构、在知识库中组织文档和快捷方式。当用户需要在知识库中查找或创建文档、浏览知识空间结构、移动或复制节点时使用。"
metadata:
  requires:
    bins: ["lark-cli"]
  cliHelp: "lark-cli wiki --help"
---

# wiki (v2)

**CRITICAL — 开始前 MUST 先用 Read 工具读取 [`../lark-shared/SKILL.md`](../lark-shared/SKILL.md)，其中包含认证、权限处理**

如果 `../lark-shared/SKILL.md` 在当前 workspace 中不存在，不要因此中断；直接使用 `lark-cli auth status` / `lark-cli auth login` 检查并补齐认证即可。
Fallback: fall back to `lark-cli auth status` / `lark-cli auth login` when the shared skill file is absent.

## 权限阻塞快速判定

- 如果读取或发送到某个 `chat_id` / wiki 资源时返回 `API error: [232010] Operator and chat can NOT be in different tenants.`，应优先判定为跨 tenant 权限阻塞。
- 这类错误不能通过重试、改参数名或切换 `msg_type` 解决；必须先确认当前 `lark-cli auth status` 的 user/app 所属 tenant 是否与目标资源一致。
- 当目标是 IM 群消息时，还应同步检查：
  - `lark-cli im chats list --as bot`
  - bot 是否实际在目标群内
- 若 tenant 不一致且 bot 不在群内，则本机不存在直接发送路径，应尽快把问题归类为外部权限阻塞，而不是继续做 payload 调试。


## Companion Skills

### `lark-doc`
- Trigger: 需要按关键词搜索 wiki/doc、按标题找提案文档，或在命中 wiki 节点后继续读取正文。
- Workflow:
  1. 先用 `lark-cli auth status` 确认当前是 `user` 身份。
  2. 关键词资源发现优先用 `lark-cli docs +search --query ...`。这一步需要 `search:docs:read` scope。
  3. 搜索结果若 `entity_type = WIKI`，再把 wiki token 交给 `lark-cli wiki spaces get_node --params '{"token":"..."}'` 解析 `obj_type` / `obj_token`。
  4. 若实际对象是 `docx` / `doc`，继续交给 `lark-doc` 的 `docs +fetch` 读取正文。
- Note: `wiki spaces get_node` 不能按关键词搜索；它只适用于已知 token 的节点解析。

## API Resources

```bash
lark-cli schema wiki.<resource>.<method>   # 调用 API 前必须先查看参数结构
lark-cli wiki <resource> <method> [flags] # 调用 API
```

> **重要**：使用原生 API 时，必须先运行 `schema` 查看 `--data` / `--params` 参数结构，不要猜测字段格式。

### spaces

  - `get_node` — 获取知识空间节点信息

## 权限表

| 方法 | 所需 scope |
|------|-----------|
| `spaces.get_node` | `wiki:node:read` |
