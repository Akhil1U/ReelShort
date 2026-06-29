import os
import re
import sys
import json
import requests


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "application/json",
    "X-IG-App-ID": "936619743392459",
}

# GraphQL document ID for fetching shortcode media — same one the Instagram
# web app uses internally (no API key or login required).
GRAPHQL_DOC_ID = "10015901848480474"
GRAPHQL_URL = "https://www.instagram.com/graphql/query"


def extract_shortcode(url):
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


def get_video_url(shortcode):
    """
    Fetches the direct MP4 video URL from Instagram's internal GraphQL API.
    No login or cookies required — this is the same endpoint the Instagram
    website uses to load the video player on a reel's page.
    """
    params = {
        "doc_id": GRAPHQL_DOC_ID,
        "variables": json.dumps({"shortcode": shortcode}),
    }
    resp = requests.get(GRAPHQL_URL, params=params, headers=HEADERS, timeout=15)
    resp.raise_for_status()

    data = resp.json()

    # The video_url field lives somewhere inside the nested response JSON
    video_url = find_nested(data, "video_url")
    if not video_url:
        raise RuntimeError(
            "Could not find video_url in the API response. "
            "The reel may be private, or Instagram may have changed their API."
        )
    return video_url


def download_reel(reel_url):
    """
    Downloads a public Instagram Reel without login or cookies.
    Saves the file as <shortcode>.mp4 in the current directory.
    """
    try:
        shortcode = extract_shortcode(reel_url)
        print(f"[*] Fetching Reel: {shortcode} ...")

        video_url = get_video_url(shortcode)
        print("[*] Video URL found. Downloading...")

        final_filename = f"{shortcode}.mp4"

        # Stream-download to handle large files efficiently
        with requests.get(video_url, headers=HEADERS, stream=True, timeout=60) as r:
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

        print()  # newline after progress bar
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
# Always wrap URLs in quotes on the command line — the '&' in the query
# string is a shell operator and will break the command if left unquoted.
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) > 1:
        user_link = sys.argv[1].strip()
    else:
        user_link = input("Paste the public Instagram Reel URL: ").strip()

    download_reel(user_link)