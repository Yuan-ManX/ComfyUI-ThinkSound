import gradio as gr
import os
import subprocess
import shutil
import uuid
import cv2
import sys
import tempfile
from datetime import datetime
from pathlib import Path

def run_infer(stage, duration_sec, videos_dir, csv_path, results_dir, cwd, use_half=False):
    cmd = (
        ["python", "extract_latents.py", "--duration_sec", str(duration_sec),
         "--root", videos_dir, "--tsv_path", csv_path, "--save-dir", results_dir]
        if stage == 1 else
        ["python", "predict.py", "--duration-sec", str(duration_sec),
         "--results-dir", results_dir]
    )

    if stage == 1 and use_half:
        cmd.append("--use_half")

    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    output_lines = []
    while True:
        line = process.stdout.readline()
        if not line:
            if process.poll() is not None:
                break
            continue
        print(line, end="", flush=True)
        output_lines.append(line)

    return_code = process.wait()
    return return_code, "".join(output_lines)

def convert_to_mp4(original_path, converted_path):
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", original_path,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-strict", "experimental",
            converted_path
        ],
        capture_output=True,
        text=True
    )
    return result.returncode == 0, result.stderr

def combine_audio_video(video_path, audio_path, output_path):
    result = subprocess.run(
        [
            "ffmpeg", "-y", "-i", video_path, "-i", audio_path,
            "-c:v", "copy", "-c:a", "aac", "-strict", "experimental",
            "-map", "0:v:0", "-map", "1:a:0", "-shortest",
            output_path
        ],
        capture_output=True,
        text=True
    )
    return result.returncode == 0, result.stderr

def generate_audio(video, title, description, use_half):
    print("start")
    if not title:
        title = " "
    if not description:
        description = " "
    if title.isdigit() or description.isdigit():
        yield "❌ 错误：标题和描述不能完全由数字构成。", None
        return

    unique_id = uuid.uuid4().hex[:8]

    session_dir = tempfile.mkdtemp(prefix="thinksound_"+unique_id)
    videos_dir  = os.path.join(session_dir, "videos")
    cot_dir     = os.path.join(session_dir, "cot_coarse")
    results_dir = os.path.join(session_dir, "results", "audios")
    project_root = Path(__file__).parent.resolve()
    os.makedirs(videos_dir,  exist_ok=True)
    os.makedirs(cot_dir,     exist_ok=True)
    os.makedirs(results_dir, exist_ok=True)

    
    orig_path = video
    ext = os.path.splitext(orig_path)[1].lower()
    vid = os.path.splitext(os.path.basename(orig_path))[0]
    temp_mp4 = os.path.join(videos_dir, f"demo.mp4")

    if ext != ".mp4":
        ok, err = convert_to_mp4(orig_path, temp_mp4)
        if not ok:
            yield f"❌ 转码失败：\n{err}", None
            return
    else:
        shutil.copy(orig_path, temp_mp4)

    # 4. 计算视频时长
    cap = cv2.VideoCapture(temp_mp4)
    fps = cap.get(cv2.CAP_PROP_FPS) or 1
    frames = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()
    duration_sec = frames / fps

    # 5. 写 cot.csv 到 cot_dir
    csv_path = os.path.join(cot_dir, "cot.csv")
    caption_cot = description.replace('"', "'")
    with open(csv_path, "w", encoding="utf-8") as f:
        f.write("id,caption,caption_cot\n")
        f.write(f"demo,{title},\"{caption_cot}\"\n")

    # 6. 特征提取
    yield "⏳ Extracting Features…", None
    code, out = run_infer(stage=1, duration_sec=duration_sec,videos_dir=videos_dir,csv_path=csv_path,results_dir=results_dir, cwd=project_root, use_half=use_half)
    if code != 0:
        yield "❌ Extracting Features Failed", out
        return

    # 7. 推理
    yield "⏳ Inferring…", None
    code, out = run_infer(stage=2, duration_sec=duration_sec,videos_dir=videos_dir,csv_path=csv_path,results_dir=results_dir, cwd=project_root)
    if code != 0:
        yield "❌ Inference Failed", out
        return

    # 8. 找到生成的音频
    today = datetime.now().strftime("%m%d")
    audio_file = os.path.join(results_dir, f"{today}_batch_size1/demo.wav")
    if not os.path.exists(audio_file):
        yield "❌ Generated audio not found", None
        return

    # 9. 合成音视频
    combined_video = os.path.join(results_dir, f"{vid}_{unique_id}_with_audio.mp4")
    ok, err = combine_audio_video(temp_mp4, audio_file, combined_video)
    if not ok:
        yield f"❌ Failed to combine audio and video:\n{err}", None
        return

    # 10. 清理上传视频，只保留结果
    shutil.rmtree(videos_dir, ignore_errors=True)

    yield "✅ Generation completed!", combined_video


class LoadOThinkSoundVideo:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video_path": ("STRING", {"default": "cat.png"}),
            }
        }

    RETURN_TYPES = ("VIDEO",)
    RETURN_NAMES = ("video",)
    FUNCTION = "load_video"
    CATEGORY = "ThinkSound"

    def load_video(self, video_path):
        video = video_path
        
        return (video,)


class LoadCaption:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "Printer Printing",
                    "multiline": True
                }),
            }
        }

    RETURN_TYPES = ("PROMPT",)
    RETURN_NAMES = ("title",)
    FUNCTION = "load_prompt"
    CATEGORY = "ThinkSound"

    def load_prompt(self, text):
        title = text
        
        return (title,)


class LoadCoTDescription:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "text": ("STRING", {
                    "default": "Generate a continuous printer printing sound with periodic beeps and paper movement, plus a cat pawing at the machine. Add subtle ambient room noise for authenticity, keeping the focus on printing, beeps, and the cat's interaction.",
                    "multiline": True
                }),
            }
        }

    RETURN_TYPES = ("PROMPT",)
    RETURN_NAMES = ("description",)
    FUNCTION = "load_prompt"
    CATEGORY = "ThinkSound"

    def load_prompt(self, text):
        description = text
        
        return (description,)
                

class ThinkSound:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "video": ("VIDEO",),
                "title": ("PROMPT",),
                "description": ("PROMPT",),
            }
        }

    RETURN_TYPES = ()
    RETURN_NAMES = ()
    FUNCTION = "generate"
    CATEGORY = "ThinkSound"

    def generate(self, video, title, description):
        
        use_half = False
        
        generate_audio(video, title, description, use_half)
        
        return ()
