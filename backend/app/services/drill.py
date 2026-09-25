"""应急演练业务规则：季度计划编排、演练记录批量下发与问题整改闭环。

三张表围绕一次季度演练展开：
- drill_plan：按季度编排的演练计划，整组进度由下属记录与问题实时汇总；
- drill_record：逐条演练记录，先由参演人确认，再批量下发给参演班组，演练结束后逐条登记问题；
- drill_issue：演练暴露的问题，按 待整改→整改中→待验收→已闭环 跟踪到闭环。
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.store import store

PLAN_MODULE = "drill_plan"
RECORD_MODULE = "drill_record"
ISSUE_MODULE = "drill_issue"

PLAN_REQUIRED = ["演练季度", "演练主题"]
RECORD_REQUIRED = ["演练名称", "参演班组"]
ISSUE_REQUIRED = ["问题描述", "责任人"]

RECORD_STATUS = ["待确认", "待下发", "已下发", "已演练"]
ISSUE_STATUS = ["待整改", "整改中", "待验收", "已闭环"]
ISSUE_ACTIONS = {"填报整改": "整改中", "提交验收": "待验收", "确认闭环": "已闭环"}

QUARTER_PATTERN = re.compile(r"^\d{4}-Q[1-4]$")


def _new_id(rows: list[dict[str, Any]]) -> int:
    return max((int(row.get("id", 0)) for row in rows), default=0) + 1


def _plan_id_of(record: dict[str, Any]) -> int | None:
    raw = record.get("plan_id")
    try:
        value = int(raw)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return value if value > 0 else None


class DrillService:
    # ------------------------------------------------------------------ 计划
    def list_plans(
        self,
        *,
        keyword: str | None = None,
        quarter: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = [self._annotate_plan(dict(plan)) for plan in store.rows(PLAN_MODULE)]
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("计划编号", "")) or keyword in str(row.get("演练主题", ""))
            ]
        if quarter:
            rows = [row for row in rows if row.get("演练季度") == quarter]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        plan = store.find(PLAN_MODULE, plan_id)
        if plan is None:
            return None
        return self._annotate_plan(plan)

    def create_plan(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in PLAN_REQUIRED if not str(values.get(field) or "").strip()]
        errors = [f"缺少必填字段：{name}" for name in missing]
        quarter = str(values.get("演练季度") or "").strip()
        if quarter and not QUARTER_PATTERN.match(quarter):
            errors.append("演练季度格式应为 YYYY-Qn，例如 2026-Q3")
        rows = store.rows(PLAN_MODULE)
        if quarter and any(row.get("演练季度") == quarter for row in rows):
            errors.append(f"{quarter} 已编排过演练计划，同一季度请勿重复编排")
        if errors:
            return None, errors
        plan = {
            "id": _new_id(rows),
            "计划编号": self._next_code(rows, "计划编号", f"DRPL-{quarter.replace('-', '')}"),
            "演练季度": quarter,
            "演练主题": str(values["演练主题"]).strip(),
            "演练场景": str(values.get("演练场景") or "").strip(),
            "计划日期": str(values.get("计划日期") or date.today().isoformat()),
            "编制人": str(values.get("编制人") or "").strip(),
        }
        plan["status"] = "待编排"
        plan["pending"] = True
        plan["abnormal"] = False
        rows.append(plan)
        return self._annotate_plan(plan), []

    # ------------------------------------------------------------------ 记录
    def list_records(self, plan_id: str | None = None) -> list[dict[str, Any]]:
        rows = store.rows(RECORD_MODULE)
        if plan_id is not None:
            if plan_id in ("none", "0"):
                rows = [row for row in rows if _plan_id_of(row) is None]
            else:
                try:
                    target = int(plan_id)
                except ValueError:
                    return []
                rows = [row for row in rows if _plan_id_of(row) == target]
        return [self._annotate_record(row) for row in rows]

    def create_record(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in RECORD_REQUIRED if not str(values.get(field) or "").strip()]
        errors = [f"缺少必填字段：{name}" for name in missing]
        plan_id = _plan_id_of({"plan_id": values.get("plan_id")})
        if values.get("plan_id") not in (None, "") and plan_id is None:
            errors.append("演练计划编号格式不正确，请从季度计划中编排演练")
        elif plan_id is not None and store.find(PLAN_MODULE, plan_id) is None:
            errors.append(f"演练计划 {plan_id} 不存在，请先编排季度演练计划")
        if errors:
            return None, errors
        rows = store.rows(RECORD_MODULE)
        record = {
            "id": _new_id(rows),
            "plan_id": plan_id,
            "演练编号": self._next_code(rows, "演练编号", "DRIL"),
            "演练名称": str(values["演练名称"]).strip(),
            "参演班组": str(values["参演班组"]).strip(),
            "参演人员": str(values.get("参演人员") or "").strip(),
            "演练时间": str(values.get("演练时间") or "").strip(),
            "确认状态": "未确认",
        }
        record["status"] = "待确认"
        record["pending"] = True
        record["abnormal"] = False
        rows.append(record)
        self._refresh_plans(record)
        return self._annotate_record(record), []

    def confirm_record(self, record_id: int) -> tuple[dict[str, Any] | None, str]:
        """参演人确认参演：待确认 → 待下发，确认后才允许批量下发。"""
        record = store.find(RECORD_MODULE, record_id)
        if record is None:
            return None, f"演练记录 {record_id} 不存在或已删除"
        if not str(record.get("参演人员") or "").strip():
            return None, "参演名单为空，请先登记参演人员再确认"
        if record["status"] != "待确认":
            return None, f"演练记录当前为「{record['status']}」，参演人无需重复确认"
        record["确认状态"] = "已确认"
        record["status"] = "待下发"
        self._refresh_plans(record)
        return self._annotate_record(record), "参演人已确认，演练记录待下发"

    def finish_record(self, record_id: int) -> tuple[dict[str, Any] | None, str]:
        """演练结束：已下发 → 已演练，之后才能逐条登记问题。"""
        record = store.find(RECORD_MODULE, record_id)
        if record is None:
            return None, f"演练记录 {record_id} 不存在或已删除"
        if record["status"] != "已下发":
            return None, f"演练记录当前为「{record['status']}」，只有已下发的演练才能登记结束"
        record["status"] = "已演练"
        self._refresh_record_flag(record)
        self._refresh_plans(record)
        return self._annotate_record(record), "应急演练已结束，可逐条登记暴露问题"

    def dispatch_records(
        self, ids: list[Any]
    ) -> tuple[list[dict[str, Any]], int, int]:
        """批量下发：逐条校验并收集**全部**说明，缺计划、重复下发、参演人未确认都不打断后续条目。"""
        results: list[dict[str, Any]] = []
        success = 0
        for raw_id in ids:
            try:
                record_id = int(raw_id)  # type: ignore[arg-type]
            except (TypeError, ValueError):
                results.append({"id": raw_id, "ok": False, "reasons": ["演练记录编号格式不正确"]})
                continue
            record = store.find(RECORD_MODULE, record_id)
            if record is None:
                results.append({
                    "id": record_id,
                    "演练编号": f"DRIL-{record_id:04d}",
                    "ok": False,
                    "reasons": [f"演练记录 {record_id} 不存在或已删除，未能下发"],
                })
                continue
            reasons = self._dispatch_reasons(record)
            item = {
                "id": record_id,
                "演练编号": record.get("演练编号"),
                "演练名称": record.get("演练名称"),
                "参演班组": record.get("参演班组"),
            }
            if reasons:
                item["ok"] = False
                item["reasons"] = reasons
            else:
                record["status"] = "已下发"
                record["下发时间"] = date.today().isoformat()
                self._refresh_plans(record)
                item["ok"] = True
                item["reasons"] = []
                item["status"] = "已下发"
                success += 1
            results.append(item)
        return results, success, len(results) - success

    def _dispatch_reasons(self, record: dict[str, Any]) -> list[str]:
        reasons: list[str] = []
        plan_id = _plan_id_of(record)
        if plan_id is None or store.find(PLAN_MODULE, plan_id or 0) is None:
            reasons.append("缺少演练计划：该记录未编入季度演练计划，不能下发")
        if record.get("status") in ("已下发", "已演练"):
            reasons.append(f"演练记录已下发（当前状态：{record['status']}），请勿重复下发")
        if not str(record.get("参演人员") or "").strip():
            reasons.append("参演人未确认：参演名单为空，不能下发")
        elif record.get("确认状态") != "已确认" or record.get("status") == "待确认":
            reasons.append("参演人未确认：请参演人员确认后再下发")
        return reasons

    # ------------------------------------------------------------------ 问题
    def list_issues(
        self,
        *,
        plan_id: int | None = None,
        record_id: int | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = store.rows(ISSUE_MODULE)
        if plan_id is not None:
            record_ids = {
                int(row["id"])
                for row in store.rows(RECORD_MODULE)
                if _plan_id_of(row) == plan_id
            }
            rows = [row for row in rows if int(row.get("record_id", 0)) in record_ids]
        if record_id is not None:
            rows = [row for row in rows if int(row.get("record_id", 0)) == record_id]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        return [self._annotate_issue(row) for row in rows]

    def create_issue(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in ISSUE_REQUIRED if not str(values.get(field) or "").strip()]
        errors = [f"缺少必填字段：{name}" for name in missing]
        record: dict[str, Any] | None = None
        raw_record_id = values.get("record_id")
        try:
            record_id = int(raw_record_id)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            record_id = 0
            if raw_record_id not in (None, ""):
                errors.append("演练记录编号格式不正确")
        if raw_record_id in (None, ""):
            errors.append("缺少关联演练记录，请选择已结束的演练")
        else:
            record = store.find(RECORD_MODULE, record_id)
            if record is None:
                errors.append(f"演练记录 {record_id} 不存在，问题无法登记")
            elif record.get("status") != "已演练":
                errors.append(
                    f"演练「{record.get('演练名称')}」当前为「{record.get('status')}」，"
                    "请先登记演练结束再逐条登记问题"
                )
        if errors:
            return None, errors
        assert record is not None
        rows = store.rows(ISSUE_MODULE)
        issue = {
            "id": _new_id(rows),
            "record_id": record_id,
            "问题编号": self._next_code(rows, "问题编号", "DRIS"),
            "问题描述": str(values["问题描述"]).strip(),
            "责任人": str(values["责任人"]).strip(),
            "整改期限": str(values.get("整改期限") or "").strip(),
            "整改措施": "",
            "验收人": "",
            "闭环时间": "",
        }
        issue["status"] = "待整改"
        issue["pending"] = True
        issue["abnormal"] = True
        rows.append(issue)
        self._refresh_record_flag(record)
        self._refresh_plans(record)
        return self._annotate_issue(issue), []

    def run_issue_action(
        self, issue_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        issue = store.find(ISSUE_MODULE, issue_id)
        if issue is None:
            return None, f"整改问题 {issue_id} 不存在或已归档"
        if action not in ISSUE_ACTIONS:
            return None, f"动作「{action}」不属于整改跟踪可执行范围"
        target = ISSUE_ACTIONS[action]
        current = issue.get("status")
        if current == target:
            return None, f"问题当前已是「{current}」，请勿重复{action}"
        expected = ISSUE_STATUS[ISSUE_STATUS.index(target) - 1]
        if current != expected:
            return None, f"问题当前为「{current}」，需先流转到「{expected}」才能{action}"
        values = values or {}
        if action == "填报整改":
            measure = str(values.get("整改措施") or "").strip()
            if not measure:
                return None, "请填写整改措施后再提交"
            issue["整改措施"] = measure
        if action == "确认闭环":
            issue["验收人"] = str(values.get("验收人") or "").strip() or issue.get("验收人", "")
            issue["闭环时间"] = date.today().isoformat()
        issue["status"] = target
        issue["pending"] = target != "已闭环"
        issue["abnormal"] = target == "待整改"
        record = store.find(RECORD_MODULE, int(issue.get("record_id", 0)))
        if record is not None:
            self._refresh_record_flag(record)
            self._refresh_plans(record)
        return self._annotate_issue(issue), f"问题已{action}"

    # ------------------------------------------------------------------ 汇总
    def _plan_records(self, plan_id: int) -> list[dict[str, Any]]:
        return [row for row in store.rows(RECORD_MODULE) if _plan_id_of(row) == plan_id]

    def _record_issues(self, record_id: int) -> list[dict[str, Any]]:
        return [row for row in store.rows(ISSUE_MODULE) if int(row.get("record_id", 0)) == record_id]

    def _annotate_record(self, record: dict[str, Any]) -> dict[str, Any]:
        issues = self._record_issues(int(record["id"]))
        closed = sum(1 for issue in issues if issue.get("status") == "已闭环")
        record["问题数"] = len(issues)
        record["闭环数"] = closed
        plan_id = _plan_id_of(record)
        record["计划编号"] = (
            store.find(PLAN_MODULE, plan_id).get("计划编号") if plan_id else ""
        )
        return record

    def _annotate_issue(self, issue: dict[str, Any]) -> dict[str, Any]:
        record = store.find(RECORD_MODULE, int(issue.get("record_id", 0)))
        issue["演练编号"] = record.get("演练编号", "") if record else ""
        issue["演练名称"] = record.get("演练名称", "") if record else ""
        return issue

    def _annotate_plan(self, plan: dict[str, Any]) -> dict[str, Any]:
        """整组进度完全按下属演练记录与问题条目实时汇总，不读取任何缓存初值。"""
        records = self._plan_records(int(plan["id"]))
        confirmed = sum(1 for row in records if row.get("确认状态") == "已确认")
        dispatched = sum(1 for row in records if row.get("status") in ("已下发", "已演练"))
        finished = sum(1 for row in records if row.get("status") == "已演练")
        issue_rows = [
            issue
            for row in records
            for issue in self._record_issues(int(row["id"]))
        ]
        issue_total = len(issue_rows)
        closed = sum(1 for issue in issue_rows if issue.get("status") == "已闭环")
        if not records:
            plan_status = "待编排"
        elif finished == len(records) and closed == issue_total:
            plan_status = "已闭环"
        elif dispatched:
            plan_status = "进行中"
        else:
            plan_status = "待下发"
        plan["status"] = plan_status
        plan["pending"] = plan_status != "已闭环"
        plan["abnormal"] = any(issue.get("abnormal") for issue in issue_rows)
        plan["记录数"] = len(records)
        plan["已确认数"] = confirmed
        plan["已下发数"] = dispatched
        plan["已演练数"] = finished
        plan["问题数"] = issue_total
        plan["闭环数"] = closed
        plan["演练进度"] = f"{finished}/{len(records)}"
        plan["闭环进度"] = f"{closed}/{issue_total}"
        plan["整改进度"] = round(closed * 100 / issue_total) if issue_total else 0
        return plan

    def _refresh_record_flag(self, record: dict[str, Any]) -> None:
        issues = self._record_issues(int(record["id"]))
        open_issues = [issue for issue in issues if issue.get("status") != "已闭环"]
        record["问题数"] = len(issues)
        record["闭环数"] = len(issues) - len(open_issues)
        record["pending"] = record.get("status") != "已演练" or bool(open_issues)
        record["abnormal"] = any(issue.get("abnormal") for issue in open_issues)

    def _refresh_plans(self, record: dict[str, Any]) -> None:
        plan_id = _plan_id_of(record)
        if plan_id is not None:
            plan = store.find(PLAN_MODULE, plan_id)
            if plan is not None:
                self._annotate_plan(plan)

    def _next_code(self, rows: list[dict[str, Any]], field: str, prefix: str) -> str:
        seq = 1
        for row in rows:
            code = str(row.get(field) or "")
            if code.startswith(prefix):
                tail = code.rsplit("-", 1)[-1]
                if tail.isdigit():
                    seq = max(seq, int(tail) + 1)
        width = 4 if prefix in ("DRIL", "DRIS") else 2
        return f"{prefix}-{seq:0{width}d}"
