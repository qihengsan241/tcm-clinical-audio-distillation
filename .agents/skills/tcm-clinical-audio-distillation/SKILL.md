---
name: tcm-clinical-audio-distillation
description: 将中医跟诊、师承讲课或病例讨论的录音与转写整理为病例、教学方法、老师经验 Wiki、方药推理、随访验证和待核对内容；支持在 Codex Cloud 中转写并整理音频。
---

# 仓库级入口

这是本仓库在 Codex Cloud 和项目级 Codex 会话中的发现入口。

1. 完整读取仓库根目录的 [`../../../SKILL.md`](../../../SKILL.md)，并遵循其中的来源区分、方药核验、隐私与医学安全要求。
2. 输入是音频且运行环境位于云端时，再读取 [`../../../CLOUD.md`](../../../CLOUD.md)，使用 [`../../../scripts/cloud_transcribe.py`](../../../scripts/cloud_transcribe.py) 生成带粗粒度时间定位的私有转写。
3. 原始音频、逐字稿和可识别病例资料不得提交到 Git；只将去标识化成稿写入环境的输出目录。

