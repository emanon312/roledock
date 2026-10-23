"""Execute the real graph locally using either offline or OpenAI-compatible mode.

Usage: roledock-agent '新能源研究' --role investor --no-model --checkpoint .state/test.sqlite
"""
import argparse
import os
from contextlib import nullcontext
from pathlib import Path

from .agent_graph import build_agent_graph, run_agent
from .model_provider import ModelSettings, OpenAICompatibleChat
from .runtime import RoleDock
from .security import DEMO_IDENTITIES


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("question")
    parser.add_argument("--role", choices=sorted(p.role for p in DEMO_IDENTITIES.values()), default="investor")
    parser.add_argument("--file-id")
    parser.add_argument("--no-model", action="store_true", help="Local graph without an LLM")
    parser.add_argument("--checkpoint", help="Local SQLite checkpoint path (not a shared multiworker database)")
    parser.add_argument("--request-id", help="Unique ID for this request; defaults to a generated UUID")
    args = parser.parse_args()
    kb = None
    if os.getenv("ROLEDOCK_RETRIEVAL_MODE", "offline") == "qdrant":
        from .rag_cli import build_vector_knowledge
        kb = build_vector_knowledge()
    service = RoleDock(kb=kb)
    model = None if args.no_model else OpenAICompatibleChat(ModelSettings.from_env())
    principal = next(p for p in DEMO_IDENTITIES.values() if p.role == args.role)
    if args.checkpoint:
        from langgraph.checkpoint.sqlite import SqliteSaver
        path = Path(args.checkpoint)
        path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_context = SqliteSaver.from_conn_string(str(path))
    else:
        checkpoint_context = nullcontext(None)
    with checkpoint_context as saver:
        graph = build_agent_graph(service, model=model, checkpointer=saver)
        result = run_agent(graph, principal, args.question, args.file_id, args.request_id)
        print(f"task={result.task_id} status={result.status} expert={result.expert}")
        print(result.content)
        for hit in result.hits:
            print(f"SOURCE [{hit.document_id}] {hit.source} (score={hit.score:.3f})")


if __name__ == "__main__":
    main()
