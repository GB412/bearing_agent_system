"""PR-02 offline tests: real LangGraph tool loop with a scripted model, no API key."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from bearing_agent_system import DesignBriefService, SQLiteDesignBriefStore
from bearing_agent_system.agent_tools import TurnTools
from bearing_agent_system.conversation import ConversationAgent
from bearing_agent_system.conversation_store import ConversationStore
from bearing_agent_system.llm_client import make_deepseek_model


class ScriptedChatModel(BaseChatModel):
    replies: list[AIMessage]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted-tool-chat"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None,
        run_manager: Any = None, **kwargs: Any,
    ) -> ChatResult:
        if self.calls >= len(self.replies):
            raise RuntimeError("Scripted LLM emitted more replies than expected")
        item = self.replies[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=item)])


def action(name: str, args: dict[str, Any], call_id: str = "call-1") -> AIMessage:
    return AIMessage(content="", tool_calls=[
        {"name": name, "args": args, "id": call_id}
    ])


def param(path: str, value: Any, evidence: str, unit: str | None = None) -> dict[str, Any]:
    return {"path": path, "value": value, "unit": unit, "evidence_span": evidence}


@pytest.fixture
def environment(tmp_path):
    db = tmp_path / "agent.sqlite3"
    service = DesignBriefService(SQLiteDesignBriefStore(db))
    history = ConversationStore(db)
    return service, history


def test_offline_langgraph_tool_call_commits_real_brief(environment):
    service, history = environment
    text = "轴承内径25mm，外径52mm，宽15mm"
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {
            "operation": "set",
            "changes": [
                param("dimensions.d_mm", 25, "内径25mm", "mm"),
                param("dimensions.D_mm", 52, "外径52mm", "mm"),
                param("dimensions.B_mm", 15, "宽15mm", "mm"),
            ],
        }),
        AIMessage(content="已记录尺寸，下一步请提供转速。"),
    ])
    agent = ConversationAgent(service, history, model)
    result = agent.respond("design-1", text, turn_id="t-1")
    assert result.error_type is None
    assert result.revision == 1
    assert result.tool_trace[0]["ok"]
    assert result.tool_trace[0]["applied_changes"] == [
        "dimensions.d_mm", "dimensions.D_mm", "dimensions.B_mm"
    ]
    brief, revision = service.get_brief("design-1")
    assert revision == 1
    assert brief.dimensions.d_mm.value == 25
    assert brief.dimensions.D_mm.value == 52
    assert brief.dimensions.B_mm.value == 15
    assert "下一步" in result.answer
    assert model.calls == 2


def test_offline_multiturn_replace_and_resume(environment, tmp_path):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("operating.inner_speed_rpm", 15000, "内圈15000rpm", "rpm")
        ]}, "speed-a"),
        AIMessage(content="已记录转速。"),
        action("update_design_brief", {"operation": "replace", "changes": [
            param("operating.inner_speed_rpm", 18000, "内圈改为18000rpm", "rpm")
        ]}, "speed-b"),
        AIMessage(content="已经修改内圈转速。"),
    ])
    agent = ConversationAgent(service, history, model)
    agent.respond("user-1", "内圈15000rpm", turn_id="t1")
    changed = agent.respond("user-1", "内圈改为18000rpm", turn_id="t2")
    assert changed.revision == 2
    assert service.get_brief("user-1")[0].operating.inner_speed_rpm.value == 18000
    reopened = ConversationStore(tmp_path / "agent.sqlite3")
    assert len(reopened.history("user-1")) == 4
    assert len(reopened.latest_trace("user-1")) == 1
    assert agent.draft("user-1")["deliverable_status"] == "DRAFT_ONLY"


def test_plain_explanation_requires_no_tool(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[AIMessage(
        content="游隙是套圈与滚动体之间的可移动余量。"
    )])
    agent = ConversationAgent(service, history, model)
    result = agent.respond("design-2", "请解释什么叫游隙", turn_id="plain")
    assert result.error_type is None
    assert result.revision == 0
    assert result.tool_trace == []
    assert "游隙" in result.answer
    assert service.get_design_status("design-2").known == {"bearing.type": "DGB"}


def test_status_tool_read_only_and_available_to_model(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("get_design_status", {}, "read-status"),
        AIMessage(content="还缺少尺寸和工况数据，请告诉我轴承内径。"),
    ])
    agent = ConversationAgent(service, history, model)
    result = agent.respond("design-1", "我现在还缺什么？", turn_id="status-1")
    assert result.error_type is None
    assert result.tool_trace[0]["name"] == "get_design_status"
    assert result.revision == 0


def test_model_cannot_forge_optimization_range_as_user_fact(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("optimization_slots.Z", {"mode": "bounded", "bounds": [10, 100]},
                  "我还不知道球数")
        ]}),
        AIMessage(content="已把球数固定在10到100之间。"),
    ])
    agent = ConversationAgent(service, history, model)
    result = agent.respond("design-1", "我还不知道球数", turn_id="fake-range")
    assert not result.tool_trace[0]["ok"]
    assert "未通过" in result.answer
    assert service.get_brief("design-1")[0].optimization_slots.Z.mode == "optimize"


def test_no_tool_call_may_not_claim_fresh_write(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[AIMessage(content="已经保存轴承尺寸。")])
    agent = ConversationAgent(service, history, model)
    result = agent.respond("design-1", "我的轴承尺寸是25×52×15mm", turn_id="no-write")
    assert "本轮没有调用参数写入工具" in result.answer
    assert service.get_brief("design-1")[0].dimensions.d_mm is None


def test_tool_rejection_overrides_false_success_claim(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("dimensions.D_mm", 52, "外径不超过52mm", "mm")
        ]}),
        AIMessage(content="所有参数全部写入成功。"),
    ])
    agent = ConversationAgent(service, history, model)
    result = agent.respond("design-1", "外径不超过52mm", turn_id="bad-bound")
    assert "未通过" in result.answer
    assert service.get_brief("design-1")[0].dimensions.D_mm is None


def test_turn_id_replay_does_not_repeat_write_or_model_call(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("dimensions.d_mm", 25, "内径25mm", "mm")
        ]}),
        AIMessage(content="内径已记录。"),
    ])
    agent = ConversationAgent(service, history, model)
    first = agent.respond("s", "内径25mm", turn_id="request-id-1")
    second = agent.respond("s", "内径25mm", turn_id="request-id-1")
    assert first.revision == second.revision == 1
    assert model.calls == 2
    with pytest.raises(ValueError):
        agent.respond("s", "内径改成30mm", turn_id="request-id-1")


def test_uncertain_previous_turn_not_blindly_reexecuted(environment):
    service, history = environment
    history.begin_turn("s", "maybe", "外径52mm")
    model = ScriptedChatModel(replies=[])
    result = ConversationAgent(service, history, model).respond(
        "s", "外径52mm", turn_id="maybe"
    )
    assert result.error_type == "UNCERTAIN_PREVIOUS_TURN"
    assert model.calls == 0


def test_tool_budget_and_repeat_guard(environment):
    service, _ = environment
    tools = TurnTools(service=service, session_id="s",
                      message_id="m", user_message="内径25mm", max_calls=2)
    update, status = tools.tools()
    first = update.invoke({"operation": "set", "changes": [
        param("dimensions.d_mm", 25, "内径25mm", "mm")
    ]})
    assert first["ok"]
    repeat = update.invoke({"operation": "set", "changes": [
        param("dimensions.d_mm", 25, "内径25mm", "mm")
    ]})
    assert repeat["error"] == "REPEATED_TOOL_CALL"
    assert status.invoke({})["error"] == "TOOL_BUDGET_EXCEEDED"
    assert service.get_brief("s")[1] == 1


def test_immutable_server_identity_not_part_of_tool_schema(environment):
    service, _ = environment
    tools = TurnTools(service=service, session_id="trusted",
                      message_id="server-id", user_message="内径25mm")
    write_tool = tools.tools()[0]
    schema = write_tool.args_schema.model_json_schema()
    assert "session_id" not in schema["properties"]
    assert "message_id" not in schema["properties"]
    assert "confirmed" not in schema["properties"]
    result = write_tool.invoke({"operation": "set", "changes": [
        {**param("dimensions.d_mm", 25, "内径25mm", "mm"),
         "confirmed": True}
    ]})
    assert not result["ok"]
    assert service.get_brief("trusted")[0].dimensions.d_mm is None


def test_reject_finalized_or_robas_claim_without_proof(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content="RoBAS输入已就绪，可以运行。")
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "现在可以运行吗", turn_id="r"
    )
    assert "NOT_ASSESSED" not in result.answer
    assert "尚未进行" in result.answer


def test_deepseek_requires_key(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="DEEPSEEK_API_KEY"):
        make_deepseek_model()


def test_deepseek_non_thinking_configuration():
    model = make_deepseek_model(api_key="unit-test-only", model_name="deepseek-flash")
    assert model.model_name == "deepseek-flash"
    assert model.extra_body == {"thinking": {"type": "disabled"}}
