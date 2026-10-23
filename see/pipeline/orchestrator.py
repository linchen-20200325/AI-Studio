"""Orchestrator：串接各階段、per-scene fingerprint 快取、成本閘門、狀態機。

這裡只依賴 Provider 介面與 Executor 介面，不知道任何具體供應商或執行位置。
"""

from __future__ import annotations

import uuid

from pydantic import ValidationError
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from see.audio.layer import AudioLayer
from see.core.approval import ApprovalGate
from see.core.config import Settings
from see.core.errors import InvalidTransition, PaidProviderNotApproved, RenderError, SchemaViolation
from see.core.hashing import file_sha256, fingerprint, short_id
from see.core.image_qa import image_defect, image_stats
from see.core.subtitles import build_cues, to_srt
from see.models.approval import Approval
from see.models.enums import ApprovalKind, CostTier, JobKind, JobStatus, Status
from see.models.project import CharacterVoice, OutputSpec, Project
from see.models.render_job import RenderJob
from see.models.scene import Scene
from see.models.timeline import Timeline
from see.pipeline.stages import make_storyboard, write_script
from see.providers.base import ImageRequest, TTSRequest, TTSResult, VideoRequest
from see.providers.registry import Providers
from see.render.renderer import FINAL_PROFILE, PREVIEW_PROFILE, ClipInput, EncodeProfile, Renderer, build_timeline
from see.storage.project_store import AssetRecord, ProjectStore, SceneManifest
from see.workers.base import Executor, Task

IMAGE_SCALE = 1.5  # placeholder 圖以輸出尺寸 1.5 倍產生，減少 zoompan 抖動
SUBTITLE_MAX_CHARS = 18


@dataclass
class SceneBuildReport:
    scene_id: str
    rebuilt: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)  # 為何重做（例如 image: "cached artifact rejected: black"）
    image_meta: dict[str, object] = field(default_factory=dict)  # 本次 image 的證據（manifest 同步保存）
    narration_meta: dict[str, object] = field(default_factory=dict)  # 本次 TTS 的證據（generated_by / voice / device / rtf）


@dataclass
class RunReport:
    project: Project
    job: RenderJob
    timeline: Timeline
    scene_reports: list[SceneBuildReport]

    @property
    def output_path(self) -> Path:
        return Path(self.job.output_path or "")


class Orchestrator:
    def __init__(self, settings: Settings, providers: Providers, executor: Executor, store: ProjectStore,
                 renderer: Renderer | None = None) -> None:
        self.settings = settings
        self.p = providers
        self.executor = executor
        self.store = store
        self.renderer = renderer or Renderer()

    # ------------------------------------------------------------ project lifecycle
    def create_project(self, text: str, title: str | None = None, project_id: str | None = None,
                       output: OutputSpec | None = None, speech_speed: float = 1.0) -> Project:
        pid = project_id or f"prj_{short_id(text + datetime.now(timezone.utc).isoformat(), 8)}"
        s = self.settings
        project = Project(project_id=pid, title=title or "untitled", input_text=text,
                          output=output or OutputSpec(width=s.width, height=s.height, fps=s.fps),
                          speech_speed=speech_speed)
        self.store.save(project)
        return project

    def write_script(self, project: Project, title: str | None = None) -> Project:
        self._gate(self.p.llm.estimate_cost, project, _llm_probe(project.input_text))
        project.script = self.executor.run(Task(task_id=f"{project.project_id}:script", kind="llm.script",
                                                fn=write_script, kwargs={"llm": self.p.llm, "story": project.input_text,
                                                                        "title": title or (None if project.title == "untitled" else project.title),
                                                                        "language": project.language}))
        project.title = project.script.title
        self.store.save(project)
        return project

    def storyboard(self, project: Project) -> Project:
        if project.script is None:
            raise InvalidTransition("write_script first")
        scenes = self.executor.run(Task(task_id=f"{project.project_id}:storyboard", kind="llm.storyboard",
                                        fn=make_storyboard, kwargs={"llm": self.p.llm, "script": project.script}))
        # 保留人工覆寫（同 scene_id 的 subtitle_override / voice / seed）
        old = {s.scene_id: s for s in project.scenes}
        for s in scenes:
            if s.scene_id in old:
                s.subtitle_override = old[s.scene_id].subtitle_override
                s.voice = old[s.scene_id].voice
                s.narrator_id = old[s.scene_id].narrator_id
                s.speech_speed = old[s.scene_id].speech_speed
        project.scenes = scenes
        project.status = Status.DRAFT
        self.store.save(project)
        return project

    # ------------------------------------------------------------ per-scene assets (cached)
    def build_scene_assets(self, project: Project, scene_ids: list[str] | None = None) -> list[SceneBuildReport]:
        reports: list[SceneBuildReport] = []
        for scene in project.scenes:
            if scene_ids and scene.scene_id not in scene_ids:
                continue
            reports.append(self._build_scene(project, scene))
        self.store.save(project)
        return reports

    def _build_scene(self, project: Project, scene: Scene) -> SceneBuildReport:
        pid = project.project_id
        sdir = self.store.scene_dir(pid, scene.scene_id)
        sdir.mkdir(parents=True, exist_ok=True)
        manifest = self.store.load_manifest(pid, scene.scene_id)
        report = SceneBuildReport(scene_id=scene.scene_id)
        s = self.settings

        # ---- image
        out = project.output
        img_req = ImageRequest(prompt=scene.effective_image_prompt, negative_prompt=scene.negative_prompt,
                               width=int(out.width * IMAGE_SCALE), height=int(out.height * IMAGE_SCALE),
                               seed=scene.index, caption=scene.visual_description)
        img_fp = fingerprint("image", img_req.model_dump(), self.p.image.info.fingerprint_key)
        img_path = sdir / "image.png"
        cached = manifest.valid("image", img_fp)
        cached_defect = image_defect(Path(cached.path)) if cached else None
        preferred = self.p.image.info.name  # Fallback 時 = 目前第一個「可用」候選
        if cached and cached_defect is None and cached.provider and cached.provider != preferred:
            # D-023：fallback 產物（例如 placeholder）是以首選 provider 的 fingerprint key 快取的；
            # 首選 provider 現在可用 → 這份降級產物不是有效快取，必須重試真正的生成
            cached_defect = f"degraded artifact from fallback provider {cached.provider}; preferred {preferred} is available"
        if cached and cached_defect is None:
            report.reused.append("image")
            report.image_meta = {**cached.meta, "regenerated": False}
        else:
            if cached:  # D-021：fingerprint 相同但內容不可用（黑圖）／D-023：降級產物 → 不得當有效快取
                report.reasons["image"] = f"cached artifact rejected: {cached_defect}"
                Path(cached.path).unlink(missing_ok=True)
            self._gate(self.p.image.estimate_cost, project, img_req)
            res = self.executor.run(Task(task_id=f"{scene.scene_id}:image", kind="image",
                                         fn=self.p.image.generate_image, kwargs={"request": img_req, "out_path": img_path}))
            defect = image_defect(Path(res.path))
            if defect is not None:  # 任何 provider 都不得交出黑圖讓 pipeline 回報成功
                Path(res.path).unlink(missing_ok=True)
                manifest.entries.pop("image", None)
                self.store.save_manifest(pid, manifest)
                raise RenderError(f"scene {scene.scene_id}: image provider {res.provider} produced unusable image ({defect})")
            meta = {"generated_by": res.meta.get("generated_by", res.provider), **res.meta, "regenerated": True,
                    "reason": report.reasons.get("image", "no valid cache"),
                    "degraded": res.provider != preferred,  # True = 這次是 fallback 產物，下次 run 若首選可用會重試
                    "image_stats": res.meta.get("image_stats") or image_stats(Path(res.path)).to_dict()}
            manifest.entries["image"] = AssetRecord(fingerprint=img_fp, path=res.path, provider=res.provider, model=res.model, meta=meta)
            report.rebuilt.append("image")
            report.image_meta = meta

        # ---- narration (TTS)
        voice, speed, voice_source = self.resolve_voice(project, scene)
        tts_req = TTSRequest(text=scene.narration, language=project.language, voice=voice, speed=speed)
        tts_fp = fingerprint("narration", tts_req.model_dump(), self.p.tts.info.fingerprint_key)
        wav_path = sdir / "narration.wav"
        rec = manifest.valid("narration", tts_fp)
        tts_preferred = self.p.tts.info.name  # Fallback 時 = 目前第一個「可用」候選
        if rec and rec.provider and rec.provider != tts_preferred:
            # 同 D-023：fallback 旁白（例如 espeak/silent）是以首選 provider 的 key 快取的；首選現在可用 → 重做
            report.reasons["narration"] = f"cached artifact rejected: degraded narration from {rec.provider}; preferred {tts_preferred} is available"
            rec = None
        if rec:
            report.reused.append("narration")
            measured = rec.duration or 0.0
            report.narration_meta = {**rec.meta, "regenerated": False}
        else:
            self._gate(self.p.tts.estimate_cost, project, tts_req)
            res = self.executor.run(Task(task_id=f"{scene.scene_id}:tts", kind="tts",
                                         fn=self.p.tts.synthesize, kwargs={"request": tts_req, "out_path": wav_path}))
            measured = res.duration
            meta = {"generated_by": res.meta.get("generated_by", res.provider), **res.meta, "regenerated": True,
                    "reason": report.reasons.get("narration", "no valid cache"), "degraded": res.provider != tts_preferred,
                    "sample_rate": res.sample_rate, "duration": round(measured, 3), "voice_source": voice_source,
                    "narrator_id": scene.narrator_id}
            manifest.entries["narration"] = AssetRecord(fingerprint=tts_fp, path=res.path, duration=measured,
                                                        provider=res.provider, model=res.model, meta=meta)
            report.rebuilt.append("narration")
            report.narration_meta = meta
        scene.measured_narration_duration = round(measured, 3)
        effective = max(scene.duration, measured + s.narration_pad, s.min_scene_duration)
        scene.duration = round(effective, 3)

        # ---- subtitles (deterministic)
        sub_text = scene.subtitle_text
        sub_fp = fingerprint("subtitle", sub_text, round(measured, 3), SUBTITLE_MAX_CHARS)
        srt_path = sdir / "subtitles.srt"
        if manifest.valid("subtitle", sub_fp):
            report.reused.append("subtitle")
        else:
            srt_path.write_text(to_srt(build_cues(sub_text, max(measured, 0.5), SUBTITLE_MAX_CHARS)), encoding="utf-8")
            manifest.entries["subtitle"] = AssetRecord(fingerprint=sub_fp, path=str(srt_path), duration=measured)
            report.rebuilt.append("subtitle")

        # ---- clip (image → video)
        vid_req = VideoRequest(prompt=scene.video_prompt, image_path=str(img_path), duration=scene.duration,
                               width=out.width, height=out.height, fps=out.fps, camera_motion=scene.camera_motion.value,
                               audio_path=str(wav_path), subtitle_path=str(srt_path), subtitle_font=s.subtitle_font)
        # D-021：clip 綁定實際圖檔內容（不只 image fingerprint），圖被重生（例如黑圖被拒）時 clip 必然重做
        clip_fp = fingerprint("clip", img_fp, file_sha256(img_path), tts_fp, sub_fp, vid_req.model_dump(exclude={"image_path", "audio_path", "subtitle_path"}),
                              s.fingerprint_params(), self.p.video.info.fingerprint_key)
        clip_path = sdir / "clip.mp4"
        if manifest.valid("clip", clip_fp):
            report.reused.append("clip")
        else:
            self._gate(self.p.video.estimate_cost, project, vid_req)
            res = self.executor.run(Task(task_id=f"{scene.scene_id}:clip", kind="video", requires={"cpu", "ffmpeg"},
                                         fn=self.p.video.generate_clip, kwargs={"request": vid_req, "out_path": clip_path}))
            manifest.entries["clip"] = AssetRecord(fingerprint=clip_fp, path=res.path, duration=res.duration,
                                                   provider=res.provider, model=res.model)
            report.rebuilt.append("clip")

        self.store.save_manifest(pid, manifest)
        return report

    # ------------------------------------------------------------ timeline + render
    def build_timeline(self, project: Project) -> Timeline:
        clips: list[ClipInput] = []
        for scene in project.scenes:
            m = self.store.load_manifest(project.project_id, scene.scene_id)
            rec = m.entries.get("clip")
            if rec is None or not Path(rec.path).exists():
                raise RenderError(f"scene {scene.scene_id} has no clip; run build_scene_assets first")
            clips.append(ClipInput(scene_id=scene.scene_id, index=scene.index, path=Path(rec.path),
                                   duration=rec.duration or scene.duration, transition_in=scene.transition))
        out = project.output
        return build_timeline(clips, self.settings.transition_duration, out.fps, out.width, out.height)

    def render(self, project: Project, kind: JobKind = JobKind.PREVIEW) -> tuple[RenderJob, Timeline]:
        if kind == JobKind.FINAL and project.status != Status.APPROVED:
            raise InvalidTransition(f"final render requires APPROVED, project is {project.status}")
        if kind == JobKind.FINAL and (pending := self.unconfirmed_characters(project)):
            # D-030：角色 voice 必須試聽確認後才進正式生成（未使用角色的專案不受影響）
            raise InvalidTransition(f"final render requires confirmed character voices; unconfirmed: {pending}")
        timeline = self.build_timeline(project)
        rdir = self.store.renders_dir(project.project_id)
        out = rdir / f"{kind.value}.mp4"
        profile: EncodeProfile = FINAL_PROFILE if kind == JobKind.FINAL else PREVIEW_PROFILE
        job = RenderJob(job_id=f"job_{uuid.uuid4().hex[:10]}", project_id=project.project_id, kind=kind,
                        status=JobStatus.RUNNING, provider="ffmpeg", model=f"libx264-crf{profile.crf}",
                        estimated_cost=0.0, actual_cost=0.0, currency=project.currency,
                        worker_id=self.executor.worker_info().worker_id)
        project.render_jobs.append(job)
        self.store.write_json(rdir / f"{kind.value}.json", timeline)
        self._write_global_srt(project, timeline, rdir / f"{kind.value}.srt")
        # D-031：Audio Layer（BGM／SFX／ducking）。null provider 或沒有 cue → 與舊版完全相同的單一步驟組裝
        layer = AudioLayer(self.p.audio, self.renderer.ffmpeg, self.settings.mix_params)
        plan = layer.plan(project, timeline) if layer.enabled else None
        mixing = plan is not None and not plan.empty
        audio_ev: dict[str, object] = {"enabled": layer.enabled, "provider": self.p.audio.info.name,
                                       "cost_tier": self.p.audio.info.cost_tier,
                                       "status": "disabled" if not layer.enabled else ("no_cues" if not mixing else "pending")}
        if plan is not None and plan.skipped:
            audio_ev["skipped"] = plan.skipped
        target = rdir / f"{kind.value}.dry.mp4" if mixing else out
        try:
            self.executor.run(Task(task_id=job.job_id, kind="render", requires={"cpu", "ffmpeg"},
                                   fn=self.renderer.assemble, kwargs={"timeline": timeline, "out_path": target, "profile": profile}))
            if mixing:
                audio_ev = layer.apply(project, plan, target, out, rdir / "audio", audio_bitrate=profile.audio_bitrate)
        except Exception as e:
            job.status, job.error = JobStatus.FAILED, str(e)
            job.finished_at = datetime.now(timezone.utc)
            self.store.save(project)
            raise
        self.store.write_json(rdir / f"{kind.value}.audio.json", audio_ev)
        self.last_audio_evidence = audio_ev
        job.status, job.output_path = JobStatus.DONE, str(out)
        job.finished_at = datetime.now(timezone.utc)
        if kind == JobKind.PREVIEW:
            project.status = Status.PREVIEW
            for sc in project.scenes:
                if sc.status == Status.DRAFT:
                    sc.status = Status.PREVIEW
        else:
            project.status = Status.FINAL
            for sc in project.scenes:
                sc.status = Status.FINAL
        self.store.save(project)
        return job, timeline

    def _write_global_srt(self, project: Project, timeline: Timeline, path: Path) -> None:
        from see.core.subtitles import Cue

        cues: list[Cue] = []
        for it in timeline.items:
            scene = project.scene(it.scene_id)
            measured = scene.measured_narration_duration or it.clip_duration
            for c in build_cues(scene.subtitle_text, max(measured, 0.5), SUBTITLE_MAX_CHARS):
                cues.append(Cue(index=len(cues) + 1, start=round(it.start + c.start, 3), end=round(it.start + c.end, 3), text=c.text))
        path.write_text(to_srt(cues), encoding="utf-8")

    # ------------------------------------------------------------ full run / edits / approval
    def run(self, text: str, title: str | None = None, project_id: str | None = None,
            output: OutputSpec | None = None, speech_speed: float = 1.0) -> RunReport:
        project = self.create_project(text, title, project_id, output=output, speech_speed=speech_speed)
        self.write_script(project, title)
        self.storyboard(project)
        return self.rebuild(project)

    def rebuild(self, project: Project) -> RunReport:
        reports = self.build_scene_assets(project)
        job, timeline = self.render(project, JobKind.PREVIEW)
        return RunReport(project=project, job=job, timeline=timeline, scene_reports=reports)

    def update_scene(self, project: Project, scene_id: str, **fields: object) -> Scene:
        """修改單一 Scene 的欄位（narration / subtitle_override / image_prompt / camera_motion / transition ...）。"""
        scene = project.scene(scene_id)
        allowed = {"narration", "subtitle_override", "image_prompt", "image_prompt_en", "negative_prompt", "visual_description", "video_prompt",
                   "camera_motion", "transition", "voice", "duration", "narrator_id", "speech_speed", "audio_cues"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"cannot edit fields {sorted(bad)}; allowed: {sorted(allowed)}")
        data = scene.model_dump()
        data.update({k: v for k, v in fields.items() if v is not None})
        try:
            updated = Scene.model_validate(data)  # 重新驗證（enum / 長度 / 型別）
        except ValidationError as e:
            raise ValueError(f"invalid scene edit: {e}") from e
        if updated.narrator_id is not None and updated.narrator_id not in project.characters:
            raise ValueError(f"unknown narrator_id '{updated.narrator_id}'; characters: {sorted(project.characters)}")
        updated.status = Status.DRAFT
        project.scenes[project.scenes.index(scene)] = updated
        project.status = Status.DRAFT  # 任何修改都使 PREVIEW/APPROVED/FINAL 失效，需重新 preview → 核准
        self.store.save(project)
        return updated

    def regenerate_scene(self, project: Project, scene_id: str) -> SceneBuildReport:
        """強制重做單一 Scene 的所有產物（image / narration / subtitle / clip；其他 Scene 不動）。

        語意：清掉該景 manifest（唯一的快取真相）後立刻重建；重建的 image 內容若改變，clip fingerprint（含圖檔 sha256）
        自然失效。不需要也不提供 asset 參數——使用者不必知道內部快取結構。
        """
        scene = project.scene(scene_id)
        self.store.clear_manifest(project.project_id, scene_id)
        scene.status = Status.DRAFT
        project.status = Status.DRAFT
        report = self._build_scene(project, scene)
        self.store.save(project)
        return report

    # ------------------------------------------------------------ voice selection（D-028／D-030；provider-agnostic）
    def resolve_voice(self, project: Project, scene: Scene) -> tuple[str, float, str]:
        """回傳 (voice, speed, source)。優先序：scene.voice（非 default）> 角色 voice > provider 預設；
        語速：scene.speech_speed > 角色 speed > project.speech_speed。未設角色的舊專案結果與先前完全相同（fingerprint 不變）。"""
        ch: CharacterVoice | None = None
        if scene.narrator_id is not None:
            ch = project.characters.get(scene.narrator_id)
            if ch is None:
                raise SchemaViolation(f"scene {scene.scene_id}: narrator_id '{scene.narrator_id}' not in project.characters")
        if scene.voice not in ("", "default"):
            voice, source = scene.voice, "scene"
        elif ch is not None:
            voice, source = ch.voice_id, f"character:{ch.character_id}"
        else:
            voice, source = "default", "provider-default"
        speed = scene.speech_speed or (ch.speed if ch is not None and ch.speed else None) or project.speech_speed
        return voice, speed, source

    def set_character(self, project: Project, character_id: str, *, display_name: str | None = None,
                      voice_id: str | None = None, speed: float | None = None, clear_speed: bool = False) -> CharacterVoice:
        """新增或修改角色 voice 設定。任何變更都清掉 confirmed，並讓使用該角色的景與專案回到 DRAFT（需重新 preview／確認）。"""
        old = project.characters.get(character_id)
        data = old.model_dump() if old else {"character_id": character_id}
        if display_name is not None:
            data["display_name"] = display_name
        if voice_id is not None:
            data["voice_id"] = voice_id
        if speed is not None:
            data["speed"] = speed
        if clear_speed:
            data["speed"] = None
        data["provider"] = self.p.tts.info.name
        try:
            ch = CharacterVoice.model_validate({**data, "confirmed": False, "confirmed_at": None})
        except ValidationError as e:
            raise ValueError(f"invalid character voice: {e}") from e
        changed = old is None or old.model_dump(exclude={"confirmed", "confirmed_at", "provider"}) != ch.model_dump(exclude={"confirmed", "confirmed_at", "provider"})
        if not changed and old is not None:
            return old  # 沒有實際變更：保留原確認狀態
        project.characters[character_id] = ch
        for sc in project.scenes:
            if sc.narrator_id == character_id:
                sc.status = Status.DRAFT
                project.status = Status.DRAFT
        self.store.save(project)
        return ch

    def confirm_character(self, project: Project, character_id: str) -> CharacterVoice:
        """人工確認角色 voice（試聽後）。只由 CLI／API 的人工動作呼叫。"""
        if character_id not in project.characters:
            raise KeyError(character_id)
        ch = project.characters[character_id]
        ch.confirmed, ch.confirmed_at = True, datetime.now(timezone.utc)
        self.store.save(project)
        return ch

    def unconfirmed_characters(self, project: Project) -> list[str]:
        used = {s.narrator_id for s in project.scenes if s.narrator_id}
        return sorted(c for c in used if c in project.characters and not project.characters[c].confirmed)

    def preview_voice(self, text: str, voice: str = "default", speed: float = 1.0, language: str = "zh-TW") -> TTSResult:
        """試聽：合成單句到 workspace/voice_previews（以內容 fingerprint 命名可重用）；**不寫 manifest、不影響任何專案**。"""
        req = TTSRequest(text=text, language=language, voice=voice, speed=speed)
        est = self.p.tts.estimate_cost(req)
        if est.cost_tier not in (CostTier.LOCAL_FREE, CostTier.FREE_TIER):
            # 試聽不屬於任何專案、沒有 Approval 可對應 → PAID 一律拒絕（fail-closed，PROJECT_RULES §1）
            raise PaidProviderNotApproved(f"voice preview refuses PAID TTS provider '{est.provider}'")
        fp = fingerprint("voice-preview", req.model_dump(), self.p.tts.info.fingerprint_key)[:16]
        out = self.store.workspace / "voice_previews" / f"{fp}.wav"
        return self.executor.run(Task(task_id=f"preview:{fp}", kind="tts", fn=self.p.tts.synthesize,
                                      kwargs={"request": req, "out_path": out}))

    def approve(self, project: Project, approved_by: str = "human", note: str = "") -> Project:
        """人工核准：只允許從 PREVIEW 進入 APPROVED。pipeline 自動流程不得呼叫。"""
        if project.status != Status.PREVIEW:
            raise InvalidTransition(f"approve requires PREVIEW, project is {project.status}")
        project.approvals.append(Approval(approval_id=f"apr_{uuid.uuid4().hex[:8]}", kind=ApprovalKind.FINAL_RENDER,
                                          target=project.project_id, approved_by=approved_by, note=note))
        project.status = Status.APPROVED
        for sc in project.scenes:
            sc.status = Status.APPROVED
        self.store.save(project)
        return project

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _gate(estimator, project: Project, request) -> None:
        ApprovalGate.check(estimator(request), project)


def _llm_probe(text: str):
    from see.providers.base import LLMRequest

    return LLMRequest(task="script", user=text, inputs={"story": text})
