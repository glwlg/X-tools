from dataclasses import dataclass
import os
import subprocess
import tempfile

from src.platform.runtime import PLATFORM_WINDOWS, current_platform


@dataclass
class HostsWriteResult:
    success: bool
    error: str = ""


def get_hosts_path() -> str:
    if current_platform() == PLATFORM_WINDOWS:
        return r"C:\Windows\System32\drivers\etc\hosts"
    return "/etc/hosts"


def write_hosts_content(content: str) -> HostsWriteResult:
    if current_platform() != PLATFORM_WINDOWS:
        return HostsWriteResult(False, "当前平台暂未实现 Hosts 提权写入")

    hosts_path = get_hosts_path()
    temp_fd, temp_path = tempfile.mkstemp(suffix=".txt", text=True)
    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
        f.write(content)

    result_fd, result_path = tempfile.mkstemp(suffix=".res", text=True)
    os.close(result_fd)

    ps_script_fd, ps_script_path = tempfile.mkstemp(suffix=".ps1", text=True)
    with os.fdopen(ps_script_fd, "w", encoding="utf-8") as f:
        f.write(f"""$ErrorActionPreference = 'Stop'
try {{
    Copy-Item -Path '{temp_path}' -Destination '{hosts_path}' -Force
    Out-File -FilePath '{result_path}' -InputObject 'SUCCESS' -Encoding utf8
    exit 0
}} catch {{
    Out-File -FilePath '{result_path}' -InputObject $_.Exception.Message -Encoding utf8
    exit 1
}}
""")

    try:
        cmd = (
            "Start-Process powershell "
            f"-ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{ps_script_path}\"' "
            "-Verb RunAs -Wait -WindowStyle Hidden"
        )
        subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-Command",
                cmd,
            ],
            capture_output=True,
            text=True,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if os.path.exists(result_path):
            with open(result_path, "r", encoding="utf-8-sig") as rf:
                result_text = rf.read().strip()
                if "SUCCESS" in result_text:
                    return HostsWriteResult(True)
                return HostsWriteResult(False, result_text or "未知执行错误")
        return HostsWriteResult(False, "无法获取执行结果文件（可能是用户拒绝了 UAC 请求）")
    except Exception as exc:
        return HostsWriteResult(False, str(exc))
    finally:
        for path in (temp_path, result_path, ps_script_path):
            try:
                if path and os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass
