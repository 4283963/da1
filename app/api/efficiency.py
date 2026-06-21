from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.core.efficiency import calculate_efficiency, format_efficiency_report
from app.database import get_db

router = APIRouter(prefix="/tests/{test_id}/efficiency", tags=["效率仿真"])


def _get_all_points(db: Session, test_id: int):
    return crud.list_data_points(db, test_id, skip=0, limit=1000000)


@router.post(
    "/calculate",
    response_model=schemas.EfficiencyResultResponse,
    status_code=status.HTTP_201_CREATED,
    summary="计算并存储充放电效率",
)
def calculate_and_store(
    test_id: int,
    db: Session = Depends(get_db),
):
    test = crud.get_battery_test(db, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")

    points = _get_all_points(db, test_id)
    result = calculate_efficiency(points)
    if not result:
        raise HTTPException(
            status_code=400,
            detail="数据不足，无法计算效率（需要同时包含充电和放电阶段的数据）",
        )

    stored = crud.create_efficiency_result(db, test_id, result)
    if not stored:
        raise HTTPException(status_code=500, detail="结果存储失败")
    return stored


@router.get(
    "/latest",
    response_model=schemas.EfficiencyResultResponse,
    summary="获取最新效率计算结果",
)
def get_latest_efficiency(
    test_id: int,
    auto_calculate: bool = Query(False, description="如无结果则自动计算"),
    db: Session = Depends(get_db),
):
    test = crud.get_battery_test(db, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")

    latest = crud.get_latest_efficiency(db, test_id)
    if latest:
        return latest

    if not auto_calculate:
        raise HTTPException(status_code=404, detail="暂无效率计算结果")

    points = _get_all_points(db, test_id)
    result = calculate_efficiency(points)
    if not result:
        raise HTTPException(
            status_code=400,
            detail="数据不足，无法计算效率",
        )
    stored = crud.create_efficiency_result(db, test_id, result)
    return stored


@router.get(
    "",
    response_model=List[schemas.EfficiencyResultResponse],
    summary="获取全部历史效率结果",
)
def list_efficiency_results(
    test_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    db: Session = Depends(get_db),
):
    test = crud.get_battery_test(db, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")
    return crud.list_efficiency_results(db, test_id=test_id, skip=skip, limit=limit)


@router.get(
    "/report",
    summary="获取文本格式的效率分析报告",
)
def get_efficiency_report(
    test_id: int,
    auto_calculate: bool = Query(True, description="如无结果则自动计算"),
    db: Session = Depends(get_db),
):
    test = crud.get_battery_test(db, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")

    latest = crud.get_latest_efficiency(db, test_id)
    if not latest and auto_calculate:
        points = _get_all_points(db, test_id)
        result = calculate_efficiency(points)
        if not result:
            raise HTTPException(status_code=400, detail="数据不足，无法生成报告")
        stored = crud.create_efficiency_result(db, test_id, result)
        latest = stored

    if not latest:
        raise HTTPException(status_code=404, detail="暂无效率数据")

    result_dict = {
        "total_charge_ah": latest.total_charge_ah,
        "total_discharge_ah": latest.total_discharge_ah,
        "total_charge_wh": latest.total_charge_wh,
        "total_discharge_wh": latest.total_discharge_wh,
        "coulombic_efficiency": latest.coulombic_efficiency,
        "energy_efficiency": latest.energy_efficiency,
        "voltage_efficiency": latest.voltage_efficiency,
        "avg_charge_voltage_v": latest.avg_charge_voltage_v,
        "avg_discharge_voltage_v": latest.avg_discharge_voltage_v,
        "charge_energy_loss_wh": latest.charge_energy_loss_wh,
        "calculated_at": latest.calculated_at,
    }
    header = f"测试ID: {test.id} | 电池: {test.battery_id} | 名称: {test.test_name}\n"
    report = header + format_efficiency_report(result_dict)
    return Response(content=report, media_type="text/plain; charset=utf-8")
