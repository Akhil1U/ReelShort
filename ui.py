import contextlib
import io
import shutil
import tempfile
import uuid
from pathlib import Path

import streamlit as st

from main import download_youtube


class StreamlitLogWriter(io.TextIOBase):
    def __init__(self, placeholder: "st.delta_generator.DeltaGenerator") -> None:
        self.placeholder = placeholder
        self.entries: list[str] = []
        self.current_line = ""

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if not text:
            return 0

        for char in text:
            if char == "\r":
                self.current_line = ""
            elif char == "\n":
                self.entries.append(self.current_line)
                self.current_line = ""
            else:
                self.current_line += char

        lines = self.entries[-200:]
        if self.current_line:
            lines = [*lines, self.current_line]
        self.placeholder.code("\n".join(lines) or "Waiting for output...")
        return len(text)

    def flush(self) -> None:
        return None


st.set_page_config(
    page_title="ReelShort Downloader",
    layout="centered",
)

st.markdown(
    """
    <style>
        .stApp {
            background:
                radial-gradient(circle at top left, rgba(255, 196, 128, 0.32), transparent 32%),
                linear-gradient(180deg, #fff8ef 0%, #f8efe2 100%);
        }
        .hero {
            padding: 2rem 2.2rem;
            border-radius: 24px;
            background: rgba(255, 255, 255, 0.72);
            border: 1px solid rgba(114, 74, 36, 0.12);
            box-shadow: 0 18px 50px rgba(114, 74, 36, 0.10);
            margin-bottom: 1.5rem;
        }
        .hero h1 {
            margin: 0;
            color: #40210f;
            font-size: 2.5rem;
            line-height: 1.05;
        }
        .hero p {
            margin: 0.75rem 0 0;
            color: #714b2d;
            font-size: 1rem;
        }
    </style>
    <div class="hero">
        <h1>ReelShort</h1>
        <p>Paste a YouTube video or Shorts link, keep the existing downloader logic, and get a merged MP4 back in one click.</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_yt, tab_ig = st.tabs(["▶️ YouTube", "📸 Instagram Reel"])

# ── YouTube tab ──────────────────────────────────────────────────────────────
with tab_yt:
    st.write("Enter a YouTube URL below to download the highest available video and audio streams.")

    default_name = st.session_state.get("output_name", "output_video.mp4")
    url = st.text_input("YouTube link", placeholder="https://www.youtube.com/watch?v=...", key="youtube_url")
    output_name = st.text_input("Output filename", value=default_name, key="output_name")

    if st.button("Download Video", type="primary", use_container_width=True):
        if not url.strip():
            st.error("Please enter a YouTube link.")
        else:
            safe_name = Path(output_name.strip() or "output_video.mp4").name
            if not safe_name.lower().endswith(".mp4"):
                safe_name = f"{safe_name}.mp4"

            run_dir = Path(tempfile.mkdtemp(prefix="reelshort_"))
            output_path = run_dir / f"{uuid.uuid4().hex}_{safe_name}"
            log_placeholder = st.empty()
            log_writer = StreamlitLogWriter(log_placeholder)

            try:
                with st.spinner("Downloading and merging streams..."):
                    with contextlib.redirect_stdout(log_writer):
                        download_youtube(url.strip(), output_path)
            except Exception as exc:
                st.error(f"Download failed: {exc}")
            else:
                st.session_state["last_output_bytes"] = output_path.read_bytes()
                st.session_state["last_output_name"] = safe_name
                st.success("Your video is ready.")
            finally:
                shutil.rmtree(run_dir, ignore_errors=True)

    last_output_bytes = st.session_state.get("last_output_bytes")
    last_output_name = st.session_state.get("last_output_name", "output_video.mp4")

    if last_output_bytes:
        st.video(last_output_bytes)
        st.download_button(
            "Save MP4",
            data=last_output_bytes,
            file_name=last_output_name,
            mime="video/mp4",
            use_container_width=True,
        )

# ── Instagram Reel tab ───────────────────────────────────────────────────────
with tab_ig:
    from reel import extract_shortcode, get_video_url

    st.write(
        "Paste any public Instagram Reel link. "
        "The server resolves the direct CDN URL — your browser then downloads "
        "the file straight from Instagram (works on Render & any cloud host)."
    )

    ig_url = st.text_input(
        "Instagram Reel link",
        placeholder="https://www.instagram.com/reel/...",
        key="ig_url",
    )

    if st.button("Get Download Link", type="primary", use_container_width=True, key="ig_btn"):
        ig_url_clean = ig_url.strip()
        if not ig_url_clean:
            st.error("Please enter an Instagram Reel link.")
        else:
            try:
                with st.spinner("Resolving CDN link from Instagram..."):
                    shortcode = extract_shortcode(ig_url_clean)
                    cdn_url = get_video_url(shortcode)
                st.session_state["ig_cdn_url"] = cdn_url
                st.session_state["ig_shortcode"] = shortcode

            except ValueError as e:
                st.error(str(e))
                st.session_state.pop("ig_cdn_url", None)
            except RuntimeError as e:
                st.error(str(e))
                st.session_state.pop("ig_cdn_url", None)
            except Exception as e:
                st.error(f"Unexpected error: {e}")
                st.session_state.pop("ig_cdn_url", None)

    ig_cdn_url = st.session_state.get("ig_cdn_url")
    ig_shortcode = st.session_state.get("ig_shortcode", "reel")

    if ig_cdn_url:
        st.success("✅ CDN link resolved! Click below to download directly.")

        # st.link_button opens the URL in a new tab — the browser handles the
        # download using the user's own IP, so Instagram's datacenter-IP block
        # never applies. This is the same trick all online reel downloaders use.
        st.link_button(
            label="⬇️ Download Reel MP4",
            url=ig_cdn_url,
            use_container_width=True,
        )

        st.info(
            "💡 The link opens Instagram's CDN directly in your browser. "
            "If it plays instead of downloading, right-click the video → **Save video as…**"
        )

        with st.expander("Raw CDN URL"):
            st.code(ig_cdn_url, language=None)

