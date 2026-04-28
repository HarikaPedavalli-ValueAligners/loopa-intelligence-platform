import json
import sys
import urllib.request


def fetch_json(url: str) -> dict:
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def main() -> int:
    base_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8787"
    checks = {
        "health": f"{base_url}/health",
        "summary": f"{base_url}/dashboard/summary",
        "top_niches": f"{base_url}/niches/top?limit=5",
        "runs": f"{base_url}/runs?limit=5",
    }

    for name, url in checks.items():
        payload = fetch_json(url)
        if isinstance(payload, dict) and payload.get("error"):
            raise RuntimeError(f"{name} returned error: {payload['error']}")
        print(f"OK {name}: {url}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
