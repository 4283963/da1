from datetime import datetime
from typing import List, Optional, Tuple

from sqlalchemy.orm import Session

from app import models, schemas
from app.config import settings


def create_battery_test(db: Session, data: schemas.BatteryTestCreate) -> models.BatteryTest:
    test = models.BatteryTest(
        battery_id=data.battery_id,
        test_name=data.test_name,
        nominal_capacity_ah=data.nominal_capacity_ah or settings.nominal_capacity_ah,
        nominal_voltage_v=data.nominal_voltage_v or settings.nominal_voltage_v,
        status=models.TestStatus.IDLE,
    )
    db.add(test)
    db.commit()
    db.refresh(test)
    return test


def get_battery_test(db: Session, test_id: int) -> Optional[models.BatteryTest]:
    return db.query(models.BatteryTest).filter(models.BatteryTest.id == test_id).first()


def list_battery_tests(
    db: Session,
    skip: int = 0,
    limit: int = 100,
    battery_id: Optional[str] = None,
) -> List[models.BatteryTest]:
    query = db.query(models.BatteryTest)
    if battery_id:
        query = query.filter(models.BatteryTest.battery_id == battery_id)
    return query.order_by(models.BatteryTest.created_at.desc()).offset(skip).limit(limit).all()


def update_test_status(
    db: Session,
    test_id: int,
    status: models.TestStatus,
    start: bool = False,
    end: bool = False,
) -> Optional[models.BatteryTest]:
    test = get_battery_test(db, test_id)
    if not test:
        return None
    test.status = status
    if start and not test.started_at:
        test.started_at = datetime.utcnow()
    if end:
        test.ended_at = datetime.utcnow()
    db.commit()
    db.refresh(test)
    return test


def _get_last_cumulatives(db: Session, test_id: int) -> Tuple[float, float, float, float]:
    last = (
        db.query(models.DataPoint)
        .filter(models.DataPoint.test_id == test_id)
        .order_by(models.DataPoint.id.desc())
        .first()
    )
    if not last:
        return 0.0, 0.0, 0.0, 0.0
    return (
        last.cumulative_charge_ah,
        last.cumulative_discharge_ah,
        last.cumulative_charge_wh,
        last.cumulative_discharge_wh,
    )


def create_data_point(
    db: Session,
    test_id: int,
    data: schemas.DataPointCreate,
) -> Optional[models.DataPoint]:
    test = get_battery_test(db, test_id)
    if not test:
        return None

    dt_hours = settings.sample_interval_ms / 1000.0 / 3600.0

    charge_ah_inc = 0.0
    discharge_ah_inc = 0.0
    if data.current_a > 0:
        charge_ah_inc = data.current_a * dt_hours
    elif data.current_a < 0:
        discharge_ah_inc = abs(data.current_a) * dt_hours

    charge_wh_inc = charge_ah_inc * data.voltage_v
    discharge_wh_inc = discharge_ah_inc * data.voltage_v

    cum_ch_ah, cum_dis_ah, cum_ch_wh, cum_dis_wh = _get_last_cumulatives(db, test_id)

    phase = data.phase or test.status
    if phase == models.TestStatus.IDLE:
        if data.current_a > 0:
            phase = models.TestStatus.CHARGING
        elif data.current_a < 0:
            phase = models.TestStatus.DISCHARGING
        else:
            phase = models.TestStatus.RESTING

    point = models.DataPoint(
        test_id=test_id,
        timestamp=data.timestamp or datetime.utcnow(),
        current_a=data.current_a,
        voltage_v=data.voltage_v,
        cumulative_charge_ah=cum_ch_ah + charge_ah_inc,
        cumulative_discharge_ah=cum_dis_ah + discharge_ah_inc,
        cumulative_charge_wh=cum_ch_wh + charge_wh_inc,
        cumulative_discharge_wh=cum_dis_wh + discharge_wh_inc,
        phase=phase,
    )
    db.add(point)
    db.commit()
    db.refresh(point)
    return point


def list_data_points(
    db: Session,
    test_id: int,
    skip: int = 0,
    limit: int = 1000,
    phase: Optional[models.TestStatus] = None,
) -> List[models.DataPoint]:
    query = db.query(models.DataPoint).filter(models.DataPoint.test_id == test_id)
    if phase:
        query = query.filter(models.DataPoint.phase == phase)
    return query.order_by(models.DataPoint.timestamp.asc()).offset(skip).limit(limit).all()


def count_data_points(db: Session, test_id: int) -> int:
    return db.query(models.DataPoint).filter(models.DataPoint.test_id == test_id).count()


def create_efficiency_result(
    db: Session,
    test_id: int,
    result_dict: dict,
) -> Optional[models.EfficiencyResult]:
    test = get_battery_test(db, test_id)
    if not test:
        return None
    result = models.EfficiencyResult(test_id=test_id, **result_dict)
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def list_efficiency_results(
    db: Session,
    test_id: Optional[int] = None,
    skip: int = 0,
    limit: int = 100,
) -> List[models.EfficiencyResult]:
    query = db.query(models.EfficiencyResult)
    if test_id:
        query = query.filter(models.EfficiencyResult.test_id == test_id)
    return query.order_by(models.EfficiencyResult.calculated_at.desc()).offset(skip).limit(limit).all()


def get_latest_efficiency(db: Session, test_id: int) -> Optional[models.EfficiencyResult]:
    return (
        db.query(models.EfficiencyResult)
        .filter(models.EfficiencyResult.test_id == test_id)
        .order_by(models.EfficiencyResult.calculated_at.desc())
        .first()
    )
