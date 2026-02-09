import PyInstaller.__main__
import os

# Ensure we are in the script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Clean previous build
if os.path.exists("dist/x-tools"):
    import shutil

    try:
        shutil.rmtree("dist/x-tools")
    except:
        pass

if os.path.exists("build/x-tools"):
    import shutil

    try:
        shutil.rmtree("build/x-tools")
    except:
        pass

icon_path = os.path.abspath("logo.ico")
if not os.path.exists(icon_path):
    print(f"Error: Icon not found at {icon_path}")
    exit(1)

PyInstaller.__main__.run(
    [
        "main.py",
        "--name=x-tools",
        "--onedir",
        "--windowed",
        "--add-data=logo.png;.",
        "--add-binary=Everything64.dll;.",
        "--clean",
        "--noconfirm",
        f"--icon={icon_path}",
    ]
)

# Also copy logo.ico to the dist folder so the installer can use it directly
shutil.copy2("logo.ico", "dist/x-tools/logo.ico")
