"""泊位计划业务规则：状态流转、字段校验、筛选排序与命中定位都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "berth"
REQUIRED_FIELDS = ["计划编号", "泊位编号", "靠泊船舶"]
STATUS_ORDER = ["待编排", "已编排", "已靠泊", "已离泊"]
ACTION_RULES = {"确认编排": "已编排", "确认靠泊": "已靠泊", "确认离泊": "已离泊"}
NEGATIVE_ACTIONS = []

# 允许排序的列，状态列按流转次序而不是字面量排
SORT_FIELDS = ["计划编号", "泊位编号", "靠泊船舶", "计划靠泊时间", "计划离泊时间", "船长", "吃水深度", "计划状态"]
NUMERIC_FIELDS = ["船长", "吃水深度"]
DEFAULT_SORT = ("计划靠泊时间", "asc")


class BerthService:
    def list_entries(
        self,
        *,
        plan_no: str | None = None,
        berth_no: str | None = None,
        vessel: str | None = None,
        status: str | None = None,
        sort_field: str | None = None,
        sort_order: str = "asc",
        page: int = 1,
        size: int = 20,
        locate_id: int | None = None,
    ) -> tuple[list[dict[str, Any]], int, int, int | None]:
        """按泊位编号、靠泊船舶、计划状态（以及计划编号）联合过滤。

        返回 (当前页记录, 命中总数, 实际页码, 定位记录 id)。
        locate_id 给出时，翻到该记录在结果集中所在的页，由前端滚动定位。
        """
        rows = store.rows(MODULE)
        if plan_no:
            rows = [row for row in rows if plan_no in str(row.get("计划编号", ""))]
        if berth_no:
            rows = [row for row in rows if berth_no in str(row.get("泊位编号", ""))]
        if vessel:
            rows = [row for row in rows if vessel in str(row.get("靠泊船舶", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]

        field = sort_field if sort_field in SORT_FIELDS else DEFAULT_SORT[0]
        reverse = sort_order == "desc"
        status_rank = {name: index for index, name in enumerate(STATUS_ORDER)}

        def sort_key(row: dict[str, Any]) -> tuple[Any, ...]:
            if field in NUMERIC_FIELDS:
                try:
                    value: Any = float(str(row.get(field, "")).strip())
                except ValueError:
                    value = float("inf")
            elif field == "计划状态":
                value = status_rank.get(str(row.get("status", "")), len(STATUS_ORDER))
            else:
                value = str(row.get(field, "") or "")
            # 同序值再按 id 兜底，保证分页边界稳定，翻页不会串记录
            return (value, int(row.get("id", 0)))

        rows = sorted(rows, key=sort_key, reverse=reverse)
        total = len(rows)
        pages = max(1, (total + size - 1) // size)

        located: int | None = None
        if locate_id is not None:
            for index, row in enumerate(rows):
                if int(row.get("id", 0)) == locate_id:
                    page = index // size + 1
                    located = locate_id
                    break

        page = min(max(page, 1), pages)
        start = (page - 1) * size
        return [self._view(row) for row in rows[start:start + size]], total, page, located

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return self._view(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["计划靠泊时间"] = values.get("计划靠泊时间")
        entry["计划离泊时间"] = values.get("计划离泊时间")
        entry["船长"] = values.get("船长")
        entry["吃水深度"] = values.get("吃水深度")
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return self._view(entry), []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"泊位计划 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于泊位计划可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return self._view(entry), f"泊位计划已{action}"

    @staticmethod
    def _view(row: dict[str, Any]) -> dict[str, Any]:
        """对外视图：列表里的“计划状态”列始终取真实流转状态，避免脏数据冒充。"""
        view = dict(row)
        view["计划状态"] = row.get("status")
        return view
