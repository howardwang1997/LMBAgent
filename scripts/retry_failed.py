"""Retry downloading failed clips and re-merge."""

import os
import requests
import time
from pathlib import Path

ARK_API_KEY = os.environ.get("ARK_API_KEY", "a69cc26e-9d57-4883-acf3-7d69675709ba")
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {ARK_API_KEY}",
}

OUTPUT_DIR = Path(__file__).parent.parent / "output" / "demo_video"
CLIPS_DIR = OUTPUT_DIR / "clips"

# Failed tasks to retry download
FAILED_TASKS = [
    ("3.1", "cgt-20260331172529-jvm8j"),
    ("5.1", "cgt-20260331172538-5mxk6"),
]


def poll_and_download(name: str, task_id: str):
    resp = requests.get(
        f"{BASE_URL}/contents/generations/tasks/{task_id}",
        headers=HEADERS,
        timeout=30,
    )
    resp.raise_for_status()
    result = resp.json()
    if result["status"] != "succeeded":
        print(f"  [{name}] status: {result['status']}")
        return False

    video_url = result["content"]["video_url"]
    clip_path = CLIPS_DIR / f"{name}.mp4"
    print(f"  [{name}] Downloading...")
    video_resp = requests.get(video_url, timeout=180)
    video_resp.raise_for_status()
    with open(clip_path, "wb") as f:
        f.write(video_resp.content)
    print(f"  [{name}] Saved: {clip_path}")
    return True


def merge_all():
    clip_order = ["1.1", "1.2", "1.3", "2.1", "2.2", "3.1", "3.2", "4.1", "5.1", "5.2", "5.3"]
    clip_files = []
    for name in clip_order:
        p = CLIPS_DIR / f"{name}.mp4"
        if p.exists():
            clip_files.append(p)
        else:
            print(f"  [MISSING] {name}.mp4")

    concat_list = OUTPUT_DIR / "concat.txt"
    with open(concat_list, "w") as f:
        for clip in clip_files:
            f.write(f"file '{clip}'\n")

    final = OUTPUT_DIR / "lmbagent_demo.mp4"
    print(f"\n[MERGE] {len(clip_files)} clips -> {final.name}")
    os.system(f'ffmpeg -y -f concat -safe 0 -i "{concat_list}" -c copy "{final}"')

    if final.exists():
        print(f"[DONE] {final} ({final.stat().st_size / 1024 / 1024:.1f} MB)")


def main():
    for name, task_id in FAILED_TASKS:
        print(f"[RETRY] {name} (task: {task_id})")
        try:
            poll_and_download(name, task_id)
        except Exception as e:
            print(f"  ERROR: {e}")

    merge_all()


if __name__ == "__main__":
    main()
