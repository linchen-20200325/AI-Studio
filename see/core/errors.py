"""專案例外。所有拒絕執行都以例外表達（fail-closed），不是警告。"""


class SeeError(Exception):
    """基底例外。"""


class ApprovalRequired(SeeError):
    """需要人工核准才能繼續。"""


class PaidProviderNotApproved(ApprovalRequired):
    """PAID provider 沒有對應 Approval。"""


class BudgetExceeded(ApprovalRequired):
    """估算費用超過 project.budget。"""


class ProviderError(SeeError):
    """Provider 執行失敗（本機工具缺失、輸出不合法等）。"""


class ProviderUnavailable(ProviderError):
    """Provider 在此環境不可用（缺工具、缺網路、缺 key）。"""


class SchemaViolation(SeeError):
    """AI 輸出未通過 schema 驗證。"""


class RenderError(SeeError):
    """FFmpeg 或組裝失敗。"""


class InvalidTransition(SeeError):
    """狀態機不允許的轉移。"""
