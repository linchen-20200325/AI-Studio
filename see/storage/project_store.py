"""ProjectStore：workspace 目錄佈局 + JSON 持久化（SSOT = project.json + scenes/*/manifest.json）。"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field

from see.models.project import Project


class AssetRecord(BaseModel):
    fingerprint: str
    path: str
    duration: float | None = None
    provider: str = ""
    model: str = ""


class SceneManifest(BaseModel):
    """每景產物與其 fingerprint；Orchestrator 用來決定是否重做。"""

    scene_id: str
    entries: dict[str, AssetRecord] = Field(default_factory=dict)

    def valid(self, key: str, fingerprint: str) -> AssetRecord | None:
        rec = self.entries.get(key)
        if rec and rec.fingerprint == fingerprint and Path(rec.path).exists():
            return rec
        return None


class ProjectStore:
    def __init__(self, workspace: Path) -> None:
        self.workspace = Path(workspace)
        self.projects_root = self.workspace / "projects"

    # ---- paths
    def project_dir(self, project_id: str) -> Path:
        return self.projects_root / project_id

    def scene_dir(self, project_id: str, scene_id: str) -> Path:
        return self.project_dir(project_id) / "scenes" / scene_id

    def renders_dir(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "renders"

    def project_file(self, project_id: str) -> Path:
        return self.project_dir(project_id) / "project.json"

    # ---- project
    def save(self, project: Project) -> Path:
        project.touch()
        d = self.project_dir(project.project_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "input.txt").write_text(project.input_text, encoding="utf-8")
        path = self.project_file(project.project_id)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(project.model_dump_json(indent=2), encoding="utf-8")
        tmp.replace(path)
        return path

    def load(self, project_id: str) -> Project:
        path = self.project_file(project_id)
        if not path.exists():
            raise FileNotFoundError(f"project not found: {project_id} ({path})")
        return Project.model_validate_json(path.read_text(encoding="utf-8"))

    def exists(self, project_id: str) -> bool:
        return self.project_file(project_id).exists()

    def list_projects(self) -> list[str]:
        if not self.projects_root.exists():
            return []
        return sorted(p.name for p in self.projects_root.iterdir() if (p / "project.json").exists())

    # ---- manifests
    def load_manifest(self, project_id: str, scene_id: str) -> SceneManifest:
        path = self.scene_dir(project_id, scene_id) / "manifest.json"
        if path.exists():
            try:
                return SceneManifest.model_validate_json(path.read_text(encoding="utf-8"))
            except ValueError:
                pass  # 損壞的 manifest 視為空 → 重做
        return SceneManifest(scene_id=scene_id)

    def save_manifest(self, project_id: str, manifest: SceneManifest) -> None:
        d = self.scene_dir(project_id, manifest.scene_id)
        d.mkdir(parents=True, exist_ok=True)
        (d / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    def clear_manifest(self, project_id: str, scene_id: str) -> None:
        path = self.scene_dir(project_id, scene_id) / "manifest.json"
        if path.exists():
            path.unlink()

    def write_json(self, path: Path, data: BaseModel | dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        text = data.model_dump_json(indent=2) if isinstance(data, BaseModel) else json.dumps(data, ensure_ascii=False, indent=2)
        path.write_text(text, encoding="utf-8")
