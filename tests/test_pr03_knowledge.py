"""PR-03 offline regression tests for source-backed, read-only knowledge lookup."""

from __future__ import annotations

from typing import Any

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from bearing_agent_system import DesignBriefService, SQLiteDesignBriefStore
from bearing_agent_system.agent_tools import TurnTools
from bearing_agent_system.conversation import ConversationAgent
from bearing_agent_system.conversation_store import ConversationStore
from bearing_agent_system.knowledge import KnowledgeRepository


class ScriptedChatModel(BaseChatModel):
    replies: list[AIMessage]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "pr03-scripted"

    def bind_tools(self, tools: Any, **kwargs: Any) -> ScriptedChatModel:
        return self

    def _generate(
        self, messages: list[BaseMessage], stop: list[str] | None = None,
        run_manager: Any = None, **kwargs: Any,
    ) -> ChatResult:
        result = self.replies[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=result)])


def tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": call_id}])


def test_6206_dimensions_are_sourced_and_not_engineering_approved():
    result = KnowledgeRepository().lookup("bearing_model", "6206 的基本尺寸")
    assert result["status"] == "FOUND"
    assert result["ok"]
    record = result["results"][0]
    assert record["id"] == "skf-6206-dimensions"
    assert {f["field"]: f["value"] for f in record["facts"]} == {
        "dimensions.d_mm": 30, "dimensions.D_mm": 62, "dimensions.B_mm": 16
    }
    assert record["source"]["publisher"] == "SKF"
    assert record["source"]["url"].startswith("https://www.skf.com/")
    assert record["review_status"] == "SOURCE_DOCUMENTED_NOT_ENGINEERING_REVIEWED"
    assert "额定寿命" in record["limitations"][1]


def test_cn_c3_concept_does_not_invent_numeric_clearance():
    result = KnowledgeRepository().lookup("clearance", "6206 CN/C3 游隙有何区别？")
    assert result["status"] == "FOUND"
    record = result["results"][0]
    assert record["source"]["publisher"] == "NTN Americas"
    assert {f["value"] for f in record["facts"]} == {"CN", "C3"}
    assert all(f["unit"] is None for f in record["facts"])
    assert any("未提供" in item for item in record["limitations"])


def test_missing_or_invalid_queries_never_return_unreviewed_values():
    repo = KnowledgeRepository()
    for topic, query in (
        ("bearing_model", "6306 外形尺寸"),
        ("lubrication", "请给出润滑油黏度数值"),
        ("material", "GCr15的热膨胀系数"),
        ("fit", "6206 k6 H7的具体公差"),
    ):
        result = repo.lookup(topic, query)
        assert result["ok"]
        assert result["status"] == "NOT_FOUND"
        assert result["results"] == []
    assert repo.lookup("unknown", "6206")["status"] == "INVALID_TOPIC"
    assert repo.lookup("clearance", " ")["status"] == "INVALID_QUERY"


def test_tool_keeps_brief_revision_unchanged_and_old_tools_available(tmp_path):
    service = DesignBriefService(SQLiteDesignBriefStore(tmp_path / "brief.sqlite"))
    tools = TurnTools(
        service=service, session_id="s", message_id="turn", user_message="6206尺寸",
    ).tools()
    assert [x.name for x in tools] == [
        "update_design_brief", "get_design_status", "lookup_engineering_knowledge"
    ]
    before = service.get_brief("s")
    answer = tools[2].invoke({"topic": "bearing_model", "query": "6206尺寸"})
    after = service.get_brief("s")
    assert answer["status"] == "FOUND"
    assert before == after


def test_agent_can_lookup_and_continue_ordinary_reply(tmp_path):
    service = DesignBriefService(SQLiteDesignBriefStore(tmp_path / "brief.sqlite"))
    history = ConversationStore(tmp_path / "history.sqlite")
    model = ScriptedChatModel(replies=[
        tool_call(
            "lookup_engineering_knowledge",
            {"topic": "bearing_model", "query": "6206基本尺寸"},
            "lookup-6206",
        ),
        AIMessage(content="SKF 6206 的主要外形尺寸为30×62×16mm；尚未进行寿命校核。"),
    ])
    agent = ConversationAgent(service, history, model)
    outcome = agent.respond("s", "请查6206的尺寸，不要写入", turn_id="lookup")
    assert outcome.error_type is None
    assert len(outcome.tool_trace) == 1
    assert outcome.tool_trace[0]["name"] == "lookup_engineering_knowledge"
    assert outcome.tool_trace[0]["ok"]
    assert outcome.revision == 0
    assert "30×62×16mm" in outcome.answer


def test_agent_knowledge_then_user_write_same_turn(tmp_path):
    service = DesignBriefService(SQLiteDesignBriefStore(tmp_path / "brief.sqlite"))
    history = ConversationStore(tmp_path / "history.sqlite")
    model = ScriptedChatModel(replies=[
        tool_call(
            "lookup_engineering_knowledge",
            {"topic": "bearing_model", "query": "6206尺寸"},
            "lookup",
        ),
        tool_call(
            "update_design_brief",
            {"operation": "set", "changes": [
                {"path": "dimensions.d_mm", "value": 30, "unit": "mm",
                 "evidence_span": "内径30mm"}
            ]},
            "write",
        ),
        AIMessage(content="6206主要外形尺寸可以查到；后续还要明确实际载荷。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "我定内径30mm，请查6206尺寸", turn_id="mixed"
    )
    assert result.error_type is None
    assert result.revision == 1
    assert [x["name"] for x in result.tool_trace] == [
        "lookup_engineering_knowledge", "update_design_brief"
    ]
    assert service.get_brief("s")[0].dimensions.d_mm.value == 30
    assert "本轮实际已写入" in result.answer
