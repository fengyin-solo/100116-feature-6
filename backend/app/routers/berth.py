"""泊位计划接口：维护泊位计划，覆盖确认编排、确认靠泊、确认离泊等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.berth import (
    DEFAULT_SORT,
    SORT_FIELDS,
    STATUS_ORDER,
    BerthService,
)

router = APIRouter(prefix="/api/berth", tags=["泊位计划"])

service = BerthService()

LIST_FIELDS = ["计划编号", "泊位编号", "靠泊船舶", "计划靠泊时间", "计划离泊时间", "船长", "吃水深度", "计划状态"]


def _list_kwargs(
    plan_no: str | None,
    berth_no: str | None,
    vessel: str | None,
    status: str | None,
    sort_field: str | None,
    sort_order: str,
    page: int,
    size: int,
    locate_id: int | None,
) -> dict[str, Any]:
    plan_no = plan_no.strip() if plan_no else None
    berth_no = berth_no.strip() if berth_no else None
    vessel = vessel.strip() if vessel else None

    if status is not None and status not in STATUS_ORDER:
        raise HTTPException(
            status_code=400,
            detail=f"计划状态「{status}」不支持，可选：{'、'.join(STATUS_ORDER)}",
        )
    if sort_field is not None and sort_field not in SORT_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持按「{sort_field}」排序，可选列：{'、'.join(SORT_FIELDS)}",
        )
    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="排序方向只支持 asc 或 desc")
    if page < 1:
        raise HTTPException(status_code=400, detail="页码必须从 1 开始")
    if size < 1:
        raise HTTPException(status_code=400, detail="每页条数至少为 1")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")

    return {
        "plan_no": plan_no,
        "berth_no": berth_no,
        "vessel": vessel,
        "status": status,
        "sort_field": sort_field,
        "sort_order": sort_order,
        "page": page,
        "size": size,
        "locate_id": locate_id,
    }


@router.get("", response_model=PageResult[dict])
def list_entries(
    plan_no: str | None = Query(default=None, description="按计划编号模糊检索"),
    berth_no: str | None = Query(default=None, description="按泊位编号模糊检索"),
    vessel: str | None = Query(default=None, description="按靠泊船舶模糊检索"),
    status: str | None = Query(default=None, description="待编排、已编排、已靠泊、已离泊"),
    sort_field: str = DEFAULT_SORT[0],
    sort_order: str = "asc",
    page: int = 1,
    size: int = 10,
    locate_id: int | None = Query(default=None, description="定位到某条记录所在页"),
) -> PageResult[dict]:
    """按泊位编号、靠泊船舶与计划状态联合过滤；没有命中时返回空页，不报错。"""
    kwargs = _list_kwargs(plan_no, berth_no, vessel, status, sort_field, sort_order, page, size, locate_id)
    items, total, actual_page, located = service.list_entries(**kwargs)
    pages = max(1, (total + size - 1) // size)
    return PageResult(
        items=items,
        total=total,
        page=actual_page,
        size=size,
        pages=pages,
        locate_id=located,
    )


@router.get("/export")
def export_entries(
    plan_no: str | None = None,
    berth_no: str | None = None,
    vessel: str | None = None,
    status: str | None = None,
    sort_field: str = DEFAULT_SORT[0],
    sort_order: str = "asc",
) -> dict[str, Any]:
    """导出泊位计划清单：返回当前过滤条件、当前排序下的全量数据。"""
    kwargs = _list_kwargs(plan_no, berth_no, vessel, status, sort_field, sort_order, 1, 10000, None)
    items, total, _, _ = service.list_entries(**kwargs)
    return {"module": "berth", "total": total, "items": items}


@router.get("/{entry_id}", response_model=dict)
def get_entry(entry_id: int) -> dict:
    """读取单条泊位计划明细；不存在时给出可读的错误说明。"""
    entry = service.get_entry(entry_id)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"泊位计划 {entry_id} 不存在或已归档")
    return entry


@router.post("", response_model=ActionResult)
def create_entry(payload: EntryPayload) -> ActionResult:
    """登记一条泊位计划，缺字段时说明原因而不是静默丢弃。"""
    entry, missing = service.create_entry(payload.values)
    if missing:
        return ActionResult(ok=False, message=f"缺少必填字段：{'、'.join(missing)}")
    return ActionResult(ok=True, message="泊位计划已登记", entry=entry)


@router.post("/{entry_id}/actions", response_model=ActionResult)
def run_action(entry_id: int, payload: EntryPayload) -> ActionResult:
    """对单条泊位计划执行确认编排、确认靠泊、确认离泊；不允许的动作会被拦下并说明原因。"""
    action = str(payload.values.get("action") or "").strip()
    entry, message = service.run_action(entry_id, action)
    if entry is None:
        return ActionResult(ok=False, message=message)
    return ActionResult(ok=True, message=message, entry=entry)
