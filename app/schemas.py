from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.models import TestStatus


class DataPointCreate(BaseModel):
    current_a: float = Field(..., description="实时电流(A)，充电为正，放电为负")
    voltage_v: float = Field(..., description="实时电压(V)")
    timestamp: Optional[datetime] = Field(None, description="采样时间戳，不传则使用服务器时间")
    phase: Optional[TestStatus] = Field(None, description="当前工况阶段")


class DataPointResponse(BaseModel):
    id: int
    test_id: int
    timestamp: datetime
    current_a: float
    voltage_v: float
    cumulative_charge_ah: float
    cumulative_discharge_ah: float
    cumulative_charge_wh: float
    cumulative_discharge_wh: float
    phase: TestStatus

    class Config:
        from_attributes = True


class BatteryTestCreate(BaseModel):
    battery_id: str = Field(..., description="电池唯一标识")
    test_name: str = Field(..., description="测试名称")
    nominal_capacity_ah: Optional[float] = Field(None, description="标称容量(Ah)")
    nominal_voltage_v: Optional[float] = Field(None, description="标称电压(V)")


class BatteryTestResponse(BaseModel):
    id: int
    battery_id: str
    test_name: str
    nominal_capacity_ah: float
    nominal_voltage_v: float
    status: TestStatus
    started_at: Optional[datetime]
    ended_at: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EfficiencyResultResponse(BaseModel):
    id: int
    test_id: int
    calculated_at: datetime
    total_charge_ah: float
    total_discharge_ah: float
    total_charge_wh: float
    total_discharge_wh: float
    coulombic_efficiency: float
    energy_efficiency: float
    voltage_efficiency: float
    avg_charge_voltage_v: float
    avg_discharge_voltage_v: float
    charge_energy_loss_wh: float

    class Config:
        from_attributes = True


class TestDetailResponse(BatteryTestResponse):
    data_points_count: int
    latest_efficiency: Optional[EfficiencyResultResponse] = None


class SimulationStartRequest(BaseModel):
    test_id: int
    total_cycles: int = Field(default=1, ge=1, description="充放电循环次数")
    charge_current_a: float = Field(default=1.0, gt=0, description="充电电流(A)")
    discharge_current_a: float = Field(default=1.0, gt=0, description="放电电流(A)")
    sample_interval_ms: int = Field(default=100, ge=10, description="采样间隔(ms)")
