# 云端运行与 Hosted Skill 发布

本项目的云端路径由两层组成：

1. **Codex Cloud／Hosted Shell** 负责运行 Skill、读写临时文件并生成成稿；
2. **OpenAI Audio API** 使用 `gpt-transcribe` 转写录音。脚本会先把音频转成单声道 MP3，并按 8 分钟分片，使每个请求低于 25 MB。

原始音频、逐字稿和病例身份信息不得进入 GitHub。Hosted Shell 的临时文件会随容器生命周期结束而消失；需要保留的去标识化成稿应写入 `/workspace/outputs` 并发布为 artifact。

## 云端环境一次性配置

云端环境需要：

- Python 3.10 或更高版本；
- `ffmpeg` 和 `ffprobe`；
- `python -m pip install -r requirements-cloud.txt`；
- 环境 Secret `OPENAI_API_KEY`。只验证变量是否存在，不能把值写入仓库、日志或提示词。

## 在 Codex Cloud 中运行

假设音频位于 `/workspace/input/recording.m4a`：

```bash
python scripts/cloud_transcribe.py \
  /workspace/input/recording.m4a \
  --out /workspace/private/tcm-run
```

脚本支持断点续跑，并生成：

- `manifest.json`：音频哈希、时长、分片和完成状态；
- `transcript_chunks.jsonl`：私有原始分片转写；
- `transcript_timestamped.md`：带分片时间范围的私有转写。

随后在同一任务中明确调用：

```text
使用 $tcm-clinical-audio-distillation 整理
/workspace/private/tcm-run/transcript_timestamped.md，
把去标识化成稿和结构化 JSON 写入 /workspace/outputs。
```

若只验证音频预处理，不调用 API：

```bash
python scripts/cloud_transcribe.py input.m4a --out /workspace/private/check --prepare-only
```

## 打包并上传 Hosted Skill

先构建只含一个 `SKILL.md` 的版本化压缩包：

```bash
python scripts/package_skill.py --out /workspace/outputs/tcm-clinical-audio-distillation.zip
```

首次创建 Hosted Skill：

```bash
curl --fail-with-body https://api.openai.com/v1/skills \
  -H "Authorization: Bearer $OPENAI_API_KEY" \
  -F "files=@/workspace/outputs/tcm-clinical-audio-distillation.zip;type=application/zip"
```

返回的 `skill_id` 和版本号应保存到受限配置中，不能硬编码 API Key。以后更新时向 `/v1/skills/<skill_id>/versions` 上传新压缩包，并在验证后再切换默认版本。

## 输入文件说明

- Audio API 单次转写文件上限为 25 MB；本项目通过云端压缩和分片处理更大的原始录音。
- 不要把真实患者录音提交到 GitHub，也不要使用公开永久链接传输病例录音。
- 如果前端无法直接上传大文件，应通过受认证的 Files API／Agent Environment 文件入口传入云端工作区；不要退回公开网盘链接。

官方依据：

- https://developers.openai.com/api/docs/guides/tools-skills
- https://developers.openai.com/api/docs/guides/speech-to-text
- https://developers.openai.com/api/docs/guides/agents-api/environments/files

