"""Interactive terminal demonstration of the PR-02 DeepSeek Conversation Agent."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import uuid4

from .brief_service import DesignBriefService
from .conversation import ConversationAgent
from .conversation_store import ConversationStore
from .llm_client import make_deepseek_model
from .state_store import SQLiteDesignBriefStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="DeepSeek DGB requirement chat (PR-02)")
    parser.add_argument("--model", default=None, help="DeepSeek model, e.g. deepseek-flash")
    parser.add_argument("--db", default=".bearing_agent/brief.sqlite3",
                        help="Local SQLite file path (not committed)")
    parser.add_argument("--session", default="dgb-demo", help="Session ID to resume")
    parser.add_argument("--max-tools", type=int, default=6)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    db = Path(args.db)
    db.parent.mkdir(parents=True, exist_ok=True)
    try:
        model = make_deepseek_model(args.model)
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    service = DesignBriefService(SQLiteDesignBriefStore(db))
    agent = ConversationAgent(
        service=service, history=ConversationStore(db), model=model,
        max_tool_calls=args.max_tools,
    )
    session = args.session
    print("DGB Conversation Agent PR-02 | 模型:", args.model or model.model_name)
    print("当前会话:", session)
    print("输入中文需求；/status /brief /trace /new /exit")
    while True:
        try:
            message = input("\n用户> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n会话结束。")
            break
        if not message:
            continue
        if message == "/exit":
            break
        if message == "/new":
            session = f"dgb-{uuid4().hex[:10]}"
            print("新的独立设计会话:", session)
            continue
        if message == "/status":
            draft = agent.draft(session)
            print(json.dumps(
                {"revision": draft["revision"], "design_status": draft["design_status"]},
                ensure_ascii=False, indent=2,
            ))
            continue
        if message == "/brief":
            print(json.dumps(agent.draft(session), ensure_ascii=False, indent=2))
            continue
        if message == "/trace":
            print(json.dumps(
                agent.history.latest_trace(session), ensure_ascii=False, indent=2
            ))
            continue
        turn = agent.respond(session, message)
        print("\nAgent>", turn.answer)
        print(f"[revision={turn.revision} tools={len(turn.tool_trace)} "
              f"tokens={turn.usage.get('total_tokens', 'NA')} "
              f"elapsed={turn.elapsed_seconds:.2f}s]")
        if turn.error_type:
            print(f"[注意：{turn.error_type}；请先 /status，不要自动重复提交]")


if __name__ == "__main__":
    main()
