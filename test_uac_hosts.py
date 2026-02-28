import tempfile, os, subprocess

HOSTS_PATH = os.path.expandvars(r"%SystemRoot%\System32\drivers\etc\hosts")

final_content = "127.0.0.1 test.local"
temp_fd, temp_path = tempfile.mkstemp(suffix=".txt", text=True)
with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
    f.write(final_content)

ps_script_fd, ps_script_path = tempfile.mkstemp(suffix=".ps1", text=True)
with os.fdopen(ps_script_fd, "w", encoding="utf-8") as f:
    f.write(f"""$ErrorActionPreference = 'Stop'
try {{
    Copy-Item -Path '{temp_path}' -Destination '{HOSTS_PATH}' -Force
    "Copied {temp_path} to {HOSTS_PATH}" | Out-File -FilePath "$env:TEMP\\test_hosts.log"
    exit 0
}} catch {{
    Write-Error $_.Exception.Message
    $_.Exception.Message | Out-File -FilePath "$env:TEMP\\test_hosts.log"
    exit 1
}}
""")

print("Running elevated script...")
result = subprocess.run(
    [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-Command",
        f"Start-Process powershell -ArgumentList '-NoProfile -ExecutionPolicy Bypass -File \"{ps_script_path}\"' -Verb RunAs -Wait -PassThru -WindowStyle Hidden | ForEach-Object {{ exit $_.ExitCode }}",
    ],
    capture_output=True,
    text=True,
    creationflags=subprocess.CREATE_NO_WINDOW,
)
print(f"R: {result.returncode}, OUT: {result.stdout}, ERR: {result.stderr}")

# Check if changed
with open(HOSTS_PATH, "r") as f:
    print("Hosts contain test.local?", "test.local" in f.read())
