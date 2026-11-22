"""Deterministic, field-level receipts for a single conversation turn.

Does not infer the user's intent or classify questions. The LLM owns the
natural-language conversation; trusted tool results own storage claims.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


# Narrow fallback ONLY for LLM-authored new-write claims, not intent routing.
# The strongest guarantee remains the tool receipt, not natural-language regex.
WRITE_CLAIM = re.compile(
    r"(?:已|已经|成功|现已|刚刚|刚才|本轮已|为你|帮你|替你).{0,10}"
    r"(?:记录|保存|写入|录入|更新|修改|设置|登记)"
    r"|(?:记录|保存|写入|录入|更新|修改|设置)(?:好了|成功|完成|到草案)"
)
PAST_CONTEXT = ("此前", "以前", "之前", "上轮", "上次", "历史")
STATUS_MARKER = "[[DESIGN_STATUS]]"
# Only explicit model claims of confirmed status; not a user-intent classifier.
CONFIRMED_LINE = re.compile(r"^\s*(?:\*\*)?已确认(?:\*\*)?(?:[：:]|.{0,12}(?:参数|工作温度))")
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


@dataclass(frozen=True)
class WriteOutcome:
    applied: tuple[str, ...]
    unresolved: tuple[tuple[str, str], ...]
    unknown_failures: tuple[str, ...]


def reconcile_writes(trace: list[dict[str, Any]]) -> WriteOutcome:
    """Resolve failed attempts by *later* successful writes of the same path.

    A rejected batch is atomic, so all attempted paths remain unresolved until
    a subsequent successful call actually applies or proves a value exists.
    Read-only tool errors are not counted as write failures.
    """
    applied: list[str] = []
    unresolved: dict[str, str] = {}
    unknown: list[str] = []
    for entry in trace:
        if entry.get("name") != "update_design_brief":
            continue
        if entry.get("ok"):
            for path in entry.get("applied_changes", []):
                if path not in applied:
                    applied.append(path)
                unresolved.pop(path, None)
            continue
        rejected = {
            item.get("path"): item.get("reason", "未通过校验")
            for item in entry.get("rejected_changes", [])
            if item.get("path")
        }
        paths = list(dict.fromkeys(
            entry.get("attempted_paths", []) or list(rejected)
        ))
        if paths:
            for path in paths:
                unresolved[path] = rejected.get(path, "同批更新未通过校验")
        else:
            unknown.append(entry.get("error") or "未识别的工具更新错误")
    return WriteOutcome(tuple(applied), tuple(unresolved.items()), tuple(unknown))


def needs_write_repair(answer: str, trace: list[dict[str, Any]]) -> bool:
    """One bounded retry only when the model claims an unexecuted NEW write.

    This lexical detector is a limited fallback, not an intent classifier.
    Tool use is never manufactured based on these words.
    """
    if any(t.get("name") == "update_design_brief" for t in trace):
        return False
    if any(t.get("name") == "get_design_status" for t in trace):
        return False
    return bool(WRITE_CLAIM.search(answer)) and not any(
        marker in answer for marker in PAST_CONTEXT
    )


def format_field(path: str, value: Any) -> str:
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
        return f"{label}：{len(value)}条约束（见 /status）"
    if isinstance(value, dict):
        return f"{label}：{value.get('mode', '已设置')}（见 /status）"
    return f"{label}={value}"


def trusted_summary(status: dict[str, Any]) -> str:
    """Explicit, optional view; calling this never depends on keywords."""
    confirmed: list[str] = []
    pending: list[str] = []
    for path, value in status.get("known", {}).items():
        if path == "bearing.type":
            continue
        item = format_field(path, value)
        if isinstance(value, dict) and (
            value.get("confirmed") is False or value.get("precision") not in (None, "exact")
        ):
            pending.append(item)
        else:
            confirmed.append(item)
    missing = [LABELS.get(path, path) for path in status.get("missing", [])]
    return "\n".join([
        "当前 DesignBrief 草案（仅依据实际存储）：",
        "已确认/已生效：" + ("；".join(confirmed) if confirmed else "暂无"),
        "近似/待确认：" + ("；".join(pending) if pending else "暂无"),
        "未提供：" + ("；".join(missing) if missing else "暂无"),
    ])


def _free_text_without_new_write_claims(answer: str) -> str:
    """Remove only model-authored commit claims; preserve engineering prose.

    The system displays a separate verified receipt. Do not let a second,
    unverified model sentence claim to have saved additional fields.
    """
    if not WRITE_CLAIM.search(answer):
        return answer.strip()
    clean: list[str] = []
    for line in answer.splitlines():
        parts = re.split(r"([，,。；;])", line)
        retained: list[str] = []
        for i in range(0, len(parts), 2):
            phrase = parts[i]
            delimiter = parts[i + 1] if i + 1 < len(parts) else ""
            if WRITE_CLAIM.search(phrase) and not any(
                mark in phrase for mark in PAST_CONTEXT
            ):
                continue
            retained.append(phrase + delimiter)
        clean.append("".join(retained).strip(" ，,；;"))
    return "\n".join(line for line in clean if line).strip()


def verified_reply(
    answer: str,
    trace: list[dict[str, Any]],
    status: dict[str, Any],
) -> str:
    """Compose server-owned receipt + model's explanation; never route intent."""
    result = reconcile_writes(trace)
    lines: list[str] = []
    known = status.get("known", {})
    if result.applied:
        rendered = [
            format_field(path, known[path]) if path in known
            else f"{LABELS.get(path, path)}：已更改（详情见 /status）"
            for path in result.applied
        ]
        lines.append("本轮实际已写入：" + "；".join(rendered) + "。")
    if result.unresolved:
        items = [
            f"{LABELS.get(path, path)}（{reason}）"
            for path, reason in result.unresolved
        ]
        lines.append("本轮仍未保存：" + "；".join(items) + "。可用 /trace 查看详情。")
    if result.unknown_failures:
        lines.append("还有无法确定字段的更新失败，请用 /trace 查看详情。")
    # Unresolved writes are reported from receipts only. A rejected model
    # attempt must never turn into a claimed design change in free text.
    if result.unresolved or result.unknown_failures:
        return "\n".join(lines)
    if UNSUPPORTED_CLAIMS.search(answer):
        answer = "当前仅建立需求草案，尚未进行工程校核、RoBAS 验证或 CAD 生成。"
    natural = _free_text_without_new_write_claims(answer)
    # Explicit structured status request from the model: render actual SQLite
    # status without inferring intent from the user's Chinese vocabulary.
    if STATUS_MARKER in natural:
        natural = natural.replace(STATUS_MARKER, trusted_summary(status))
    # Narrow fallback for unsupported *confirmed* declarations in free text.
    # Replace only the assertion line, never an unrelated engineering analysis.
    paragraphs = []
    for line in natural.splitlines():
        if CONFIRMED_LINE.search(line):
            paragraphs.append(trusted_summary(status))
        else:
            paragraphs.append(line)
    natural = "\n".join(paragraphs).strip()
    if not natural and not lines:
        return "本轮没有成功写入新的参数。请澄清需求或通过 /status 核对已有数据。"
    return "\n".join([*lines, natural] if natural else lines)
