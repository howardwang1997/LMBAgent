"""Generate a demo video from screenshots using doubao-seedance API."""

import base64
import os
import time
import requests
from pathlib import Path

ARK_API_KEY = os.environ.get("ARK_API_KEY", "a69cc26e-9d57-4883-acf3-7d69675709ba")
BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"
MODEL = "doubao-seedance-1-0-pro-fast-251015"

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {ARK_API_KEY}",
}

SCREENSHOTS_DIR = Path(__file__).parent.parent / "screenshots"
OUTPUT_DIR = Path(__file__).parent.parent / "output" / "demo_video"

# Each screenshot with a motion prompt
IMAGES = [
    ("1.1.pic.jpg", "The web application interface smoothly loads, the cursor moves to the upload area"),
    ("1.2.pic.jpg", "A CSV file is being dragged into the upload area, the file info appears"),
    ("1.3.pic.jpg", "The upload button is clicked, a success notification slides in from the right"),
    ("2.1.pic.jpg", "The dataset management page loads, data table rows fade in one by one"),
    ("2.2.pic.jpg", "The user scrolls through the dataset details, statistics update smoothly"),
    ("3.1.pic.jpg", "Battery data visualization charts animate in, lines draw progressively"),
    ("3.2.pic.jpg", "The chart transitions smoothly, showing different visualization angles"),
    ("4.1.pic.jpg", "A report is being generated, content fills in progressively from top to bottom"),
    ("5.1.pic.jpg", "The AI chat interface opens, a greeting message types out character by character"),
    ("5.2.pic.jpg", "The user sends a message, the AI starts responding with analysis"),
    ("5.3.pic.jpg", "The AI response completes with charts and data insights appearing"),
]


def image_to_base64(path: Path) -> str:
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()


def create_task(image_path: Path, prompt: str) -> str:
    b64 = image_to_base64(image_path)
    data_uri = f"data:image/jpeg;base64,{b64}"

    payload = {
        "model": MODEL,
        "content": [
            {"type": "text", "text": prompt},
            {
                "type": "image_url",
                "image_url": {"url": data_uri},
                "role": "first_frame",
            },
        ],
        "ratio": "adaptive",
        "duration": 5,
        "resolution": "720p",
    }

    resp = requests.post(
        f"{BASE_URL}/contents/generations/tasks",
        headers=HEADERS,
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    task_id = resp.json()["id"]
    return task_id


def poll_task(task_id: str, max_wait: int = 300) -> str:
    """Poll until task completes. Returns video URL."""
    start = time.time()
    while time.time() - start < max_wait:
        resp = requests.get(
            f"{BASE_URL}/contents/generations/tasks/{task_id}",
            headers=HEADERS,
            timeout=15,
        )
        resp.raise_for_status()
        result = resp.json()
        status = result.get("status", "unknown")

        if status == "succeeded":
            return result["content"]["video_url"]
        elif status in ("failed", "expired", "cancelled"):
            error = result.get("error", {})
            raise RuntimeError(f"Task {task_id} {status}: {error}")

        time.sleep(10)

    raise TimeoutError(f"Task {task_id} timed out after {max_wait}s")


def download_video(url: str, output_path: Path):
    resp = requests.get(url, timeout=120)
    resp.raise_for_status()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "wb") as f:
        f.write(resp.content)


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    clips_dir = OUTPUT_DIR / "clips"
    clips_dir.mkdir(exist_ok=True)

    # Step 1: Submit all tasks
    tasks = []
    for filename, prompt in IMAGES:
        image_path = SCREENSHOTS_DIR / filename
        if not image_path.exists():
            print(f"[SKIP] {filename} not found")
            continue

        print(f"[SUBMIT] {filename} ...")
        try:
            task_id = create_task(image_path, prompt)
            print(f"  -> task_id: {task_id}")
            tasks.append((filename, task_id))
        except Exception as e:
            print(f"  -> ERROR: {e}")

    if not tasks:
        print("No tasks submitted!")
        return

    # Step 2: Poll all tasks for results
    clip_files = []
    for filename, task_id in tasks:
        print(f"[POLL] {filename} (task: {task_id}) ...")
        try:
            video_url = poll_task(task_id)
            clip_path = clips_dir / f"{filename.replace('.pic.jpg', '')}.mp4"
            download_video(video_url, clip_path)
            clip_files.append(clip_path)
            print(f"  -> saved: {clip_path.name}")
        except Exception as e:
            print(f"  -> ERROR: {e}")

    if not clip_files:
        print("No clips generated!")
        return

    # Step 3: Write ffmpeg concat list and merge
    concat_list = OUTPUT_DIR / "concat.txt"
    with open(concat_list, "w") as f:
        for clip in clip_files:
            f.write(f"file '{clip}'\n")

    final_output = OUTPUT_DIR / "lmbagent_demo.mp4"
    print(f"\n[MERGE] Concatenating {len(clip_files)} clips -> {final_output.name}")
    os.system(
        f'ffmpeg -y -f concat -safe 0 -i "{concat_list}" -c copy "{final_output}"'
    )

    if final_output.exists():
        size_mb = final_output.stat().st_size / 1024 / 1024
        print(f"\n[DONE] {final_output} ({size_mb:.1f} MB)")
    else:
        print("\n[ERROR] ffmpeg merge failed")


if __name__ == "__main__":
    main()
