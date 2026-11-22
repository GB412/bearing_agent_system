"""PR-02 offline tests: real LangGraph tool loop with a scripted model, no API key."""

from __future__ import annotations

from typing import Any

import pytest
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from bearing_agent_system import DesignBriefService, SQLiteDesignBriefStore
from bearing_agent_system.agent_tools import TurnTools
from bearing_agent_system.parameter_catalog import FIELDS
from bearing_agent_system.conversation import ConversationAgent
from bearing_agent_system.conversation_store import ConversationStore
from bearing_agent_system.llm_client import make_deepseek_model
from bearing_agent_system.models import DesignBrief, ParameterValue, Source
from bearing_agent_system.reply_guard import reconcile_writes, trusted_summary
from examples.pr02_live_eval import grade


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
    assert "本轮仍未保存" in result.answer
    assert "已把球数固定" not in result.answer
    assert service.get_brief("design-1")[0].optimization_slots.Z.mode == "optimize"


def test_no_tool_call_may_not_claim_fresh_write(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content="已经保存轴承尺寸。"),
        AIMessage(content="抱歉，尚未写入，请确认尺寸所属字段。"),
    ])
    agent = ConversationAgent(service, history, model)
    result = agent.respond("design-1", "我的轴承尺寸是25×52×15mm", turn_id="no-write")
    assert "尚未写入" in result.answer
    assert model.calls == 2  # exactly one correction, no infinite loop
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
    assert "本轮仍未保存" in result.answer
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


def test_live_grader_checks_exact_values_and_approximate_status():
    brief = DesignBrief()
    brief.dimensions.d_mm = ParameterValue(
        value=25, unit="mm", confirmed=True, source=Source(kind="user", message_id="m")
    )
    brief.operating.temperature_c = ParameterValue(
        value=60, unit="degC", precision="approximate", confirmed=False,
        source=Source(kind="user", message_id="m"),
    )
    assert grade(brief, {"id": "ok", "expected": {"dimensions.d_mm": 25},
                         "pending": ["operating.temperature_c"]}) == []
    assert grade(brief, {"id": "wrong", "expected": {"dimensions.d_mm": 30}})
    brief.operating.temperature_c.confirmed = True
    assert grade(brief, {"id": "bad-confirmation",
                         "pending": ["operating.temperature_c"]})


def test_read_only_progress_question_can_report_past_saved_values(environment):
    service, history = environment
    prior = TurnTools(
        service=service, session_id="s", message_id="earlier",
        user_message="内径25mm",
    ).tools()[0].invoke({"operation": "set", "changes": [
        param("dimensions.d_mm", 25, "内径25mm", "mm")
    ]})
    assert prior["ok"]
    model = ScriptedChatModel(replies=[AIMessage(
        content="此前已经保存了内径25mm，目前还缺转速。"
    )])
    agent = ConversationAgent(service, history, model)
    result = agent.respond("s", "目前已经保存哪些参数？", turn_id="progress")
    assert "此前已经保存了内径25mm" in result.answer
    assert result.tool_trace == []


def test_repair_runs_same_agent_then_saves_grease(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content="已记录：润滑方式是脂润滑。"),
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "grease", "润滑方式：脂润滑")
        ]}, "repair-grease"),
        AIMessage(content="已记录润滑方式为脂润滑。下一步想确定润滑剂牌号吗？"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "润滑方式：脂润滑", turn_id="grease"
    )
    assert result.error_type is None
    assert model.calls == 3
    assert result.revision == 1
    assert len(result.tool_trace) == 1 and result.tool_trace[0]["ok"]
    saved = service.get_brief("s")[0].engineering.lubrication.mode
    assert saved.value == "grease"
    assert "本轮实际已写入" in result.answer
    assert "脂润滑" in result.answer
    assert len(history.history("s")) == 2  # no internal correction persisted


def test_repair_only_once_when_model_keeps_claiming_success(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content="已保存润滑方式。"),
        AIMessage(content="已经记录脂润滑。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "润滑方式：脂润滑", turn_id="twice"
    )
    assert result.error_type is None
    assert model.calls == 2
    assert result.tool_trace == []
    assert "没有成功写入" in result.answer
    assert service.get_brief("s")[1] == 0


def test_repair_failed_write_never_confirms_parameter(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content="已记录脂润滑。"),
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "grease", "油润滑")
        ]}, "bad-evidence"),
        AIMessage(content="成功记录润滑方式为脂润滑。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "润滑方式：脂润滑", turn_id="fail"
    )
    assert model.calls == 3
    assert result.tool_trace[0]["ok"] is False
    assert "本轮仍未保存" in result.answer
    assert service.get_brief("s")[0].engineering.lubrication.mode is None


def test_first_tool_failure_does_not_trigger_unbounded_repair(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("dimensions.D_mm", 52, "外径不超过52mm", "mm")
        ]}, "wrong-bound"),
        AIMessage(content="已记录外径52mm。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "外径不超过52mm", turn_id="reject"
    )
    assert model.calls == 2
    assert len(result.tool_trace) == 1
    assert "本轮仍未保存" in result.answer


def test_partial_write_receipt_overrides_unsaved_claims(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "grease", "脂润滑")
        ]}, "only-grease"),
        AIMessage(content="已记录：脂润滑，并已保存内外圈和钢球GCr15。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "脂润滑，材料GCr15", turn_id="partial"
    )
    assert model.calls == 2
    assert result.revision == 1
    assert "润滑方式=脂润滑" in result.answer
    assert "GCr15" not in result.answer
    assert service.get_brief("s")[0].engineering.materials.ball_id is None


def test_trusted_state_view_ignores_unwritten_chat_history(environment):
    service, history = environment
    history.begin_turn("s", "old", "内外圈和钢球GCr15")
    history.finish_turn("s", "old", "已记录内外圈、钢球GCr15", [])
    history.begin_turn("s", "old2", "润滑方式脂润滑")
    history.finish_turn("s", "old2", "已记录脂润滑", [])
    view = trusted_summary(service.get_design_status("s").model_dump(mode="json"))
    assert "GCr15" not in view
    assert "脂润滑" not in view
    assert "内圈材料" in view
    assert "未提供" in view


def test_repair_does_not_start_for_explanation_question(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content="径向游隙是套圈间允许的径向相对位移。")
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "什么是径向游隙？", turn_id="explain"
    )
    assert model.calls == 1
    assert result.tool_trace == []


def test_summary_separates_approximate_value_from_confirmed(environment):
    service, history = environment
    from bearing_agent_system.models import TrustedContext, UpdateBatch

    change = UpdateBatch.model_validate({
        "operation": "set",
        "changes": [{
            "path": "operating.temperature_c", "value": 40,
            "unit": "℃", "precision": "approximate",
            "evidence_span": "约40℃"
        }],
    })
    service.update_design_brief("s", change, TrustedContext(
        message_id="temp", user_message="约40℃"
    ))
    view = trusted_summary(service.get_design_status("s").model_dump(mode="json"))
    assert "近似/待确认" in view
    assert "工作温度=40.0℃" in view
    model = ScriptedChatModel(replies=[
        AIMessage(content="温度只有近似值，尚未确认，具体值可在 /status 查看。")
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "目前确定了什么？", turn_id="temp-summary"
    )
    assert result.error_type is None
    assert "尚未确认" in result.answer


def test_current_preference_is_not_mistaken_for_status_question(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content="已记录当前润滑方式为脂润滑。"),
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "grease", "润滑方式选脂润滑")
        ]}, "current-grease"),
        AIMessage(content="已记录脂润滑。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "目前润滑方式选脂润滑", turn_id="current"
    )
    assert model.calls == 3
    assert result.error_type is None
    assert result.tool_trace[0]["ok"]
    assert "润滑方式=脂润滑" in result.answer
    assert service.get_brief("s")[0].engineering.lubrication.mode.value == "grease"



def test_cage_analysis_not_overwritten_by_summary_guard(environment):
    service, history = environment
    user_text = (
        "保持架类型我不太清楚。你能根据目前工况分析冲压钢和尼龙保持架吗？"
        "请不要把建议当作我已经确认的参数。"
    )
    analysis = (
        "可以先比较：冲压钢保持架成本和制造成熟度通常更有优势；"
        "聚合物保持架要核对材料、工作温度和润滑条件。"
        "目前没有足够依据确定具体选型，建议先确定润滑方式。"
    )
    model = ScriptedChatModel(replies=[AIMessage(content=analysis)])
    result = ConversationAgent(service, history, model).respond(
        "s", user_text, turn_id="cage-analysis"
    )
    assert result.error_type is None
    assert result.answer == analysis
    assert model.calls == 1
    assert result.tool_trace == []
    assert result.revision == 0
    assert service.get_brief("s")[0].engineering.cage.type is None


def test_oil_invalid_enum_then_success_is_not_reported_as_failure(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "油润滑", "油润滑")
        ]}, "wrong-enum"),
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "oil", "油润滑")
        ]}, "right-enum"),
        AIMessage(content="润滑剂牌号还没有确定，下一步可以考虑油的种类。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "油润滑", turn_id="oil"
    )
    assert result.error_type is None
    assert result.revision == 1
    assert len(result.tool_trace) == 2
    assert not result.tool_trace[0]["ok"]
    assert result.tool_trace[1]["ok"]
    assert result.tool_trace[0]["attempted_paths"] == ["engineering.lubrication.mode"]
    assert "本轮实际已写入：润滑方式=油润滑" in result.answer
    assert "本轮仍未保存" not in result.answer
    assert "润滑剂牌号还没有确定" in result.answer
    assert model.calls == 3
    assert service.get_brief("s")[0].engineering.lubrication.mode.value == "oil"


def test_partial_batch_failed_then_partial_correction_reports_remaining(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "油润滑", "油润滑"),
            param("engineering.materials.ball_id", "GCr15", "钢球采用GCr15")
        ]}, "bad-batch"),
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "oil", "油润滑")
        ]}, "oil-only"),
        AIMessage(content="关于钢球材料仍需要澄清，但润滑油类型可以后续确定。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "油润滑；钢球采用GCr15", turn_id="partial-repair"
    )
    assert result.revision == 1
    assert "本轮实际已写入：润滑方式=油润滑" in result.answer
    assert "本轮仍未保存：钢球材料" in result.answer
    # A failed write still reports trusted receipts, while preserving
    # independent guidance that does not claim the field was saved.
    assert "关于钢球材料仍需要澄清" in result.answer
    assert service.get_brief("s")[0].engineering.materials.ball_id is None
    assert reconcile_writes(result.tool_trace).unresolved[0][0] == (
        "engineering.materials.ball_id"
    )


def test_success_then_later_rejection_is_not_hidden(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "oil", "油润滑")
        ]}, "initial"),
        action("update_design_brief", {"operation": "replace", "changes": [
            param("engineering.lubrication.mode", "invalid", "油润滑")
        ]}, "bad-replacement"),
        AIMessage(content="油润滑已经讨论过，请继续说明润滑剂需求。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "油润滑", turn_id="after-success"
    )
    assert result.revision == 1
    assert "本轮实际已写入：润滑方式=油润滑" in result.answer
    assert "本轮仍未保存：润滑方式" in result.answer
    assert service.get_brief("s")[0].engineering.lubrication.mode.value == "oil"


def test_analysis_after_write_preserved_without_unverified_claims(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("engineering.lubrication.mode", "grease", "脂润滑")
        ]}, "grease"),
        AIMessage(content=(
            "已记录脂润滑，工况分析可以先关注润滑脂稠度和供脂条件。"
            "后面仍要考虑温度和密封设计。"
        )),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "脂润滑", turn_id="analysis-and-write"
    )
    assert "本轮实际已写入：润滑方式=脂润滑" in result.answer
    assert "工况分析可以先关注润滑脂稠度" in result.answer
    assert "后面仍要考虑温度和密封设计" in result.answer


def test_read_only_status_does_not_trigger_write_repair(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("get_design_status", {}, "read"),
        AIMessage(content="以前已经保存的字段可通过 /status 查看。"),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "帮我看看目前草案的状态", turn_id="read-only"
    )
    assert model.calls == 2
    assert len(result.tool_trace) == 1
    assert result.tool_trace[0]["name"] == "get_design_status"
    assert "以前已经保存" in result.answer


def test_plain_question_with_summary_words_stays_natural(environment):
    service, history = environment
    question = "目前我想知道保持架的材料选择，是否已经确认很重要？"
    model = ScriptedChatModel(replies=[
        AIMessage(content="保持架材料的选择应考虑温度、润滑和机械条件，先不确定也可以。")
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", question, turn_id="preserve-explanation"
    )
    assert model.calls == 1
    assert "温度、润滑和机械条件" in result.answer
    assert "当前 DesignBrief 草案" not in result.answer



def test_explicit_status_marker_preserves_explanation_and_uses_db(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content=(
            "保持架选型时要考虑实际温升和润滑条件。\n"
            "[[DESIGN_STATUS]]\n"
            "如需分析冲压钢与尼龙保持架，也可以继续讨论。"
        )),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "请说明当前设计状态并简要分析保持架", turn_id="both"
    )
    assert model.calls == 1
    assert result.error_type is None
    assert "[[DESIGN_STATUS]]" not in result.answer
    assert "当前 DesignBrief 草案" in result.answer
    assert "保持架选型时要考虑实际温升" in result.answer
    assert "如需分析冲压钢与尼龙保持架" in result.answer
    assert "内圈材料" in result.answer


def test_unverified_confirmed_list_only_replaces_that_line(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        AIMessage(content=(
            "材料选择建议先考虑工作温度与润滑。\n"
            "**已确认**：所有钢球GCr15（其实没有写入）。\n"
            "用户如果尚未决定材料，可以先保留为未知。"
        )),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "告诉我材料选择的考虑因素", turn_id="local-status"
    )
    assert result.error_type is None
    assert "材料选择建议先考虑工作温度与润滑" in result.answer
    assert "当前 DesignBrief 草案" in result.answer
    assert "所有钢球GCr15" not in result.answer
    assert "用户如果尚未决定材料" in result.answer


def test_write_tool_description_lists_exact_paths_and_examples(environment):
    service, _ = environment
    write_tool = TurnTools(
        service=service, session_id="s", message_id="m",
        user_message="游隙选CN",
    ).tools()[0]
    description = write_tool.description
    assert all(path in description for path in FIELDS)
    assert '"path":"requirements.geometric_bounds[]"' in description
    assert '"field":"life_hours","operator":">="' in description
    assert '"path":"engineering.clearance.group","value":"CN"' in description


def test_failed_write_keeps_independent_engineering_answer(environment):
    service, history = environment
    model = ScriptedChatModel(replies=[
        action("update_design_brief", {"operation": "set", "changes": [
            param("requirements", 62, "外径不能超过62mm")
        ]}, "invalid-requirements"),
        AIMessage(content=(
            "已经记录外径上限62mm。\\n"
            "脂润滑结构简单，维护相对方便；油润滑更便于带走热量。"
        )),
    ])
    result = ConversationAgent(service, history, model).respond(
        "s", "外径不能超过62mm，顺便分析脂润滑和油润滑。",
        turn_id="failed-but-explained",
    )
    assert result.error_type is None
    assert result.revision == 0
    assert "本轮仍未保存" in result.answer
    assert "requirements" in result.answer
    assert "已经记录外径上限" not in result.answer
    assert "脂润滑结构简单" in result.answer
    assert "油润滑更便于带走热量" in result.answer
    assert service.get_brief("s")[0].requirements.geometric_bounds == []
