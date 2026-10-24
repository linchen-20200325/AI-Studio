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
import os
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


def tts_evidence(orch: Orchestrator, project) -> list[dict]:
    """每景 narration 的生成證據（manifest meta）：真正生成者、voice、device、rtf、是否降級／fallback。"""
    rows = []
    for s in project.scenes:
        rec = orch.store.load_manifest(project.project_id, s.scene_id).entries.get("narration")
        m = rec.meta if rec else {}
        rows.append({"scene_id": s.scene_id, "provider": rec.provider if rec else None, "model": rec.model if rec else None,
                     "generated_by": m.get("generated_by"), "voice": m.get("voice"), "device": m.get("device"),
                     "duration": rec.duration if rec else None, "sample_rate": m.get("sample_rate"),
                     "synth_seconds": m.get("synth_seconds"), "rtf": m.get("rtf"), "regenerated": m.get("regenerated"),
                     "degraded": m.get("degraded"), "fallback_from": m.get("fallback_from"),
                     "model_sha256": m.get("model_sha256"), "model_revision": m.get("model_revision")})
    return rows


def audio_evidence(orch: Orchestrator, project, kind: str = "preview") -> dict:
    """最近一次 render 的 Audio Layer 證據（renders/<kind>.audio.json）；沒有檔案 → 明確回報 missing，不補假資料。"""
    f = orch.store.renders_dir(project.project_id) / f"{kind}.audio.json"
    return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {"status": "missing"}


def _parse_sfx(items: list[str] | None) -> list[dict] | None:
    """`--sfx 描述@秒數`（可重複）→ AudioCue dict；`--sfx none` 清空本景 sfx。"""
    if items is None:
        return None
    if items == ["none"]:
        return []
    out = []
    for it in items:
        desc, _, off = it.rpartition("@") if "@" in it else (it, "", "0")
        out.append({"kind": "sfx", "description": desc.strip(), "start_offset": float(off or 0)})
    return out


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
        "tts_evidence": tts_evidence(orch, project),
        "audio_evidence": audio_evidence(orch, project, getattr(job.kind, "value", str(job.kind))),
    }, ensure_ascii=False, indent=2))


def cmd_run(args: argparse.Namespace) -> int:
    settings = Settings()
    if args.tts:
        settings.tts_provider = args.tts
    if getattr(args, "voice", None):
        settings.tts_default_voice = args.voice
    if getattr(args, "audio", None):
        settings.audio_provider = args.audio
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
    settings = Settings()
    if args.audio:
        settings.audio_provider = args.audio
    _, orch = build(settings)
    project = orch.store.load(args.project_id)
    cues = _parse_sfx(args.sfx)
    if cues is not None:  # 保留本景既有的 bgm／其他 cue，只替換 sfx
        cues = [c.model_dump() for c in project.scene(args.scene_id).audio_cues if c.kind != "sfx"] + cues
    orch.update_scene(project, args.scene_id, audio_cues=cues, narration=args.narration, subtitle_override=args.subtitle,
                      image_prompt=args.image_prompt, image_prompt_en=args.image_prompt_en,
                      camera_motion=args.camera, transition=args.transition,
                      voice=args.voice, narrator_id=args.narrator, speech_speed=args.speed,
                      character_ids=args.characters, lipsync={"on": True, "off": False}.get(args.lipsync))
    report = orch.rebuild(project)
    for r in report.scene_reports:
        print(f"{r.scene_id}: rebuilt={r.rebuilt} reused={r.reused}")
    _print_summary(orch, report.project, report.job, report.timeline)
    return 0


def cmd_regen(args: argparse.Namespace) -> int:
    _, orch = build()
    project = orch.store.load(args.project_id)
    r = orch.regenerate_scene(project, args.scene_id)
    ev = next(e for e in image_evidence(orch, project) if e["scene_id"] == r.scene_id)
    print(f"{r.scene_id}: rebuilt={r.rebuilt} image: generated_by={ev['generated_by']} final_dtype={ev['final_dtype']} "
          f"numeric_downgrade={ev['numeric_downgrade']} fallback={ev['fallback']}", file=sys.stderr)
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


def cmd_doctor(args: argparse.Namespace) -> int:
    """D-064 Environment Doctor：唯讀檢查（--write-manifest 才寫 workspace/environment_manifest.json）。"""
    from see.core.environment import run_doctor, write_manifest

    s = Settings()
    rep = run_doctor(s, hash_files=args.hash)
    if args.json:
        print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2))
    else:
        group = None
        for c in rep.checks:
            if c.group != group:
                group = c.group
                print(f"--- {group}")
            req = "REQUIRED" if c.required else "optional"
            print(f"[{c.status.value:11s}] {c.name:24s} {req:8s} {c.detail}")
            if c.hint and c.status.value != "OK":
                print(f"{'':14s}→ {c.hint}")
        print("--- 基本設定（優先序：環境變數 > see.local.json > 程式預設）")
        from see.core.config import setting_source

        for k in ("SEE_MODELS_DIR", "SEE_IMAGE_PROVIDER", "SEE_TTS_PROVIDER"):
            v, src = setting_source(k)
            print(f"  {k:20s} {v or '(未設定：使用程式預設)'}  [來源：{src}]")
        print("--- Ready for")
        for k, v in rep.readiness["ready"].items():
            print(f"  ✓ {k:32s} {v}")
        print("--- Not ready for")
        for k, v in rep.readiness["not_ready"].items():
            print(f"  ✗ {k:32s} {v}")
        print("--- Tiers")
        for k, v in rep.tiers.items():
            print(f"  {k:18s} {v['status']:11s} " + ("缺：" + "；".join(v["missing"]) if v["missing"] else ""))
    if args.write_manifest:
        print(f"manifest → {write_manifest(rep, s)}", file=sys.stderr)
    if rep.failed_required:
        print(f"REQUIRED 項目失敗：{rep.failed_required}", file=sys.stderr)
        return 1
    return 0


def cmd_bootstrap(args: argparse.Namespace) -> int:
    """D-064 Bootstrap：預設只列計畫（唯讀）；--apply-safe 只建立缺少的空 workspace 資料夾與版本檔。"""
    from see.core.environment import apply_safe, bootstrap_plan, run_doctor

    s = Settings()
    if args.apply_safe:
        done = apply_safe(s)
        print("已執行（只建立、不刪除、不覆寫）：" + ("；".join(done) if done else "無需變更"))
    plan = bootstrap_plan(run_doctor(s), s)
    if args.json:
        print(json.dumps(plan, ensure_ascii=False, indent=2))
        return 0
    titles = {"auto_safe": "1. 可自動完成（需 --apply-safe 才執行）", "user_action": "2. 需使用者操作",
              "needs_approval": "3. 需下載／安裝裁示（不會自動執行）", "blocked": "4. 目前 blocked（不要做）"}
    for k, title in titles.items():
        print(f"--- {title}")
        for it in plan[k] or [{"item": "（無）", "detail": "", "command": ""}]:
            print(f"  • {it['item']}" + (f"：{it['detail']}" if it["detail"] else ""))
            if it["command"]:
                print(f"      {it['command']}")
    if not args.apply_safe:
        print("（唯讀：未安裝、未下載、未修改任何系統設定）")
    return 0


def cmd_env_export(args: argparse.Namespace) -> int:
    """D-064 匯出可恢復資訊（manifest、套件清單、模型 ID／hash、workspace／角色／reference metadata、設定）；不含模型與私人圖片。"""
    from see.core.environment import export_environment

    try:
        out = export_environment(Settings(), Path(args.out) if args.out else None, hash_files=args.hash)
    except FileExistsError as e:
        print(str(e), file=sys.stderr)
        return 1
    print(f"exported → {out}")
    for p in sorted(out.iterdir()):
        print(f"  {p.name}  {p.stat().st_size} bytes")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    """D-065 專案本機設定檔（see.local.json；machine-specific；不進 Git）。只有 set／unset 會寫檔。"""
    from see.core.config import (LOCAL_CONFIG_KEYS, LocalConfigError, local_config_path, read_local_config, setting_source,
                                 write_local_config)

    path = local_config_path()
    if args.action in ("set", "unset"):
        if args.key not in LOCAL_CONFIG_KEYS:
            print(f"未知設定 {args.key!r}；可用：{sorted(LOCAL_CONFIG_KEYS)}（只收 machine-specific，不收 secret／專案偏好）", file=sys.stderr)
            return 2
        if args.action == "set" and not args.value:
            print("config set 需要值", file=sys.stderr)
            return 2
        try:
            write_local_config({args.key: args.value if args.action == "set" else None}, path)
        except LocalConfigError as e:
            print(str(e), file=sys.stderr)
            return 1
        print(f"已寫入 {path.name}：{args.key} = {args.value if args.action == 'set' else '(移除)'}")
    local, err = read_local_config(path)
    print(f"本機設定檔：{path}（{'不存在' if not path.is_file() else '格式錯誤，未採用：' + err if err else '有效'}）")
    for key, env_name in LOCAL_CONFIG_KEYS.items():
        v, src = setting_source(env_name, local=local)
        print(f"  {key:18s} {v or '(程式預設)'}  [來源：{src}；環境變數 {env_name}]")
    return 1 if err else 0


def cmd_cast(args: argparse.Namespace) -> int:
    """D-068 唯讀：顯示 Project.cast 的 pinned revision 與 readiness（foundation；尚非 production 角色來源）。"""
    from see.core.cast import resolve_project_cast
    from see.storage.character_store import CharacterStore

    s = Settings()
    from see.storage.project_store import ProjectStore

    try:
        project = ProjectStore(s.workspace).load(args.project_id)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    rep = resolve_project_cast(project, CharacterStore(s.workspace))
    if args.json:
        print(json.dumps(rep.to_dict(include_snapshot=False), ensure_ascii=False, indent=2))
        return 0 if rep.status in ("not_configured", "ok") else 1
    print(f"Project {project.project_id} cast：{rep.status}（foundation；production 角色來源仍是 Project.characters）")
    for e in rep.entries:
        b = e.binding
        label = " ".join(x for x in (b.role_label, f"({b.alias})" if b.alias else "") if x)
        state = "OK" if e.integrity == "ok" and e.generation_ready else "NOT READY" if e.integrity == "ok" else "ERROR"
        print(f"  {b.character_id}@r{b.character_revision} {label}  [{state}]"
              + (f" archived" if e.archived else "") + (f" missing={e.missing_references}" if e.missing_references else "")
              + (f" — {e.error}" if e.error and e.integrity == "error" else ""))
    return 0 if rep.status in ("not_configured", "ok") else 1


def cmd_character_migrate(args: argparse.Namespace) -> int:
    """D-069 Batch 4：舊 Project.characters → Character Library／Project.cast 的 dry-run 分析（只讀）。
    Batch 4 only analyzes. No project has been migrated."""
    from datetime import datetime, timezone

    from see.core.character_migration import analyze, human_summary, workspace_digest

    if not args.dry_run:
        print("拒絕執行：實際 migration 尚未核准（Batch 5 需客戶確認 dry-run 報告後另行裁示）。請加 --dry-run 只做分析。", file=sys.stderr)
        return 2
    s = Settings()
    ws = s.workspace
    out = Path(args.out).resolve() if args.out else None
    if out is not None and out.is_relative_to(ws.resolve()):
        print(f"拒絕：報告不可寫進 workspace（{ws}）內，以免影響 zero-write 驗證；請指定 workspace 以外的路徑或用 stdout", file=sys.stderr)
        return 2
    if out is not None and out.exists():
        print(f"拒絕：{out} 已存在（不覆寫）", file=sys.stderr)
        return 2
    before = workspace_digest(ws)
    try:
        result = analyze(args.project_id, ws)
    except FileNotFoundError as e:
        print(str(e), file=sys.stderr)
        return 1
    after = workspace_digest(ws)
    proof = {"workspace_digest_before": before, "workspace_digest_after": after, "unchanged": before == after}
    envelope = {"migration_report_schema_version": result["report"]["migration_report_schema_version"],
                "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),  # 不進 report_sha256
                "report_sha256": result["report_sha256"], "zero_write_proof": proof, "report": result["report"]}
    text = json.dumps(envelope, ensure_ascii=False, indent=2, sort_keys=True) if args.json else \
        human_summary(result) + f"\nzero-write：{'通過（workspace 前後一致）' if proof['unchanged'] else '失敗！workspace 有變動'}"
    if out is not None:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "x", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"report → {out}")
    else:
        print(text)
    return 0 if proof["unchanged"] else 3


def cmd_smoke(args: argparse.Namespace) -> int:
    """D-064 Smoke test（不需 GPU；暫存 workspace；mock／placeholder／silent）。"""
    from see.core.environment import Status, smoke_test

    res = smoke_test()
    for name, st, detail in res:
        print(f"[{st.value:11s}] {name:16s} {detail}")
    return 1 if any(st == Status.ERROR for _, st, _ in res) else 0


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


def cmd_tts_setup(args: argparse.Namespace) -> int:
    """印出 Kokoro（D-027 候選）安裝與下載步驟；不執行安裝、不下載。"""
    from see.core.hardware import detect_hardware
    from see.providers.tts.kokoro import KokoroTTSProvider, download_plan, local_voices, read_provenance, weights_present

    s = Settings()
    plan = download_plan()
    dest = Path(s.tts_model_path) if s.tts_model_path else s.models_dir / KokoroTTSProvider.DEFAULT_DIRNAME
    hw = detect_hardware(".")
    win = hw.os == "Windows"
    print(f"# 機器：{hw.os} · Python {hw.python}")
    print(f"# 候選：{plan['repo_id']} · {plan['license']} · 預估下載 ≈{plan['estimated_mb']} MB · 存放 {dest} · {plan['approval']}")
    print(f"# 現況：weights_present={weights_present(dest)} voices={local_voices(dest)} provenance={'yes' if read_provenance(dest) else 'no'}")
    print("# 依序執行（每行一步；一次只做一步）：")
    print("pip install " + " ".join(f'"{p}"' for p in plan["pip"]))
    print("python -m see.app.cli tts-download --yes")
    print("python -m see.app.cli tts-check")
    print(("set" if win else "export") + " SEE_TTS_PROVIDER=auto")
    return 0


def cmd_tts_download(args: argparse.Namespace) -> int:
    """下載 Kokoro v1.1-zh 權重到 SEE_MODELS_DIR/kokoro-v1_1-zh（僅 D-027 已核准的 ≈330 MB）。沒有 --yes 只印計畫。"""
    from see.providers.tts.kokoro_download import download_kokoro, plan_text

    s = Settings()
    dest = Path(args.dest).resolve() if args.dest else (Path(s.tts_model_path) if s.tts_model_path else s.models_dir / "kokoro-v1_1-zh")
    print(plan_text(dest))
    if not args.yes:
        print("未加 --yes：只顯示計畫，未下載任何檔案。", file=sys.stderr)
        return 0
    try:
        prov = download_kokoro(dest, voices=args.voices)
    except ImportError as e:
        print(f"缺少套件：{e}（pip install huggingface_hub）", file=sys.stderr)
        return 1
    print(json.dumps(prov, ensure_ascii=False, indent=2))
    return 0


def cmd_character(args: argparse.Namespace) -> int:
    """設定／確認／列出角色 voice（Voice Selection 非 UI 版；D-030）。"""
    _, orch = build()
    project = orch.store.load(args.project_id)
    if args.character_id and not args.list:
        if args.confirm:
            ch = orch.confirm_character(project, args.character_id)
        else:
            ch = orch.set_character(project, args.character_id, display_name=args.name, voice_id=args.voice,
                                    speed=args.speed, clear_speed=args.clear_speed)
        print(json.dumps(ch.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0
    print(json.dumps({"characters": {k: v.model_dump(mode="json") for k, v in project.characters.items()},
                      "scenes": [{"scene_id": s.scene_id, "narrator_id": s.narrator_id, "voice": s.voice, "speech_speed": s.speech_speed,
                                  "resolved": dict(zip(("voice", "speed", "source"), orch.resolve_voice(project, s)))} for s in project.scenes],
                      "unconfirmed": orch.unconfirmed_characters(project)}, ensure_ascii=False, indent=2))
    return 0


def cmd_style(args: argparse.Namespace) -> int:
    """列出 Style Profile；給 project_id + style_id 則設定該專案風格（D-032）。"""
    from see.core.styles import BUILTIN_STYLES

    if args.project_id and args.style_id:
        _, orch = build()
        project = orch.set_style(orch.store.load(args.project_id), args.style_id)
        print(json.dumps({"project_id": project.project_id, "style_id": project.style_id, "status": project.status}, ensure_ascii=False))
        return 0
    print(json.dumps([s.model_dump() for s in BUILTIN_STYLES.values()], ensure_ascii=False, indent=2))
    return 0


STYLE_TEST_SCENE = "小貓咪在院子裡追蝴蝶，陽光很溫暖"  # = STYLE_TEST_CASES["kitten_butterfly"]（相容舊引用）
STYLE_TEST_SEED = 1234


def _style_test_stem(style_id: str, case_id: str, seed: int, gen_policy: str, custom_prompt: bool,
                     checkpoint_id: str | None = None, scheduler: str | None = None, prompt_mode: str | None = None) -> str:
    """基準條件沿用舊檔名（<style>_seed<seed>）；任何診斷變數都加後綴 → 永不覆寫既有失敗證據。"""
    stem = f"{style_id}_seed{seed}"
    if case_id != "kitten_butterfly":
        stem += f"_{case_id}"
    if gen_policy != "fit":
        stem += f"_{gen_policy}"
    if custom_prompt:
        stem += "_customprompt"
    if checkpoint_id:
        stem += f"_ckpt-{checkpoint_id}"
    if scheduler and scheduler != "default":
        stem += f"_sched-{scheduler}"
    if prompt_mode:
        stem += f"_{prompt_mode}"
    return stem


def _style_test_image_provider(s: Settings, checkpoint_id: str | None, scheduler: str | None, identity_id: str | None = None):
    """D-039：指定 checkpoint 或 scheduler 時直接建 DiffusersImageProvider（**不 fallback 到 placeholder**，fail-closed）。
    回傳 (provider, error)；兩者都沒指定 → (None, None)，沿用 registry 的 image provider。"""
    if not checkpoint_id and not scheduler and not identity_id:
        return None, None
    from see.providers.image.checkpoints import checkpoint_file, get_checkpoint, read_provenance
    from see.providers.image.diffusers_local import DiffusersImageProvider

    base = s.image_model_path or str(s.models_dir / "sd15")
    spec = get_checkpoint(checkpoint_id) if checkpoint_id else None
    path = str(checkpoint_file(s.models_dir, spec)) if spec else None
    if spec is not None:
        prov = read_provenance(s.models_dir, spec)
        if not prov or not prov.get("verified") or prov.get("local_sha256") != spec.sha256:
            from see.core.config import setting_source

            if setting_source("SEE_MODELS_DIR")[1] == "unset":  # D-064／D-065：區分「模型目錄未設定」與「未驗證」
                return None, (f"模型目錄未設定：環境變數與 see.local.json 都沒有 models_dir，程式在預設 {s.models_dir} 找不到 {spec.checkpoint_id}；"
                              f"請先 `python -m see.app.cli config set models_dir \"E:\\AI\\models\"` 再執行 `python -m see.app.cli doctor`")
            return None, (f"checkpoint {spec.checkpoint_id} 沒有通過驗證的 provenance（{checkpoint_file(s.models_dir, spec).parent}）；"
                          f"若是從舊機搬來，先 `python -m see.app.cli doctor --hash` 確認；否則 "
                          f"`python -m see.app.cli checkpoint-download {spec.checkpoint_id} --yes`")
        if Path(path).stat().st_size != spec.bytes:
            return None, f"checkpoint 檔案大小與 provenance 不符：{path}"
    id_spec, id_dir = None, None
    if identity_id:
        from see.providers.image import adapters as ad

        id_spec = ad.get_adapter(identity_id)
        try:
            ad.assert_usable(id_spec)
        except (PermissionError, ValueError) as e:
            return None, str(e)
        if not ad.is_verified(s.models_dir, id_spec):
            return None, (f"identity adapter {identity_id} 沒有通過驗證的 provenance（{ad.adapter_dir(s.models_dir, id_spec)}）；"
                          f"請先 `python -m see.app.cli adapter-download {identity_id} --yes`（或確認 SEE_MODELS_DIR）")
        id_dir = str(ad.adapter_dir(s.models_dir, id_spec))
    prov_obj = DiffusersImageProvider(preset="sd15", model_path=base, checkpoint=spec, checkpoint_path=path, scheduler=scheduler,
                                      identity_adapter=id_spec, identity_dir=id_dir)
    if not prov_obj.is_available():
        return None, prov_obj.unavailable_reason()
    return prov_obj, None


def cmd_style_test(args: argparse.Namespace) -> int:
    """Style 真機驗收（DG-18 A；分層判定 D-035）：同一案例／seed／尺寸，只換 Style Profile，出一張圖。
    輸出到 workspace/style_tests/（**不建立專案、不寫任何 manifest、不動快取**）；同時寫 evidence json。
    `technical_valid` 自動判定；`scene_validated`／`style_validated` 只能由 `style-review` 人工填入。"""
    import time

    from see.core.hashing import file_sha256
    from see.core.image_qa import image_stats
    from see.core.prompting import build_image_prompt_en, default_negative_prompt
    from see.core.style_tests import get_case, prompt_subject_check, technical_validity
    from see.core.styles import apply_style, get_style
    from see.pipeline.orchestrator import IMAGE_SCALE
    from see.providers.base import ImageRequest

    s = Settings()
    if s.image_provider == "placeholder":
        s.image_provider = "auto"  # 風格驗收必須走本機生圖；沒有權重時 auto 會退回 placeholder，下面會標為無效
    style = get_style(args.style)
    case = get_case(args.case)
    from see.core.style_tests import STYLE_TEST_CASES, case_base_prompt

    if args.scene and args.scene in STYLE_TEST_CASES:
        # 防呆（D-041）：`--scene girl_city_night` 會把案例 id 當成中文場景字串 → 關鍵詞全落空、prompt 變成泛用描述
        print(f"錯誤：'{args.scene}' 是測試案例 id，請改用 `--case {args.scene}`（--scene 只接受中文場景描述）", file=sys.stderr)
        return 2
    scene = args.scene or case.scene_zh
    seed = case.seed if args.seed is None else args.seed
    _, orch = build(s)
    refs, err = (_identity_references(s, case, args.ref or []) if args.identity else ([], None))
    if err:
        print(f"錯誤：{err}", file=sys.stderr)
        return 2
    if args.identity and args.regional:
        print("錯誤：--identity 不與 --regional（S2）疊加（D-054）", file=sys.stderr)
        return 2
    image, err = _style_test_image_provider(s, args.checkpoint, args.scheduler, args.identity)
    if err:
        print(f"錯誤：{err}", file=sys.stderr)
        return 2
    image = image or orch.p.image
    if args.base_prompt:
        base_prompt, prompt_source = args.base_prompt, "base_prompt_override"
    else:
        base_prompt, prompt_source = case_base_prompt(case, args.scene, build_image_prompt_en)
    base_negative = default_negative_prompt()
    prompt, negative, params = apply_style(base_prompt, base_negative, style, image.info.name)
    req_params: dict[str, object] = {"style": params} if params else {}
    if args.gen_policy != "fit":
        req_params["gen_policy"] = args.gen_policy
    # D-051（DG-24 A）：S1／S2 皆 opt-in 診斷；不帶旗標時 params 與既有完全相同
    if args.regional:
        if not case.characters:
            print(f"錯誤：--regional 需要多角色案例（例 two_characters_ab）；{case.case_id} 沒有 characters", file=sys.stderr)
            return 2
        from see.core.style_tests import regional_prompts

        rb, rr = regional_prompts(case)
        req_params["prompt_mode"] = {"long_prompt": True, "regional": {
            "base": apply_style(rb, "", style, image.info.name)[0],
            "regions": [apply_style(t, "", style, image.info.name)[0] for t in rr], "layout": "columns"}}
    elif args.long_prompt:
        req_params["prompt_mode"] = {"long_prompt": True}
    if args.identity:  # D-054（S4，opt-in）：每角色獨立參考圖＋分欄 mask
        req_params["identity"] = {"adapter_id": args.identity, "references": refs, "layout": "columns"}
    req = ImageRequest(prompt=prompt, negative_prompt=negative, width=int(s.width * IMAGE_SCALE), height=int(s.height * IMAGE_SCALE),
                       seed=seed, caption=f"style-test {style.style_id}", params=req_params)
    orch._gate(image.estimate_cost, _StyleTestBudget(), req)
    out_dir = s.workspace / "style_tests"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (_style_test_stem(style.style_id, case.stem_id, seed, args.gen_policy, bool(args.base_prompt),
                                      args.checkpoint, args.scheduler,
                                      "regional" if args.regional else ("longprompt" if args.long_prompt else None))
           + _identity_stem_suffix(args.identity, refs) + ".png")
    t0 = time.perf_counter()
    res = image.generate_image(req, out)
    elapsed = round(time.perf_counter() - t0, 2)
    generated_by = res.meta.get("generated_by", res.provider)
    stats = image_stats(Path(res.path)).to_dict()
    tech = technical_validity(generated_by, stats)
    diag = {k: res.meta.get(k) for k in ("gen_policy", "gen_width", "gen_height", "crop_box", "upscale_factor", "steps", "guidance",
                                          "scheduler", "prompt_tokens", "negative_tokens", "token_limit", "prompt_truncated",
                                          "negative_truncated", "weights_variant", "attempts", "scheduler_name",
                                          "clip_skip_a1111", "clip_skip_diffusers", "vram_peak_mb", "final_max_side",
                                          "prompt_mode", "prompt_encoding", "prompt_truncated_effective", "identity",
                                          "oom_downgrade", "numeric_downgrade", "initial_plan", "final_plan") if k in res.meta}
    ev = {"style_id": style.style_id, "style_display_name": style.display_name, "case_id": case.case_id,
          "scene": scene, "seed": seed, "width": req.width, "height": req.height,
          # D-043：舊 `fair_comparison` 更名——它只表示「fit 基準條件、無診斷覆寫」，不代表跨次比較公平；
          # 兩張圖是否只差一個變數請用 `style-compare <stem_a> <stem_b>`（逐項比對 comparison_conditions）
          "baseline_condition": args.gen_policy == "fit" and not args.base_prompt and not args.scene,
          # D-039：checkpoint 只用於內部品質驗證；commercial_cleared 一律 false（不得用於正式商用輸出）
          "checkpoint": res.meta.get("checkpoint"), "commercial_cleared": False if args.checkpoint else None,
          "diagnostic_overrides": {"gen_policy": args.gen_policy, "base_prompt_override": bool(args.base_prompt),
                                   "scene_override": bool(args.scene), "long_prompt": bool(args.long_prompt or args.regional),
                                   "regional": bool(args.regional), "identity": args.identity},
          "base_prompt": base_prompt, "prompt": prompt, "negative_prompt": negative, "style_params": params,
          "provider": res.provider, "generated_by": generated_by, "final_dtype": res.meta.get("final_dtype"),
          "fallback": res.meta.get("fallback"), "fallback_from": res.meta.get("fallback_from"),
          "generation": diag, "image_stats": stats, "image_sha256": file_sha256(Path(res.path)),
          "elapsed_s": elapsed, "image_path": str(res.path), "cost": "NT$0",
          # ---- 分層判定（D-035）：只有 technical_valid 是自動的
          **tech,
          "prompt_subject_check": prompt_subject_check(prompt, case.expected_subjects_en),
          "scene_validated": None, "style_validated": None,
          "prompt_source": prompt_source,
          # D-049：多角色案例的角色錨點與「不得互換」屬性（人工審圖用；不是自動判定）
          # D-058：案例定義版本（A／B 性別修正後＝2）；舊 JSON 無此欄位＝v1＝historical_reversed_character_mapping
          "case_definition_version": case.definition_version,
          "historical_reversed_character_mapping": False,
          **({"character_definitions": [c.definition.model_dump(mode="json") for c in case.characters if c.definition is not None]}
             if case.characters else {}),
          **({"case_characters": [{"character_id": c.character_id, "position": c.position, "anchor": c.anchor,
                                   "swap_checks": list(c.swap_checks)} for c in case.characters]} if case.characters else {}),
          "human_review": {"status": "pending", "checklist": list(case.review_checklist or case.expected_subjects_en),
                           "subjective": "single-user subjective",
                           "how": f"python -m see.app.cli style-review {out.stem} --scene pass|fail --style pass|fail --note \"...\""},
          # 型錄旗標（該 StyleProfile 是否曾有真機驗收紀錄），不是本張圖的判定
          "style_profile_catalog_validated": style.validated}
    from see.core.style_tests import comparison_conditions

    ev["comparison_conditions"] = comparison_conditions(ev)
    if args.identity and isinstance(diag.get("identity"), dict):  # D-056：角色 ↔ 區域對照（含輸出圖座標）＋人工審圖疊圖
        ev["identity_region_map"] = identity_region_map(diag["identity"], diag.get("crop_box"))
        ev["identity_region_overlay"] = str(_identity_overlay(Path(res.path), ev["identity_region_map"]))
    out.with_suffix(".json").write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(ev, ensure_ascii=False, indent=2))
    if not ev["technical_valid"]:
        print(f"警告：本張技術無效（{'; '.join(ev['technical_reasons'])}），不能作為風格驗收證據。", file=sys.stderr)
        return 3
    print("注意：technical_valid=true 只代表技術上有效；scene／style 是否通過須人工 style-review。", file=sys.stderr)
    return 0


# D-056 Reference Library（workspace/identity_refs/<category>/；私人素材只在本機，不進 Git）
# D-058：主路徑 workspace/reference_library/，舊 workspace/identity_refs/ 為 legacy 相容；類別存在 ≠ 功能完成
REFERENCE_CATEGORIES = {"people": "人物身份／臉／全身／服裝／pose（identity_face：S4 --identity 研究用；其他用途 not yet supported）",
                        "animals": "動物外觀 reference（not yet supported）",
                        "characters": "虛構角色／角色設計 reference（not yet supported）",
                        "backgrounds": "場景／環境 reference（not yet supported）",
                        "styles": "風格／色調／畫風 reference（not yet supported）"}


def identity_region_map(identity: dict, crop_box: list | None) -> list[dict]:
    """生成座標的 mask 欄位 → 最終輸出圖座標（native 會中心裁切）。純函式，可測。"""
    left = int(crop_box[0]) if crop_box else 0
    out = []
    for r in identity.get("references") or []:
        x0, y0, x1, y1 = r["mask_bounds_gen_px"]
        if crop_box:
            cx0, cy0, cx1, cy1 = (int(v) for v in crop_box)
            x0, x1 = max(x0, cx0) - left, min(x1, cx1) - left
            y0, y1 = max(y0, cy0) - cy0, min(y1, cy1) - cy0
        out.append({"character_id": r["character_id"], "reference_sha256": r["sha256"], "assigned_region": r["assigned_region"],
                    "adapter_index": r["adapter_index"], "image_index": r["image_index"],
                    "mask_bounds_gen_px": r["mask_bounds_gen_px"], "mask_bounds_output_px": [x0, y0, x1, y1]})
    return out


def _identity_overlay(img_path: Path, region_map: list[dict]) -> Path:
    """人工審圖用：在輸出圖副本上框出每個角色的 identity 區域並標 character_id（只存本機 workspace，不進 Git）。"""
    from PIL import Image, ImageDraw

    im = Image.open(img_path).convert("RGB")
    d = ImageDraw.Draw(im)
    colors = [(255, 64, 64), (64, 160, 255), (64, 220, 120), (255, 200, 0)]
    for k, r in enumerate(region_map):
        x0, y0, x1, y1 = r["mask_bounds_output_px"]
        col = colors[k % len(colors)]
        d.rectangle([x0 + 2, y0 + 2, x1 - 3, y1 - 3], outline=col, width=4)
        d.text((x0 + 10, y0 + 10), f"{r['character_id']} ({r['assigned_region']}) ref {r['reference_sha256'][:8]}", fill=col)
    out = img_path.with_name(img_path.stem + "_identity_regions.png")
    im.save(out)
    return out


def _identity_stem_suffix(identity_id: str | None, refs: list[dict]) -> str:
    """D-060：reference 不同＝不同實驗 → 檔名帶各 reference sha256 前 8 碼；換 reference 重跑永不覆寫舊 evidence。"""
    if not identity_id:
        return ""
    return f"_identity-{identity_id}_ref-" + "-".join(r["sha256"][:8] for r in refs)


def _identity_references(s: Settings, case, ref_args: list[str]) -> tuple[list[dict], str | None]:
    """`--ref char_a=<style-test stem 或本機圖檔>`：每個案例角色都要一張。只讀本機（§16）；evidence 只記 sha256／bytes／來源，
    不複製圖片、不記內容。style-test stem → 本專案生成圖（非真人照片），一併記來源 evidence 檔名。"""
    from see.core.hashing import file_sha256

    if not case.characters:
        return [], f"--identity 需要多角色案例（{case.case_id} 沒有 characters）"
    given: dict[str, str] = {}
    for item in ref_args:
        if "=" not in item:
            return [], f"--ref 格式應為 <character_id>=<stem 或路徑>：{item}"
        k, v = item.split("=", 1)
        given[k.strip()] = v.strip()
    need = [c.character_id for c in case.characters]
    if sorted(given) != sorted(need):
        return [], f"每個角色需要一張獨立參考圖：需要 {need}，收到 {sorted(given)}"
    from see.core.style_tests import region_of

    try:  # D-056：依角色 position 明確排成左→右（mask 欄位 i ↔ refs[i]），不依賴 tuple／dict 順序
        ordered = sorted(case.characters, key=lambda c: region_of(c.position)[1])
    except ValueError as e:
        return [], str(e)
    if len({region_of(c.position)[0] for c in ordered}) != len(ordered):
        return [], "兩個角色的 position 相同，無法分配獨立 identity 區域"
    refs = []
    for c in ordered:
        cid = c.character_id
        v = given[cid]
        if "://" in v:
            return [], f"參考圖只接受本機檔案（PROJECT_RULES §16）：{v}"
        st = s.workspace / "style_tests" / f"{v}.png"
        lib_root = next((r for r in _library_roots(s) if (r / v).is_file()), None) if not Path(v).is_absolute() else None
        lib = lib_root / v if lib_root is not None else None
        category = None
        if st.exists():
            path, source, src_ev = st, "style_test_output", f"{v}.json"
        elif lib is not None and lib.resolve().is_relative_to(lib_root.resolve()):
            category = Path(v).parts[0]
            if category not in REFERENCE_CATEGORIES:
                return [], f"Reference Library 類別未知：{category}（可用 {list(REFERENCE_CATEGORIES)}）"
            if category != "people":  # 目前 S4 只做人物臉部 identity；不得假裝支援其他類別
                return [], f"--identity 目前只支援 people/ 人物參考圖；{category}/ not yet supported（BACKLOG，D-056／D-058）"
            path, source, src_ev = lib, "reference_library" if lib_root.name == "reference_library" else "reference_library_legacy", None
        else:
            path, source, src_ev = Path(v), "local_file", None
        if not path.is_file():
            have = sorted(p.stem for p in (s.workspace / "style_tests").glob("*.png")) if (s.workspace / "style_tests").exists() else []
            return [], f"找不到參考圖 {v}（可用 style-test 產出：{have}）"
        sha = file_sha256(path)
        meta, err = _reference_sidecar(path, cid, sha)
        if err:
            return [], err
        refs.append({"character_id": cid, "path": str(path), "sha256": sha, "bytes": path.stat().st_size,
                     "source": source, "source_evidence": src_ev, "library_category": category, "position": c.position,
                     "region": region_of(c.position)[0], "asset_metadata": meta})
    err = _character_gate(case, refs)
    if err:
        return [], err
    return refs, None


def _library_roots(s: Settings) -> list[Path]:
    """D-058：Reference Library 主路徑 workspace/reference_library/；workspace/identity_refs/ 為 legacy 相容路徑（D-056）。"""
    return [s.workspace / "reference_library", s.workspace / "identity_refs"]


def _reference_sidecar(path: Path, character_id: str, sha: str) -> tuple[dict | None, str | None]:
    """選用 metadata sidecar `<圖檔>.ref.json`（ReferenceAsset schema）。存在時必須與本次綁定一致，否則 fail closed。
    不存在時，綁定只來自使用者顯式的 `--ref <character_id>=…`（不從檔名或資料夾猜身份）。"""
    side = path.with_name(path.name + ".ref.json")
    if not side.is_file():
        return None, None
    from see.models.character_definition import ReferenceAsset

    try:
        asset = ReferenceAsset.model_validate_json(side.read_text(encoding="utf-8"))
    except ValueError as e:
        return None, f"reference metadata 格式錯誤（{side.name}）：{e}"
    if asset.character_id != character_id:
        return None, f"reference metadata 衝突：{path.name} 綁定 {asset.character_id}，但 --ref 指給 {character_id}"
    if asset.sha256 != sha:
        return None, f"reference metadata 衝突：{path.name} 的 sha256 與 metadata 不符（檔案被換過？）"
    if asset.role.value != "identity_face":
        return None, f"reference 用途不符：{path.name} 為 {asset.role.value}，--identity 需要 identity_face"
    return asset.model_dump(mode="json"), None


def _character_gate(case, refs: list[dict]) -> str | None:
    """D-058 Character Validation Gate（--identity 路徑）：任何 blocking 衝突 → 不生成。"""
    from see.core.style_tests import region_of
    from see.models.character_definition import (CharacterDefinition, CommercialClearance, RefCategory, ReferenceAsset, RefRole,
                                                 ScenePlacement, SourceType, blocking, validate_characters)

    defs = [c.definition if c.definition is not None else CharacterDefinition(character_id=c.character_id, display_name=c.character_id)
            for c in case.characters]
    for d, r in zip(sorted(defs, key=lambda d: d.character_id), sorted(refs, key=lambda r: r["character_id"])):
        if r["character_id"] != d.character_id:
            return f"reference 綁定不一致：{r['character_id']} vs {d.character_id}"
    assets = []
    for r in refs:
        m = r.get("asset_metadata") or {}
        assets.append(ReferenceAsset(
            asset_id=m.get("asset_id") or f"ref_{r['character_id']}", category=RefCategory.people, file_path=r["path"],
            character_id=r["character_id"], role=RefRole.identity_face, sha256=r["sha256"],
            source_type=SourceType(m["source_type"]) if m.get("source_type") else
            (SourceType.generated if r["source"] == "style_test_output" else SourceType.user_supplied),
            commercial_clearance_status=CommercialClearance(m.get("commercial_clearance_status") or "unknown")))
    placements = [ScenePlacement(character_id=c.character_id, horizontal=region_of(c.position)[0]) for c in case.characters]
    issues = validate_characters(defs, assets, placements, repo_root=Path(__file__).resolve().parents[2])
    hard = blocking(issues)
    if hard:
        return "Character Validation Gate 未通過（不生成，請修正）：" + "；".join(i.message for i in hard)
    return None


def cmd_adapter_download(args: argparse.Namespace) -> int:
    """D-054（DG-25）：只下載型錄內、已核准的 Identity adapter（safetensors／json；固定 revision；逐檔 bytes＋sha256）。"""
    import shutil

    from see.providers.image import adapters as ad

    s = Settings()
    spec = ad.get_adapter(args.adapter_id)
    dest = ad.adapter_dir(s.models_dir, spec)
    plan = {"adapter_id": spec.adapter_id, "repo": spec.repo, "revision": spec.revision,
            "files": [{"path": f.path, "bytes": f.bytes, "sha256": f.sha256} for f in spec.files],
            "total_bytes": spec.total_bytes, "gb": round(spec.total_bytes / 1e9, 3), "license_status": spec.license_status,
            "approved": spec.approved, "commercial_cleared": spec.commercial_cleared, "usage": spec.usage, "dest": str(dest)}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    try:
        ad.assert_usable(spec)
    except (PermissionError, ValueError) as e:
        print(f"拒絕：{e}", file=sys.stderr)
        return 3
    if ad.is_verified(s.models_dir, spec):
        print(f"已存在且通過驗證：{dest}；略過下載。")
        return 0
    if args.verify:  # 搬移自他機：只做本機核對，不下載
        errs = ad.verify_local(s.models_dir, spec)
        if errs:
            print(json.dumps({"verified": False, "errors": errs}, ensure_ascii=False, indent=2))
            return 3
        ad.write_provenance(s.models_dir, spec, {f.path: {"bytes": f.bytes, "sha256": f.sha256} for f in spec.files})
        print("本機檔案核對通過（未下載），已寫 provenance。")
        return 0
    if args.check:
        try:
            remote = ad.fetch_remote_metadata(spec)
        except Exception as e:  # noqa: BLE001
            print(f"遠端核對失敗（{type(e).__name__}: {e}）；未下載任何檔案。", file=sys.stderr)
            return 1
        errs = ad.validate_remote(spec, remote)
        base = dest if dest.exists() else (s.models_dir if s.models_dir.exists() else Path("."))
        free = shutil.disk_usage(base).free
        print(json.dumps({"match": not errs, "errors": errs, "disk_free_gb": round(free / 1e9, 1),
                          "enough_disk": free > spec.total_bytes * 1.1}, ensure_ascii=False, indent=2))
        print("核對通過，未下載任何檔案。" if not errs else "核對失敗，不可下載。", file=sys.stderr)
        return 0 if not errs else 3
    if not args.yes:
        print("未加 --yes：只顯示計畫，未下載任何檔案。", file=sys.stderr)
        return 0
    try:
        prov = ad.download_adapter(s.models_dir, spec)
    except Exception as e:  # noqa: BLE001
        print(f"下載失敗或驗證不符（{type(e).__name__}: {e}）", file=sys.stderr)
        return 3
    print(json.dumps({"adapter_id": prov["adapter_id"], "verified": prov["verified"], "local_files": prov["local_files"],
                      "commercial_cleared": prov["commercial_cleared"], "usage": prov["usage"]}, ensure_ascii=False, indent=2))
    print("下載完成且 bytes／sha256 全部相符；僅限內部 S4 PoC，commercial_cleared=false。", file=sys.stderr)
    return 0


def cmd_checkpoint_download(args: argparse.Namespace) -> int:
    """D-039：只下載型錄內、客戶核准的單檔 safetensors。無 --yes／--check 只印計畫。"""
    import shutil

    from see.providers.image import checkpoints as ck

    s = Settings()
    spec = ck.get_checkpoint(args.checkpoint_id)
    dest = ck.checkpoint_file(s.models_dir, spec)
    plan = {"checkpoint_id": spec.checkpoint_id, "name": f"{spec.display_name} {spec.version}", "filename": spec.filename,
            "bytes": spec.bytes, "gb": round(spec.bytes / 1e9, 3), "sha256": spec.sha256, "official_source": spec.official_source,
            "download_from": f"https://huggingface.co/{spec.download_repo}（revision {spec.download_revision}）",
            "download_note": spec.download_note, "license_status": spec.license_status,
            "commercial_cleared": spec.commercial_cleared, "usage": spec.usage, "dest": str(dest)}
    print(json.dumps(plan, ensure_ascii=False, indent=2))
    prov = ck.read_provenance(s.models_dir, spec)
    if prov and prov.get("verified") and dest.exists() and dest.stat().st_size == spec.bytes:
        print(f"已存在且通過驗證（{prov.get('downloaded_at')}）：{dest}；略過下載。")
        return 0
    if args.check:
        try:
            remote = ck.fetch_remote_metadata(spec)
        except Exception as e:  # noqa: BLE001
            print(f"遠端核對失敗（{type(e).__name__}: {e}）；未下載任何檔案。", file=sys.stderr)
            return 1
        errs = ck.validate_remote(spec, remote)
        free = shutil.disk_usage(dest.parent if dest.parent.exists() else s.models_dir if s.models_dir.exists() else Path(".")).free
        print(json.dumps({"remote": remote, "match": not errs, "errors": errs, "disk_free_gb": round(free / 1e9, 1),
                          "enough_disk": free > spec.bytes * 1.1}, ensure_ascii=False, indent=2))
        print("核對通過，未下載任何檔案。" if not errs else "核對失敗，不可下載。", file=sys.stderr)
        return 0 if not errs else 3
    if not args.yes:
        print("未加 --yes：只顯示計畫，未下載任何檔案。", file=sys.stderr)
        return 0
    try:
        prov = ck.download_checkpoint(s.models_dir, spec)
    except Exception as e:  # noqa: BLE001
        print(f"下載失敗或驗證不符（{type(e).__name__}: {e}）", file=sys.stderr)
        return 3
    print(json.dumps({k: prov[k] for k in ("checkpoint_id", "local_file", "local_bytes", "local_sha256", "verified",
                                            "commercial_cleared", "usage", "downloaded_at")}, ensure_ascii=False, indent=2))
    print("下載完成且 sha256 相符；僅限內部品質驗證，commercial_cleared=false。", file=sys.stderr)
    return 0


def cmd_style_review(args: argparse.Namespace) -> int:
    """人工審圖結果寫回 evidence json（scene_validated／style_validated 唯一來源；主觀、單一審查者）。"""
    from datetime import datetime, timezone

    from see.core.style_tests import verdict_to_bool

    path = Settings().workspace / "style_tests" / f"{args.stem}.json"
    if not path.exists():
        print(f"找不到 {path}；請先執行 style-test", file=sys.stderr)
        return 2
    ev = json.loads(path.read_text(encoding="utf-8"))
    if not ev.get("technical_valid", ev.get("valid_for_style_test", False)):
        print("此張 technical_valid=false，不能做 scene／style 審查", file=sys.stderr)
        return 3
    ev["scene_validated"] = verdict_to_bool(args.scene)
    ev["style_validated"] = verdict_to_bool(args.style)
    ev["human_review"] = {**ev.get("human_review", {}), "status": "reviewed", "scene": args.scene, "style": args.style,
                          "note": args.note or "", "reviewer": args.by, "subjective": True,
                          "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: ev[k] for k in ("style_id", "technical_valid", "scene_validated", "style_validated", "human_review")},
                     ensure_ascii=False, indent=2))
    return 0


def _compose_load_layer(d: Path, stem: str, role: str) -> tuple[dict, Path]:
    """合成來源只收 style-test 產出（有 evidence JSON、technical_valid=true）→ 每層 provenance 可追溯到生成條件。"""
    img, evp = d / f"{stem}.png", d / f"{stem}.json"
    if not img.is_file() or not evp.is_file():
        raise ValueError(f"{role}：找不到 style-test 產出 {stem}（.png＋.json）")
    ev = json.loads(evp.read_text(encoding="utf-8"))
    if not ev.get("technical_valid"):
        raise ValueError(f"{role}：{stem} technical_valid=false，不能作為合成來源")
    from see.core.style_tests import historical_reversed_character_mapping

    if historical_reversed_character_mapping(ev):
        raise ValueError(f"{role}：{stem} 屬 historical_reversed_character_mapping（舊 A／B 定義相反，D-058），不能作為角色層")
    return ev, img


def _layer_character_id(ev: dict, layer_id: str) -> str:
    """角色層以穩定 character_id 綁定（D-058）：來源 evidence 只能有一個角色，且必須等於 layer_id；不以 A／B、左右或性別推論。"""
    chars = [c.get("character_id") for c in ev.get("case_characters") or []]
    if len(chars) != 1:
        raise ValueError(f"layer {layer_id}：來源必須是單人角色層（evidence case_characters={chars}）")
    if chars[0] != layer_id:
        raise ValueError(f"layer {layer_id}：來源圖片屬於 {chars[0]}，與 layer 的 character_id 不符（不生成）")
    return chars[0]


def cmd_compose_scene(args: argparse.Namespace) -> int:
    """D-057（DG-26 Route A）：背景層＋各角色層（各自 style-test 單獨生成）→ 去背 → 擺位 → 合成。
    不生成、不下載、不改任何 style-test evidence；重做某角色＝只重跑該角色的 style-test 再重新合成。"""
    import numpy as np
    from PIL import Image

    import hashlib

    from see.core import compose as cp
    from see.core.hashing import file_sha256
    from see.core.image_qa import image_stats

    s = Settings()
    d = s.workspace / "style_tests"
    try:
        bg_ev, bg_img = _compose_load_layer(d, args.background, "background")
        specs = []
        for item in args.layer or []:
            if "=" not in item:
                raise ValueError(f"--layer 格式應為 <layer_id>=<style-test stem>：{item}")
            lid, stem = (x.strip() for x in item.split("=", 1))
            specs.append((lid, stem))
        if not specs:
            raise ValueError("至少需要一個 --layer")
        ids = [lid for lid, _ in specs]
        if len(set(ids)) != len(ids):
            raise ValueError(f"layer_id 重複：{ids}")
        places = {}
        for item in args.place or []:
            lid, txt = item.split("=", 1)
            places[lid.strip()] = cp.Placement.parse(txt)
        if set(places) != set(ids):
            raise ValueError(f"每個 layer 都需要 --place（需要 {ids}，收到 {sorted(places)}）")
        order = [x.strip() for x in args.order.split(",")] if args.order else ids
        if sorted(order) != sorted(ids):
            raise ValueError(f"--order 必須恰好列出所有 layer：{ids}")
    except ValueError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 2
    key = json.dumps([args.background, sorted(specs), order, {k: vars(v) for k, v in sorted(places.items())}])
    name = args.name or "compose_" + hashlib.sha256(key.encode()).hexdigest()[:10]  # 同輸入＝同資料夾（可重現）
    out = s.workspace / "compositions" / name
    (out / "layers").mkdir(parents=True, exist_ok=True)
    background = np.asarray(Image.open(bg_img).convert("RGB"))
    layers, layer_ev = [], []
    for lid in order:
        stem = dict(specs)[lid]
        try:
            ev, img = _compose_load_layer(d, stem, lid)
        except ValueError as e:
            print(f"錯誤：{e}", file=sys.stderr)
            return 2
        try:
            character_id = _layer_character_id(ev, lid)
        except ValueError as e:
            print(f"錯誤：{e}", file=sys.stderr)
            return 2
        rgb = np.asarray(Image.open(img).convert("RGB"))
        alpha, matte = cp.key_matte(rgb, tolerance=args.key_tolerance, feather=args.feather)
        Image.fromarray((alpha * 255).astype(np.uint8)).save(out / "layers" / f"{lid}_mask.png")
        rgba = np.dstack([rgb, (alpha * 255).astype(np.uint8)])
        Image.fromarray(rgba, "RGBA").save(out / "layers" / f"{lid}_cutout.png")
        layers.append({"layer_id": lid, "rgb": rgb, "alpha": alpha, "placement": places[lid]})
        ident = ((ev.get("generation") or {}).get("identity") or {}).get("references") or []
        layer_ev.append({"layer_id": lid, "layer_type": "character", "character_id": character_id, "kind": "people",
                         "style_override": ev.get("style_id"), "regeneration_scope": f"only layer {lid}（其他層原樣重用）",
                         "character_definition": next(iter(ev.get("character_definitions") or []), None),
                         "source_case_definition_version": ev.get("case_definition_version"), "source_stem": stem, "source_image_sha256": file_sha256(img),
                         "source_evidence": f"{stem}.json", "source_case_id": ev.get("case_id"), "source_seed": ev.get("seed"),
                         "source_checkpoint": ev.get("checkpoint"), "source_technical_valid": ev.get("technical_valid"),
                         "identity_references": [{k: r.get(k) for k in ("character_id", "sha256", "source", "library_category")}
                                                 for r in ident],
                         "matte": matte, "mask_file": f"layers/{lid}_mask.png", "cutout_file": f"layers/{lid}_cutout.png"})
    try:
        result, placed = cp.composite_layers(background, layers, color_strength=args.color_match, shadow_opacity=args.shadow)
    except ValueError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 2
    comp = out / "composite.png"
    Image.fromarray(result).save(comp)
    for le, pl in zip(layer_ev, placed):
        le.update(pl)
    boxes = [p["visible_box"] for p in placed]
    stats = image_stats(comp).to_dict()
    reasons = [r for r in (["black image"] if stats.get("is_black") else []) + (["flat image"] if stats.get("is_flat") else [])]
    suspects = [le["layer_id"] for le in layer_ev if le["matte"]["matte_suspect"]]
    ev = {"composition": name, "route": "DG-26 Route A (separate generation + key matte + alpha composite)",
          "background": {"layer_id": "background", "layer_type": "background", "style_override": bg_ev.get("style_id"),
                         "regeneration_scope": "only background layer", "source_stem": args.background, "source_image_sha256": file_sha256(bg_img),
                         "source_evidence": f"{args.background}.json", "source_case_id": bg_ev.get("case_id"),
                         "source_seed": bg_ev.get("seed"), "source_checkpoint": bg_ev.get("checkpoint"), "size": list(background.shape[1::-1])},
          "layers": layer_ev, "depth_order": order,
          "overlap": {f"{order[i]}|{order[j]}": cp.overlap_ratio(boxes[i], boxes[j])
                      for i in range(len(order)) for j in range(i + 1, len(order))},
          "harmonization": {"color_match": args.color_match, "shadow_opacity": args.shadow, "feather_px": args.feather,
                            "img2img_or_inpaint": False},
          "composite_file": "composite.png", "composite_sha256": file_sha256(comp), "image_stats": stats,
          # 分層判定：technical 自動；scene／identity／「貼上感」只能人工（single-user subjective）
          "technical_valid": not reasons, "technical_reasons": reasons, "matte_suspect_layers": suspects,
          "scene_validated": None, "identity_validated": {lid: None for lid in order}, "pasted_look": None,
          "commercial_cleared": False, "cost": "NT$0", "generated_new_images": False,
          "human_review": {"status": "pending", "subjective": "single-user subjective",
                           "how": f"python -m see.app.cli compose-review {name} --scene pass|fail "
                                  + " ".join(f"--identity {lid}=pass|fail" for lid in order) + " --pasted yes|no --note \"...\""}}
    (out / "composite.json").write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(ev, ensure_ascii=False, indent=2))
    if suspects:
        print(f"警告：去背可能不可靠（{suspects}）：角色層背景不夠單純；請看 layers/*_mask.png", file=sys.stderr)
    print("注意：technical_valid 只代表技術有效；scene／identity／是否像貼上去，須人工 compose-review。", file=sys.stderr)
    return 0 if not reasons else 3


def cmd_compose_review(args: argparse.Namespace) -> int:
    """合成圖人工審查（scene、各角色 identity、貼上感；主觀、單一審查者）。"""
    from datetime import datetime, timezone

    from see.core.style_tests import verdict_to_bool

    path = Settings().workspace / "compositions" / args.name / "composite.json"
    if not path.exists():
        print(f"找不到 {path}；請先執行 compose-scene", file=sys.stderr)
        return 2
    ev = json.loads(path.read_text(encoding="utf-8"))
    if not ev.get("technical_valid"):
        print("此張 technical_valid=false，不能做人工審查", file=sys.stderr)
        return 3
    try:
        ident = {k.strip(): verdict_to_bool(v.strip()) for k, v in (x.split("=", 1) for x in args.identity or [])}
        if args.scene:
            ev["scene_validated"] = verdict_to_bool(args.scene)
    except ValueError as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 2
    unknown = set(ident) - set(ev["identity_validated"])
    if unknown:
        print(f"錯誤：未知 layer {sorted(unknown)}", file=sys.stderr)
        return 2
    ev["identity_validated"].update(ident)
    if args.pasted:
        ev["pasted_look"] = args.pasted == "yes"
    ev["human_review"] = {**ev.get("human_review", {}), "status": "reviewed", "note": args.note or "", "reviewer": args.by,
                          "subjective": True, "reviewed_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    path.write_text(json.dumps(ev, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: ev[k] for k in ("composition", "technical_valid", "scene_validated", "identity_validated", "pasted_look",
                                         "human_review")}, ensure_ascii=False, indent=2))
    return 0


def cmd_ref(args: argparse.Namespace) -> int:
    """D-062 Reference Library（本機；只讀寫 metadata sidecar，不碰圖片、不上傳）。"""
    from see.core.reference_library import ReferenceLibrary, ReferenceLibraryError, entries_json

    lib = ReferenceLibrary(Settings().workspace)
    try:
        if args.ref_cmd == "list":
            print(entries_json(lib.list(category=args.category)))
            return 0
        if args.ref_cmd == "register":
            a = lib.register(args.path, asset_id=args.asset_id, role=args.role, source_type=args.source_type,
                             character_id=args.character, commercial_clearance_status=args.clearance, notes=args.note or "")
        elif args.ref_cmd == "bind":
            a = lib.bind(args.asset_id, None if args.unbind else args.character)
        else:
            a = lib.mark_primary(args.asset_id)
    except (ReferenceLibraryError, ValueError) as e:
        print(f"錯誤：{e}", file=sys.stderr)
        return 2
    print(a.model_dump_json(indent=2))
    return 0


def cmd_style_compare(args: argparse.Namespace) -> int:
    """D-043：兩份 style-test evidence 逐項比對生成條件，判定是否為單一變數比較（相容舊 JSON；唯讀）。"""
    from see.core.style_tests import compare_conditions, historical_reversed_character_mapping

    d = Settings().workspace / "style_tests"
    evs = []
    for stem in (args.stem_a, args.stem_b):
        path = d / f"{stem}.json"
        if not path.exists():
            have = sorted(p.stem for p in d.glob("*.json")) if d.exists() else []
            print(f"找不到 {path}；現有：{have}", file=sys.stderr)
            return 2
        evs.append(json.loads(path.read_text(encoding="utf-8")))
    # D-052：未指定 --intended → 自動判定實驗變數（model 或 prompt_mode，恰好一個不同時）
    intended = tuple(x.strip() for x in args.intended.split(",") if x.strip()) if args.intended else None
    res = compare_conditions(evs[0], evs[1], intended)
    res = {"a": args.stem_a, "b": args.stem_b, **res,
           "technical_valid": [evs[0].get("technical_valid"), evs[1].get("technical_valid")],
           "image_sha256": [evs[0].get("image_sha256"), evs[1].get("image_sha256")],
           # D-058：舊 A／B 定義相反 → 不可用來判定 A／B 性別 assignment（仍可作模型能力證據）
           "historical_reversed_character_mapping": [historical_reversed_character_mapping(e) for e in evs]}
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["verdict"] != "not_comparable" else 4


class _StyleTestBudget:
    """style-test 沒有專案；ApprovalGate 需要 project 物件時以 budget=0、無核准的空殼代替 → PAID 一律拒絕。"""

    budget = 0.0
    approvals: list = []


def cmd_appearance(args: argparse.Namespace) -> int:
    """設定角色外觀錨點（Character Consistency；D-032）。--clear 移除。"""
    from see.models.project import CharacterAppearance, CharacterTraits

    _, orch = build()
    project = orch.store.load(args.project_id)
    traits_kw = {k: v for k, v in {"gender_presentation": args.gender, "age": args.age, "age_range": args.age_range,
                                   "appearance_region": args.region, "hair_style": args.hair_style, "hair_color": args.hair_color,
                                   "facial_features": args.facial_feature, "body_type": args.body_type,
                                   "distinctive_marks": args.mark}.items() if v}
    app = None if args.clear else CharacterAppearance(description_en=args.description or "", outfit_en=args.outfit or "",
                                                       features_en=args.feature or [], reference_images=args.ref or [], seed=args.seed,
                                                       traits=CharacterTraits(**traits_kw) if traits_kw else None)
    ch = orch.set_character_appearance(project, args.character_id, app)
    print(json.dumps(ch.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_voice_preview(args: argparse.Namespace) -> int:
    """試聽一句（不寫任何專案 manifest）；輸出 wav 路徑與 duration／rtf。"""
    settings = Settings()
    if args.tts:
        settings.tts_provider = args.tts
    _, orch = build(settings)
    res = orch.preview_voice(args.text, voice=args.voice, speed=args.speed)
    print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))
    return 0


def cmd_tts_voices(args: argparse.Namespace) -> int:
    """列出目前 TTS provider 本機可用的 voice（Voice Selector 規格的 CLI 版）。"""
    from see.providers.registry import ProviderRegistry

    s = Settings()
    if args.tts:
        s.tts_provider = args.tts
    tts = ProviderRegistry(s).build().tts
    print(json.dumps({"provider": tts.info.name, "default_voice": s.tts_default_voice or "(provider default)",
                      "voices": [v.model_dump() for v in tts.list_voices()]}, ensure_ascii=False, indent=2))
    return 0


def cmd_tts_check(args: argparse.Namespace) -> int:
    """真機驗證：以本機 Kokoro 合成一句，印出 duration / rtf / device / voice（不進 pipeline）。"""
    from see.providers.base import TTSRequest
    from see.providers.registry import ProviderRegistry
    from see.providers.tts.kokoro import KokoroTTSProvider, local_voices, read_provenance

    s = Settings()
    s.tts_provider = "kokoro"
    tts = ProviderRegistry(s).build().tts
    assert isinstance(tts, KokoroTTSProvider)
    print(json.dumps({"available": tts.is_available(), "model_dir": str(tts.model_dir), "voices": local_voices(tts.model_dir),
                      "provenance": read_provenance(tts.model_dir)}, ensure_ascii=False, indent=2))
    if not tts.is_available():
        print("kokoro 不可用：請先 pip install 套件並執行 tts-download --yes", file=sys.stderr)
        return 1
    out = Path(args.out).resolve()
    res = tts.synthesize(TTSRequest(text=args.text, language="zh-TW", voice=args.voice, speed=args.speed), out)
    print(json.dumps(res.model_dump(), ensure_ascii=False, indent=2))
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
    r.add_argument("--tts", choices=["auto", "kokoro", "espeak", "silent", "edge"])
    r.add_argument("--voice", default=None, help="scene.voice=default 時使用的 voice id（例如 zm_010；等同 SEE_TTS_DEFAULT_VOICE）")
    r.add_argument("--audio", choices=["null", "procedural"], default=None, help="BGM/SFX 來源（預設 null = 不加；procedural = 程式生成測試音）")
    r.add_argument("--workspace")
    r.set_defaults(fn=cmd_run)
    st = sub.add_parser("status"); st.add_argument("project_id"); st.set_defaults(fn=cmd_status)
    ss = sub.add_parser("set-scene", help="修改單一 scene 後只重做該 scene 並重新組裝 preview")
    ss.add_argument("project_id"); ss.add_argument("scene_id")
    ss.add_argument("--narration"); ss.add_argument("--subtitle"); ss.add_argument("--image-prompt"); ss.add_argument("--image-prompt-en")
    ss.add_argument("--camera"); ss.add_argument("--transition")
    ss.add_argument("--voice", help="本景 voice id（覆寫角色）"); ss.add_argument("--narrator", help="本景旁白角色 id")
    ss.add_argument("--speed", type=float, help="本景語速覆寫（0.5–2.0）")
    ss.add_argument("--sfx", action="append", help="本景音效「描述@秒數」（可重複；none = 清空）")
    ss.add_argument("--audio", choices=["null", "procedural"], default=None)
    ss.add_argument("--characters", nargs="*", default=None, help="本景出現的角色 id（外觀錨點用）")
    ss.add_argument("--lipsync", choices=["on", "off"], default=None, help="本景嘴型同步（需非 null 的 lipsync provider）")
    ss.set_defaults(fn=cmd_set_scene)
    rg = sub.add_parser("regen", help="強制重做單一 scene"); rg.add_argument("project_id"); rg.add_argument("scene_id"); rg.set_defaults(fn=cmd_regen)
    apv = sub.add_parser("approve", help="人工核准（PREVIEW → APPROVED）"); apv.add_argument("project_id")
    apv.add_argument("--by", default="human"); apv.add_argument("--note"); apv.set_defaults(fn=cmd_approve)
    fn = sub.add_parser("final", help="Final render（需 APPROVED）"); fn.add_argument("project_id"); fn.set_defaults(fn=cmd_final)
    ce = sub.add_parser("check-env"); ce.set_defaults(fn=cmd_check_env)
    doc = sub.add_parser("doctor", help="環境檢查（系統／Python／GPU／工具／模型／workspace；唯讀；Ready／Not ready）")
    doc.add_argument("--json", action="store_true")
    doc.add_argument("--hash", action="store_true", help="重算模型 sha256（大檔很慢；搬機後驗證用）")
    doc.add_argument("--write-manifest", action="store_true", help="寫入 workspace/environment_manifest.json（machine-local，不進 Git）")
    doc.set_defaults(fn=cmd_doctor)
    bs = sub.add_parser("bootstrap", help="環境建置計畫（預設唯讀 dry-run）；--apply-safe 只建立缺少的空 workspace 資料夾")
    bs.add_argument("--check", action="store_true", help="唯讀列出計畫（預設行為）")
    bs.add_argument("--apply-safe", action="store_true", help="只建立缺少的空資料夾與 workspace_version.json；不安裝、不下載")
    bs.add_argument("--json", action="store_true")
    bs.set_defaults(fn=cmd_bootstrap)
    ee = sub.add_parser("env-export", help="匯出可恢復資訊到 workspace/exports/env-<時間>/（不含模型與私人圖片）")
    ee.add_argument("--out", default=None, help="輸出資料夾（必須不存在或為空）")
    ee.add_argument("--hash", action="store_true", help="重算模型 sha256")
    ee.set_defaults(fn=cmd_env_export)
    cfg = sub.add_parser("config", help="專案本機設定檔 see.local.json（machine-specific；不進 Git）：show／set／unset")
    cfg.add_argument("action", choices=["show", "set", "unset"], nargs="?", default="show")
    cfg.add_argument("key", nargs="?", default="")
    cfg.add_argument("value", nargs="?", default="")
    cfg.set_defaults(fn=cmd_config)
    cst = sub.add_parser("cast", help="（唯讀）Project.cast：pinned Library revision 與 readiness；foundation，尚非 production 角色來源")
    cst.add_argument("action", choices=["show"])
    cst.add_argument("project_id")
    cst.add_argument("--json", action="store_true")
    cst.set_defaults(fn=cmd_cast)
    cmg = sub.add_parser("character-migrate", help="（只分析）舊 Project.characters → Character Library 的 dry-run 報告；不寫任何資料")
    cmg.add_argument("project_id")
    cmg.add_argument("--dry-run", action="store_true", help="必填：只分析、不遷移（實際 migration 尚未核准）")
    cmg.add_argument("--json", action="store_true", help="輸出 versioned JSON（供 Batch 5 使用）")
    cmg.add_argument("--out", default=None, help="報告檔（必須在 workspace 外、不可已存在）；預設 stdout")
    cmg.set_defaults(fn=cmd_character_migrate)
    sm = sub.add_parser("smoke", help="快速冒煙測試（不需 GPU；暫存 workspace；不碰使用者資料）"); sm.set_defaults(fn=cmd_smoke)
    hw = sub.add_parser("hardware", help="偵測 GPU/VRAM/RAM/disk/torch 並給出 AI Image Provider 建議")
    hw.add_argument("--json", action="store_true"); hw.add_argument("--path", default=".", help="評估磁碟空間的路徑（預設 workspace 所在）")
    hw.set_defaults(fn=cmd_hardware)
    ise = sub.add_parser("image-setup", help="印出本機 AI 生圖安裝步驟（不執行安裝）"); ise.set_defaults(fn=cmd_image_setup)
    idl = sub.add_parser("image-download", help="下載 open-weight 模型（需 --yes 才真的下載）")
    idl.add_argument("--preset", default=None); idl.add_argument("--dest", default=None); idl.add_argument("--yes", action="store_true")
    idl.set_defaults(fn=cmd_image_download)
    tse = sub.add_parser("tts-setup", help="印出 Kokoro TTS（D-027 候選）安裝步驤（不執行安裝）"); tse.set_defaults(fn=cmd_tts_setup)
    tdl = sub.add_parser("tts-download", help="下載 Kokoro-82M v1.1-zh 權重（需 --yes 才真的下載；寫 provenance.json）")
    tdl.add_argument("--dest", default=None); tdl.add_argument("--yes", action="store_true")
    tdl.add_argument("--voices", nargs="*", default=None, help="要下載的 voice id（預設 2 女 2 男）")
    tdl.set_defaults(fn=cmd_tts_download)
    chp = sub.add_parser("character", help="角色 voice：設定（--voice/--speed/--name）、--confirm 確認、或列出")
    chp.add_argument("project_id"); chp.add_argument("character_id", nargs="?")
    chp.add_argument("--name"); chp.add_argument("--voice"); chp.add_argument("--speed", type=float)
    chp.add_argument("--clear-speed", action="store_true"); chp.add_argument("--confirm", action="store_true")
    chp.add_argument("--list", action="store_true"); chp.set_defaults(fn=cmd_character)
    sty = sub.add_parser("style", help="列出 Style Profile，或 `style <project_id> <style_id>` 設定專案風格")
    sty.add_argument("project_id", nargs="?"); sty.add_argument("style_id", nargs="?"); sty.set_defaults(fn=cmd_style)
    stt = sub.add_parser("style-test", help="Style 真機驗收：固定場景／seed 只換風格出一張圖（不建專案、不動快取）")
    stt.add_argument("--style", required=True); stt.add_argument("--seed", type=int, default=None)
    stt.add_argument("--case", default="kitten_butterfly", help="測試案例（see/core/style_tests.py）")
    stt.add_argument("--scene", default=None, help="（診斷）覆寫案例場景；結果標 baseline_condition=false")
    stt.add_argument("--gen-policy", choices=["fit", "native"], default="fit",
                     help="（診斷）fit＝現行（16:9 長邊壓到 512→512×288）；native＝短邊 512 生成後裁切")
    stt.add_argument("--base-prompt", default=None, help="（診斷）手寫英文 base prompt；結果標 baseline_condition=false")
    stt.add_argument("--checkpoint", default=None, help="（內部驗證，D-039）SD 1.5 單檔 checkpoint id；不 fallback")
    stt.add_argument("--scheduler", default=None, choices=["default", "dpmpp_2m_karras", "euler_a"],
                     help="覆寫 scheduler（預設：checkpoint 建議值；base SD 1.5＝模型自帶）")
    stt.add_argument("--long-prompt", action="store_true",
                     help="（診斷，D-051 S1）超過 77 token 時分段編碼，不截斷；預設關閉")
    stt.add_argument("--regional", action="store_true",
                     help="（診斷，D-051 S2）多角色案例：每角色一欄 regional cross-attention（隱含 --long-prompt）；預設關閉")
    stt.add_argument("--identity", default=None, help="（診斷，D-054 S4）Identity adapter id，例 ip_adapter_plus_face_sd15；預設關閉")
    stt.add_argument("--ref", action="append",
                     help="（搭配 --identity）<character_id>=<style-test stem 或本機圖檔>，每個角色一張、不可相同")
    stt.set_defaults(fn=cmd_style_test)
    add = sub.add_parser("adapter-download", help="下載已核准的 Identity adapter（IP-Adapter；safetensors／json；逐檔 bytes＋sha256）")
    add.add_argument("adapter_id"); add.add_argument("--check", action="store_true", help="只核對遠端，不下載")
    add.add_argument("--verify", action="store_true", help="只核對本機既有檔案（換電腦搬移），不下載")
    add.add_argument("--yes", action="store_true", help="確認下載"); add.set_defaults(fn=cmd_adapter_download)
    ckd = sub.add_parser("checkpoint-download", help="下載已核准的 SD 1.5 checkpoint（單檔 safetensors；核對大小＋sha256；寫 provenance）")
    ckd.add_argument("checkpoint_id"); ckd.add_argument("--check", action="store_true", help="只核對遠端檔名／大小／sha256，不下載")
    ckd.add_argument("--yes", action="store_true", help="確認下載"); ckd.set_defaults(fn=cmd_checkpoint_download)
    srv = sub.add_parser("style-review", help="人工審圖：把 scene／style 判定寫回 style-test evidence（主觀）")
    srv.add_argument("stem", help="style_tests 下的檔名（不含副檔名），例如 picture_book_seed1234")
    srv.add_argument("--scene", choices=["pass", "fail"], required=True)
    srv.add_argument("--style", choices=["pass", "fail"], required=True)
    srv.add_argument("--note"); srv.add_argument("--by", default="customer"); srv.set_defaults(fn=cmd_style_review)
    scp = sub.add_parser("style-compare", help="比對兩份 style-test evidence 的生成條件（是否只差一個變數；唯讀）")
    scp.add_argument("stem_a"); scp.add_argument("stem_b")
    scp.add_argument("--intended", default=None,
                     help="刻意改變的條件（逗號分隔）；預設自動：model 或 prompt_mode 恰好一個不同時視為 intended")
    scp.set_defaults(fn=cmd_style_compare)
    csc = sub.add_parser("compose-scene", help="（診斷，D-057 DG-26 Route A）背景層＋角色層（style-test 產出）去背擺位合成；不生成新圖")
    csc.add_argument("--background", required=True, help="背景層 style-test stem（例 ab_background 的產出）")
    csc.add_argument("--layer", action="append", help="<layer_id>=<style-test stem>（每個角色一層，可重複）")
    csc.add_argument("--place", action="append", help="<layer_id>=center_x[,bottom[,height]]（相對背景 0..1；例 char_a=0.3,1.0,0.9）")
    csc.add_argument("--order", default=None, help="深度順序，先列者在後方（例 char_b,char_a）；預設＝--layer 順序")
    csc.add_argument("--name", default=None, help="輸出資料夾名（workspace/compositions/<name>/）")
    csc.add_argument("--key-tolerance", type=float, default=38.0)
    csc.add_argument("--feather", type=float, default=2.0)
    csc.add_argument("--color-match", type=float, default=0.25)
    csc.add_argument("--shadow", type=float, default=0.25)
    csc.set_defaults(fn=cmd_compose_scene)
    crv = sub.add_parser("compose-review", help="合成圖人工審查：scene／各角色 identity／是否像貼上去（主觀）")
    crv.add_argument("name")
    crv.add_argument("--scene", choices=["pass", "fail"])
    crv.add_argument("--identity", action="append", help="<layer_id>=pass|fail")
    crv.add_argument("--pasted", choices=["yes", "no"], help="是否看起來像貼上去")
    crv.add_argument("--note"); crv.add_argument("--by", default="customer"); crv.set_defaults(fn=cmd_compose_review)
    rf = sub.add_parser("ref", help="Reference Library（workspace/reference_library/<category>/；metadata 決定歸屬與用途，不看檔名）")
    rfs = rf.add_subparsers(dest="ref_cmd", required=True)
    rl = rfs.add_parser("list", help="列出圖片、metadata 狀態與支援度（含 legacy identity_refs/，唯讀）")
    rl.add_argument("--category", choices=["people", "animals", "characters", "backgrounds", "styles"])
    rr = rfs.add_parser("register", help="登記已放進 Library 的圖片（計算 sha256、寫 <檔名>.ref.json）")
    rr.add_argument("path", help="<category>/<檔名>，例 people/hero_v1.jpg")
    rr.add_argument("--asset-id", required=True)
    rr.add_argument("--role", required=True, choices=["identity_face", "full_body", "outfit", "pose", "style_reference", "background_reference"])
    rr.add_argument("--source-type", required=True, choices=["user_supplied", "generated", "imported"])
    rr.add_argument("--character", default=None, help="綁定的 character_id（角色用途必填於生成前）")
    rr.add_argument("--clearance", default="unknown", choices=["cleared", "not_cleared", "unknown"])
    rr.add_argument("--note", default=None)
    rb = rfs.add_parser("bind", help="綁定／解除綁定角色")
    rb.add_argument("asset_id"); rb.add_argument("--character", default=None); rb.add_argument("--unbind", action="store_true")
    rp = rfs.add_parser("primary", help="設為該角色的主要 identity reference")
    rp.add_argument("asset_id")
    rf.set_defaults(fn=cmd_ref)
    app_ = sub.add_parser("appearance", help="角色外觀錨點（英文描述／服裝／特徵／參考圖）")
    app_.add_argument("project_id"); app_.add_argument("character_id")
    app_.add_argument("--description"); app_.add_argument("--outfit"); app_.add_argument("--feature", action="append")
    app_.add_argument("--ref", action="append"); app_.add_argument("--seed", type=int); app_.add_argument("--clear", action="store_true")
    # D-047 結構化人物設定（全部可選、無預設；英文描述）
    app_.add_argument("--gender", help="性別呈現，例 woman／man"); app_.add_argument("--age", type=int)
    app_.add_argument("--age-range"); app_.add_argument("--region", help="地區外貌描述，例 'East Asian'")
    app_.add_argument("--hair-style"); app_.add_argument("--hair-color"); app_.add_argument("--facial-feature", action="append")
    app_.add_argument("--body-type"); app_.add_argument("--mark", action="append", help="辨識特徵（可重複）")
    app_.set_defaults(fn=cmd_appearance)
    vpp = sub.add_parser("voice-preview", help="試聽一句（不影響專案）")
    vpp.add_argument("--text", default="你好，這是角色試聽。"); vpp.add_argument("--voice", default="default")
    vpp.add_argument("--speed", type=float, default=1.0)
    vpp.add_argument("--tts", choices=["auto", "kokoro", "espeak", "silent", "edge"], default=None); vpp.set_defaults(fn=cmd_voice_preview)
    tvs = sub.add_parser("tts-voices", help="列出目前 TTS provider 本機可用 voice（id／可讀名稱／性別／已知限制）")
    tvs.add_argument("--tts", choices=["auto", "kokoro", "espeak", "silent", "edge"], default=None); tvs.set_defaults(fn=cmd_tts_voices)
    tck = sub.add_parser("tts-check", help="以本機 Kokoro 合成一句並印出 duration/rtf/device（真機驗證用）")
    tck.add_argument("--text", default="你好，這是 AI-Studio 的中文旁白測試。"); tck.add_argument("--voice", default="default")
    tck.add_argument("--speed", type=float, default=1.0); tck.add_argument("--out", default="tts_check.wav")
    tck.set_defaults(fn=cmd_tts_check)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except SeeError as e:
        print(f"ERROR [{type(e).__name__}] {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
