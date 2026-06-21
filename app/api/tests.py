from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app import crud, models, schemas
from app.database import get_db

router = APIRouter(prefix="/tests", tags=["测试管理"])


@router.post(
    "",
    response_model=schemas.BatteryTestResponse,
    status_code=status.HTTP_201_CREATED,
    summary="创建电池化成测试",
)
def create_test(data: schemas.BatteryTestCreate, db: Session = Depends(get_db)):
    return crud.create_battery_test(db, data)


@router.get(
    "",
    response_model=List[schemas.BatteryTestResponse],
    summary="获取测试列表",
)
def list_tests(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=1000),
    battery_id: Optional[str] = Query(None),
    db: Session = Depends(get_db),
):
    return crud.list_battery_tests(db, skip=skip, limit=limit, battery_id=battery_id)


@router.get(
    "/{test_id}",
    response_model=schemas.TestDetailResponse,
    summary="获取测试详情",
)
def get_test(test_id: int, db: Session = Depends(get_db)):
    test = crud.get_battery_test(db, test_id)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")
    count = crud.count_data_points(db, test_id)
    latest_eff = crud.get_latest_efficiency(db, test_id)
    return {
        "id": test.id,
        "battery_id": test.battery_id,
        "test_name": test.test_name,
        "nominal_capacity_ah": test.nominal_capacity_ah,
        "nominal_voltage_v": test.nominal_voltage_v,
        "status": test.status,
        "started_at": test.started_at,
        "ended_at": test.ended_at,
        "created_at": test.created_at,
        "updated_at": test.updated_at,
        "data_points_count": count,
        "latest_efficiency": latest_eff,
    }


@router.patch(
    "/{test_id}/status",
    response_model=schemas.BatteryTestResponse,
    summary="更新测试状态",
)
def update_test_status(
    test_id: int,
    target_status: models.TestStatus = Query(..., description="目标状态"),
    start: bool = Query(False, description="是否标记开始（设置started_at）"),
    end: bool = Query(False, description="是否标记结束（设置ended_at）"),
    db: Session = Depends(get_db),
):
    test = crud.update_test_status(db, test_id, target_status, start=start, end=end)
    if not test:
        raise HTTPException(status_code=404, detail="测试不存在")
    return test
