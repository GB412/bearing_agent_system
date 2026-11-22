"""Server-side guard for write receipts and trusted DesignBrief summaries.

This is not a semantic verifier. It prevents an unexecuted tool write from
becoming a "saved" confirmation and avoids summaries based on past LLM claims.
"""

from __future__ import annotations

import re
from typing import Any

# Only affirmative first-person/new write statements; never infer success from text.
WRITE_CLAIM = re.compile(
    r"(?:已|已经|成功|现已|刚刚|刚才|本轮已|为你|帮你|替你).{0,10}"
    r"(?:记录|保存|写入|录入|更新|修改|设置|登记)"
    r"|(?:记录|保存|写入|录入|更新|修改|设置)(?:好了|成功|完成|到草案)"
)
SUMMARY_INTENTS = (
    "目前", "当前", "此前", "之前", "已确认", "已确定", "进度",
    "进展", "汇总", "总结", "草案", "清单", "有哪些", "还缺", "整理",
    "已经保存", "已记录",
)
SUMMARY_ANSWER = re.compile(
    r"(?:\*\*已确认\*\*|\*\*已保存\*\*|目前草案状态|"
    r"当前设计需求汇总|已确认的参数(?:如下|：|:))"
)
UNSUPPORTED_CLAIMS = re.compile(
    r"(?:已完成全部设计|需求已正式确认|RoBAS.{0,10}(?:可运行|已就绪)"
    r"|已经完成校核|CAD已生成)", re.I
)

LABELS = {
    "dimensions.d_mm": "内径 d",
    "dimensions.D_mm": "外径 D",
    "dimensions.B_mm": "宽度 B",
    "operating.inner_speed_rpm": "内圈转速",
    "operating.outer_speed_rpm": "外圈转速",
    "operating.radial_load_n": "径向载荷",
    "operating.axial_load_n": "轴向载荷",
    "operating.temperature_c": "工作温度",
    "engineering.materials.inner_ring_id": "内圈材料",
    "engineering.materials.outer_ring_id": "外圈材料",
    "engineering.materials.ball_id": "钢球材料",
    "engineering.cage.type": "保持架类型",
    "engineering.cage.material_id": "保持架材料",
    "engineering.lubrication.mode": "润滑方式",
    "engineering.lubrication.lubricant_id": "润滑剂",
    "engineering.fits.inner_ring": "内圈配合",
    "engineering.fits.outer_ring": "外圈配合",
    "engineering.clearance": "游隙",
}
VALUES = {"grease": "脂润滑", "oil": "油润滑", "other": "其他"}
UNITS = {"degC": "℃"}


def summary_intent(user_message: str, answer: str = "") -> bool:
    return any(word in user_message for word in SUMMARY_INTENTS) or bool(
        SUMMARY_ANSWER.search(answer)
    )


def needs_write_repair(
    answer: str,
    user_message: str,
    applied_paths: list[str],
) -> bool:
    """Request a single repair only for an unbacked NEW-write claim."""
    if applied_paths or summary_intent(user_message):
        return False
    return bool(WRITE_CLAIM.search(answer))


def _known_value(path: str, value: Any) -> str:
    label = LABELS.get(path, path)
    if isinstance(value, dict) and "value" in value:
        raw = value["value"]
        rendered = VALUES.get(str(raw), str(raw))
        unit = UNITS.get(value.get("unit"), value.get("unit")) or ""
        pending = "（近似/待确认）" if (
            not value.get("confirmed", False) or value.get("precision") != "exact"
        ) else ""
        return f"{label}={rendered}{unit}{pending}"
    if isinstance(value, list):
        return f"{label}：{len(value)}条已生效约束（见 /status）"
    if isinstance(value, dict):
        return f"{label}：{value.get('mode', '已设置')}（见 /status）"
    return f"{label}={value}"


def trusted_summary(status: dict[str, Any]) -> str:
    """Construct an exhaustive status from saved SQLite facts, not chat history."""
    saved: list[str] = []
    pending: list[str] = []
    for path, value in status.get("known", {}).items():
        if path == "bearing.type":
            continue
        item = _known_value(path, value)
        if isinstance(value, dict) and (
            value.get("confirmed") is False or value.get("precision") not in (None, "exact")
        ):
            pending.append(item)
        else:
            saved.append(item)
    missing = [LABELS.get(path, path) for path in status.get("missing", [])]
    result = [
        "当前 DesignBrief 草案（仅依据数据库中的实际记录）：",
        "已确认/已生效：" + ("；".join(saved) if saved else "暂无"),
        "近似/待确认：" + ("；".join(pending) if pending else "暂无"),
        "未提供：" + ("；".join(missing) if missing else "暂无"),
    ]
    if status.get("conflicts"):
        result.append("冲突：" + "；".join(status["conflicts"]))
    result.append("可以输入 /status 或 /brief 核对完整数据。")
    return "\n".join(result)


def _followup_questions(answer: str) -> str:
    """Retain only innocuous questions, not model-authored saved-field claims."""
    questions: list[str] = []
    for line in answer.splitlines():
        # A saved-value sentence and the next question may share one line.
        for clause in re.split(r"(?<=[。；;])", line):
            item = clause.strip()
            # "已记录尺寸，下一步请提供转速。" contains both a claim
            # and a useful prompt. Preserve only the prompt suffix.
            if WRITE_CLAIM.search(item):
                next_step = re.search(r"下一步|接下来", item)
                item = item[next_step.start():] if next_step else ""
            if not item or WRITE_CLAIM.search(item) or "已确认" in item:
                continue
            if not (("？" in item or "?" in item)
                    or item.startswith(("下一步", "接下来"))):
                continue
            questions.append(item)
            if len(questions) == 2:
                return "\n".join(questions)
    return "\n".join(questions)


def verified_reply(
    answer: str,
    user_message: str,
    status: dict[str, Any],
    applied_paths: list[str],
    failed_writes: list[dict[str, Any]],
) -> str:
    """A model answer cannot authorize a write or claim an unpersisted field."""
    applied_paths = list(dict.fromkeys(applied_paths))
    if failed_writes:
        names = "、".join(LABELS.get(path, path) for path in applied_paths) or "无"
        return (
            "本轮有参数更新未通过校验。实际已写入字段：" + names
            + "。未通过的字段没有保存。请用 /trace 查看拒绝原因，"
            "用 /status 核对当前数据。"
        )
    if summary_intent(user_message, answer):
        return trusted_summary(status)
    if WRITE_CLAIM.search(answer):
        if not applied_paths:
            return (
                "本轮没有成功写入新的设计参数，不能宣称已保存。"
                "请补充或确认相关信息，或输入 /status 检查已有数据。"
            )
        known = status.get("known", {})
        lines = [
            _known_value(path, known[path]) if path in known
            else f"{LABELS.get(path, path)}：已更新（详见 /status）"
            for path in applied_paths
        ]
        followup = _followup_questions(answer)
        return "本轮实际已写入：" + "；".join(lines) + "。" + (
            "\n" + followup if followup else ""
        )
    if UNSUPPORTED_CLAIMS.search(answer):
        return (
            "当前只有需求草案，尚未进行整份确认、工程校核、"
            "RoBAS 输入验证或 CAD 生成。"
        )
    return answer
