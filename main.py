import subprocess
import argparse
from pathlib import Path


def _progress(stream, _chunk, bytes_remaining) -> None:
    total = stream.filesize
    done = total - bytes_remaining
    pct = done / total * 100
    print(f"\r  {pct:5.1f}%  {done // 1024:,} / {total // 1024:,} KB", end="", flush=True)
    if bytes_remaining == 0:
        print()


def download_youtube(url: str, output_path: Path) -> None:
    from pytubefix import YouTube

    print(f"Connecting to: {url}")
    yt = YouTube(
        url,
        client="ANDROID_VR",
        on_progress_callback=_progress,
    )
    print(f"Title: {yt.title}")

    video_stream = (
        yt.streams.filter(adaptive=True, only_video=True)
        .order_by("resolution")
        .last()
    )
    audio_stream = (
        yt.streams.filter(adaptive=True, only_audio=True)
        .order_by("abr")
        .last()
    )

    if not video_stream or not audio_stream:
        raise RuntimeError("Could not find suitable video or audio streams.")

    print(f"Video stream : {video_stream}")
    print(f"Audio stream : {audio_stream}")

    tmp_dir = output_path.parent
    tmp_video = tmp_dir / "_tmp_video.mp4"
    tmp_audio = tmp_dir / "_tmp_audio.mp4"

    print("\nDownloading video...")
    video_stream.download(output_path=str(tmp_dir), filename="_tmp_video.mp4")

    print("\nDownloading audio...")
    audio_stream.download(output_path=str(tmp_dir), filename="_tmp_audio.mp4")

    print("\nMerging with ffmpeg...")
    subprocess.run(
        [
            "ffmpeg", "-y",
            "-i", str(tmp_video),
            "-i", str(tmp_audio),
            "-c:v", "copy",
            "-c:a", "aac",
            str(output_path),
        ],
        check=True,
    )

    tmp_video.unlink(missing_ok=True)
    tmp_audio.unlink(missing_ok=True)

    print(f"\nSaved to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Download a YouTube video with audio.")
    parser.add_argument("url", help="YouTube video or Shorts URL")
    parser.add_argument(
        "-o", "--output",
        default="output_video.mp4",
        help="Output filename (default: output_video.mp4)",
    )
    args = parser.parse_args()

    output_path = Path(args.output).resolve()
    download_youtube(args.url, output_path)


if __name__ == "__main__":
    main()
