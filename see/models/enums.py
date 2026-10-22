"""列舉型別：狀態、成本層級、鏡頭運動、轉場等。"""

from __future__ import annotations

from enum import StrEnum


class Status(StrEnum):
    """Project / Scene 狀態機：DRAFT → PREVIEW → APPROVED → FINAL。"""

    DRAFT = "DRAFT"
    PREVIEW = "PREVIEW"
    APPROVED = "APPROVED"
    FINAL = "FINAL"


class CostTier(StrEnum):
    LOCAL_FREE = "LOCAL_FREE"
    FREE_TIER = "FREE_TIER"
    PAID = "PAID"


class ProviderKind(StrEnum):
    LLM = "llm"
    IMAGE = "image"
    VIDEO = "video"
    TTS = "tts"
    AUDIO = "audio"
    LIPSYNC = "lipsync"


class CameraMotion(StrEnum):
    STATIC = "static"
    ZOOM_IN = "zoom_in"
    ZOOM_OUT = "zoom_out"
    PAN_LEFT = "pan_left"
    PAN_RIGHT = "pan_right"
    PAN_UP = "pan_up"
    PAN_DOWN = "pan_down"


class Transition(StrEnum):
    CUT = "cut"
    FADE = "fade"
    DISSOLVE = "dissolve"
    WIPE_LEFT = "wipe_left"
    SLIDE_LEFT = "slide_left"
    FADE_BLACK = "fade_black"


class AssetKind(StrEnum):
    IMAGE = "image"
    NARRATION = "narration"
    SUBTITLE = "subtitle"
    CLIP = "clip"
    BGM = "bgm"
    SFX = "sfx"
    VIDEO = "video"


class JobKind(StrEnum):
    PREVIEW = "preview"
    FINAL = "final"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    REJECTED = "rejected"


class ApprovalKind(StrEnum):
    PAID_PROVIDER = "PAID_PROVIDER"
    BUDGET = "BUDGET"
    FINAL_RENDER = "FINAL_RENDER"
    PROJECT = "PROJECT"
