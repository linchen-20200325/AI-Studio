"""Orchestrator：串接各階段、per-scene fingerprint 快取、成本閘門、狀態機。

這裡只依賴 Provider 介面與 Executor 介面，不知道任何具體供應商或執行位置。
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from see.core.approval import ApprovalGate
from see.core.config import Settings
from see.core.errors import InvalidTransition, RenderError
from see.core.hashing import fingerprint, short_id
from see.core.subtitles import build_cues, to_srt
from see.models.approval import Approval
from see.models.enums import ApprovalKind, JobKind, JobStatus, Status
from see.models.project import Project
from see.models.render_job import RenderJob
from see.models.scene import Scene
from see.models.timeline import Timeline
from see.pipeline.stages import make_storyboard, write_script
from see.providers.base import ImageRequest, TTSRequest, VideoRequest
from see.providers.registry import Providers
from see.render.renderer import FINAL_PROFILE, PREVIEW_PROFILE, ClipInput, EncodeProfile, Renderer, build_timeline
from see.storage.project_store import AssetRecord, ProjectStore, SceneManifest
from see.workers.base import Executor, Task

IMAGE_W, IMAGE_H = 1920, 1080
SUBTITLE_MAX_CHARS = 18


@dataclass
class SceneBuildReport:
    scene_id: str
    rebuilt: list[str] = field(default_factory=list)
    reused: list[str] = field(default_factory=list)


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
    def create_project(self, text: str, title: str | None = None, project_id: str | None = None) -> Project:
        pid = project_id or f"prj_{short_id(text + datetime.now(timezone.utc).isoformat(), 8)}"
        project = Project(project_id=pid, title=title or "untitled", input_text=text)
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
        img_req = ImageRequest(prompt=scene.image_prompt, width=IMAGE_W, height=IMAGE_H, seed=scene.index,
                               caption=scene.visual_description)
        img_fp = fingerprint("image", img_req.model_dump(), self.p.image.info.fingerprint_key)
        img_path = sdir / "image.png"
        if manifest.valid("image", img_fp):
            report.reused.append("image")
        else:
            self._gate(self.p.image.estimate_cost, project, img_req)
            res = self.executor.run(Task(task_id=f"{scene.scene_id}:image", kind="image",
                                         fn=self.p.image.generate_image, kwargs={"request": img_req, "out_path": img_path}))
            manifest.entries["image"] = AssetRecord(fingerprint=img_fp, path=res.path, provider=res.provider, model=res.model)
            report.rebuilt.append("image")

        # ---- narration (TTS)
        tts_req = TTSRequest(text=scene.narration, language=project.language, voice=scene.voice)
        tts_fp = fingerprint("narration", tts_req.model_dump(), self.p.tts.info.fingerprint_key)
        wav_path = sdir / "narration.wav"
        rec = manifest.valid("narration", tts_fp)
        if rec:
            report.reused.append("narration")
            measured = rec.duration or 0.0
        else:
            self._gate(self.p.tts.estimate_cost, project, tts_req)
            res = self.executor.run(Task(task_id=f"{scene.scene_id}:tts", kind="tts",
                                         fn=self.p.tts.synthesize, kwargs={"request": tts_req, "out_path": wav_path}))
            measured = res.duration
            manifest.entries["narration"] = AssetRecord(fingerprint=tts_fp, path=res.path, duration=measured,
                                                        provider=res.provider, model=res.model)
            report.rebuilt.append("narration")
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
                               width=s.width, height=s.height, fps=s.fps, camera_motion=scene.camera_motion.value,
                               audio_path=str(wav_path), subtitle_path=str(srt_path), subtitle_font=s.subtitle_font)
        clip_fp = fingerprint("clip", img_fp, tts_fp, sub_fp, vid_req.model_dump(exclude={"image_path", "audio_path", "subtitle_path"}),
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
        s = self.settings
        return build_timeline(clips, s.transition_duration, s.fps, s.width, s.height)

    def render(self, project: Project, kind: JobKind = JobKind.PREVIEW) -> tuple[RenderJob, Timeline]:
        if kind == JobKind.FINAL and project.status != Status.APPROVED:
            raise InvalidTransition(f"final render requires APPROVED, project is {project.status}")
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
        try:
            self.executor.run(Task(task_id=job.job_id, kind="render", requires={"cpu", "ffmpeg"},
                                   fn=self.renderer.assemble, kwargs={"timeline": timeline, "out_path": out, "profile": profile}))
        except Exception as e:
            job.status, job.error = JobStatus.FAILED, str(e)
            job.finished_at = datetime.now(timezone.utc)
            self.store.save(project)
            raise
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
    def run(self, text: str, title: str | None = None, project_id: str | None = None) -> RunReport:
        project = self.create_project(text, title, project_id)
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
        allowed = {"narration", "subtitle_override", "image_prompt", "visual_description", "video_prompt",
                   "camera_motion", "transition", "voice", "duration"}
        bad = set(fields) - allowed
        if bad:
            raise ValueError(f"cannot edit fields {sorted(bad)}; allowed: {sorted(allowed)}")
        updated = scene.model_copy(update={k: v for k, v in fields.items() if v is not None})
        updated = Scene.model_validate(updated.model_dump())  # 重新驗證
        updated.status = Status.DRAFT
        project.scenes[project.scenes.index(scene)] = updated
        project.status = Status.DRAFT  # 任何修改都使 PREVIEW/APPROVED/FINAL 失效，需重新 preview → 核准
        self.store.save(project)
        return updated

    def regenerate_scene(self, project: Project, scene_id: str) -> SceneBuildReport:
        """強制重做單一 Scene 的所有產物（其他 Scene 不動）。"""
        scene = project.scene(scene_id)
        self.store.clear_manifest(project.project_id, scene_id)
        scene.status = Status.DRAFT
        project.status = Status.DRAFT
        report = self._build_scene(project, scene)
        self.store.save(project)
        return report

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
