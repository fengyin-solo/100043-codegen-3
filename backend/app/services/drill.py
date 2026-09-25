"""应急演练业务规则：季度演练计划编排、批量下发、参演确认与问题整改闭环。

和其它模块不同，这里涉及三张表：
- drill_plan：按季度编排的演练计划；
- drill_record：挂在计划下、下发给参演班组的演练记录；
- drill_issue：演练结束后逐条登记的问题，跟踪到整改闭环。

整组进度不落地存储，每次都按演练记录与问题的实际状态现算，避免返回列表再进来时
进度停在初始值。
"""
from __future__ import annotations

from typing import Any

from app.store import store

PLAN_MODULE = "drill_plan"
RECORD_MODULE = "drill_record"
ISSUE_MODULE = "drill_issue"

PLAN_REQUIRED_FIELDS = ["计划编号", "演练季度", "演练名称", "计划演练日"]
ISSUE_REQUIRED_FIELDS = ["演练编号", "问题描述", "责任人"]

RECORD_STATUS_ORDER = ["待下发", "已下发", "已完成"]
ISSUE_STATUS_ORDER = ["待整改", "整改中", "已闭环"]
ISSUE_ACTION_RULES = {"开始整改": "整改中", "闭环验收": "已闭环"}


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
        rows = store.rows(PLAN_MODULE)
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in str(row.get("计划编号", ""))
                or keyword in str(row.get("演练名称", ""))
            ]
        if quarter:
            rows = [row for row in rows if row.get("演练季度") == quarter]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        page_rows = rows[start:start + size]
        return [self._plan_with_progress(row) for row in page_rows], total

    def get_plan(self, plan_id: int) -> dict[str, Any] | None:
        plan = store.find(PLAN_MODULE, plan_id)
        if plan is None:
            return None
        return self._plan_with_progress(plan)

    def find_plan_by_no(self, plan_no: str) -> dict[str, Any] | None:
        for row in store.rows(PLAN_MODULE):
            if str(row.get("计划编号", "")) == plan_no:
                return row
        return None

    def create_plan(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [
            field for field in PLAN_REQUIRED_FIELDS if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, missing
        rows = store.rows(PLAN_MODULE)
        plan_no = str(values["计划编号"]).strip()
        if any(str(row.get("计划编号", "")) == plan_no for row in rows):
            return None, ["计划编号重复"]
        plan = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        plan.update({field: values.get(field) for field in PLAN_REQUIRED_FIELDS})
        plan.update({
            "演练类型": str(values.get("演练类型") or "综合演练").strip(),
            "编排人员": str(values.get("编排人员") or "").strip(),
            "编排日期": str(values.get("编排日期") or "").strip(),
            "status": "已编排",
            "pending": True,
            "abnormal": False,
        })
        rows.append(plan)
        return self._plan_with_progress(plan), []

    def _plan_with_progress(self, plan: dict[str, Any]) -> dict[str, Any]:
        """把计划连同其名下记录、问题的整组进度一起返回（每次现算，不读缓存值）。"""
        detail = dict(plan)
        plan_no = str(plan.get("计划编号", ""))
        records = [
            row
            for row in store.rows(RECORD_MODULE)
            if str(row.get("计划编号", "")) == plan_no
        ]
        record_ids = [int(row["id"]) for row in records]
        issues = [
            row
            for row in store.rows(ISSUE_MODULE)
            if int(row.get("演练记录id", 0)) in record_ids
        ]
        dispatched = sum(1 for row in records if row.get("status") != "待下发")
        finished = sum(1 for row in records if row.get("status") == "已完成")
        closed = sum(1 for row in issues if row.get("status") == "已闭环")
        detail.update({
            "演练记录数": len(records),
            "已下发数": dispatched,
            "已完成数": finished,
            "问题总数": len(issues),
            "已闭环数": closed,
            "整组进度": f"{closed}/{len(issues)}" if issues else "0/0",
            "整改闭环率": f"{round(closed / len(issues) * 100)}%" if issues else "—",
        })
        return detail

    # -------------------------------------------------------------- 演练记录
    def list_records(
        self,
        *,
        plan_no: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(RECORD_MODULE)
        if plan_no:
            rows = [row for row in rows if str(row.get("计划编号", "")) == plan_no]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def find_record_by_no(self, record_no: str) -> dict[str, Any] | None:
        for row in store.rows(RECORD_MODULE):
            if str(row.get("演练编号", "")) == record_no:
                return row
        return None

    def confirm_participants(self, record_id: int) -> tuple[dict[str, Any] | None, str]:
        record = store.find(RECORD_MODULE, record_id)
        if record is None:
            return None, f"演练记录 {record_id} 不存在或已归档"
        if not str(record.get("参演人员") or "").strip():
            return None, "参演名单为空，无法确认，请先补齐参演人员"
        record["人员已确认"] = True
        return record, f"{record.get('参演班组', '参演班组')} 的参演人员已确认"

    def batch_dispatch(
        self, record_ids: list[Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """批量下发演练记录。

        先逐条把全部问题找出来（缺计划 / 重复下发 / 参演人未确认），只要有一条不通过
        就整批不下发，避免同组记录只发出去一半；返回值里每条记录都带说明，不只报第一条。
        """
        return self._batch_transition(
            record_ids,
            allow_from="待下发",
            target="已下发",
            action="下发",
        )

    def batch_finish(
        self, record_ids: list[Any]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """演练结束：把已下发的记录整批置为已完成，同样逐条给出不能结束的说明。"""
        return self._batch_transition(
            record_ids,
            allow_from="已下发",
            target="已完成",
            action="结束演练",
        )

    def _batch_transition(
        self,
        record_ids: list[Any],
        *,
        allow_from: str,
        target: str,
        action: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        # 请求里同一条记录可能被勾选两次，先按 id 去重，避免重复处理。
        unique_ids: list[int] = []
        for raw in record_ids:
            try:
                rid = int(raw)
            except (TypeError, ValueError):
                continue
            if rid not in unique_ids:
                unique_ids.append(rid)

        picked: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        for rid in unique_ids:
            record = store.find(RECORD_MODULE, rid)
            if record is None:
                failures.append({
                    "演练记录id": rid,
                    "演练编号": f"id={rid}",
                    "原因": "演练记录不存在或已归档",
                })
                continue
            reasons = self._record_blockers(record, allow_from, action)
            if reasons:
                failures.append({
                    "演练记录id": rid,
                    "演练编号": record.get("演练编号", f"id={rid}"),
                    "参演班组": record.get("参演班组", ""),
                    "原因": "；".join(reasons),
                })
            else:
                picked.append(record)

        # 有任何一条不合规就整批不动作，问题一次性全部带回前端说明。
        if failures:
            return [], failures

        from datetime import date

        today = date.today().isoformat()
        for record in picked:
            record["status"] = target
            if target == "已下发":
                record["下发时间"] = today
            if target == "已完成":
                record["完成时间"] = today
            record["pending"] = target != RECORD_STATUS_ORDER[-1]
        return picked, []

    def _record_blockers(
        self, record: dict[str, Any], allow_from: str, action: str
    ) -> list[str]:
        reasons: list[str] = []
        plan_no = str(record.get("计划编号") or "").strip()
        if not plan_no or self.find_plan_by_no(plan_no) is None:
            reasons.append(
                f"缺演练计划（计划编号「{plan_no or '空'}」不存在），请先编排季度演练计划并挂接"
            )
        if record.get("status") != allow_from:
            reasons.append(
                f"重复{action}：该记录状态为「{record.get('status')}」，"
                f"只有「{allow_from}」状态的记录才能{action}"
            )
        if action == "下发" and not record.get("人员已确认"):
            reasons.append("参演人未确认：需参演班组确认参演名单后才能下发")
        return reasons

    # ------------------------------------------------------------------ 问题
    def list_issues(
        self,
        *,
        plan_no: str | None = None,
        record_no: str | None = None,
        status: str | None = None,
        page: int = 1,
        size: int = 100,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = store.rows(ISSUE_MODULE)
        if record_no:
            rows = [row for row in rows if str(row.get("演练编号", "")) == record_no]
        if plan_no:
            rows = [row for row in rows if str(row.get("计划编号", "")) == plan_no]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def create_issue(
        self, values: dict[str, Any]
    ) -> tuple[dict[str, Any] | None, list[str], str]:
        """演练结束后逐条登记问题；缺字段、演练未结束都要说明，不静默落库。"""
        missing = [
            field for field in ISSUE_REQUIRED_FIELDS if not str(values.get(field) or "").strip()
        ]
        if missing:
            return None, missing, ""
        record = self.find_record_by_no(str(values["演练编号"]).strip())
        if record is None:
            return None, [], f"演练编号「{values['演练编号']}」不存在，问题无法挂接"
        if record.get("status") != "已完成":
            return None, [], (
                f"演练「{record.get('演练编号')}」尚未结束"
                f"（当前状态：{record.get('status')}），需结束演练后才能登记问题"
            )
        rows = store.rows(ISSUE_MODULE)
        issue = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        issue.update({
            "演练编号": record.get("演练编号"),
            "演练记录id": int(record["id"]),
            "计划编号": record.get("计划编号", ""),
            "参演班组": record.get("参演班组", ""),
            "问题描述": str(values["问题描述"]).strip(),
            "问题分类": str(values.get("问题分类") or "一般问题").strip(),
            "责任人": str(values["责任人"]).strip(),
            "整改要求": str(values.get("整改要求") or "").strip(),
            "整改措施": "",
            "登记时间": str(values.get("登记时间") or "").strip(),
            "闭环时间": "",
            "status": "待整改",
            "pending": True,
            "abnormal": True,
        })
        rows.append(issue)
        return issue, [], ""

    def run_issue_action(
        self, issue_id: int, action: str, values: dict[str, Any] | None = None
    ) -> tuple[dict[str, Any] | None, str]:
        issue = store.find(ISSUE_MODULE, issue_id)
        if issue is None:
            return None, f"问题 {issue_id} 不存在或已归档"
        if action not in ISSUE_ACTION_RULES:
            return None, f"动作「{action}」不属于整改跟踪可执行范围"
        target = ISSUE_ACTION_RULES[action]
        if action == "闭环验收" and not str((values or {}).get("整改措施") or "").strip():
            return None, "闭环前必须填写整改措施与验收说明，不能空口闭环"
        if target == "整改中" and issue.get("status") != "待整改":
            return None, f"问题当前为「{issue.get('status')}」，不能开始整改"
        if target == "已闭环" and issue.get("status") not in ("待整改", "整改中"):
            return None, f"问题当前为「{issue.get('status')}」，无法再次闭环"
        from datetime import date

        if str((values or {}).get("整改措施") or "").strip():
            issue["整改措施"] = str(values["整改措施"]).strip()
        issue["status"] = target
        issue["pending"] = target != "已闭环"
        issue["abnormal"] = target != "已闭环"
        if target == "已闭环":
            issue["闭环时间"] = date.today().isoformat()
        return issue, f"问题已{action}"
