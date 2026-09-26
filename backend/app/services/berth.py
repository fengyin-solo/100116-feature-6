"""泊位计划业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "berth"
REQUIRED_FIELDS = ["计划编号", "泊位编号", "靠泊船舶"]
STATUS_ORDER = ["待编排", "已编排", "已靠泊", "已离泊"]
ACTION_RULES = {"确认编排": "已编排", "确认靠泊": "已靠泊", "确认离泊": "已离泊"}
NEGATIVE_ACTIONS: list[str] = []

# 列表支持的检索条件：查询参数名 -> 记录字段名，多个条件之间是“并且”的关系
FILTER_FIELDS = {"keyword": "计划编号", "berth": "泊位编号", "vessel": "靠泊船舶"}
# 允许前端指定的排序字段，先后次序只认这几个，其余一律在路由层拦下
SORTABLE_FIELDS = ["计划编号", "泊位编号", "靠泊船舶", "计划靠泊时间", "计划离泊时间"]


def _present(row: dict[str, Any]) -> dict[str, Any]:
    """展示层统一把「计划状态」对齐到流转状态，避免列表里看到过期的占位文本。"""
    return {**row, "计划状态": row.get("status", "")}


def _apply_filters(
    rows: list[dict[str, Any]],
    *,
    keyword: str | None = None,
    berth: str | None = None,
    vessel: str | None = None,
    status: str | None = None,
) -> list[dict[str, Any]]:
    conditions = {"keyword": keyword, "berth": berth, "vessel": vessel}
    for param, value in conditions.items():
        text = str(value or "").strip()
        if not text:
            continue
        field = FILTER_FIELDS[param]
        rows = [row for row in rows if text.lower() in str(row.get(field) or "").lower()]
    if status:
        rows = [row for row in rows if row.get("status") == status]
    return rows


def _apply_sort(
    rows: list[dict[str, Any]],
    *,
    sort: str | None = None,
    order: str = "asc",
) -> list[dict[str, Any]]:
    if not sort:
        return rows
    # 主键之外再带上 id 兜底，保证同一字段值下先后次序稳定、可复现
    return sorted(
        rows,
        key=lambda row: (str(row.get(sort) or ""), int(row.get("id", 0))),
        reverse=(order == "desc"),
    )


class BerthService:
    def list_entries(
        self,
        *,
        keyword: str | None = None,
        berth: str | None = None,
        vessel: str | None = None,
        status: str | None = None,
        sort: str | None = None,
        order: str = "asc",
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = _apply_filters(store.rows(MODULE), keyword=keyword, berth=berth, vessel=vessel, status=status)
        rows = _apply_sort(rows, sort=sort, order=order)
        total = len(rows)
        start = max(page - 1, 0) * size
        return [_present(row) for row in rows[start:start + size]], total

    def locate_entry(
        self,
        entry_id: int,
        *,
        keyword: str | None = None,
        berth: str | None = None,
        vessel: str | None = None,
        status: str | None = None,
        sort: str | None = None,
        order: str = "asc",
    ) -> tuple[int, int] | None:
        """在当前筛选与排序口径下找一条记录的位置，返回（从 0 起的序号, 命中总数）。"""
        rows = _apply_filters(store.rows(MODULE), keyword=keyword, berth=berth, vessel=vessel, status=status)
        rows = _apply_sort(rows, sort=sort, order=order)
        for index, row in enumerate(rows):
            if int(row.get("id", 0)) == entry_id:
                return index, len(rows)
        return None

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        entry = store.find(MODULE, entry_id)
        return _present(entry) if entry is not None else None

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return _present(entry), []

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
        return _present(entry), f"泊位计划已{action}"
