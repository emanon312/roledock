# RoleDock v0.3 / 迭代验收

## 已编码、可运行的部分
- OpenAI-Compatible SDK adapter (Chat Completions only); injectable fake client; `api_key/base_url/model` environment variables
- FastEmbed BAAI/bge-small-zh-v1.5 adapter, Qdrant collection ingestion and scoped vector query
- Trusted chunk readback using server-side partition, source ID, deterministic UUID, SHA256 fingerprint verification
- LangGraph StateGraph: role loading, policy-gated route, three expert nodes, result finalization; optional SqliteSaver
- `roledock-index`, `roledock-agent` CLI; `/v1/agent/tasks` optional local endpoint; existing `/v1/tasks` offline path preserved
- Offline Qdrant/model SDK mocks; optional real Qdrant local and real LangGraph/SQLite integration tests

## 验证分级（不可混为一谈）
1. 本地：基础单元与安全测试（不安装大体积可选依赖）。
2. CI：`.[all]` 后执行真正的 Qdrant 本地向量查询、LangGraph 路由与 SQLite checkpoint 读写；Encoder 用确定性的测试向量。
3. 用户环境待验证：FastEmbed BGE ONNX 模型首次下载、真实中文召回质量、任意第三方聊天 API 的延时/限流/JSON 兼容性。

## 仍未交付
- SiYuan 文档增量同步与文档版本控制、真正的持久化权威内容仓库
- PostgreSQL checkpointer、人工确认 interrupt/resume、失败步骤幂等重试、并发多租户保障
- 身份认证/租户隔离、限流、生产密钥管理、安全审计脱敏与链路监控
- 以真实标签评估召回效果、成本、延时和 5 类端到端场景覆盖率
- 可视化控制台、审批流、Gateway 守护

## 下一次 PR 建议
1. 加权召回与引用精度的离线评测集，量化 Recall@K 和分区泄露率。
2. 引入可信文件存储与 Qdrant collection 别名迁移，避免在线索引销毁与 stale source。
3. 引入真正的 `interrupt` 人工确认和审批签名、恢复幂等性测试。
