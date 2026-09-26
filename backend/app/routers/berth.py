"""泊位计划接口：维护泊位计划，覆盖确认编排、确认靠泊、确认离泊等动作。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.schemas import ActionResult, EntryPayload, PageResult
from app.services.berth import SORTABLE_FIELDS, STATUS_ORDER, BerthService

router = APIRouter(prefix="/api/berth", tags=["泊位计划"])

service = BerthService()

LIST_FIELDS = ["计划编号", "泊位编号", "靠泊船舶", "计划靠泊时间", "计划离泊时间", "船长", "吃水深度", "计划状态"]
STATUSES = STATUS_ORDER
SORT_ORDERS = ("asc", "desc")


def _validate_query(status: str | None, sort: str | None, order: str, page: int, size: int) -> None:
    """把填错的检索条件拦在路由层，直接说明错在哪、可选值是什么。"""
    if page < 1:
        raise HTTPException(status_code=400, detail="页码从 1 开始，请调整 page 参数")
    if size < 1:
        raise HTTPException(status_code=400, detail="每页条数至少为 1，请调整 size 参数")
    if size > 200:
        raise HTTPException(status_code=400, detail="每页最多 200 条，请缩小分页范围")
    if status and status not in STATUSES:
        raise HTTPException(
            status_code=400,
            detail=f"计划状态「{status}」不存在，可选：{'、'.join(STATUSES)}",
        )
    if sort and sort not in SORTABLE_FIELDS:
        raise HTTPException(
            status_code=400,
            detail=f"排序字段「{sort}」不支持，可选：{'、'.join(SORTABLE_FIELDS)}",
        )
    if order not in SORT_ORDERS:
        raise HTTPException(status_code=400, detail="排序方向只支持 asc（升序）或 desc（降序）")


def _describe_conditions(keyword: str | None, berth: str | None, vessel: str | None, status: str | None) -> str:
    """把当前生效的检索条件拼成一句可读的话，给空结果和定位失败时说明原因用。"""
    parts = []
    if keyword and keyword.strip():
        parts.append(f"计划编号含「{keyword.strip()}」")
    if berth and berth.strip():
        parts.append(f"泊位编号含「{berth.strip()}」")
    if vessel and vessel.strip():
        parts.append(f"靠泊船舶含「{vessel.strip()}」")
    if status:
        parts.append(f"计划状态为「{status}」")
    return "、".join(parts)


# 注意：/export、/locate 这类固定路径必须放在 /{entry_id} 之前，
# 否则会被当成 entry_id 解析，直接 422。
@router.get("/export")
def export_entries() -> dict[str, Any]:
    """导出泊位计划清单：返回当前过滤条件下的全量数据。"""
    items, total = service.list_entries(page=1, size=10000)
    return {"module": "berth", "total": total, "items": items}


@router.get("/locate")
def locate_entry(
    id: int = Query(description="要定位的泊位计划记录 id"),
    keyword: str | None = Query(default=None, description="按计划编号检索"),
    berth: str | None = Query(default=None, description="按泊位编号检索"),
    vessel: str | None = Query(default=None, description="按靠泊船舶检索"),
    status: str | None = Query(default=None, description="待编排、已编排、已靠泊、已离泊"),
    sort: str | None = Query(default=None, description="排序字段"),
    order: str = Query(default="asc", description="asc 升序 / desc 降序"),
    size: int = 20,
) -> dict[str, Any]:
    """定位一条泊位计划：在当前筛选与排序口径下算出它在第几页，便于前端翻过去并高亮。"""
    _validate_query(status, sort, order, page=1, size=size)
    found = service.locate_entry(
        id, keyword=keyword, berth=berth, vessel=vessel, status=status, sort=sort, order=order,
    )
    if found is None:
        conditions = _describe_conditions(keyword, berth, vessel, status)
        if conditions:
            detail = f"泊位计划 {id} 不在当前筛选条件（{conditions}）内，可调整或重置条件后再定位"
        else:
            detail = f"泊位计划 {id} 不存在或已归档"
        raise HTTPException(status_code=404, detail=detail)
    index, total = found
    return {"id": id, "page": index // size + 1, "index": index, "total": total}


@router.get("", response_model=PageResult[dict])
def list_entries(
    keyword: str | None = Query(default=None, description="按计划编号检索"),
    berth: str | None = Query(default=None, description="按泊位编号检索"),
    vessel: str | None = Query(default=None, description="按靠泊船舶检索"),
    status: str | None = Query(default=None, description="待编排、已编排、已靠泊、已离泊"),
    sort: str | None = Query(default=None, description="排序字段"),
    order: str = Query(default="asc", description="asc 升序 / desc 降序"),
    page: int = 1,
    size: int = 20,
) -> PageResult[dict]:
    """按计划编号、泊位编号、靠泊船舶与计划状态组合过滤泊位计划列表；条件填错时说明原因。"""
    _validate_query(status, sort, order, page, size)
    items, total = service.list_entries(
        keyword=keyword, berth=berth, vessel=vessel, status=status,
        sort=sort, order=order, page=page, size=size,
    )
    return PageResult(items=items, total=total, page=page, size=size)


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
