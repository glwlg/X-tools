import urllib.request
import zipfile
import os
import shutil


def download_sdk():
    url = "https://www.voidtools.com/Everything-SDK.zip"
    zip_path = "Everything-SDK.zip"
    extract_folder = "Everything-SDK"

    print(f"Downloading {url}...")
    try:
        with urllib.request.urlopen(url) as response, open(zip_path, "wb") as out_file:
            shutil.copyfileobj(response, out_file)
    except Exception as e:
        print(f"Failed to download: {e}")
        return

    print("Extracting...")
    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(extract_folder)

    # Find DLL
    dll_name = "Everything64.dll"
    found = False
    for root, dirs, files in os.walk(extract_folder):
        if dll_name in files:
            src = os.path.join(root, dll_name)
            dst = os.path.join(os.getcwd(), dll_name)
            print(f"Found {dll_name} at {src}")
            shutil.copy2(src, dst)
            print(f"Copied to {dst}")
            found = True
            break

    if not found:
        print(f"Could not find {dll_name} in the SDK zip.")
        # List contents for debugging
        for root, dirs, files in os.walk(extract_folder):
            for file in files:
                print(os.path.join(root, file))
    else:
        # Cleanup
        try:
            os.remove(zip_path)
            shutil.rmtree(extract_folder)
            print("Cleanup done.")
        except Exception as e:
            print(f"Cleanup warning: {e}")


if __name__ == "__main__":
    download_sdk()
