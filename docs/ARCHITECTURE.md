# RoleDock 架构（v0.1）

> 独立重建，不是 ATM Capital 的原始仓库或内部源码。配置、示例资料和测试数据均为合成内容。

## 目标

原始简历中的双层路由、知识分区/权限隔离、工具白名单、受限 PDF 读取、任务状态恢复、安全评测。

## 当前已实现

- 从服务端身份解析 Role Profile；请求中的 `role` 字段不得提升权限。
- 确定性任务路由至 `knowledge_expert` / `document_expert` / `research_expert`。
- 检索候选集合 ACL 前置过滤 + readback 复核 + 工具执行白名单。
- 12 个**自拟**示例知识分区、5 种演示角色、模拟材料和来源引用。
- 仅通过批准的文件 ID 解析 PDF；没有任意路径读取或任意命令执行。
- FastAPI 演示接口；18 条合成的矩阵式越权回归，加其他边界测试。
- 可选 LangGraph `StateGraph` 适配（需安装依赖；当前运行 API 为确定性路径）。
- Qdrant 真实 ACL 检索适配器原型（需额外安装与配置，未连接默认执行入口）。
- SiYuan read-only adapter 原型（需显式配置，不自动拉取任何企业数据）。

## 理想目标架构

```
HTTP/API + AuthN/OIDC
      |
  Trusted Principal ---> Role Policy (server-side)
      |
 LangGraph Gateway -> Role Profile -> Task Router
                                    |-> Knowledge Agent -> Qdrant ACL filter -> Readback ACL
                                    |-> Research Agent -> Approved search & citations
                                    |-> Document Agent -> Approved PDF ID -> PyMuPDF
      |
 Tool Executor policy -> audit events -> persistent Checkpointer -> recovery
```

## 需要与用户确认

1. 原系统 Agent 来源：OpenClaw/Hermes Gateway，还是完全基于 LangGraph？原工具和配置是否允许复刻？
2. 角色与任务分类：实际有什么岗位、专家角色、路由判定标准？
3. 12 个知识分区的真实划分规则；是否仅内部私用，不可公开？
4. SiYuan 是核心知识来源，还是管理文档的辅助系统？是否使用全量、增量、Webhook 同步？
5. 检索中“回读原文”是 SiYuan Block ID 回读还是文档存储对象？
6. 164 项任务和 82% 的统计口径及匿名复现范围。
7. Checkpointer 的数据库、恢复粒度、Gateway 自愈逻辑；是否要上前端管理台？

## 威胁模型

- 不信任用户自然语言；角色身份必须来自已认证会话。
- 不信任 LLM 给出的工具名称或授权指令。
- RAG 检索过滤只是第一道关，结果回读再校验。
- 可疑文档内容属于数据，不能重置 Role Profile 权限。
- 工具默认拒绝任意 shell / python / 文件系统访问。
- PDF 工具独立开放，只接受受控的已批准文件 ID。
- 生产版还需要安全的身份提供方、审计留存策略、租户隔离、加密、速率限制、密钥管理、Prompt Injection 专项测试。
