# RoleDock — 企业多角色 Agent 系统（独立复刻）

> **边界声明**：本仓库从简历描述出发进行独立重构，不包含 ATM Capital 的源代码、商业信息、生产配置、真实文档或原始评测集。所有演示文档与攻击集均为合成数据。这里展示的是新的可验证实现，不代表原公司实际部署情况。

**当前状态：v0.4 / 功能性开发版本，不可公网部署。** GitHub PR #1 中持续开发。具备离线演示，以及可选择接入 **Qdrant + FastEmbed** 和 **LangGraph + OpenAI-Compatible Chat Completions** 的代码路径。

## 架构与信任边界

```text
Client (demo key; LOCAL ONLY)
   │
FastAPI identity boundary → principal = {actor, role}    [role never from body or model]
   │
Role Profile (server-defined tool whitelist + partition ACL)
   │
LangGraph: load_role → route → policy gate
   │                ├── knowledge_expert → prefiltered Qdrant → trusted chunk readback ─┐
   │                ├── research_expert → bounded LLM planning                      ─────┤
   │                └── document_expert → approved PDF ID registry                 ──────┤
   │                                                                               finish
   └── checkpoint (optional SqliteSaver) / metadata-only audit
```

- **Role before task**：先建立身份和 Role Profile，模型只能提议在该角色白名单中的工具，执行前再校验。
- **Qdrant is an untrusted index**：payload 只存 `chunk_id/source_id/partition/fingerprint` 等索引元数据，不存正文。检索使用分区过滤，回读服务端可信切片并验证 ID、分区、内容指纹。对伪造的索引元数据 fail closed。
- **LLM never executes tools**：模型可分类请求、总结检索证据和制定研究计划，但真正的工具调用由 LangGraph 中确定性的专家节点处理。
- **Source isolation**：演示中权威来源是应用启动加载的合成 JSON 文档；向量索引变化或文档版本不匹配时拒绝返回。生产环境必须换持久化受控文档存储。

## ① 无模型、无外部服务的离线演示

Python 3.11+：

```bash
python -m venv .venv
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e '.[test]'
pytest -q
uvicorn roledock.api:app --host 127.0.0.1 --port 8000
```

访问 `http://127.0.0.1:8000/docs`，在 HTTP 请求中传 `X-Demo-Key: demo-investor-key`（其他演示角色：`demo-finance-key`、`demo-ir-key`、`demo-ops-key`、`demo-deal-key`、`demo-compliance-key`、`demo-admin-key`）。

原 `/v1/tasks` 使用**词项检索 + 确定性路由**，不代表向量/模型执行。

## ② 真正的向量检索：BGE-small-zh-v1.5 + Qdrant

```bash
python -m pip install -e '.[rag]'
# First use downloads ~90 MB ONNX embedding model and needs network access.
# Option A: persistent embedded Qdrant (default .qdrant directory):
roledock-index index

# Option B: Qdrant service (run `docker compose up -d qdrant` first):
# export ROLEDOCK_QDRANT_URL=http://127.0.0.1:6333
# roledock-index index

# Activate retrieval in this shell BEFORE starting the API/agent:
# export ROLEDOCK_RETRIEVAL_MODE=qdrant  (PowerShell: $env:ROLEDOCK_RETRIEVAL_MODE='qdrant')
uvicorn roledock.api:app --host 127.0.0.1 --port 8000
```

`roledock-index index` **仅允许可信本地操作员执行**，会重建对应 Qdrant collection；这是非零停机的演示设计，不是生产迁移流程。服务端须访问与索引脚本相同的 Qdrant 存储，不能将 `.qdrant` 作为多进程共享数据库。生产请采用远程 Qdrant、版本化 collection/别名切换、变更审计和持久化文档存储。

可以打开 `/v1/tasks` 执行原路由并走真实的向量检索（切换环境变量后重启服务）。模型不需要参与向量化；Embedding 和聊天模型分别可配置。

## ③ LangGraph 条件专家节点 + OpenAI-Compatible 模型

```bash
python -m pip install -e '.[agent,rag]'
# Select a provider supporting /chat/completions; provider/model compatibility varies.
# export ROLEDOCK_LLM_BASE_URL=https://YOUR-ENDPOINT/v1
# export ROLEDOCK_LLM_MODEL=YOUR-MODEL
# export ROLEDOCK_LLM_API_KEY=YOUR-PRIVATE-KEY
# export LANGGRAPH_STRICT_MSGPACK=true

# LLM-connected orchestration; optionally combine with ROLEDOCK_RETRIEVAL_MODE=qdrant
roledock-agent '帮我规划新能源汽车行业研究' --role investor --checkpoint .state/graph.sqlite

# Zero-token local graph (still requires LangGraph):
roledock-agent '帮我检索新能源汽车研究材料' --role investor --no-model --checkpoint .state/graph.sqlite
```

Graph path: `load_role → route → {knowledge_expert | research_expert | document_expert | policy_denied} → finish`。`SqliteSaver` 中的任务状态可在重启后检查；**此旧版 CLI 路径仅证明已完成步骤的 checkpoint 持久化；v0.4 的真正 HITL 仅在第④节新增的 `/v1/runtime/*` 路径中启用，仍不保证任意工具的 exactly-once 重试**。Checkpoint 可能存储检索正文，必须使用私有目录、限制操作系统权限，并制定保留/删除策略。

如需本地通过 API 调用模型 Agent：

```bash
# ONLY localhost; do not expose demo keys to other machines.
# export ROLEDOCK_ENABLE_AGENT_API=1
uvicorn roledock.api:app --host 127.0.0.1 --port 8000
# POST /v1/agent/tasks with X-Demo-Key header; model env vars must be set
```

OpenAI SDK 统一 `api_key / base_url / model`，只使用 Chat Completions 的文本输入/输出能力，不假设任意兼容提供方都支持 JSON 模式、function calling 或某个特定参数。错误的路由 JSON/越权工具选择会被拒绝，而不是执行。

## 测试与说明

```bash
pytest -q                              # offline tests; optional integrations may skip
python -m pip install -e '.[all]'
pytest -q tests/test_integrations.py  # real Qdrant local + LangGraph + SQLite (no API key)
```

- `tests/test_regression.py`：6 个受限分区 × 3 条路径的 **18 条合成权限回归**，与原公司测试集无关。
- `tests/test_qdrant_unit.py`：验证注入非法 partition、篡改 fingerprint、payload 伪造正文时 fail closed。
- `tests/test_model_provider.py`：Fake Chat Completions 响应，不消耗真实 API 额度，验证模型无法扩权。
- `tests/test_integrations.py`：用真实 Qdrant 的 `:memory:` 模式与**确定性测试 Encoder**验证向量往返；使用真实 LangGraph、SQLite 验证路由和已完成任务的 checkpoint 读取。**不在 CI 下载 BGE 模型或拨打 LLM API**。
- 真实 BGE 下载与远端模型服务须在用户环境另行验证；未运行时不能声称完整线上联调已完成。

**安全警示**：此仓库使用公开 Demo API Keys，只允许回环地址本地运行。不存在真正的企业 SSO、租户隔离、密钥轮换、输入配额、PII 清洗、完整审计保留或任意中断后幂等恢复。千万不要把 demo 直接部署到公网。

详见 [架构](docs/ARCHITECTURE.md)、[设计决策](docs/DECISIONS.md)、[下一步](docs/NEXT_PHASE.md)。

## ④ v0.4 持久化人工审批 / 中断恢复（localhost demo）

安装完整依赖后，执行以下命令（仍然不需要聊天模型 API Key）：

```bash
python -m pip install -e '.[all]'
# Linux/macOS: export ROLEDOCK_ENABLE_RUNTIME_API=1
# PowerShell: $env:ROLEDOCK_ENABLE_RUNTIME_API='1'
# The default is no-model, permission-checked routing.
uvicorn roledock.api:app --host 127.0.0.1 --port 8000 --workers 1
```

`POST /v1/runtime/tasks` 必须有 `X-Demo-Key: demo-finance-key`，JSON 示例：

```json
{"question":"解析pdf","file_id":"sample-finance-policy","request_key":"finance-demo-01"}
```

返回 `pending_approval` 与 `task_id`；重试**相同**请求和 `request_key` 返回同一个任务，修改内容后重用相同键则返回 HTTP 409。此处注册的 PDF 是代码现场生成的 **纯虚构样本**，不包含真实雇主材料。

使用 `X-Demo-Key: demo-compliance-key` 审批：

```text
GET  /v1/runtime/reviews/{task_id}
POST /v1/runtime/tasks/{task_id}/review
Body: {"approved":true}  # false means reject
```

审批通过后，LangGraph 从 SQLite Checkpointer 恢复，**重新校验**用户工具白名单与批准文件 ID，然后才真正解析 PDF。原始请求者通过 `GET /v1/runtime/tasks/{task_id}` 获取结果；审批者只能获得状态，不会收到 PDF 正文。非合规/管理员无法审批，请求者也不能自己审批。

**这不是企业级 exactly-once 保障。** SQLite task ledger 为请求建立幂等登记、审计审批决定；LangGraph 的 `interrupt()` 保证待审批流程可以重启后恢复。对于已经启动但中途崩溃的非审批节点，系统采取失败封闭处理，不自动重放。真实有副作用的工具需要独立事务外盒/幂等键/租约和一致性补偿。`.state/` 内的 checkpoint **仍可能包含原始问题和解析文本**，须限制文件权限并定期清理；不能公网部署，不能开多个 Uvicorn worker 共用此 SQLite 目录。

完整测试包括纯 Python TaskLedger 权限与重试测试，以及 GitHub Actions 中真实 LangGraph interrupt/SQLite 重启恢复、越权/拒绝、伪造 resume 的集成测试；**不在 CI 调用真实大模型或下载 BGE**。
