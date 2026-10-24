"""D-069 Batch 4 測試用合成專案（不含任何私人資料）：涵蓋 narrator、空條目、legacy-only、同名、性別／年齡自由值、
reference（唯一 sha、遺失、重複 sha、對應既有 Library 角色）、未知欄位、Scene／對白／視線引用。"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from PIL import Image

from see.core.reference_library import ReferenceLibrary
from see.models.character_definition import RefRole
from see.models.project import CharacterAppearance, CharacterTraits, CharacterVoice
from see.models.scene import Dialogue
from see.models.scene_character import SceneCharacter
from see.storage.character_store import CharacterStore

PID = "mig_fixture"


def _img(path: Path, color) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), color).save(path, format="PNG")
    return path


def build(orch, private_dir: Path, text: str) -> str:
    ws = orch.settings.workspace
    lib = ReferenceLibrary(ws)
    cs = CharacterStore(ws)
    # Library：既有角色「阿明」＋綁定的參考圖；未綁定的參考圖；兩張位元相同的參考圖
    libchar = cs.create_new(display_name="阿明").definition.character_id
    _img(ws / "reference_library" / "people" / "lib_face.png", (200, 10, 10))
    lib.register("people/lib_face.png", asset_id="lib_face", role=RefRole.identity_face, source_type="user_supplied", character_id=libchar)
    _img(ws / "reference_library" / "people" / "free_face.png", (10, 200, 10))
    lib.register("people/free_face.png", asset_id="free_face", role=RefRole.identity_face, source_type="user_supplied")
    _img(ws / "reference_library" / "people" / "dup_a.png", (10, 10, 200))
    _img(ws / "reference_library" / "people" / "dup_b.png", (10, 10, 200))
    lib.register("people/dup_a.png", asset_id="dup_a", role=RefRole.identity_face, source_type="user_supplied")
    lib.register("people/dup_b.png", asset_id="dup_b", role=RefRole.identity_face, source_type="user_supplied")
    # 使用者本機的舊 reference 路徑（workspace 外）
    shutil.copy(ws / "reference_library" / "people" / "free_face.png", private_dir / "clean.png")
    shutil.copy(ws / "reference_library" / "people" / "lib_face.png", private_dir / "match.png")
    shutil.copy(ws / "reference_library" / "people" / "dup_a.png", private_dir / "dup.png")

    p = orch.create_project(text, project_id=PID)
    orch.write_script(p)
    orch.storyboard(p)
    C = CharacterVoice
    p.characters = {
        "narrator": C(character_id="narrator", display_name="旁白", voice_id="zm_010"),
        "hero": C(character_id="hero", display_name="阿明", voice_id="zm_010", speed=1.1, confirmed=True,
                  appearance=CharacterAppearance(outfit_en="grey suit", traits=CharacterTraits(hair_style="short", gender_presentation="man", age=30))),
        "heroine": C(character_id="heroine", display_name="小美",
                     appearance=CharacterAppearance(outfit_en="red coat", reference_images=[str(private_dir / "gone.png")])),
        "clean": C(character_id="clean", display_name="阿華", voice_id="zm_009",
                   appearance=CharacterAppearance(outfit_en="blue jacket", traits=CharacterTraits(hair_color="black"),
                                                  reference_images=[str(private_dir / "clean.png")])),
        "match": C(character_id="match", display_name="大雄", appearance=CharacterAppearance(reference_images=[str(private_dir / "match.png")])),
        "dupref": C(character_id="dupref", display_name="小強", appearance=CharacterAppearance(reference_images=[str(private_dir / "dup.png")])),
        "ghost": C(character_id="ghost"),
        "model_only": C(character_id="model_only", appearance=CharacterAppearance(seed=42, adapter={"lora": "x"})),
        "both": C(character_id="both", display_name="老師", voice_id="zm_011"),
    }
    s0, s1 = p.scenes[0], p.scenes[1]
    s0.character_ids = ["hero", "heroine", "both"]
    s0.characters = [SceneCharacter(character_id="hero", gaze={"preset": "at_character", "target_character_id": "heroine"})]
    s0.dialogue = [Dialogue(character_id="hero", text="走吧"), Dialogue(character_id="stranger", text="等等")]
    s0.narrator_id = "narrator"
    s0.voice = "zf_001"
    s1.character_ids = ["clean", "match", "dupref"]
    s1.narrator_id = "both"
    orch.store.save(p)
    f = orch.store.project_file(PID)  # 模擬未來／手改欄位（程式不認得）
    raw = json.loads(f.read_text(encoding="utf-8"))
    raw["characters"]["clean"]["mood_hint"] = "x"
    f.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    return PID
