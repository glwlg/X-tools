from src.core.app_scanner import app_scanner
import sys


def test_scanner():
    print("Scanning apps...")
    apps = app_scanner.scan()
    print(f"Found {len(apps)} apps.")

    if len(apps) > 0:
        print(f"Sample: {apps[0]}")

    results = app_scanner.search("cmd")
    print(f"Search 'cmd': {len(results)} results")
    for r in results:
        print(f"  - {r['name']} ({r['path']})")


if __name__ == "__main__":
    try:
        test_scanner()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
