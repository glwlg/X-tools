import re


PLACEHOLDER_RE = re.compile(r"\{([^{}]+)\}")


def parse_workflow_steps_text(text) -> list[dict]:
    if not isinstance(text, str):
        return []

    steps = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if "|" in line:
            command, pick = line.split("|", 1)
            command = command.strip()
            pick = pick.strip()
        else:
            command = line
            pick = ""

        payload = {"command": command}
        if pick:
            payload["pick"] = pick
        steps.append(payload)

    return steps


def format_workflow_steps_text(steps) -> str:
    if not isinstance(steps, list):
        return ""

    lines = []
    for step in steps:
        if not isinstance(step, dict):
            continue

        command = step.get("command")
        if not isinstance(command, str):
            continue
        command = command.strip()
        if not command:
            continue

        pick_value = step.get("pick")
        pick = pick_value.strip() if isinstance(pick_value, str) else ""
        lines.append(f"{command} | {pick}" if pick else command)

    return "\n".join(lines)


def extract_placeholders(text) -> list[str]:
    if not isinstance(text, str):
        return []

    found = []
    for match in PLACEHOLDER_RE.finditer(text):
        token = match.group(1).strip()
        if token:
            found.append(token)
    return found


def find_unknown_placeholders(text, allowed_vars) -> list[str]:
    allowed = {
        str(item).strip() for item in (allowed_vars or set()) if str(item).strip()
    }
    unknown = {token for token in extract_placeholders(text) if token not in allowed}
    return sorted(unknown)
