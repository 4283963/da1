import asyncio
from typing import Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.config import settings
from app.core.data_simulator import BidirectionalDCSimulator
from app.database import get_db

router = APIRouter(prefix="/tests/{test_id}/data", tags=["数据流接收"])

_active_simulations: Dict[int, asyncio.Task] = {}


def _get_test_or_404(db: Session, test_id: int) -> models.BatteryTest:
    test = crud.get_battery_test(db, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")
    return test


@router.post(
    "",
    response_model=schemas.DataPointResponse,
    status_code=status.HTTP_201_CREATED,
    summary="接收单条实时数据",
)
def receive_data_point(
    test_id: int,
    data: schemas.DataPointCreate,
    db: Session = Depends(get_db),
):
    _get_test_or_404(db, test_id)
    point = crud.create_data_point(db, test_id, data)
    if not point:
        raise HTTPException(status_code=500, detail="数据存储失败")
    return point


@router.post(
    "/batch",
    response_model=List[schemas.DataPointResponse],
    status_code=status.HTTP_201_CREATED,
    summary="批量接收实时数据",
)
def receive_data_batch(
    test_id: int,
    batch: List[schemas.DataPointCreate],
    db: Session = Depends(get_db),
):
    _get_test_or_404(db, test_id)
    results = []
    for item in batch:
        point = crud.create_data_point(db, test_id, item)
        if point:
            results.append(point)
    return results


@router.get(
    "",
    response_model=List[schemas.DataPointResponse],
    summary="查询历史数据",
)
def list_data_points(
    test_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(1000, ge=1, le=10000),
    phase: Optional[models.TestStatus] = Query(None, description="按工况阶段过滤"),
    db: Session = Depends(get_db),
):
    _get_test_or_404(db, test_id)
    return crud.list_data_points(db, test_id, skip=skip, limit=limit, phase=phase)


async def _run_simulation_in_background(
    test_id: int,
    total_cycles: int,
    charge_current_a: float,
    discharge_current_a: float,
    sample_interval_ms: int,
):
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        test = crud.get_battery_test(db, test_id)
        if not test:
            return

        simulator = BidirectionalDCSimulator(
            nominal_capacity_ah=test.nominal_capacity_ah,
            nominal_voltage_v=test.nominal_voltage_v,
        )
        simulator.reset(initial_soc=0.0)
        crud.update_test_status(db, test_id, models.TestStatus.CHARGING, start=True)

        total = 0
        async for point in simulator.simulate_multi_cycle(
            total_cycles=total_cycles,
            charge_current_a=charge_current_a,
            discharge_current_a=discharge_current_a,
            sample_interval_ms=sample_interval_ms,
            rest_seconds=5.0,
        ):
            crud.create_data_point(db, test_id, point)
            total += 1

        crud.update_test_status(db, test_id, models.TestStatus.COMPLETED, end=True)
    finally:
        db.close()
        _active_simulations.pop(test_id, None)


@router.post(
    "/simulate",
    response_model=Dict,
    status_code=status.HTTP_202_ACCEPTED,
    summary="启动双向直流电源仿真测试",
)
async def start_simulation(
    test_id: int,
    req: schemas.SimulationStartRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    if test_id != req.test_id:
        raise HTTPException(status_code=400, detail="URL中的test_id与请求体不一致")
    _get_test_or_404(db, test_id)

    if test_id in _active_simulations and not _active_simulations[test_id].done():
        raise HTTPException(status_code=409, detail="该测试已有正在运行的仿真任务")

    task = asyncio.create_task(
        _run_simulation_in_background(
            test_id=test_id,
            total_cycles=req.total_cycles,
            charge_current_a=req.charge_current_a,
            discharge_current_a=req.discharge_current_a,
            sample_interval_ms=req.sample_interval_ms,
        )
    )
    _active_simulations[test_id] = task

    return {
        "message": "仿真任务已启动并在后台运行",
        "test_id": test_id,
        "total_cycles": req.total_cycles,
        "sample_interval_ms": req.sample_interval_ms,
        "task_id": str(id(task)),
    }


@router.get(
    "/simulate/status",
    response_model=Dict,
    summary="查询仿真任务状态",
)
async def simulation_status(test_id: int):
    task = _active_simulations.get(test_id)
    if not task:
        return {"test_id": test_id, "running": False, "status": "not_found"}
    if task.done():
        exc = task.exception()
        return {
            "test_id": test_id,
            "running": False,
            "status": "completed" if not exc else "failed",
            "error": str(exc) if exc else None,
        }
    return {"test_id": test_id, "running": True, "status": "in_progress"}


@router.get(
    "/stream",
    response_class=StreamingResponse,
    summary="SSE流式输出仿真数据（不入库，仅演示）",
)
async def stream_simulation_data(
    test_id: int,
    total_cycles: int = Query(1, ge=1, le=5),
    charge_current_a: float = Query(1.0, gt=0),
    discharge_current_a: float = Query(1.0, gt=0),
    sample_interval_ms: int = Query(100, ge=10, le=1000),
    db: Session = Depends(get_db),
):
    test = _get_test_or_404(db, test_id)
    simulator = BidirectionalDCSimulator(
        nominal_capacity_ah=test.nominal_capacity_ah,
        nominal_voltage_v=test.nominal_voltage_v,
    )
    simulator.reset()

    async def event_generator():
        yield f"event: start\ndata: 开始仿真 test_id={test_id}\n\n"
        count = 0
        async for point in simulator.simulate_multi_cycle(
            total_cycles=total_cycles,
            charge_current_a=charge_current_a,
            discharge_current_a=discharge_current_a,
            sample_interval_ms=sample_interval_ms,
            rest_seconds=2.0,
        ):
            count += 1
            payload = (
                f"{{\"idx\":{count},\"soc\":{simulator.current_soc:.4f},"
                f"\"current_a\":{point.current_a:.4f},\"voltage_v\":{point.voltage_v:.4f},"
                f"\"phase\":\"{point.phase.value}\",\"ts\":\"{point.timestamp.isoformat()}\"}}"
            )
            yield f"event: data\ndata: {payload}\n\n"
        yield f"event: end\ndata: 仿真结束，共{count}条数据\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )
