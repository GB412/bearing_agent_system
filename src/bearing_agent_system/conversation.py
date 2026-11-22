"""Single bounded LangGraph-backed Conversation Agent for DGB requirement capture."""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

from langchain.agents import create_agent

from .agent_prompt import build_system_prompt
from .agent_tools import TurnTools
from .brief_service import DesignBriefService
from .conversation_store import ConversationStore
from .reply_guard import needs_write_repair, verified_reply


@dataclass(frozen=True)
class ChatTurn:
    session_id: str
    turn_id: str
    answer: str
    revision: int
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    elapsed_seconds: float = 0.0
    error_type: str | None = None


def _answer_text(message: Any) -> str:
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        return "".join(
            part if isinstance(part, str) else str(part.get("text", ""))
            for part in content
        ).strip()
    return str(content).strip()


def _usage(messages: list[Any]) -> dict[str, int]:
    result = {"input_tokens": 0, "output_tokens": 0, "total_tokens": 0}
    for message in messages:
        if getattr(message, "type", None) != "ai":
            continue
        stats = getattr(message, "usage_metadata", None) or {}
        for key in result:
            result[key] += int(stats.get(key) or 0)
    return result


class ConversationAgent:
    """The model chooses actions, not field facts; SQLite is the only trusted brief."""

    def __init__(
        self,
        service: DesignBriefService,
        history: ConversationStore,
        model: Any,
        *,
        max_tool_calls: int = 6,
        history_turns: int = 10,
        agent_factory: Callable[..., Any] = create_agent,
    ):
        if max_tool_calls < 1 or history_turns < 0:
            raise ValueError("Invalid agent limits")
        self.service = service
        self.history = history
        self.model = model
        self.max_tool_calls = max_tool_calls
        self.history_turns = history_turns
        self.agent_factory = agent_factory
        # PR-02 is deliberately single-process / serial, with no distributed locks.
        self._lock = threading.RLock()

    def draft(self, session_id: str) -> dict[str, Any]:
        brief, revision = self.service.get_brief(session_id)
        status = self.service.get_design_status(session_id)
        return {
            "revision": revision,
            "schema_version": brief.schema_version,
            "brief": brief.model_dump(mode="json"),
            "design_status": status.model_dump(mode="json"),
            "deliverable_status": "DRAFT_ONLY",
            "robas_template_ready": "NOT_ASSESSED",
        }

    def respond(
        self, session_id: str, user_message: str, *, turn_id: str | None = None
    ) -> ChatTurn:
        if not session_id or not session_id.strip() or not user_message.strip():
            raise ValueError("Nonempty session_id and user message required")
        user_turn_id = turn_id or f"turn-{uuid4().hex}"
        with self._lock:
            previous = self.history.get_turn(session_id, user_turn_id)
            if previous is not None:
                if previous.user_message != user_message:
                    raise ValueError("turn_id cannot be reused for a different message")
                if previous.assistant_message is not None:
                    revision = self.service.get_brief(session_id)[1]
                    return ChatTurn(session_id, user_turn_id,
                                    previous.assistant_message, revision,
                                    tool_trace=previous.trace)
                revision = self.service.get_brief(session_id)[1]
                return ChatTurn(
                    session_id, user_turn_id,
                    "本轮曾开始但未确认结束。为避免重复写入已停止自动重试，请使用 /status 检查。",
                    revision, error_type="UNCERTAIN_PREVIOUS_TURN",
                )
            _, revision = self.service.get_brief(session_id)
            status = self.service.get_design_status(session_id).model_dump(mode="json")
            previous_messages = self.history.history(session_id, self.history_turns)
            self.history.begin_turn(session_id, user_turn_id, user_message)

            turn_tools = TurnTools(
                service=self.service, session_id=session_id,
                message_id=user_turn_id, user_message=user_message,
                max_calls=self.max_tool_calls,
            )
            started = time.perf_counter()
            try:
                agent = self.agent_factory(
                    self.model, turn_tools.tools(),
                    system_prompt=build_system_prompt(status, revision),
                )
                messages = previous_messages + [{"role": "user", "content": user_message}]
                # LangGraph recursion cap also limits model/tool cycles.
                output = agent.invoke(
                    {"messages": messages},
                    config={"recursion_limit": 2 * self.max_tool_calls + 5},
                )
                emitted = output["messages"][len(messages):]
                answer = _answer_text(output["messages"][-1])
                stats = _usage(emitted)
                # A model answer is not a write receipt. Allow one repair with
                # exactly the same trusted turn and remaining tool-call budget.
                if (needs_write_repair(
                    answer, user_message, turn_tools.successful_paths
                ) and not turn_tools.failed_writes
                        and len(turn_tools.trace) < self.max_tool_calls):
                    repair = output["messages"] + [{
                        "role": "user",
                        "content": (
                            "[程序核验反馈，不是新用户消息] 你刚才声称参数已保存，"
                            "但本轮没有成功写入。请基于本轮原始用户消息调用"
                            " update_design_brief；如果用户意图或对应部件不明确，"
                            "请先澄清，不得自行补足。evidence_span 只能引用"
                            "原始用户消息，不能引用此反馈。这是唯一一次纠正机会。"
                        ),
                    }]
                    correction = agent.invoke(
                        {"messages": repair},
                        config={"recursion_limit": 2 * self.max_tool_calls + 5},
                    )
                    for key, count in _usage(
                        correction["messages"][len(repair):]
                    ).items():
                        stats[key] += count
                    answer = _answer_text(correction["messages"][-1])
                if not answer:
                    answer = "本轮未生成有效回复。当前已保存状态可通过 /status 查看。"
                answer = verified_reply(
                    answer, user_message,
                    self.service.get_design_status(session_id).model_dump(mode="json"),
                    turn_tools.successful_paths, turn_tools.failed_writes,
                )
                error_type = None
            except Exception as exc:
                # Never retry a model/tool loop after an uncertain partial write.
                error_type = type(exc).__name__
                stats = {}
                answer = (
                    "本轮未能正常完成，已有写入可能已经生效。"
                    "请先使用 /status 查看真实参数；本轮不会自动重试。"
                )
            final_revision = self.service.get_brief(session_id)[1]
            self.history.finish_turn(
                session_id, user_turn_id, answer, turn_tools.trace,
                failed=error_type is not None,
            )
            return ChatTurn(
                session_id, user_turn_id, answer, final_revision,
                tool_trace=turn_tools.trace, usage=stats,
                elapsed_seconds=time.perf_counter() - started, error_type=error_type,
            )

