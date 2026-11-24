"""Negated write claims must not trigger a fake repair / remove useful replies."""

from __future__ import annotations

import pytest

from bearing_agent_system.reply_guard import (
    _free_text_without_new_write_claims,
    needs_write_repair,
    verified_reply,
)


@pytest.mark.parametrize("statement", [
    "我没有保存到草案，只查询了资料。",
    "尚未写入任何轴承参数。",
    "当前没有保存参数，不需要更新设计草案。",
    "未记录润滑方式，只是提供专业知识说明。",
])
def test_no_repair_on_explicit_negative_write_statement(statement):
    assert not needs_write_repair(statement, [])
    assert "保存" in _free_text_without_new_write_claims(statement) or (
        "写入" in statement or "记录" in statement
    )
    assert statement.rstrip("。") in verified_reply(
        statement, [], {"known": {}, "missing": [], "pending_confirmation": []}
    )


def test_positive_unexecuted_write_claim_still_requests_repair():
    assert needs_write_repair("已保存润滑方式脂润滑。", [])
    assert not needs_write_repair(
        "只查询知识，但没有保存到草案。", []
    )


def test_read_only_knowledge_receipt_does_not_modify_brief():
    trace = [{"name": "lookup_engineering_knowledge", "ok": True,
              "knowledge_status": "RELATED_EVIDENCE"}]
    assert not needs_write_repair("尚未写入设计参数，以下是配合的一般原则。", trace)
