from PIL import Image
import os


def convert_to_ico(source="logo.png", dest="logo.ico"):
    if not os.path.exists(source):
        print(f"Error: {source} not found.")
        return False

    try:
        img = Image.open(source)
        # Resize if huge? Windows icons usually 256x256 max.
        # But PIL handles it. Let's just save.
        img.save(
            dest,
            format="ICO",
            sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)],
        )
        print(f"Created {dest}")
        return True
    except Exception as e:
        print(f"Error converting icon: {e}")
        return False


if __name__ == "__main__":
    convert_to_ico()
