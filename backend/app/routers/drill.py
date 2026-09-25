"""应急演练接口：按季度编排计划，批量下发演练记录，并跟踪问题整改到闭环。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, BatchPayload, BatchResult, EntryPayload, PageResult
from app.services.drill import DrillService

router = APIRouter(prefix="/api/drill", tags=["应急演练"])

service = DrillService()

PLAN_FIELDS = ["计划编号", "演练季度", "演练主题", "演练场景", "计划日期", "编制人", "记录数", "闭环进度", "整改进度"]
RECORD_FIELDS = ["演练编号", "计划编号", "演练名称", "参演班组", "参演人员", "演练时间", "确认状态", "问题数", "闭环数"]
ISSUE_FIELDS = ["问题编号", "演练编号", "问题描述", "责任人", "整改措施", "整改期限", "验收人"]


# -------------------------------------------------------------- 演练计划
@router.get("/plans", response_model=PageResult[dict])
def list_plans(
    keyword: str | None = Query(default=None, description="按计划编号或演练主题检索"),
    quarter: str | None = Query(default=None, description="按演练季度过滤，如 2026-Q3"),
    status: str | None = Query(default=None, description="待编排、待下发、进行中、已闭环"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """演练计划列表：整组进度在每次读取时按下属条目实时汇总。"""
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    items, total = service.list_plans(keyword=keyword, quarter=quarter, status=status, page=page, size=size)
    return PageResult(items=items, total=total, page=page, size=size)


@router.post("/plans", response_model=ActionResult)
def create_plan(payload: EntryPayload) -> ActionResult:
    """编排季度演练计划；缺字段、季度格式不对或重复编排都要逐条说明。"""
    plan, errors = service.create_plan(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    return ActionResult(ok=True, message="季度演练计划已编排", entry=plan)


@router.get("/plans/{plan_id}", response_model=dict)
def get_plan(plan_id: int) -> dict[str, Any]:
    """读取计划明细与整组进度；不存在时给出可读说明。"""
    plan = service.get_plan(plan_id)
    if plan is None:
        raise HTTPException(status_code=404, detail=f"演练计划 {plan_id} 不存在或已删除")
    return plan


@router.get("/plans/{plan_id}/records")
def plan_records(plan_id: int) -> dict[str, Any]:
    """整组下属演练记录；计划不存在时说明，不能静默返回。"""
    if service.get_plan(plan_id) is None:
        raise HTTPException(status_code=404, detail=f"演练计划 {plan_id} 不存在或已删除")
    items = service.list_records(str(plan_id))
    return {"plan_id": plan_id, "total": len(items), "items": items}


@router.get("/plans/{plan_id}/issues")
def plan_issues(plan_id: int) -> dict[str, Any]:
    """整组下属问题清单，供从计划列表进入整改跟踪时使用。"""
    if service.get_plan(plan_id) is None:
        raise HTTPException(status_code=404, detail=f"演练计划 {plan_id} 不存在或已删除")
    items = service.list_issues(plan_id=plan_id)
    return {"plan_id": plan_id, "total": len(items), "items": items}


# -------------------------------------------------------------- 演练记录
@router.get("/records")
def list_records(
    plan_id: str | None = Query(default=None, description="按计划过滤；传 none 只看缺少计划的孤儿记录"),
) -> dict[str, Any]:
    """演练记录列表，可按计划过滤，便于批量勾选下发。"""
    items = service.list_records(plan_id)
    return {"total": len(items), "items": items}


@router.post("/records", response_model=ActionResult)
def create_record(payload: EntryPayload) -> ActionResult:
    """在季度计划下编排一条演练记录；缺计划或缺必填字段都给出说明。"""
    record, errors = service.create_record(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    return ActionResult(ok=True, message="演练记录已编入计划", entry=record)


@router.post("/records/dispatch", response_model=BatchResult)
def dispatch_records(payload: BatchPayload) -> BatchResult:
    """批量下发：对每一条记录分别校验并返回说明，缺计划、重复下发、参演人未确认都不会只处理第一条。"""
    if not payload.ids:
        return BatchResult(ok=False, message="未勾选任何演练记录，请先勾选需要下发的记录")
    items, success, failed = service.dispatch_records(payload.ids)
    message = f"批量下发完成：成功 {success} 条，未成功 {failed} 条"
    return BatchResult(ok=failed == 0, message=message, success=success, failed=failed, items=items)


@router.post("/records/{record_id}/actions", response_model=ActionResult)
def run_record_action(record_id: int, payload: EntryPayload) -> ActionResult:
    """单条演练记录动作：参演人确认、演练结束；非法动作与错误状态都给出说明。"""
    action = str(payload.values.get("action") or "").strip()
    if action == "参演确认":
        entry, message = service.confirm_record(record_id)
    elif action == "登记结束":
        entry, message = service.finish_record(record_id)
    else:
        return ActionResult(ok=False, message=f"动作「{action}」不属于应急演练可执行范围")
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)


# -------------------------------------------------------------- 问题整改
@router.get("/issues")
def list_issues(
    plan_id: int | None = Query(default=None, description="按演练计划过滤整组问题"),
    record_id: int | None = Query(default=None, description="按单条演练记录过滤"),
    status: str | None = Query(default=None, description="待整改、整改中、待验收、已闭环"),
) -> dict[str, Any]:
    """整改跟踪清单：按计划进入时看到整组问题及其闭环进度。"""
    items = service.list_issues(plan_id=plan_id, record_id=record_id, status=status)
    return {"total": len(items), "items": items}


@router.post("/issues", response_model=ActionResult)
def create_issue(payload: EntryPayload) -> ActionResult:
    """演练结束后逐条登记问题；未结束的演练或缺字段都会被拦下并说明。"""
    issue, errors = service.create_issue(payload.values)
    if errors:
        return ActionResult(ok=False, message="；".join(errors))
    return ActionResult(ok=True, message="演练问题已登记，进入整改跟踪", entry=issue)


@router.post("/issues/{issue_id}/actions", response_model=ActionResult)
def run_issue_action(issue_id: int, payload: EntryPayload) -> ActionResult:
    """整改跟踪动作：填报整改、提交验收、确认闭环，最终走到已闭环。"""
    action = str(payload.values.pop("action", "") or "").strip()
    issue, message = service.run_issue_action(issue_id, action, payload.values)
    if issue is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=issue)


@router.get("/export")
def export_drill() -> dict[str, Any]:
    """导出应急演练数据：计划、记录、问题整组返回。"""
    plans, plan_total = service.list_plans(page=1, size=10000)
    return {
        "module": "drill",
        "plans_total": plan_total,
        "plans": plans,
        "records": service.list_records(),
        "issues": service.list_issues(),
    }
