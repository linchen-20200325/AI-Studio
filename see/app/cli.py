"""see 命令列入口。

    python -m see.app.cli run examples/story_short.txt
    python -m see.app.cli status <project_id>
    python -m see.app.cli set-scene <project_id> scene_003 --narration "..."
    python -m see.app.cli regen <project_id> scene_003
    python -m see.app.cli approve <project_id>
    python -m see.app.cli final <project_id>
    python -m see.app.cli check-env
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from see.core.config import Settings
from see.core.errors import SeeError
from see.core.ffmpeg import FFmpeg
from see.models.enums import JobKind
from see.pipeline.orchestrator import Orchestrator
from see.providers.registry import ProviderRegistry
from see.render.renderer import Renderer
from see.storage.project_store import ProjectStore
from see.workers.local import LocalExecutor


def build(settings: Settings | None = None) -> tuple[Settings, Orchestrator]:
    settings = settings or Settings()
    registry = ProviderRegistry(settings)
    providers = registry.build()
    orch = Orchestrator(settings, providers, LocalExecutor(), ProjectStore(settings.workspace), Renderer(registry.ffmpeg))
    return settings, orch


def _read_text(src: str) -> str:
    if src == "-":
        return sys.stdin.read()
    return Path(src).read_text(encoding="utf-8")


def _print_summary(orch: Orchestrator, project, job, timeline) -> None:
    ff = FFmpeg(orch.settings.ffmpeg, orch.settings.ffprobe)
    out = Path(job.output_path or "")
    info = ff.probe(out) if out.exists() else None
    print(json.dumps({
        "project_id": project.project_id, "title": project.title, "status": project.status,
        "scenes": len(project.scenes), "timeline_total_s": round(timeline.total_duration, 3),
        "output": str(out), "probe": info.__dict__ if info else None,
        "job": {"id": job.job_id, "status": job.status, "provider": job.provider, "model": job.model,
                "estimated_cost": job.estimated_cost, "actual_cost": job.actual_cost, "currency": job.currency},
        "providers": {k: getattr(orch.p, k).info.model_dump() for k in ("llm", "image", "video", "tts", "audio", "lipsync")},
    }, ensure_ascii=False, indent=2))


def cmd_run(args: argparse.Namespace) -> int:
    settings = Settings()
    if args.tts:
        settings.tts_provider = args.tts
    if args.workspace:
        settings.workspace = Path(args.workspace).resolve()
    _, orch = build(settings)
    report = orch.run(_read_text(args.source), title=args.title, project_id=args.project_id)
    _print_summary(orch, report.project, report.job, report.timeline)
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    _, orch = build()
    project = orch.store.load(args.project_id)
    print(json.dumps({
        "project_id": project.project_id, "title": project.title, "status": project.status, "budget": project.budget,
        "scenes": [{"scene_id": s.scene_id, "status": s.status, "duration": s.duration, "camera": s.camera_motion,
                    "transition": s.transition, "narration": s.narration} for s in project.scenes],
        "render_jobs": [j.model_dump(mode="json") for j in project.render_jobs[-3:]],
        "approvals": [a.model_dump(mode="json") for a in project.approvals],
    }, ensure_ascii=False, indent=2))
    return 0


def cmd_set_scene(args: argparse.Namespace) -> int:
    _, orch = build()
    project = orch.store.load(args.project_id)
    orch.update_scene(project, args.scene_id, narration=args.narration, subtitle_override=args.subtitle,
                      image_prompt=args.image_prompt, camera_motion=args.camera, transition=args.transition)
    report = orch.rebuild(project)
    for r in report.scene_reports:
        print(f"{r.scene_id}: rebuilt={r.rebuilt} reused={r.reused}")
    _print_summary(orch, report.project, report.job, report.timeline)
    return 0


def cmd_regen(args: argparse.Namespace) -> int:
    _, orch = build()
    project = orch.store.load(args.project_id)
    r = orch.regenerate_scene(project, args.scene_id)
    print(f"{r.scene_id}: rebuilt={r.rebuilt}")
    report = orch.rebuild(project)
    _print_summary(orch, report.project, report.job, report.timeline)
    return 0


def cmd_approve(args: argparse.Namespace) -> int:
    _, orch = build()
    project = orch.store.load(args.project_id)
    orch.approve(project, approved_by=args.by, note=args.note or "")
    print(f"{project.project_id}: {project.status}")
    return 0


def cmd_final(args: argparse.Namespace) -> int:
    _, orch = build()
    project = orch.store.load(args.project_id)
    job, timeline = orch.render(project, JobKind.FINAL)
    _print_summary(orch, project, job, timeline)
    return 0


def cmd_check_env(args: argparse.Namespace) -> int:
    s = Settings()
    rows = {
        "ffmpeg": shutil.which(s.ffmpeg), "ffprobe": shutil.which(s.ffprobe), "espeak-ng": shutil.which("espeak-ng"),
        "subtitle_font": s.subtitle_font or "(none detected)", "workspace": str(s.workspace),
        "tts_provider": s.tts_provider, "llm_provider": s.llm_provider, "image_provider": s.image_provider,
    }
    for k, v in rows.items():
        print(f"{k:14s} {v}")
    return 0 if rows["ffmpeg"] and rows["ffprobe"] else 1


def cmd_hardware(args: argparse.Namespace) -> int:
    from see.core.hardware import hardware_report

    rep = hardware_report(args.path)
    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
        return 0
    hw, rec = rep["hardware"], rep["image_recommendation"]
    print(f"OS        {hw['os']} {hw['arch']} · Python {hw['python']} · CPU x{hw['cpu_cores']}")
    print(f"RAM       {hw['ram_total_mb']} MB (avail {hw['ram_available_mb']}) · disk free {hw['disk_free_mb']} MB @ {hw['disk_path']}")
    for g in hw["gpus"] or [{"vendor": "-", "name": "(none)", "vram_total_mb": None, "source": ""}]:
        print(f"GPU       {g['vendor']} {g['name']} VRAM {g['vram_total_mb']} MB [{g['source']}]")
    t = hw["torch"]
    print(f"torch     installed={t['installed']} {t['version']} cuda={t['cuda_available']} {t['cuda_version']} rocm={t['rocm']} mps={t['mps']} directml={t['directml']} diffusers={t['diffusers_installed']}")
    for n in hw["notes"]:
        print(f"note      {n}")
    print("--- image provider recommendation")
    for k in ("recommended", "fallback"):
        tier = rec[k]
        print(f"{k:11s} " + (f"{tier['label']} · {tier['model_id']} · {tier['license']} · 下載≈{tier['download_gb']}GB · VRAM≥{tier['min_vram_mb']}MB" if tier else "(none)"))
    print(f"cpu_only    {rec['cpu_only']}")
    for r in rec["reasons"]:
        print(f"reason      {r}")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="see", description="文字 → 影片（Phase 0 MVP）")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="從文字檔跑完整 pipeline 產生 preview.mp4")
    r.add_argument("source", help="文字檔路徑或 - 讀 stdin")
    r.add_argument("--title")
    r.add_argument("--project-id")
    r.add_argument("--tts", choices=["auto", "espeak", "silent", "edge"])
    r.add_argument("--workspace")
    r.set_defaults(fn=cmd_run)
    st = sub.add_parser("status"); st.add_argument("project_id"); st.set_defaults(fn=cmd_status)
    ss = sub.add_parser("set-scene", help="修改單一 scene 後只重做該 scene 並重新組裝 preview")
    ss.add_argument("project_id"); ss.add_argument("scene_id")
    ss.add_argument("--narration"); ss.add_argument("--subtitle"); ss.add_argument("--image-prompt")
    ss.add_argument("--camera"); ss.add_argument("--transition")
    ss.set_defaults(fn=cmd_set_scene)
    rg = sub.add_parser("regen", help="強制重做單一 scene"); rg.add_argument("project_id"); rg.add_argument("scene_id"); rg.set_defaults(fn=cmd_regen)
    apv = sub.add_parser("approve", help="人工核准（PREVIEW → APPROVED）"); apv.add_argument("project_id")
    apv.add_argument("--by", default="human"); apv.add_argument("--note"); apv.set_defaults(fn=cmd_approve)
    fn = sub.add_parser("final", help="Final render（需 APPROVED）"); fn.add_argument("project_id"); fn.set_defaults(fn=cmd_final)
    ce = sub.add_parser("check-env"); ce.set_defaults(fn=cmd_check_env)
    hw = sub.add_parser("hardware", help="偵測 GPU/VRAM/RAM/disk/torch 並給出 AI Image Provider 建議")
    hw.add_argument("--json", action="store_true"); hw.add_argument("--path", default=".", help="評估磁碟空間的路徑（預設 workspace 所在）")
    hw.set_defaults(fn=cmd_hardware)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except SeeError as e:
        print(f"ERROR [{type(e).__name__}] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
