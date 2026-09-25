"""应急演练接口：季度演练计划、演练记录批量下发、问题登记与整改闭环。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.drill import DrillService

router = APIRouter(prefix="/api/drill", tags=["应急演练"])

service = DrillService()

PLAN_FIELDS = ["计划编号", "演练季度", "演练名称", "演练类型", "计划演练日", "编排人员", "编排日期"]
RECORD_FIELDS = [
    "演练编号", "计划编号", "演练科目", "参演班组", "参演人数",
    "参演人员", "人员已确认", "下发时间", "完成时间",
]
ISSUE_FIELDS = [
    "问题编号", "演练编号", "参演班组", "问题描述", "问题分类",
    "责任人", "整改要求", "整改措施", "登记时间", "闭环时间", "整改状态",
]


class BatchPayload(BaseModel):
    """批量下发/结束演练时勾选的记录 id 列表。"""

    record_ids: list[int] = Field(default_factory=list)


class IssueActionPayload(BaseModel):
    """整改动作：开始整改不需要补充说明，闭环验收必须带整改措施。"""

    action: str
    整改措施: str | None = None


@router.get("/plans", response_model=PageResult[dict])
def list_plans(
    keyword: str | None = Query(default=None, description="按计划编号或演练名称检索"),
    quarter: str | None = Query(default=None, description="按演练季度过滤，如 2026年第三季度"),
    status: str | None = Query(default=None, description="已编排、已下发、已闭环"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """演练计划列表；每条都现算整组下发/完成/整改闭环进度。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_plans(keyword=keyword, quarter=quarter, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.get("/plans/{plan_id}", response_model=dict)
def get_plan(plan_id: int) -> dict:
    """读取单个演练计划及其整组进度；不存在时给出可读说明。"""
    plan = service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"演练计划 {plan_id} 不存在或已归档")
    return plan


@router.post("/plans", response_model=ActionResult)
def create_plan(payload: EntryPayload) -> ActionResult:
    """按季度编排一条演练计划，缺字段或编号重复时说明原因。"""
    plan, missing = service.create_plan(payload.values)
    if missing:
        if missing == ["计划编号重复"]:
            return ActionResult(ok=False, message="计划编号已存在，换一个编号再编排")
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="季度演练计划已编排", entry=plan)


@router.get("/records", response_model=PageResult[dict])
def list_records(
    plan_no: str | None = Query(default=None, description="按计划编号过滤演练记录"),
    status: str | None = Query(default=None, description="待下发、已下发、已完成"),
    page: int = 1,
    size: int = 100,
) -> PageResult[dict]:
    """演练记录清单；整改跟踪页按计划编号拉取整组记录。"""
    items, total = service.list_records(plan_no=plan_no, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/records/{record_id}/confirm", response_model=ActionResult)
def confirm_participants(record_id: int) -> ActionResult:
    """参演班组确认参演名单；名单为空或记录不存在时说明原因。"""
    record, message = service.confirm_participants(record_id)
    if record is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=record)


@router.post("/records/dispatch")
def batch_dispatch(payload: BatchPayload) -> dict[str, Any]:
    """一次把多条演练记录批量下发给参演班组。

    缺演练计划、重复下发、参演人未确认都会逐条给出说明，不只处理第一条；
    只要有一条不合规，整批都不下发，避免同组记录发出去一半。
    """
    if not payload.record_ids:
        return {"ok": False, "message": "未勾选任何演练记录，请先勾选要下发的记录", "success": [], "failures": []}
    success, failures = service.batch_dispatch(payload.record_ids)
    if failures:
        return {
            "ok": False,
            "message": f"批量下发未执行：{len(failures)} 条记录未通过校验，请按下述说明处理后整组重新下发",
            "success": [],
            "failures": failures,
        }
    return {
        "ok": True,
        "message": f"已批量下发 {len(success)} 条演练记录至参演班组",
        "success": success,
        "failures": [],
    }


@router.post("/records/finish")
def batch_finish(payload: BatchPayload) -> dict[str, Any]:
    """演练结束后批量把记录置为已完成；状态不对的逐条说明。"""
    if not payload.record_ids:
        return {"ok": False, "message": "未勾选任何演练记录", "success": [], "failures": []}
    success, failures = service.batch_finish(payload.record_ids)
    if failures:
        return {
            "ok": False,
            "message": f"结束演练未执行：{len(failures)} 条记录不满足条件",
            "success": [],
            "failures": failures,
        }
    return {
        "ok": True,
        "message": f"{len(success)} 条演练记录已登记为演练结束",
        "success": success,
        "failures": [],
    }


@router.get("/issues", response_model=PageResult[dict])
def list_issues(
    plan_no: str | None = Query(default=None, description="按计划编号过滤整组问题"),
    record_no: str | None = Query(default=None, description="按演练编号过滤"),
    status: str | None = Query(default=None, description="待整改、整改中、已闭环"),
    page: int = 1,
    size: int = 100,
) -> PageResult[dict]:
    """整改跟踪清单；计划列表进入整改跟踪时按计划编号取整组问题。"""
    items, total = service.list_issues(plan_no=plan_no, record_no=record_no, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/issues", response_model=ActionResult)
def create_issue(payload: EntryPayload) -> ActionResult:
    """演练结束后逐条登记问题；缺字段、演练未结束都说明原因。"""
    issue, missing, error = service.create_issue(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    if error:
        return ActionResult(ok=False, message=error)
    return ActionResult(ok=True, message="演练问题已登记，进入整改跟踪", entry=issue)


@router.post("/issues/{issue_id}/actions", response_model=ActionResult)
def run_issue_action(issue_id: int, payload: IssueActionPayload) -> ActionResult:
    """问题整改动作：开始整改、闭环验收；闭环必须填写整改措施。"""
    issue, message = service.run_issue_action(
        issue_id, payload.action, {"整改措施": payload.整改措施}
    )
    if issue is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=issue)


@router.get("/export")
def export_plans() -> dict[str, Any]:
    """导出应急演练计划清单及整组进度。"""
    items, total = service.list_plans(page=1, size=10000)
    return {"module": "drill", "total": total, "items": items}
