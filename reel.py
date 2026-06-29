import os
import re
import sys
import json
import requests


# Base browser headers — shared across all requests
BASE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Origin": "https://www.instagram.com",
    "Referer": "https://www.instagram.com/",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Dest": "empty",
    "Sec-Ch-Ua": '"Chromium";v="125", "Not.A/Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "X-IG-App-ID": "936619743392459",
    "X-Requested-With": "XMLHttpRequest",
}

GRAPHQL_DOC_ID = "10015901848480474"
GRAPHQL_URL = "https://www.instagram.com/graphql/query"


def _make_session() -> requests.Session:
    """
    Builds a requests Session for Instagram API calls.

    Strategy (in order):
    1. If INSTAGRAM_SESSION_ID env var is set → use it as the sessionid cookie.
       This is required on cloud/datacenter IPs (Render, AWS, etc.) because
       Instagram returns 401 for anonymous requests from those IPs.
    2. Otherwise → do an anonymous homepage warm-up to collect csrftoken etc.
       This works on residential/local IPs but will likely fail on cloud hosts.

    How to get your session ID:
      - Log into Instagram in your browser.
      - Open DevTools (F12) → Application → Cookies → instagram.com
      - Copy the value of the 'sessionid' cookie.
      - Set it as INSTAGRAM_SESSION_ID in your Render environment variables.
    """
    session = requests.Session()
    session.headers.update(BASE_HEADERS)

    session_id = os.environ.get("INSTAGRAM_SESSION_ID", "").strip()

    if session_id:
        # Authenticated mode: inject the real session cookie.
        # Instagram trusts logged-in sessions from any IP, including datacenters.
        session.cookies.set("sessionid", session_id, domain=".instagram.com")
        # Still do a lightweight warm-up to pick up csrftoken
        try:
            warmup = session.get(
                "https://www.instagram.com/",
                headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
                timeout=10,
                allow_redirects=True,
            )
            csrf = session.cookies.get("csrftoken", "")
            if csrf:
                session.headers.update({"X-CSRFToken": csrf})
        except Exception:
            pass
    else:
        # Anonymous mode: works on residential IPs, may 401 on cloud hosts.
        try:
            warmup = session.get(
                "https://www.instagram.com/",
                headers={"Accept": "text/html,application/xhtml+xml,*/*;q=0.8"},
                timeout=10,
                allow_redirects=True,
            )
            csrf = session.cookies.get("csrftoken", "")
            if csrf:
                session.headers.update({"X-CSRFToken": csrf})
        except Exception:
            pass

    return session


def extract_shortcode(url: str) -> str:
    """
    Extracts the shortcode from any Instagram Reel / Post URL.
    e.g. https://www.instagram.com/reel/DZXe1uOICas/... -> DZXe1uOICas
    """
    pattern = r'(?:https?://)?(?:www\.)?instagram\.com/(?:p|reel|tv)/([^/?#&]+)'
    match = re.search(pattern, url)
    if match:
        return match.group(1)
    raise ValueError("Invalid Instagram URL. Please provide a valid Reel/Post link.")


def find_nested(data, key):
    """Recursively searches a nested dict/list for the first occurrence of key."""
    if isinstance(data, dict):
        if key in data:
            return data[key]
        for v in data.values():
            result = find_nested(v, key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = find_nested(item, key)
            if result is not None:
                return result
    return None


def get_video_url(shortcode: str) -> str:
    """
    Fetches the direct MP4 video URL from Instagram's internal GraphQL API.

    Requires INSTAGRAM_SESSION_ID env var on cloud deployments (Render, etc.)
    because Instagram blocks anonymous requests from datacenter IPs with 401.
    Works anonymously on local/residential IPs.
    """
    session = _make_session()

    params = {
        "doc_id": GRAPHQL_DOC_ID,
        "variables": json.dumps({"shortcode": shortcode}),
    }

    try:
        resp = session.get(
            GRAPHQL_URL,
            params=params,
            headers={"Accept": "application/json"},
            timeout=15,
        )
        resp.raise_for_status()
    except requests.HTTPError as e:
        if e.response is not None and e.response.status_code == 401:
            raise RuntimeError(
                "Instagram returned 401 Unauthorized. "
                "This usually means the app is running on a cloud server whose IP "
                "Instagram doesn't trust for anonymous requests.\n\n"
                "Fix: Set the INSTAGRAM_SESSION_ID environment variable in Render:\n"
                "  1. Log into Instagram in your browser.\n"
                "  2. Open DevTools (F12) → Application → Cookies → instagram.com\n"
                "  3. Copy the 'sessionid' cookie value.\n"
                "  4. Add it as INSTAGRAM_SESSION_ID in your Render service → Environment."
            ) from e
        raise

    data = resp.json()
    video_url = find_nested(data, "video_url")

    if not video_url:
        raise RuntimeError(
            "Could not find video_url in the API response. "
            "The reel may be private, or Instagram may have changed their API."
        )
    return video_url


def download_reel(reel_url: str):
    """
    Downloads a public Instagram Reel.
    Saves the file as <shortcode>.mp4 in the current directory.
    """
    try:
        shortcode = extract_shortcode(reel_url)
        print(f"[*] Fetching Reel: {shortcode} ...")

        video_url = get_video_url(shortcode)
        print("[*] Video URL found. Downloading...")

        final_filename = f"{shortcode}.mp4"
        session = requests.Session()
        session.headers.update(BASE_HEADERS)

        with session.get(video_url, stream=True, timeout=60) as r:
            r.raise_for_status()
            total = int(r.headers.get("content-length", 0))
            downloaded = 0

            with open(final_filename, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 64):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total:
                            pct = downloaded * 100 // total
                            kb_done = downloaded // 1024
                            kb_total = total // 1024
                            print(
                                f"\r    {pct:3d}%  {kb_done} KB / {kb_total} KB",
                                end="",
                                flush=True,
                            )

        print()
        size_mb = os.path.getsize(final_filename) / (1024 * 1024)
        print(f"[+] Done! Saved as: {final_filename}  ({size_mb:.1f} MB)")
        return final_filename

    except requests.HTTPError as e:
        print(f"[-] HTTP error: {e}")
    except requests.ConnectionError:
        print("[-] Connection error. Check your internet connection.")
    except RuntimeError as e:
        print(f"[-] {e}")
    except ValueError as e:
        print(f"[-] {e}")
    except Exception as e:
        print(f"[-] Unexpected error: {e}")

    return None


# ---------------------------------------------------------------------------
# Usage:
#   Interactive:   python reel.py
#   With URL arg:  python reel.py "https://www.instagram.com/reel/..."
#
# For cloud deployments, set: INSTAGRAM_SESSION_ID=<your sessionid cookie>
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_link = sys.argv[1].strip()
    else:
        user_link = input("Paste the public Instagram Reel URL: ").strip()

    download_reel(user_link)