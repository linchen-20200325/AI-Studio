"""ApprovalGate：PAID 無核准 → 拒絕；超出預算 → 拒絕。這是 PROJECT_RULES §1/§4 的執行點。"""

from __future__ import annotations

from see.core.errors import BudgetExceeded, PaidProviderNotApproved
from see.models.approval import Approval
from see.models.cost import CostEstimate
from see.models.enums import ApprovalKind, CostTier
from see.models.project import Project


class ApprovalGate:
    @staticmethod
    def find_approval(project: Project, provider_name: str) -> Approval | None:
        for a in project.approvals:
            if a.kind == ApprovalKind.PAID_PROVIDER and a.target == provider_name:
                return a
        return None

    @classmethod
    def check(cls, estimate: CostEstimate, project: Project) -> None:
        """通過則靜默返回；否則 raise。"""
        if estimate.cost_tier in (CostTier.LOCAL_FREE, CostTier.FREE_TIER):
            return
        approval = cls.find_approval(project, estimate.provider)
        if approval is None:
            raise PaidProviderNotApproved(
                f"PAID provider '{estimate.provider}' (model={estimate.model}) needs human approval: "
                f"units={estimate.units} {estimate.unit_name}, estimated={estimate.estimated_cost} {estimate.currency}"
            )
        cap = approval.max_cost if approval.max_cost is not None else project.budget
        if estimate.estimated_cost > cap:
            raise BudgetExceeded(
                f"estimated {estimate.estimated_cost} {estimate.currency} exceeds cap {cap} "
                f"for provider '{estimate.provider}' (project budget={project.budget})"
            )
