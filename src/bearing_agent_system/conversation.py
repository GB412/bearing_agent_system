"""Single bounded LangGraph-backed Conversation Agent for DGB requirement capture."""

from __future__ import annotations

import re
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
                emitted = output["messages"][len(previous_messages) + 1:]
                answer = _answer_text(output["messages"][-1])
                if not answer:
                    answer = "本轮未生成有效回复。当前已保存状态可通过 /status 查看。"
                answer = self._finalize(answer, turn_tools, user_message)
                stats = _usage(emitted)
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

    @staticmethod
    def _finalize(answer: str, tools: TurnTools, user_message: str) -> str:
        """Guard reportable claims against real tool receipts, never model self-report."""
        success = tools.successful_paths
        failures = tools.failed_writes
        if failures:
            succeeded = "、".join(dict.fromkeys(success)) if success else "无"
            return (
                f"本轮存在未通过的参数更新，不能宣称全部保存成功。"
                f"实际写入字段：{succeeded}。请根据 /status 查看当前数据，"
                "对被拒绝的字段补充或澄清原话。"
            )
        claims_new_write = bool(re.search(r"(?:本轮|刚才|刚刚|已经|成功).{0,8}"
                                          r"(?:保存|记录|修改|更新|写入)", answer))
        called_write = any(t["name"] == "update_design_brief" for t in tools.trace)
        asking_about_history = any(
            word in user_message
            for word in ("目前", "当前", "以前", "此前", "之前", "已经保存", "已记录",
                         "进度", "进展", "已确定", "还缺", "有哪些")
        )
        # A status summary can correctly say "previously saved" without a NEW write.
        if claims_new_write and not called_write and not asking_about_history:
            return (
                "本轮没有调用参数写入工具，因此没有新增或修改已保存的设计参数。"
                "可以继续提供信息；已有状态请通过 /status 查看。"
            )
        unsupported_completion = bool(
            re.search(r"(?:已完成全部设计|需求已正式确认|RoBAS.{0,10}(?:可运行|已就绪)"
                      r"|已经完成校核|CAD已生成)", answer, re.I)
        )
        if unsupported_completion:
            return (
                "当前仅建立用户层设计需求草案，尚未进行正式整份确认、"
                "工程计算校核、RoBAS 输入验证或 CAD 生成。"
            )
        return answer
