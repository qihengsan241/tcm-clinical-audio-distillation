#!/usr/bin/env python3
"""Prepare and transcribe a clinical audio file in a cloud shell.

The script normalizes and splits audio with ffmpeg so every request stays well
below the Audio API's 25 MB limit. It uses the current gpt-transcribe model by
default and writes raw transcript material only to the caller-selected private
directory. It deliberately does not perform medical summarization; the Skill
does that after reading the transcript.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable


MAX_CHUNK_BYTES = 24_000_000
DEFAULT_CHUNK_SECONDS = 8 * 60
DEFAULT_MODEL = "gpt-transcribe"
DEFAULT_PROMPT = (
    "这是中文中医临床跟诊、师承讲课或病例讨论录音。请忠实转写，保留否定词、"
    "方名、药名、剂量、单位和人物指代；听不清时不要用常见方名强行补全。"
)
DEFAULT_KEYWORDS = [
    "中医",
    "辨证",
    "舌苔",
    "脉象",
    "方剂",
    "方药",
    "剂量",
    "煎服法",
    "初诊",
    "复诊",
]


def format_timestamp(seconds: float) -> str:
    total = max(0, int(round(seconds)))
    hours, remainder = divmod(total, 3600)
    minutes, secs = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{secs:02d}"


def sanitize_keywords(values: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for raw in values:
        value = raw.strip()
        if not value or value.startswith("#"):
            continue
        if any(char in value for char in ("<", ">", "\r", "\n")):
            raise ValueError(f"关键词包含不支持的字符：{value!r}")
        if value not in seen:
            seen.add(value)
            result.append(value)
    return result


def build_prompt(previous_tail: str = "") -> str:
    if not previous_tail:
        return DEFAULT_PROMPT
    return f"{DEFAULT_PROMPT}\n上一段结尾仅供上下文衔接：{previous_tail[-500:]}"


def run_checked(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return completed.stdout.strip()


def require_executable(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise RuntimeError(f"缺少运行依赖：{name}")
    return path


def probe_duration(path: Path, ffprobe: str) -> float:
    value = run_checked(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ]
    )
    duration = float(value)
    if duration <= 0:
        raise RuntimeError(f"无法取得有效音频时长：{path.name}")
    return duration


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def split_audio(
    source: Path,
    chunks_dir: Path,
    ffmpeg: str,
    chunk_seconds: int,
    bitrate: str,
) -> list[Path]:
    existing = sorted(chunks_dir.glob("chunk_*.mp3")) if chunks_dir.exists() else []
    if existing:
        return existing

    chunks_dir.mkdir(parents=True, exist_ok=True)
    pattern = chunks_dir / "chunk_%04d.mp3"
    run_checked(
        [
            ffmpeg,
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-i",
            str(source),
            "-map_metadata",
            "-1",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "libmp3lame",
            "-b:a",
            bitrate,
            "-f",
            "segment",
            "-segment_time",
            str(chunk_seconds),
            "-reset_timestamps",
            "1",
            str(pattern),
        ]
    )
    chunks = sorted(chunks_dir.glob("chunk_*.mp3"))
    if not chunks:
        raise RuntimeError("ffmpeg 未生成任何音频分片")
    for chunk in chunks:
        if chunk.stat().st_size >= MAX_CHUNK_BYTES:
            raise RuntimeError(
                f"分片仍超过安全上传上限：{chunk.name} ({chunk.stat().st_size} bytes)。"
                "请减小 --chunk-seconds 或 --bitrate。"
            )
    return chunks


def load_keywords(path: Path | None) -> list[str]:
    if path is None:
        return list(DEFAULT_KEYWORDS)
    return sanitize_keywords(path.read_text(encoding="utf-8").splitlines())


def load_existing_rows(path: Path) -> dict[int, dict[str, Any]]:
    rows: dict[int, dict[str, Any]] = {}
    if not path.exists():
        return rows
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        rows[int(row["index"])] = row
    return rows


def response_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str):
        return text.strip()
    if isinstance(response, dict) and isinstance(response.get("text"), str):
        return response["text"].strip()
    raise RuntimeError("转写响应中没有 text 字段")


def write_timestamped(rows: list[dict[str, Any]], path: Path) -> None:
    parts = []
    for row in rows:
        parts.append(
            f"[{format_timestamp(float(row['start']))}–"
            f"{format_timestamp(float(row['end']))}] {row['text']}"
        )
    path.write_text("\n\n".join(parts) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="在云端压缩、分片并转写中医跟诊或师承录音。"
    )
    parser.add_argument("audio", type=Path, help="输入音频路径")
    parser.add_argument("--out", type=Path, required=True, help="私有转写输出目录")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--chunk-seconds", type=int, default=DEFAULT_CHUNK_SECONDS)
    parser.add_argument("--bitrate", default="48k")
    parser.add_argument("--keywords-file", type=Path)
    parser.add_argument(
        "--prepare-only",
        action="store_true",
        help="只执行音频预处理和分片，不调用 OpenAI API",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audio = args.audio.resolve()
    output = args.out.resolve()
    if not audio.is_file():
        raise FileNotFoundError(f"找不到音频文件：{audio}")
    if args.chunk_seconds < 60:
        raise ValueError("--chunk-seconds 不应小于 60")

    ffmpeg = require_executable("ffmpeg")
    ffprobe = require_executable("ffprobe")
    output.mkdir(parents=True, exist_ok=True)
    chunks_dir = output / "chunks"
    chunks = split_audio(
        audio,
        chunks_dir,
        ffmpeg,
        args.chunk_seconds,
        args.bitrate,
    )

    offsets: list[tuple[float, float]] = []
    offset = 0.0
    for chunk in chunks:
        duration = probe_duration(chunk, ffprobe)
        offsets.append((offset, offset + duration))
        offset += duration

    manifest_path = output / "manifest.json"
    base_manifest = {
        "source_name": audio.name,
        "source_sha256": sha256_file(audio),
        "source_duration_seconds": probe_duration(audio, ffprobe),
        "model": args.model,
        "chunk_seconds": args.chunk_seconds,
        "chunks": [
            {
                "index": index,
                "name": chunk.name,
                "bytes": chunk.stat().st_size,
                "start": offsets[index][0],
                "end": offsets[index][1],
            }
            for index, chunk in enumerate(chunks)
        ],
    }

    if args.prepare_only:
        manifest_path.write_text(
            json.dumps({**base_manifest, "status": "prepared"}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(json.dumps({"status": "prepared", "chunks": len(chunks)}, ensure_ascii=False))
        return 0

    if not os.environ.get("OPENAI_API_KEY"):
        raise RuntimeError(
            "云端环境未配置 OPENAI_API_KEY。请把它设置为环境 Secret，切勿写入仓库。"
        )

    try:
        from openai import OpenAI
    except ImportError as exc:
        raise RuntimeError(
            "缺少 openai Python 包；请运行 python -m pip install -r requirements-cloud.txt"
        ) from exc

    keywords = load_keywords(args.keywords_file)
    transcript_jsonl = output / "transcript_chunks.jsonl"
    existing = load_existing_rows(transcript_jsonl)
    previous_tail = existing[max(existing)]["text"][-500:] if existing else ""
    client = OpenAI(timeout=1800.0, max_retries=3)

    with transcript_jsonl.open("a", encoding="utf-8") as sink:
        for index, chunk in enumerate(chunks):
            if index in existing:
                print(f"SKIP {index + 1}/{len(chunks)} {chunk.name} (already transcribed)")
                continue
            with chunk.open("rb") as audio_handle:
                response = client.audio.transcriptions.create(
                    model=args.model,
                    file=audio_handle,
                    languages=["zh-cn"],
                    prompt=build_prompt(previous_tail),
                    keywords=keywords,
                )
            text = response_text(response)
            row = {
                "index": index,
                "start": offsets[index][0],
                "end": offsets[index][1],
                "text": text,
            }
            sink.write(json.dumps(row, ensure_ascii=False) + "\n")
            sink.flush()
            existing[index] = row
            previous_tail = text[-500:]
            print(f"DONE {index + 1}/{len(chunks)} {chunk.name}")

    ordered = [existing[index] for index in sorted(existing)]
    if len(ordered) != len(chunks):
        raise RuntimeError("转写分片数量不完整，保留现有结果供下次续跑")
    timestamped = output / "transcript_timestamped.md"
    write_timestamped(ordered, timestamped)
    manifest_path.write_text(
        json.dumps(
            {
                **base_manifest,
                "status": "complete",
                "transcript_chunks": len(ordered),
                "timestamped_transcript": timestamped.name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "status": "complete",
                "chunks": len(ordered),
                "transcript": str(timestamped),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"ERROR: {error}", file=sys.stderr)
        raise SystemExit(1)

