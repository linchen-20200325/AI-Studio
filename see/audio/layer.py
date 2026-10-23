"""AudioLayer：在 render 階段把「已組裝好的 narration 音軌」與 BGM／SFX 混成最終音軌（D-031）。

    narration（各景 clip 的音軌，xfade 後）
          ↓
    AudioMixer ← BGM（AudioProvider）
          ↑
       SFX（AudioProvider；scene.audio_cues 的 start_offset → 絕對時間）
          ↓
    ducking → gain → limiter → mux 回影片

- per-scene clip 不含 BGM／SFX → 既有 clip fingerprint 完全不變；audio provider = null 時整個 layer 停用，輸出與舊版相同。
- 來源失敗 → 該來源標 unavailable，照樣輸出 narration（不把 missing 當成功，evidence 寫明 degraded）。PAID 來源一律先過 ApprovalGate。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from see.audio.mixer import MixParams, SfxEvent, mix
from see.audio.pcm import decode_to_wav, fit_length, read_wav, write_wav
from see.core.approval import ApprovalGate
from see.core.errors import ProviderError
from see.core.ffmpeg import FFmpeg
from see.core.hashing import fingerprint
from see.models.project import Project
from see.models.timeline import Timeline
from see.providers.base import AudioProvider, AudioRequest
from see.providers.audio.procedural import SFX_DEFAULT_S

SUPPORTED_KINDS = ("bgm", "sfx")


@dataclass
class AudioPlan:
    bgm: AudioRequest | None = None
    bgm_from: str | None = None
    sfx: list[tuple[float, str, AudioRequest]] = field(default_factory=list)  # (absolute start, scene_id, request)
    skipped: list[dict[str, Any]] = field(default_factory=list)

    @property
    def empty(self) -> bool:
        return self.bgm is None and not self.sfx


class AudioLayer:
    def __init__(self, provider: AudioProvider, ffmpeg: FFmpeg, params: MixParams | None = None) -> None:
        self.provider = provider
        self.ffmpeg = ffmpeg
        self.params = params or MixParams()

    @property
    def enabled(self) -> bool:
        return bool(self.provider.generates_audio)

    def plan(self, project: Project, timeline: Timeline) -> AudioPlan:
        plan = AudioPlan()
        starts = {it.scene_id: (it.start, it.clip_duration) for it in timeline.items}
        for sc in project.scenes:
            st, dur = starts.get(sc.scene_id, (0.0, 0.0))
            for cue in sc.audio_cues:
                if cue.kind == "bgm":
                    if plan.bgm is None:  # v1：整支影片一條 BGM，取第一個 bgm cue
                        plan.bgm = AudioRequest(kind="bgm", description=cue.description, duration=timeline.total_duration)
                        plan.bgm_from = sc.scene_id
                    else:
                        plan.skipped.append({"scene_id": sc.scene_id, "kind": "bgm", "reason": "v1 uses the first bgm cue only"})
                elif cue.kind == "sfx":
                    if cue.start_offset >= dur:
                        plan.skipped.append({"scene_id": sc.scene_id, "kind": "sfx", "description": cue.description,
                                             "reason": f"start_offset {cue.start_offset}s beyond scene duration {dur}s"})
                        continue
                    plan.sfx.append((st + cue.start_offset, sc.scene_id,
                                     AudioRequest(kind="sfx", description=cue.description, duration=SFX_DEFAULT_S)))
                else:
                    plan.skipped.append({"scene_id": sc.scene_id, "kind": cue.kind, "reason": f"unsupported kind (v1: {SUPPORTED_KINDS})"})
        return plan

    def _source(self, project: Project, req: AudioRequest, cache_dir: Path) -> tuple[Path | None, dict[str, Any]]:
        info = self.provider.info
        ev: dict[str, Any] = {"kind": req.kind, "description": req.description, "provider": info.name, "model": info.model,
                              "cost_tier": info.cost_tier}
        try:
            ApprovalGate.check(self.provider.estimate_cost(req), project)  # Free First：PAID 無核准 → raise（不吞掉）
            fp = fingerprint("audio-src", req.model_dump(), info.fingerprint_key)[:16]
            raw = cache_dir / f"{req.kind}_{fp}.wav"
            if raw.exists():
                ev.update(json.loads(raw.with_suffix(".json").read_text(encoding="utf-8")))
                ev["cached"] = True
            else:
                res = self.provider.generate_audio(req, raw)
                if not res.path or not Path(res.path).exists():
                    raise ProviderError(f"{info.name} returned no audio for {req.kind}")
                raw.with_suffix(".json").write_text(json.dumps(res.meta, ensure_ascii=False), encoding="utf-8")
                ev.update(res.meta)
                ev["cached"] = False
            ev["status"] = "ok"
            return raw, ev
        except ProviderError as e:
            ev.update({"status": "unavailable", "error": str(e)})
            return None, ev

    def apply(self, project: Project, plan: AudioPlan, dry_mp4: Path, out_mp4: Path, work_dir: Path,
              audio_bitrate: str = "128k") -> dict[str, Any]:
        work_dir.mkdir(parents=True, exist_ok=True)
        cache = work_dir / "sources"
        cache.mkdir(exist_ok=True)
        narr = read_wav(decode_to_wav(self.ffmpeg, dry_mp4, work_dir / "narration.wav"))
        n = len(narr)
        bgm = None
        bgm_ev = None
        if plan.bgm is not None:
            path, bgm_ev = self._source(project, plan.bgm, cache)
            bgm_ev["from_scene"] = plan.bgm_from
            if path is not None:
                bgm = fit_length(read_wav(path), n, loop=True)
        events, sfx_ev = [], []
        for start, sid, req in plan.sfx:
            path, ev = self._source(project, req, cache)
            ev.update({"scene_id": sid, "start_s": round(start, 3)})
            sfx_ev.append(ev)
            if path is not None:
                events.append(SfxEvent(start_s=start, samples=read_wav(path), label=f"{sid}:{req.description}"))
        evidence: dict[str, Any] = {"enabled": True, "provider": self.provider.info.name, "cost_tier": self.provider.info.cost_tier,
                                    "bgm": bgm_ev, "sfx": sfx_ev, "skipped": plan.skipped, "params": self.params.to_dict()}
        unavailable = [e for e in ([bgm_ev] if bgm_ev else []) + sfx_ev if e["status"] != "ok"]
        evidence["degraded"] = bool(unavailable)
        if bgm is None and not events:
            evidence["status"] = "unavailable"  # 所有來源都失敗 → 不混音，輸出 narration-only（明確標示）
            dry_mp4.replace(out_mp4)
            return evidence
        mixed, stats = mix(narr, bgm, events, self.params)
        wav = write_wav(work_dir / "mix.wav", mixed)
        self.ffmpeg.run(["-i", str(dry_mp4), "-i", str(wav), "-map", "0:v", "-map", "1:a", "-c:v", "copy",
                         "-c:a", "aac", "-b:a", audio_bitrate, "-movflags", "+faststart", str(out_mp4)])
        dry_mp4.unlink(missing_ok=True)
        evidence.update({"status": "mixed_degraded" if unavailable else "mixed", "mix": stats})
        return evidence
