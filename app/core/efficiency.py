from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np

from app.models import DataPoint, TestStatus


@dataclass
class PhaseStats:
    total_capacity_ah: float
    total_energy_wh: float
    avg_voltage_v: float
    duration_seconds: float
    data_count: int


def _is_valid_point(p: Optional[DataPoint]) -> bool:
    if p is None:
        return False
    if p.timestamp is None:
        return False
    if p.current_a is None:
        return False
    if p.voltage_v is None:
        return False
    try:
        cur = float(p.current_a)
        vol = float(p.voltage_v)
        if np.isnan(cur) or np.isinf(cur):
            return False
        if np.isnan(vol) or np.isinf(vol):
            return False
    except (TypeError, ValueError):
        return False
    return True


def _safe_float(value, default: float = 0.0) -> float:
    try:
        v = float(value)
        if np.isnan(v) or np.isinf(v):
            return default
        return v
    except (TypeError, ValueError):
        return default


def _validate_and_filter(points: Sequence[DataPoint]) -> List[DataPoint]:
    return [p for p in points if _is_valid_point(p)]


def _split_phases(points: Sequence[DataPoint]) -> Tuple[List[DataPoint], List[DataPoint]]:
    valid_points = _validate_and_filter(points)
    charge_points: List[DataPoint] = []
    discharge_points: List[DataPoint] = []
    for p in valid_points:
        if p.phase == TestStatus.CHARGING:
            charge_points.append(p)
        elif p.phase == TestStatus.DISCHARGING:
            discharge_points.append(p)
    return charge_points, discharge_points


def _trapz_ah(points: List[DataPoint]) -> float:
    if len(points) < 2:
        return 0.0

    t0 = points[0].timestamp
    timestamps = np.array(
        [_safe_float((p.timestamp - t0).total_seconds(), default=0.0) for p in points],
        dtype=np.float64,
    )
    currents = np.array(
        [abs(_safe_float(p.current_a, default=0.0)) for p in points],
        dtype=np.float64,
    )

    integral_s = float(np.trapz(currents, timestamps))
    return integral_s / 3600.0


def _trapz_wh(points: List[DataPoint]) -> float:
    if len(points) < 2:
        return 0.0

    t0 = points[0].timestamp
    timestamps = np.array(
        [_safe_float((p.timestamp - t0).total_seconds(), default=0.0) for p in points],
        dtype=np.float64,
    )
    powers = np.array(
        [abs(_safe_float(p.current_a, default=0.0)) * _safe_float(p.voltage_v, default=0.0) for p in points],
        dtype=np.float64,
    )

    integral_ws = float(np.trapz(powers, timestamps))
    return integral_ws / 3600.0


def _phase_stats(points: List[DataPoint]) -> PhaseStats:
    if not points:
        return PhaseStats(0.0, 0.0, 0.0, 0.0, 0)

    currents_abs = [abs(_safe_float(p.current_a, default=0.0)) for p in points]
    voltages = [_safe_float(p.voltage_v, default=0.0) for p in points]

    total_capacity_ah = _trapz_ah(points)
    total_energy_wh = _trapz_wh(points)

    if total_capacity_ah > 1e-12:
        weighted_v_sum = 0.0
        weighted_c_sum = 0.0
        for i in range(len(points)):
            c = _safe_float(currents_abs[i], default=0.0)
            v = _safe_float(voltages[i], default=0.0)
            weighted_v_sum += c * v
            weighted_c_sum += c
        if weighted_c_sum > 1e-12:
            avg_voltage_v = weighted_v_sum / weighted_c_sum
        else:
            valid_v = [v for v in voltages if not (np.isnan(v) or np.isinf(v))]
            avg_voltage_v = float(np.mean(valid_v)) if valid_v else 0.0
    else:
        valid_v = [v for v in voltages if not (np.isnan(v) or np.isinf(v))]
        avg_voltage_v = float(np.mean(valid_v)) if valid_v else 0.0

    duration = 0.0
    if len(points) >= 2 and points[0].timestamp and points[-1].timestamp:
        try:
            duration = _safe_float(
                (points[-1].timestamp - points[0].timestamp).total_seconds(),
                default=0.0,
            )
        except Exception:
            duration = 0.0

    return PhaseStats(
        total_capacity_ah=total_capacity_ah,
        total_energy_wh=total_energy_wh,
        avg_voltage_v=avg_voltage_v,
        duration_seconds=duration,
        data_count=len(points),
    )


def calculate_efficiency(points: Sequence[DataPoint]) -> Optional[Dict]:
    if not points:
        return None

    valid_points = _validate_and_filter(points)
    if not valid_points:
        return None

    charge_points, discharge_points = _split_phases(valid_points)

    charge_stats = _phase_stats(charge_points)
    discharge_stats = _phase_stats(discharge_points)

    if charge_stats.total_capacity_ah <= 0 or discharge_stats.total_capacity_ah <= 0:
        return None

    coulombic_efficiency = discharge_stats.total_capacity_ah / charge_stats.total_capacity_ah

    if charge_stats.total_energy_wh > 0:
        energy_efficiency = discharge_stats.total_energy_wh / charge_stats.total_energy_wh
    else:
        energy_efficiency = 0.0

    if charge_stats.avg_voltage_v > 0:
        voltage_efficiency = discharge_stats.avg_voltage_v / charge_stats.avg_voltage_v
    else:
        voltage_efficiency = 0.0

    energy_loss = max(0.0, charge_stats.total_energy_wh - discharge_stats.total_energy_wh)

    return {
        "total_charge_ah": charge_stats.total_capacity_ah,
        "total_discharge_ah": discharge_stats.total_capacity_ah,
        "total_charge_wh": charge_stats.total_energy_wh,
        "total_discharge_wh": discharge_stats.total_energy_wh,
        "coulombic_efficiency": coulombic_efficiency,
        "energy_efficiency": energy_efficiency,
        "voltage_efficiency": voltage_efficiency,
        "avg_charge_voltage_v": charge_stats.avg_voltage_v,
        "avg_discharge_voltage_v": discharge_stats.avg_voltage_v,
        "charge_energy_loss_wh": energy_loss,
        "calculated_at": datetime.utcnow(),
    }


def format_efficiency_report(result: Dict) -> str:
    lines = [
        "===== 锂电池化成效率分析报告 =====",
        f"计算时间: {result['calculated_at'].strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "--- 容量统计 ---",
        f"充电总容量: {result['total_charge_ah']:.4f} Ah",
        f"放电总容量: {result['total_discharge_ah']:.4f} Ah",
        "",
        "--- 能量统计 ---",
        f"充电总能量: {result['total_charge_wh']:.4f} Wh",
        f"放电总能量: {result['total_discharge_wh']:.4f} Wh",
        f"能量损失:   {result['charge_energy_loss_wh']:.4f} Wh",
        "",
        "--- 电压统计 ---",
        f"平均充电电压: {result['avg_charge_voltage_v']:.4f} V",
        f"平均放电电压: {result['avg_discharge_voltage_v']:.4f} V",
        "",
        "--- 效率指标 ---",
        f"库仑效率 (CE):  {result['coulombic_efficiency'] * 100:.3f} %",
        f"能量效率 (EE):  {result['energy_efficiency'] * 100:.3f} %",
        f"电压效率 (VE):  {result['voltage_efficiency'] * 100:.3f} %",
        "==================================",
    ]
    return "\n".join(lines)
