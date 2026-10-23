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
import logging
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


def image_evidence(orch: Orchestrator, project) -> list[dict]:
    """每景 image 的生成證據（來自 manifest；D-021）：真正生成者、是否重生、最終 dtype/vae_fp32、降級與 fallback。"""
    rows = []
    for s in project.scenes:
        rec = orch.store.load_manifest(project.project_id, s.scene_id).entries.get("image")
        m = rec.meta if rec else {}
        rows.append({"scene_id": s.scene_id, "provider": rec.provider if rec else None,
                     "generated_by": m.get("generated_by"), "regenerated": m.get("regenerated"), "reason": m.get("reason"),
                     "final_dtype": m.get("final_dtype"), "final_vae_fp32": m.get("final_vae_fp32"),
                     "numeric_downgrade": m.get("numeric_downgrade"), "oom_downgrade": m.get("oom_downgrade"),
                     "fallback": m.get("fallback"), "fallback_from": m.get("fallback_from"),
                     "attempts": m.get("attempts"), "image_stats": m.get("image_stats")})
    return rows


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
        "image_evidence": image_evidence(orch, project),  # providers.image.name 只是「第一個可用候選」，這裡才是實際生成證據
    }, ensure_ascii=False, indent=2))


def cmd_run(args: argparse.Namespace) -> int:
    settings = Settings()
    if args.tts:
        settings.tts_provider = args.tts
    if args.workspace:
        settings.workspace = Path(args.workspace).resolve()
    _, orch = build(settings)
    report = orch.run(_read_text(args.source), title=args.title, project_id=args.project_id)
    for r in report.scene_reports:
        print(f"{r.scene_id}: rebuilt={r.rebuilt} reused={r.reused}" + (f" reasons={r.reasons}" if r.reasons else ""), file=sys.stderr)
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
                      image_prompt=args.image_prompt, image_prompt_en=args.image_prompt_en,
                      camera_motion=args.camera, transition=args.transition)
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


def cmd_image_setup(args: argparse.Namespace) -> int:
    """印出此機器安裝本機生圖所需的單一步驟指令（不執行任何安裝）。"""
    from see.core.hardware import detect_hardware
    from see.providers.image.diffusers_local import download_plan

    s = Settings()
    hw = detect_hardware(s.models_dir.parent if s.models_dir.parent.exists() else ".")
    gpu = hw.best_gpu
    cuda = gpu is not None and gpu.vendor == "nvidia"
    plan = download_plan(s.image_model_preset)
    win = hw.os == "Windows"
    act = r".venv\Scripts\activate" if win else "source .venv/bin/activate"
    torch_cmd = ("pip install torch --index-url https://download.pytorch.org/whl/cu126" if cuda else "pip install torch")
    print(f"# 機器：{hw.os} · Python {hw.python} · GPU {(gpu.name if gpu else '(none)')} VRAM {(gpu.vram_total_mb if gpu else '-')} MB")
    print(f"# 方案：{plan['preset']} ({plan['model_id']}) · 預估下載 ≈{plan['estimated_gb']} GB · 存放 {s.models_dir}")
    print("# 依序在專案根目錄執行（每行一步；已裝過可跳過）：")
    print("python -m venv .venv" if not win else "py -3.12 -m venv .venv")
    print(act)
    print("pip install -r requirements.txt")
    print(torch_cmd)
    print("pip install diffusers transformers accelerate safetensors huggingface_hub")
    print(f"python -m see.app.cli image-download --preset {plan['preset']} --yes")
    print("python -m see.app.cli hardware        # 確認 torch/cuda/diffusers 皆為 True")
    print(f"set SEE_IMAGE_PROVIDER=auto" if win else "export SEE_IMAGE_PROVIDER=auto")
    return 0


def cmd_image_download(args: argparse.Namespace) -> int:
    """下載 open-weight 模型到 SEE_MODELS_DIR/<preset>。沒有 --yes 只印計畫，不下載。"""
    from see.providers.image.diffusers_local import download_plan

    s = Settings()
    preset = args.preset or s.image_model_preset
    plan = download_plan(preset)
    dest = Path(args.dest).resolve() if args.dest else s.models_dir / preset
    print(json.dumps({"plan": plan, "dest": str(dest)}, ensure_ascii=False, indent=2))
    if not args.yes:
        print("未加 --yes：只顯示計畫，未下載任何檔案。", file=sys.stderr)
        return 0
    if (dest / "model_index.json").exists():
        from see.providers.image.diffusers_local import local_weight_variants

        print(f"已存在：{dest}（略過下載）；各元件權重 variant：{ {k: sorted(map(str, v)) for k, v in local_weight_variants(dest).items()} }")
        print(f"fp32 升級策略：{plan['fp32_escalation']}")
        return 0
    try:
        from huggingface_hub import snapshot_download  # type: ignore
    except ImportError:
        print("需要 huggingface_hub：pip install huggingface_hub", file=sys.stderr)
        return 1
    dest.mkdir(parents=True, exist_ok=True)
    (dest.parent / ".gitignore").write_text("*\n", encoding="utf-8")  # 雙重保險：模型資料夾永不進 Git
    path = snapshot_download(repo_id=plan["model_id"], local_dir=str(dest), allow_patterns=plan["allow_patterns"])
    print(f"下載完成：{path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    from see.core.proc import ensure_utf8_stdio

    ensure_utf8_stdio()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s", stream=sys.stderr)
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
    ss.add_argument("--narration"); ss.add_argument("--subtitle"); ss.add_argument("--image-prompt"); ss.add_argument("--image-prompt-en")
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
    ise = sub.add_parser("image-setup", help="印出本機 AI 生圖安裝步驟（不執行安裝）"); ise.set_defaults(fn=cmd_image_setup)
    idl = sub.add_parser("image-download", help="下載 open-weight 模型（需 --yes 才真的下載）")
    idl.add_argument("--preset", default=None); idl.add_argument("--dest", default=None); idl.add_argument("--yes", action="store_true")
    idl.set_defaults(fn=cmd_image_download)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except SeeError as e:
        print(f"ERROR [{type(e).__name__}] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
