import PyInstaller.__main__
import os
import shutil

# Ensure we are in the script directory
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# Clean previous build
if os.path.exists("dist/x-tools"):
    try:
        shutil.rmtree("dist/x-tools")
    except Exception as e:
        print(f"Warning: Could not clean dist folder: {e}")

if os.path.exists("build/x-tools"):
    try:
        shutil.rmtree("build/x-tools")
    except Exception as e:
        print(f"Warning: Could not clean build folder: {e}")

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
        "--add-data=src/ui/check.svg;src/ui",
        "--add-data=src/plugins;src/plugins",
        "--add-binary=Everything64.dll;.",
        # --- Hidden imports for dynamically-loaded plugins and their deps ---
        # UI modules imported by plugins (not traceable via static analysis)
        "--hidden-import=src.ui.hosts_window",
        "--hidden-import=src.ui.screenshot_overlay",
        "--hidden-import=src.ui.pinned_image_window",
        # Plugin files themselves (loaded via importlib at runtime)
        "--hidden-import=src.plugins.hosts_tool",
        "--hidden-import=src.plugins.qr_tool",
        "--hidden-import=src.plugins.hash_tool",
        "--hidden-import=src.plugins.json_tool",
        "--hidden-import=src.plugins.url_tool",
        "--hidden-import=src.plugins.uuid_tool",
        # Third-party libs used by new plugins/UI
        "--hidden-import=qrcode",
        "--hidden-import=cv2",
        "--hidden-import=rapidocr_onnxruntime",
        "--collect-all=rapidocr_onnxruntime",
        "--clean",
        "--noconfirm",
        f"--icon={icon_path}",
    ]
)

# Also copy logo.ico to the dist folder so the installer can use it directly
shutil.copy2("logo.ico", "dist/x-tools/logo.ico")
