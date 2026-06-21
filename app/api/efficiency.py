from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app import crud, schemas
from app.config import settings
from app.core.efficiency import (
    aggregate_cabinet_savings,
    calculate_efficiency,
    calculate_energy_recovery,
    format_efficiency_report,
    format_saving_ranking_table,
    log_saving_ranking,
)
from app.database import get_db

router = APIRouter(prefix="/tests/{test_id}/efficiency", tags=["效率仿真"])


def _get_all_points(db: Session, test_id: int):
    return crud.list_data_points(db, test_id, skip=0, limit=1000000)


def _merge_recovery_into_result(efficiency_result: Dict) -> Dict:
    recovery = calculate_energy_recovery(efficiency_result)
    efficiency_result.update(recovery)
    return efficiency_result


@router.post(
    "/calculate",
    response_model=schemas.EfficiencyResultResponse,
    status_code=status.HTTP_201_CREATED,
    summary="计算并存储充放电效率（含能量回收和电费节省）",
)
def calculate_and_store(
    test_id: int,
    recovery_ratio: Optional[float] = Query(None, ge=0.0, le=1.0, description="能量回收比例，默认使用配置"),
    grid_price: Optional[float] = Query(None, ge=0.0, description="电网电价 元/kWh，默认使用配置"),
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

    recovery = calculate_energy_recovery(result, recovery_ratio=recovery_ratio, grid_price_yuan_per_kwh=grid_price)
    result.update(recovery)

    stored = crud.create_efficiency_result(db, test_id, result)
    if not stored:
        raise HTTPException(status_code=500, detail="结果存储失败")
    return stored


@router.get(
    "/latest",
    response_model=schemas.EfficiencyResultResponse,
    summary="获取最新效率计算结果（含能量回收和电费节省）",
)
def get_latest_efficiency(
    test_id: int,
    auto_calculate: bool = Query(False, description="如无结果则自动计算"),
    recovery_ratio: Optional[float] = Query(None, ge=0.0, le=1.0, description="自动计算时的回收比例"),
    grid_price: Optional[float] = Query(None, ge=0.0, description="自动计算时的电价 元/kWh"),
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
    recovery = calculate_energy_recovery(result, recovery_ratio=recovery_ratio, grid_price_yuan_per_kwh=grid_price)
    result.update(recovery)
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
        "energy_recovery_ratio": getattr(latest, "energy_recovery_ratio", 0.0),
        "recovered_energy_wh": getattr(latest, "recovered_energy_wh", 0.0),
        "electricity_cost_saved_yuan": getattr(latest, "electricity_cost_saved_yuan", 0.0),
        "grid_price_yuan_per_kwh": getattr(latest, "grid_price_yuan_per_kwh", 0.0),
        "calculated_at": latest.calculated_at,
    }
    header = f"测试ID: {test.id} | 电池: {test.battery_id} | 化成柜: {test.cabinet_id} | 名称: {test.test_name}\n"
    report = header + format_efficiency_report(result_dict)
    return Response(content=report, media_type="text/plain; charset=utf-8")
