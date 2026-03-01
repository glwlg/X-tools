import copy
import re


WORKFLOW_ID_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


DEFAULT_WORKFLOWS = [
    {
        "id": "clip-md5",
        "name": "剪贴板文本 -> MD5",
        "description": "读取剪贴板文本并复制其 MD5 值",
        "steps": [
            {"command": "hash {clipboard}", "pick": "MD5"},
        ],
    },
    {
        "id": "clip-url-encode",
        "name": "剪贴板文本 -> URL 编码",
        "description": "读取剪贴板文本并复制 URL 编码结果",
        "steps": [
            {"command": "url {clipboard}", "pick": "编码结果"},
        ],
    },
    {
        "id": "clip-base64-encode",
        "name": "剪贴板文本 -> Base64 编码",
        "description": "读取剪贴板文本并复制 Base64 编码结果",
        "steps": [
            {"command": "base64 {clipboard}", "pick": "编码结果"},
        ],
    },
    {
        "id": "now-timestamp",
        "name": "当前时间 -> 时间戳",
        "description": "生成当前 Unix 时间戳并复制到剪贴板",
        "steps": [
            {"command": "timestamp now", "pick": "当前时间戳"},
        ],
    },
]


def validate_workflow_id(value: str) -> bool:
    if not isinstance(value, str):
        return False
    return bool(WORKFLOW_ID_RE.fullmatch(value.strip()))


def normalize_workflows(raw) -> list[dict]:
    if not isinstance(raw, list):
        return copy.deepcopy(DEFAULT_WORKFLOWS)

    normalized = []
    seen_ids = set()

    for item in raw:
        if not isinstance(item, dict):
            continue

        raw_id = item.get("id")
        if not isinstance(raw_id, str):
            continue
        workflow_id = raw_id.strip().lower()

        raw_name = item.get("name")
        if not isinstance(raw_name, str):
            continue
        name = raw_name.strip()

        raw_description = item.get("description")
        description = (
            raw_description.strip() if isinstance(raw_description, str) else ""
        )
        steps = item.get("steps", [])

        if not validate_workflow_id(workflow_id) or not name or workflow_id in seen_ids:
            continue
        if not isinstance(steps, list) or not steps:
            continue

        clean_steps = []
        for step in steps:
            if not isinstance(step, dict):
                continue

            raw_command = step.get("command")
            if not isinstance(raw_command, str):
                continue
            command = raw_command.strip()

            raw_pick = step.get("pick")
            pick = raw_pick.strip() if isinstance(raw_pick, str) else ""
            if not command:
                continue

            clean_step = {"command": command}
            if pick:
                clean_step["pick"] = pick
            clean_steps.append(clean_step)

        if not clean_steps:
            continue

        normalized.append(
            {
                "id": workflow_id,
                "name": name,
                "description": description,
                "steps": clean_steps,
            }
        )
        seen_ids.add(workflow_id)

    return normalized or copy.deepcopy(DEFAULT_WORKFLOWS)
