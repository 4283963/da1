import enum
from datetime import datetime

from sqlalchemy import Column, DateTime, Enum, Float, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.database import Base


class TestStatus(str, enum.Enum):
    IDLE = "idle"
    CHARGING = "charging"
    DISCHARGING = "discharging"
    RESTING = "resting"
    COMPLETED = "completed"
    FAILED = "failed"


class BatteryTest(Base):
    __tablename__ = "battery_tests"

    id = Column(Integer, primary_key=True, index=True)
    battery_id = Column(String, index=True, nullable=False)
    cabinet_id = Column(String, index=True, default="CAB-001", nullable=False)
    test_name = Column(String, nullable=False)
    nominal_capacity_ah = Column(Float, nullable=False)
    nominal_voltage_v = Column(Float, nullable=False)
    status = Column(Enum(TestStatus), default=TestStatus.IDLE, nullable=False)
    started_at = Column(DateTime, default=None)
    ended_at = Column(DateTime, default=None)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    data_points = relationship("DataPoint", back_populates="test", cascade="all, delete-orphan")
    efficiency_results = relationship("EfficiencyResult", back_populates="test", cascade="all, delete-orphan")


class DataPoint(Base):
    __tablename__ = "data_points"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("battery_tests.id"), nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
    current_a = Column(Float, nullable=False)
    voltage_v = Column(Float, nullable=False)
    cumulative_charge_ah = Column(Float, default=0.0, nullable=False)
    cumulative_discharge_ah = Column(Float, default=0.0, nullable=False)
    cumulative_charge_wh = Column(Float, default=0.0, nullable=False)
    cumulative_discharge_wh = Column(Float, default=0.0, nullable=False)
    phase = Column(Enum(TestStatus), nullable=False)

    test = relationship("BatteryTest", back_populates="data_points")


class EfficiencyResult(Base):
    __tablename__ = "efficiency_results"

    id = Column(Integer, primary_key=True, index=True)
    test_id = Column(Integer, ForeignKey("battery_tests.id"), nullable=False)
    calculated_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    total_charge_ah = Column(Float, nullable=False)
    total_discharge_ah = Column(Float, nullable=False)
    total_charge_wh = Column(Float, nullable=False)
    total_discharge_wh = Column(Float, nullable=False)

    coulombic_efficiency = Column(Float, nullable=False)
    energy_efficiency = Column(Float, nullable=False)
    voltage_efficiency = Column(Float, nullable=False)

    avg_charge_voltage_v = Column(Float, nullable=False)
    avg_discharge_voltage_v = Column(Float, nullable=False)
    charge_energy_loss_wh = Column(Float, default=0.0, nullable=False)

    energy_recovery_ratio = Column(Float, default=0.92, nullable=False)
    recovered_energy_wh = Column(Float, default=0.0, nullable=False)
    electricity_cost_saved_yuan = Column(Float, default=0.0, nullable=False)
    grid_price_yuan_per_kwh = Column(Float, default=0.85, nullable=False)

    test = relationship("BatteryTest", back_populates="efficiency_results")
