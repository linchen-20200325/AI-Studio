"""FastAPI Web UI（Phase 0.5）：貼故事 → 建立 Preview → 播放 → 單景修改 → 核准。

    uvicorn see.ui.server:app --host 0.0.0.0 --port 8000
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from pydantic import BaseModel, Field

from see.core.config import Settings
from see.core.errors import InvalidTransition, SeeError
from see.models import JobKind, OutputSpec, Project
from see.pipeline.orchestrator import Orchestrator
from see.providers.registry import ProviderRegistry
from see.render.renderer import Renderer
from see.storage.project_store import ProjectStore
from see.ui.runner import BackgroundRunner
from see.workers.local import LocalExecutor

STATIC = Path(__file__).parent / "static"
_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
CURRENCY_SYMBOL = {"TWD": "NT$", "USD": "US$"}


class CreateProjectIn(BaseModel):
    text: str = Field(min_length=1, max_length=5000)
    title: str | None = None
    aspect: str = "16:9"
    speech_speed: float = Field(default=1.0, gt=0.5, lt=2.0)


class SceneEditIn(BaseModel):
    narration: str | None = None
    subtitle_override: str | None = None
    image_prompt: str | None = None
    image_prompt_en: str | None = Field(default=None, max_length=2000, description="英文圖片描述；空字串＝退回 image_prompt")
    visual_description: str | None = Field(default=None, min_length=1, max_length=1000)
    video_prompt: str | None = Field(default=None, max_length=1000)
    duration: float | None = Field(default=None, gt=0, le=60, description="規劃秒數；實際仍以旁白長度校正（下限）")
    camera_motion: str | None = None
    transition: str | None = None
    voice: str | None = None
    narrator_id: str | None = None
    speech_speed: float | None = Field(default=None, gt=0.5, lt=2.0)
    audio_cues: list[dict[str, Any]] | None = Field(default=None, max_length=20, description="AudioCue 清單（bgm/sfx）；由 Scene schema 驗證")
    character_ids: list[str] | None = Field(default=None, max_length=10)
    lipsync: bool | None = None


class CharacterIn(BaseModel):
    display_name: str | None = Field(default=None, max_length=64)
    voice_id: str | None = Field(default=None, min_length=1, max_length=64)
    speed: float | None = Field(default=None, gt=0.5, lt=2.0)
    clear_speed: bool = False


class StyleIn(BaseModel):
    style_id: str = Field(min_length=1, max_length=64)


class AppearanceIn(BaseModel):
    description_en: str = Field(default="", max_length=300)
    outfit_en: str = Field(default="", max_length=200)
    features_en: list[str] = Field(default_factory=list, max_length=10)
    seed: int | None = None
    traits: dict[str, Any] | None = None  # D-047 結構化人物設定（CharacterTraits 驗證）


class VoicePreviewIn(BaseModel):
    text: str = Field(default="你好，這是角色試聽。", min_length=1, max_length=200)
    voice: str = Field(default="default", min_length=1, max_length=64)
    speed: float = Field(default=1.0, gt=0.5, lt=2.0)


class ApproveIn(BaseModel):
    by: str = "human"
    note: str = ""


def create_app(settings: Settings | None = None, sync_jobs: bool = False) -> FastAPI:
    settings = settings or Settings()
    registry = ProviderRegistry(settings)
    providers = registry.build()
    store = ProjectStore(settings.workspace)
    orch = Orchestrator(settings, providers, LocalExecutor(), store, Renderer(registry.ffmpeg))
    runner = BackgroundRunner(sync=sync_jobs)
    app = FastAPI(title="see", version="0.0.2")
    app.state.orchestrator, app.state.runner = orch, runner

    def _load(pid: str) -> Project:
        _check_id(pid)
        try:
            return store.load(pid)
        except FileNotFoundError:
            raise HTTPException(404, f"project not found: {pid}")

    def _check_id(*ids: str) -> None:
        for i in ids:
            if not _ID_RE.match(i):
                raise HTTPException(404, "invalid id")

    def _guard_idle(pid: str) -> None:
        if runner.is_busy(pid):
            raise HTTPException(409, "此專案正在處理中，請等候完成")

    def _cost(project: Project) -> dict[str, Any]:
        est = sum(j.estimated_cost for j in project.render_jobs)
        act = sum(j.actual_cost or 0.0 for j in project.render_jobs)
        sym = CURRENCY_SYMBOL.get(project.currency, project.currency + " ")
        return {"currency": project.currency, "estimated": est, "actual": act, "budget": project.budget,
                "display": f"{sym}{act:,.0f}", "budget_display": f"{sym}{project.budget:,.0f}",
                "providers": {k: {"name": getattr(providers, k).info.name, "cost_tier": getattr(providers, k).info.cost_tier}
                              for k in ("llm", "image", "video", "tts", "audio", "lipsync")}}

    def _project_view(project: Project) -> dict[str, Any]:
        job = runner.status(project.project_id)
        renders = store.renders_dir(project.project_id)
        return {
            "project_id": project.project_id, "title": project.title, "status": project.status,
            "aspect": project.output.aspect, "speech_speed": project.speech_speed,
            "input_text": project.input_text, "created_at": project.created_at.isoformat(),
            "job": job.to_dict(),
            "preview_url": f"/api/projects/{project.project_id}/preview.mp4" if (renders / "preview.mp4").exists() else None,
            "final_url": f"/api/projects/{project.project_id}/final.mp4" if (renders / "final.mp4").exists() else None,
            "scenes": [{
                "scene_id": s.scene_id, "index": s.index, "status": s.status, "duration": s.duration,
                "narration": s.narration, "subtitle_override": s.subtitle_override, "subtitle_text": s.subtitle_text,
                "visual_description": s.visual_description, "image_prompt": s.image_prompt, "image_prompt_en": s.image_prompt_en,
                "camera_motion": s.camera_motion, "transition": s.transition,
                "video_prompt": s.video_prompt, "voice": s.voice,
                "preferences": s.preferences.model_dump(mode="json") if s.preferences else None,
                "image_url": f"/api/projects/{project.project_id}/scenes/{s.scene_id}/image.png"
                if (store.scene_dir(project.project_id, s.scene_id) / "image.png").exists() else None,
                "image_meta": _image_meta(project.project_id, s.scene_id),
                "narration_meta": _narration_meta(project.project_id, s.scene_id),
                "character_ids": s.character_ids, "lipsync": s.lipsync,
            } for s in project.scenes],
            "render_jobs": [j.model_dump(mode="json") for j in project.render_jobs[-5:]],
            "approvals": [a.model_dump(mode="json") for a in project.approvals],
            "cost": _cost(project),
            "characters": {k: v.model_dump(mode="json") for k, v in project.characters.items()},
            "unconfirmed_characters": orch.unconfirmed_characters(project),
            "audio_evidence": _audio_evidence(project.project_id),
            "style_id": project.style_id,
        }

    def _image_meta(pid: str, sid: str) -> dict[str, Any]:
        """Scene 卡顯示用的生成證據（D-021）：真正生成者、是否重生、dtype、降級／fallback。"""
        rec = store.load_manifest(pid, sid).entries.get("image")
        if rec is None:
            return {}
        m = rec.meta
        return {"provider": rec.provider, "generated_by": m.get("generated_by"), "regenerated": m.get("regenerated"),
                "final_dtype": m.get("final_dtype"), "final_vae_fp32": m.get("final_vae_fp32"),
                "numeric_downgrade": m.get("numeric_downgrade"), "oom_downgrade": m.get("oom_downgrade"),
                "fallback": m.get("fallback"), "fallback_from": m.get("fallback_from"), "image_stats": m.get("image_stats")}

    def _audio_evidence(pid: str) -> dict[str, Any]:
        import json as _json

        f = store.renders_dir(pid) / "preview.audio.json"
        return _json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"status": "missing"}

    def _narration_meta(pid: str, sid: str) -> dict[str, Any]:
        """Scene 卡顯示用的旁白證據：真正生成者、voice、device、rtf、是否降級／fallback。"""
        rec = store.load_manifest(pid, sid).entries.get("narration")
        if rec is None:
            return {}
        m = rec.meta
        return {"provider": rec.provider, "model": rec.model, "generated_by": m.get("generated_by"), "voice": m.get("voice"),
                "device": m.get("device"), "duration": rec.duration, "rtf": m.get("rtf"), "regenerated": m.get("regenerated"),
                "degraded": m.get("degraded"), "fallback_from": m.get("fallback_from")}

    # ------------------------------------------------------------ pages
    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        return HTMLResponse((STATIC / "index.html").read_text(encoding="utf-8"))

    # ------------------------------------------------------------ api
    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"ok": True, "ffmpeg": registry.ffmpeg.available(), "tts": providers.tts.info.name,
                "image": providers.image.info.name, "image_skipped": getattr(providers.image, "skipped", []),
                "worker": orch.executor.worker_info().model_dump(mode="json")}

    @app.get("/api/hardware")
    def hardware() -> dict[str, Any]:
        from see.core.hardware import hardware_report

        rep = hardware_report(settings.workspace if settings.workspace.exists() else ".")
        rep["image_provider"] = {"configured": settings.image_provider, "active": providers.image.info.model_dump(),
                                 "skipped": getattr(providers.image, "skipped", [])}
        return rep

    @app.get("/api/options")
    def options() -> dict[str, Any]:
        return {"aspects": ["16:9", "9:16", "1:1"], "speech_speeds": [{"label": "慢", "value": 0.85}, {"label": "正常", "value": 1.0}, {"label": "快", "value": 1.2}],
                "camera_motions": ["static", "zoom_in", "zoom_out", "pan_left", "pan_right", "pan_up", "pan_down"],
                "transitions": ["cut", "fade", "dissolve", "wipe_left", "slide_left", "fade_black"]}

    @app.get("/api/projects")
    def list_projects() -> list[dict[str, Any]]:
        out = []
        for pid in store.list_projects():
            p = store.load(pid)
            out.append({"project_id": pid, "title": p.title, "status": p.status, "created_at": p.created_at.isoformat(),
                        "scenes": len(p.scenes), "job": runner.status(pid).to_dict()})
        return sorted(out, key=lambda x: x["created_at"], reverse=True)

    @app.post("/api/projects", status_code=202)
    def create_project(body: CreateProjectIn) -> dict[str, Any]:
        try:
            output = OutputSpec.from_aspect(body.aspect, fps=settings.fps)
        except ValueError as e:
            raise HTTPException(422, str(e))
        project = orch.create_project(body.text, body.title, output=output, speech_speed=body.speech_speed)
        pid = project.project_id

        def _work() -> None:
            runner.set_stage(pid, "script", "產生劇本")
            orch.write_script(project, body.title)
            runner.set_stage(pid, "storyboard", "規劃分鏡")
            orch.storyboard(project)
            runner.set_stage(pid, "assets", f"產生 {len(project.scenes)} 景素材（圖片／旁白／字幕／片段）")
            orch.build_scene_assets(project)
            runner.set_stage(pid, "render", "組裝 preview.mp4")
            orch.render(project, JobKind.PREVIEW)

        runner.submit(pid, "create", _work)
        return {"project_id": pid, "job": runner.status(pid).to_dict()}

    @app.get("/api/projects/{pid}")
    def get_project(pid: str) -> dict[str, Any]:
        return _project_view(_load(pid))

    @app.post("/api/projects/{pid}/scenes/{sid}", status_code=202)
    def edit_scene(pid: str, sid: str, body: SceneEditIn) -> dict[str, Any]:
        _guard_idle(pid)
        project = _load(pid)
        try:
            impact = orch.edit_impact(project, sid, **body.model_dump())  # D-062：只重做受影響產物（其餘沿用快取）
            orch.update_scene(project, sid, **body.model_dump())
        except KeyError:
            raise HTTPException(404, f"scene not found: {sid}")
        except (ValueError, SeeError) as e:
            raise HTTPException(422, str(e))

        def _work() -> None:
            runner.set_stage(pid, "assets", f"重做 {sid}")
            orch.build_scene_assets(project)
            runner.set_stage(pid, "render", "重新組裝 preview.mp4")
            orch.render(project, JobKind.PREVIEW)

        runner.submit(pid, "edit", _work)
        return {"project_id": pid, "job": runner.status(pid).to_dict(), "impact": impact}

    @app.post("/api/projects/{pid}/scenes/{sid}/impact")
    def scene_edit_impact(pid: str, sid: str, body: SceneEditIn) -> dict[str, Any]:
        """預覽修改影響範圍（不寫入、不重做）：UI 用來提示「會重做哪些產物」。"""
        project = _load(pid)
        try:
            return orch.edit_impact(project, sid, **body.model_dump())
        except KeyError:
            raise HTTPException(404, f"scene not found: {sid}")
        except ValueError as e:
            raise HTTPException(422, str(e))

    @app.post("/api/projects/{pid}/scenes/{sid}/regen", status_code=202)
    def regen_scene(pid: str, sid: str) -> dict[str, Any]:
        _guard_idle(pid)
        project = _load(pid)
        if sid not in {s.scene_id for s in project.scenes}:
            raise HTTPException(404, f"scene not found: {sid}")

        def _work() -> None:
            runner.set_stage(pid, "assets", f"重做 {sid}")
            orch.regenerate_scene(project, sid)
            runner.set_stage(pid, "render", "重新組裝 preview.mp4")
            orch.render(project, JobKind.PREVIEW)

        runner.submit(pid, "regen", _work)
        return {"project_id": pid, "job": runner.status(pid).to_dict()}

    # ------------------------------------------------------------ voice selection API（UI 形式待 DG-15；此處只提供資料／動作）
    @app.get("/api/voices")
    def voices() -> dict[str, Any]:
        return {"provider": providers.tts.info.name, "default_voice": settings.tts_default_voice or None,
                "voices": [v.model_dump() for v in providers.tts.list_voices()]}

    @app.post("/api/voices/preview")
    def voice_preview(body: VoicePreviewIn) -> dict[str, Any]:
        try:
            res = orch.preview_voice(body.text, voice=body.voice, speed=body.speed)
        except SeeError as e:
            raise HTTPException(422, str(e))
        return {**res.model_dump(exclude={"path"}), "url": f"/api/voice-previews/{Path(res.path).stem}.wav"}

    @app.get("/api/voice-previews/{name}.wav")
    def voice_preview_file(name: str) -> FileResponse:
        _check_id(name)
        f = store.workspace / "voice_previews" / f"{name}.wav"
        if not f.exists():
            raise HTTPException(404)
        return FileResponse(f, media_type="audio/wav")

    @app.post("/api/projects/{pid}/characters/{cid}")
    def set_character(pid: str, cid: str, body: CharacterIn) -> dict[str, Any]:
        _guard_idle(pid)
        _check_id(cid)
        project = _load(pid)
        try:
            orch.set_character(project, cid, display_name=body.display_name, voice_id=body.voice_id,
                               speed=body.speed, clear_speed=body.clear_speed)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return _project_view(project)

    @app.get("/api/styles")
    def styles() -> list[dict[str, Any]]:
        from see.core.styles import BUILTIN_STYLES

        return [s.model_dump() for s in BUILTIN_STYLES.values()]

    @app.post("/api/projects/{pid}/style")
    def set_style(pid: str, body: StyleIn) -> dict[str, Any]:
        _guard_idle(pid)
        project = _load(pid)
        try:
            orch.set_style(project, body.style_id)
        except ValueError as e:
            raise HTTPException(422, str(e))
        return _project_view(project)

    @app.post("/api/projects/{pid}/characters/{cid}/appearance")
    def set_appearance(pid: str, cid: str, body: AppearanceIn) -> dict[str, Any]:
        from see.models.project import CharacterAppearance

        _guard_idle(pid)
        _check_id(cid)
        project = _load(pid)
        from pydantic import ValidationError

        try:
            appearance = CharacterAppearance(**body.model_dump())
        except ValidationError as e:
            raise HTTPException(422, str(e))
        orch.set_character_appearance(project, cid, appearance)
        return _project_view(project)

    @app.post("/api/projects/{pid}/characters/{cid}/confirm")
    def confirm_character(pid: str, cid: str) -> dict[str, Any]:
        _guard_idle(pid)
        _check_id(cid)
        project = _load(pid)
        try:
            orch.confirm_character(project, cid)
        except KeyError:
            raise HTTPException(404, f"character not found: {cid}")
        return _project_view(project)

    @app.post("/api/projects/{pid}/approve")
    def approve(pid: str, body: ApproveIn) -> dict[str, Any]:
        _guard_idle(pid)
        project = _load(pid)
        try:
            orch.approve(project, approved_by=body.by, note=body.note)
        except InvalidTransition as e:
            raise HTTPException(409, str(e))
        return _project_view(project)

    @app.post("/api/projects/{pid}/final", status_code=202)
    def render_final(pid: str) -> dict[str, Any]:
        _guard_idle(pid)
        project = _load(pid)
        if project.status != "APPROVED":
            raise HTTPException(409, f"final render requires APPROVED, project is {project.status}")
        if pending := orch.unconfirmed_characters(project):
            raise HTTPException(409, f"final render requires confirmed character voices; unconfirmed: {pending}")

        def _work() -> None:
            runner.set_stage(pid, "render", "組裝 final.mp4")
            orch.render(project, JobKind.FINAL)

        runner.submit(pid, "final", _work)
        return {"project_id": pid, "job": runner.status(pid).to_dict()}

    # ------------------------------------------------------------ media
    @app.get("/api/projects/{pid}/{name}.mp4")
    def media(pid: str, name: str) -> FileResponse:
        _check_id(pid)
        if name not in ("preview", "final"):
            raise HTTPException(404)
        path = store.renders_dir(pid) / f"{name}.mp4"
        if not path.exists():
            raise HTTPException(404, f"{name}.mp4 not rendered yet")
        return FileResponse(path, media_type="video/mp4", filename=f"{pid}_{name}.mp4", content_disposition_type="inline")

    @app.get("/api/projects/{pid}/scenes/{sid}/image.png")
    def scene_image(pid: str, sid: str) -> FileResponse:
        _check_id(pid, sid)
        path = store.scene_dir(pid, sid) / "image.png"
        if not path.exists():
            raise HTTPException(404)
        return FileResponse(path, media_type="image/png")

    return app


app = create_app()
