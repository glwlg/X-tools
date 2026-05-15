import difflib
import json
import re
from dataclasses import dataclass
from json import JSONDecodeError
from typing import Any


@dataclass(frozen=True)
class JsonDifference:
    kind: str
    path: str
    left: Any = None
    right: Any = None


@dataclass(frozen=True)
class JsonCompareResult:
    ok: bool
    summary: str
    differences: list[JsonDifference]
    report: str
    unified_diff: str
    left_formatted: str = ""
    right_formatted: str = ""
    error: str = ""


_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def parse_json_text(text: str, label: str = "JSON") -> Any:
    raw = str(text).strip()
    if not raw:
        raise ValueError(f"{label} 不能为空")
    try:
        return json.loads(raw)
    except JSONDecodeError as exc:
        raise ValueError(
            f"{label} 解析失败: 第 {exc.lineno} 行，第 {exc.colno} 列，{exc.msg}"
        ) from exc


def format_json_value(value: Any, *, sort_keys: bool = True) -> str:
    return json.dumps(value, indent=2, ensure_ascii=False, sort_keys=sort_keys)


def compare_json_text(
    left_text: str,
    right_text: str,
    *,
    sort_keys: bool = True,
    max_report_items: int = 500,
) -> JsonCompareResult:
    try:
        left_value = parse_json_text(left_text, "左侧 JSON")
        right_value = parse_json_text(right_text, "右侧 JSON")
    except ValueError as exc:
        return JsonCompareResult(
            ok=False,
            summary="解析失败",
            differences=[],
            report=str(exc),
            unified_diff="",
            error=str(exc),
        )

    differences = list(_compare_values(left_value, right_value, "$"))
    left_formatted = format_json_value(left_value, sort_keys=sort_keys)
    right_formatted = format_json_value(right_value, sort_keys=sort_keys)
    unified_diff = _build_unified_diff(left_formatted, right_formatted)
    report = build_difference_report(differences, max_items=max_report_items)
    summary = build_summary(differences)

    return JsonCompareResult(
        ok=True,
        summary=summary,
        differences=differences,
        report=report,
        unified_diff=unified_diff,
        left_formatted=left_formatted,
        right_formatted=right_formatted,
    )


def build_summary(differences: list[JsonDifference]) -> str:
    if not differences:
        return "两个 JSON 语义一致"

    added = sum(1 for item in differences if item.kind == "added")
    removed = sum(1 for item in differences if item.kind == "removed")
    changed = sum(1 for item in differences if item.kind == "changed")
    return f"发现 {len(differences)} 处差异：新增 {added}，删除 {removed}，变更 {changed}"


def build_difference_report(
    differences: list[JsonDifference],
    *,
    max_items: int = 500,
) -> str:
    if not differences:
        return "两个 JSON 语义一致。对象字段顺序不会被判定为差异。"

    lines = [build_summary(differences), ""]
    for diff in differences[:max_items]:
        if diff.kind == "added":
            lines.append(f"+ {diff.path}: {summarize_value(diff.right)}")
        elif diff.kind == "removed":
            lines.append(f"- {diff.path}: {summarize_value(diff.left)}")
        else:
            lines.append(
                f"~ {diff.path}: {summarize_value(diff.left)} -> {summarize_value(diff.right)}"
            )

    remaining = len(differences) - max_items
    if remaining > 0:
        lines.extend(["", f"... 还有 {remaining} 处差异未展示"])

    return "\n".join(lines)


def summarize_value(value: Any, *, limit: int = 160) -> str:
    text = json.dumps(value, ensure_ascii=False, sort_keys=True)
    if len(text) > limit:
        return text[: limit - 3] + "..."
    return text


def _build_unified_diff(left_formatted: str, right_formatted: str) -> str:
    if left_formatted == right_formatted:
        return "(规范化格式后没有行差异)"

    lines = difflib.unified_diff(
        left_formatted.splitlines(),
        right_formatted.splitlines(),
        fromfile="left.json",
        tofile="right.json",
        lineterm="",
    )
    return "\n".join(lines)


def _compare_values(left: Any, right: Any, path: str):
    if type(left) is not type(right):
        yield JsonDifference("changed", path, left, right)
        return

    if isinstance(left, dict):
        left_keys = set(left.keys())
        right_keys = set(right.keys())

        for key in sorted(left_keys - right_keys, key=str):
            yield JsonDifference("removed", _join_object_path(path, key), left[key], None)

        for key in sorted(right_keys - left_keys, key=str):
            yield JsonDifference("added", _join_object_path(path, key), None, right[key])

        for key in sorted(left_keys & right_keys, key=str):
            yield from _compare_values(
                left[key],
                right[key],
                _join_object_path(path, key),
            )
        return

    if isinstance(left, list):
        common_length = min(len(left), len(right))
        for index in range(common_length):
            yield from _compare_values(left[index], right[index], f"{path}[{index}]")

        for index in range(common_length, len(left)):
            yield JsonDifference("removed", f"{path}[{index}]", left[index], None)

        for index in range(common_length, len(right)):
            yield JsonDifference("added", f"{path}[{index}]", None, right[index])
        return

    if left != right:
        yield JsonDifference("changed", path, left, right)


def _join_object_path(path: str, key: Any) -> str:
    key_text = str(key)
    if _IDENTIFIER_RE.match(key_text):
        return f"{path}.{key_text}"
    return f"{path}[{json.dumps(key_text, ensure_ascii=False)}]"
