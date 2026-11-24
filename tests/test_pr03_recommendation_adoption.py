"""PR-03: explicit CN choices, scoped recommendations, trusted adoption."""
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
from bearing_agent_system.models import TrustedContext, UpdateBatch


@pytest.fixture
def environment(tmp_path):
    db = tmp_path / "brief.sqlite3"
    return DesignBriefService(SQLiteDesignBriefStore(db)), ConversationStore(db)


def tool(service, message, *, session="s", turn_id="turn"):
    return TurnTools(service=service, session_id=session, message_id=turn_id,
                     user_message=message)


def propose_fits(turn):
    return turn.tools()[0].invoke({
        "operation": "propose", "changes": [
            {"path": "engineering.fits.inner_ring", "value": "k6"},
            {"path": "engineering.fits.outer_ring", "value": "H7"},
        ],
    })


@pytest.mark.parametrize("message", ["游隙组别CN", "游隙组别确认CN", "游隙等级为CN"])
def test_clearance_explicit_user_choice_is_saved(environment, message):
    service, _ = environment
    batch = UpdateBatch.model_validate({
        "operation": "set",
        "changes": [{"path": "engineering.clearance.group", "value": "CN",
                     "evidence_span": message}],
    })
    out = service.update_design_brief(
        "s", batch, TrustedContext(message_id="c1", user_message=message)
    )
    assert not out.rejected_changes
    assert service.get_brief("s")[0].engineering.clearance.group.value == "CN"


@pytest.mark.parametrize("message", [
    "游隙组别CN是什么意思？", "CN和C3哪个更好？",
    "不要采用CN", "我还没确定游隙，想了解CN",
])
def test_questions_and_negations_cannot_fake_cn_confirmation(environment, message):
    service, _ = environment
    batch = UpdateBatch.model_validate({
        "operation": "set",
        "changes": [{"path": "engineering.clearance.group", "value": "CN",
                     "evidence_span": message}],
    })
    out = service.update_design_brief(
        "s", batch, TrustedContext(message_id="c1", user_message=message)
    )
    assert out.rejected_changes
    assert service.get_brief("s")[0].engineering.clearance.group is None


def test_propose_does_not_write_and_later_approval_uses_stored_values(environment):
    service, _ = environment
    first = tool(service, "请推荐配合，但先不要保存", turn_id="t1")
    proposed = propose_fits(first)
    assert proposed["ok"]
    assert proposed["status"] == "PROPOSED"
    assert proposed["review_status"] == "UNVERIFIED"
    assert service.get_brief("s")[1] == 0
    assert service.get_brief("s")[0].engineering.fits.inner_ring is None
    proposal_id = proposed["proposal_id"]

    # New process/tool instance: no model re-supplies either recommended value.
    second = tool(service, "就按你推荐的来", turn_id="t2")
    adopted = second.tools()[0].invoke({
        "operation": "accept", "proposal_id": proposal_id,
        "approval_evidence_span": "就按你推荐的来",
    })
    assert adopted["ok"] and adopted["revision"] == 1
    assert adopted["decision_method"] == "user_accepted"
    brief, rev = service.get_brief("s")
    assert rev == 1
    assert brief.engineering.fits.inner_ring.value == "k6"
    assert brief.engineering.fits.outer_ring.value == "H7"
    assert brief.engineering.fits.inner_ring.source.ref == proposal_id
    assert brief.engineering.fits.inner_ring.source.kind == "derived"
    assert brief.engineering.fits.outer_ring.evidence_status == "UNVERIFIED"
    assert "未经工程校核" in brief.engineering.fits.outer_ring.note
    assert service.store.pending_recommendation("s") is None

    replay = tool(service, "就按你推荐的来", turn_id="t3")
    again = replay.tools()[0].invoke({
        "operation": "accept", "proposal_id": proposal_id,
        "approval_evidence_span": "就按你推荐的来",
    })
    assert not again["ok"]
    assert service.get_brief("s")[1] == 1


@pytest.mark.parametrize("reply", [
    "不可以", "我不同意", "如果按你推荐的来会怎样？", "先别采用",
    "你刚才推荐的方案是什么意思？", "我可以再考虑一下",
])
def test_approval_question_or_refusal_does_not_commit(environment, reply):
    service, _ = environment
    proposal_id = propose_fits(tool(service, "请推荐", turn_id="t1"))["proposal_id"]
    attempt = tool(service, reply, turn_id="t2").tools()[0].invoke({
        "operation": "accept", "proposal_id": proposal_id,
        "approval_evidence_span": reply,
    })
    assert not attempt["ok"]
    assert service.get_brief("s")[0].engineering.fits.inner_ring is None


def test_recommendation_cannot_cross_sessions_or_survive_revision_change(environment):
    service, _ = environment
    proposal_id = propose_fits(tool(service, "请推荐", turn_id="t1"))["proposal_id"]
    cross = tool(service, "就按你推荐的来", session="another", turn_id="t2")
    result = cross.tools()[0].invoke({
        "operation": "accept", "proposal_id": proposal_id,
        "approval_evidence_span": "就按你推荐的来",
    })
    assert not result["ok"]
    change = tool(service, "轴承宽度10mm", turn_id="t3").tools()[0].invoke({
        "operation": "set",
        "changes": [{"path": "dimensions.B_mm", "value": 10, "unit": "mm",
                     "evidence_span": "宽度10mm"}],
    })
    assert change["ok"]
    stale = tool(service, "就按你推荐的来", turn_id="t4").tools()[0].invoke({
        "operation": "accept", "proposal_id": proposal_id,
        "approval_evidence_span": "就按你推荐的来",
    })
    assert not stale["ok"]
    assert service.get_brief("s")[0].engineering.fits.inner_ring is None


def test_proposal_cannot_lock_numerical_design_or_write_unknown_paths(environment):
    service, _ = environment
    t = tool(service, "给我推荐")
    for bad in [
        {"path": "dimensions.d_mm", "value": "25"},
        {"path": "optimization_slots.Z", "value": "12"},
        {"path": "engineering.clearance.group", "value": "C8"},
        {"path": "engineering.fits.inner_ring", "value": 12},
    ]:
        result = t.tools()[0].invoke({"operation": "propose", "changes": [bad]})
        assert not result["ok"]
    assert service.store.pending_recommendation("s") is None
    assert service.get_brief("s")[1] == 0


class FitKnowledge:
    _records = ({"id": "fit-background", "topic": "fit"},)

    def search(self, query, catalog_query=None):
        return {
            "ok": True, "status": "RELATED_EVIDENCE",
            "query_type": "concept", "retrieval_method": "lexical_fallback",
            "results": [{"id": "fit-background", "source": {
                "url": "https://example.org/fit",
            }}],
        }


def test_delegate_requires_matching_lookup_and_current_turn_scope(environment):
    service, _ = environment
    text = "配合你来推荐和指定吧"
    t = tool(service, text, turn_id="delegate")
    proposed = propose_fits(t)
    fail = t.tools()[0].invoke({
        "operation": "delegate", "proposal_id": proposed["proposal_id"],
        "approval_evidence_span": text,
    })
    assert not fail["ok"]
    assert service.get_brief("s")[1] == 0

    t2 = tool(service, text, session="other", turn_id="d2")
    t2.knowledge = FitKnowledge()
    lookup = t2.tools()[2].invoke({"query": "轴承套圈与轴的配合"})
    assert lookup["status"] == "RELATED_EVIDENCE"
    proposed = propose_fits(t2)
    assert proposed["knowledge_ids"] == ["fit-background"]
    accepted = t2.tools()[0].invoke({
        "operation": "delegate", "proposal_id": proposed["proposal_id"],
        "approval_evidence_span": text,
    })
    assert accepted["ok"]
    assert accepted["decision_method"] == "agent_delegated"
    assert "授权Agent" in service.get_brief("other")[0].engineering.fits.inner_ring.note

    t3 = tool(service, "润滑你来决定", session="third", turn_id="d3")
    t3.knowledge = FitKnowledge()
    t3.tools()[2].invoke({"query": "配合"})
    proposed = propose_fits(t3)
    denied = t3.tools()[0].invoke({
        "operation": "delegate", "proposal_id": proposed["proposal_id"],
        "approval_evidence_span": "润滑你来决定",
    })
    assert not denied["ok"]
    assert service.get_brief("third")[1] == 0

    # Asking for advice is not delegated permission to save a selection.
    t4 = tool(service, "配合帮我推荐一下", session="advice", turn_id="d4")
    t4.knowledge = FitKnowledge()
    t4.tools()[2].invoke({"query": "轴承配合"})
    proposed = propose_fits(t4)
    only_advice = t4.tools()[0].invoke({
        "operation": "delegate", "proposal_id": proposed["proposal_id"],
        "approval_evidence_span": "配合帮我推荐一下",
    })
    assert not only_advice["ok"]
    assert service.get_brief("advice")[1] == 0


class ScriptedModel(BaseChatModel):
    replies: list[AIMessage]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "recommendation-tool-model"

    def bind_tools(self, tools: Any, **kwargs: Any):
        return self

    def _generate(self, messages: list[BaseMessage], stop=None,
                  run_manager=None, **kwargs):
        answer = self.replies[self.calls]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=answer)])


def call(operation, **kwargs):
    return AIMessage(content="", tool_calls=[{
        "name": "update_design_brief",
        "args": {"operation": operation, **kwargs},
        "id": "id-" + operation,
    }])


def test_real_langgraph_loop_proposes_then_adopts_next_user_turn(environment):
    service, history = environment
    first = ConversationAgent(service, history, ScriptedModel(replies=[
        call("propose", changes=[
            {"path": "engineering.lubrication.mode", "value": "grease"},
        ]),
        AIMessage(content="建议考虑脂润滑。这只是初步建议，尚未工程校核。"),
    ])).respond("s", "帮我推荐润滑方式，暂时不要确定", turn_id="first")
    assert first.error_type is None
    assert first.revision == 0
    proposal_id = service.store.pending_recommendation("s")["proposal_id"]
    assert first.tool_trace[0]["proposal_id"] == proposal_id

    second = ConversationAgent(service, history, ScriptedModel(replies=[
        call("accept", proposal_id=proposal_id,
             approval_evidence_span="就按你推荐的来"),
        AIMessage(content="后续还要核对工作温度和润滑剂。"),
    ])).respond("s", "就按你推荐的来", turn_id="second")
    assert second.error_type is None
    assert second.revision == 1
    assert second.tool_trace[0]["decision_method"] == "user_accepted"
    assert service.get_brief("s")[0].engineering.lubrication.mode.value == "grease"
    assert "润滑方式=脂润滑" in second.answer
