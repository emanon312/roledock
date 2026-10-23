# RoleDock — 企业多角色 Agent 系统（独立复刻）

> **注意**：这是基于个人简历公开描述独立构建的作品集项目，**不是** ATM Capital 内部源代码、真实数据、原始项目交付物或原始评测集。所有 demo 文档均为合成内容。本仓库当前为 **v0.2 offline security-first foundation**，尚非简历所有能力的完整复现。

## 核心设计

- **双层路由**：服务端角色上下文先行，再进行任务选择。
- **多层鉴权**：工具执行前、Qdrant 检索条件、召回结果、原文回读均校验权限。
- **最小权限**：财务 PDF 读取走批准文件 ID；不授予通用 Shell。
- **可溯源**：每个离线检索结果都有 `document_id / partition / source`。
- **可扩展**：预留 LangGraph、Qdrant、FastEmbed、SiYuan 接口。

## 运行（不需要 LLM API Key）

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS / Linux: source .venv/bin/activate
pip install -e '.[test]'
pytest -q
uvicorn roledock.api:app --reload
```

访问 http://127.0.0.1:8000/docs ，使用下方任一 **本地演示** API key：

- `demo-investor-key`
- `demo-ir-key`
- `demo-finance-key`
- `demo-ops-key`
- `demo-admin-key`
- `demo-deal-key`
- `demo-compliance-key`

```bash
curl -X POST http://127.0.0.1:8000/v1/tasks \
  -H 'Content-Type: application/json' \
  -H 'X-Demo-Key: demo-ir-key' \
  -d '{"question":"请检索公司财务和交易政策"}'
```

切记：这些密钥写在代码中，只用于本地功能演示。**不要将当前 API 开放公网。**

## 实验性可选模块

```bash
pip install -e '.[agent,rag]'
```

- `roledock.runtime.build_langgraph(...)`：LangGraph 的真实 StateGraph + `InMemorySaver` 入口；进程重启后不会持久恢复，生产版应接持久化 Checkpointer。
- `roledock.qdrant_adapter.QdrantSecureRetriever`：Qdrant ACL 过滤 + 可信源文档回读，**不再信任向量库返回的正文**；需自建 collection、选择 embedding 模型并完成写入。
- `roledock.siyuan.SiYuanClient`：访问本地 SiYuan 的只读 API，尚未接到默认知识索引管线。

这些集成是**代码级适配器**，不能误写成已经完成端到端联调。

## v0.2 新增

- 交易执行与合规风控两个演示角色（共七类），12 个合成知识分区。
- 可复现的固定窗口切片和 SHA-256 指纹，禁止 agent 直接指定任意本地路径。
- 基于 SQLite 的元数据审计日志：记录 task/actor/role/tool/status，不保存提示词或 RAG 正文。
- 搜索无命中时返回空结果，避免无关文档回退。
- 新增 `GET /v1/tasks/{task_id}/audit`，仅本人可读取审计元信息。
- Qdrant 检索适配器强制回读权威文档并比对索引分区元信息（仍需真实服务联调）。

详见 [设计决策](docs/DECISIONS.md)、[验收及待办](docs/NEXT_PHASE.md)。

## 安全测试

`tests/test_regression.py` 生成 `6 个受限分区 × 3 类路径 = 18 条` 确定性回归测试（合成数据）；通过后只说明这 18 条新测试通过，并不等于完整的真实-world 100% 防护，也不等于原公司测试原样复现。

## 里程碑

- [x] v0.1：架构、角色策略、受限知识样例、双层路由、受控 PDF、基本 API、18 条合成回归
- [x] v0.2 基础：角色重设计、可重复切片、元数据审计、受控 Qdrant 回读适配器
- [ ] v0.2 完整：真实 Qdrant + FastEmbed/BGE 数据写入和联调
- [ ] v0.3：LangGraph 主干 + 专家 Agent + 持久化 Checkpointer + Human-in-the-loop
- [ ] v0.4：SiYuan 同步、文件处理沙箱、Gateway 守护 + 告警
- [ ] v0.5：评测中心、攻击集、任务指标与演示前端

详见 [架构及问题](docs/ARCHITECTURE.md)。
