import asyncio
import math
import random
from datetime import datetime, timedelta
from typing import AsyncGenerator, Optional

from app.config import settings
from app.models import TestStatus
from app.schemas import DataPointCreate


class BidirectionalDCSimulator:
    def __init__(
        self,
        nominal_capacity_ah: float = settings.nominal_capacity_ah,
        nominal_voltage_v: float = settings.nominal_voltage_v,
        charge_cutoff_v: float = settings.charge_cutoff_voltage_v,
        discharge_cutoff_v: float = settings.discharge_cutoff_voltage_v,
        noise_level: float = 0.002,
    ):
        self.nominal_capacity_ah = nominal_capacity_ah
        self.nominal_voltage_v = nominal_voltage_v
        self.charge_cutoff_v = charge_cutoff_v
        self.discharge_cutoff_v = discharge_cutoff_v
        self.noise_level = noise_level

        self._current_soc = 0.0
        self._current_voltage = nominal_voltage_v
        self._phase: TestStatus = TestStatus.IDLE
        self._elapsed = timedelta(0)

    def reset(self, initial_soc: float = 0.0):
        self._current_soc = max(0.0, min(1.0, initial_soc))
        self._current_voltage = self._soc_to_voltage(self._current_soc)
        self._phase = TestStatus.IDLE
        self._elapsed = timedelta(0)

    def _soc_to_voltage(self, soc: float) -> float:
        base = self.discharge_cutoff_v + (self.charge_cutoff_v - self.discharge_cutoff_v)
        v = self.discharge_cutoff_v + base * (0.08 + 0.92 * math.pow(max(0.0, min(1.0, soc)), 0.55))
        return v

    def _add_noise(self, value: float) -> float:
        return value * (1.0 + random.uniform(-self.noise_level, self.noise_level))

    def _step_charge(self, current_a: float, dt_seconds: float) -> DataPointCreate:
        dt_hours = dt_seconds / 3600.0
        delta_capacity = current_a * dt_hours
        self._current_soc = min(1.0, self._current_soc + delta_capacity / self.nominal_capacity_ah)
        target_v = self._soc_to_voltage(self._current_soc)
        overpotential = 0.05 + 0.08 * (1.0 - self._current_soc)
        self._current_voltage = min(self.charge_cutoff_v * 1.005, target_v + overpotential)
        self._phase = TestStatus.CHARGING

        return DataPointCreate(
            current_a=self._add_noise(current_a),
            voltage_v=self._add_noise(self._current_voltage),
            timestamp=datetime.utcnow(),
            phase=self._phase,
        )

    def _step_discharge(self, current_a: float, dt_seconds: float) -> DataPointCreate:
        dt_hours = dt_seconds / 3600.0
        delta_capacity = current_a * dt_hours
        self._current_soc = max(0.0, self._current_soc - delta_capacity / self.nominal_capacity_ah)
        target_v = self._soc_to_voltage(self._current_soc)
        overpotential = 0.03 + 0.06 * self._current_soc
        self._current_voltage = max(self.discharge_cutoff_v * 0.995, target_v - overpotential)
        self._phase = TestStatus.DISCHARGING

        return DataPointCreate(
            current_a=self._add_noise(-current_a),
            voltage_v=self._add_noise(self._current_voltage),
            timestamp=datetime.utcnow(),
            phase=self._phase,
        )

    def _step_rest(self, dt_seconds: float) -> DataPointCreate:
        target_v = self._soc_to_voltage(self._current_soc)
        self._current_voltage += (target_v - self._current_voltage) * 0.1
        self._phase = TestStatus.RESTING

        return DataPointCreate(
            current_a=self._add_noise(0.0),
            voltage_v=self._add_noise(self._current_voltage),
            timestamp=datetime.utcnow(),
            phase=self._phase,
        )

    @property
    def current_soc(self) -> float:
        return self._current_soc

    @property
    def current_voltage(self) -> float:
        return self._current_voltage

    @property
    def phase(self) -> TestStatus:
        return self._phase

    async def simulate_cycle(
        self,
        charge_current_a: float = 1.0,
        discharge_current_a: float = 1.0,
        sample_interval_ms: int = settings.sample_interval_ms,
        target_soc_max: float = 1.0,
        target_soc_min: float = 0.0,
        rest_seconds: float = 30.0,
        max_cycle_seconds: Optional[float] = None,
    ) -> AsyncGenerator[DataPointCreate, None]:
        dt = sample_interval_ms / 1000.0
        steps_per_rest = max(1, int(rest_seconds / dt))
        start_elapsed = self._elapsed

        while self._current_soc < target_soc_max:
            if max_cycle_seconds and (self._elapsed - start_elapsed).total_seconds() > max_cycle_seconds:
                break
            yield self._step_charge(charge_current_a, dt)
            self._elapsed += timedelta(seconds=dt)
            await asyncio.sleep(dt * 0.001)

        for _ in range(steps_per_rest):
            yield self._step_rest(dt)
            self._elapsed += timedelta(seconds=dt)
            await asyncio.sleep(dt * 0.001)

        while self._current_soc > target_soc_min:
            if max_cycle_seconds and (self._elapsed - start_elapsed).total_seconds() > max_cycle_seconds:
                break
            yield self._step_discharge(discharge_current_a, dt)
            self._elapsed += timedelta(seconds=dt)
            await asyncio.sleep(dt * 0.001)

        for _ in range(steps_per_rest):
            yield self._step_rest(dt)
            self._elapsed += timedelta(seconds=dt)
            await asyncio.sleep(dt * 0.001)

    async def simulate_multi_cycle(
        self,
        total_cycles: int = 1,
        charge_current_a: float = 1.0,
        discharge_current_a: float = 1.0,
        sample_interval_ms: int = settings.sample_interval_ms,
        target_soc_max: float = 1.0,
        target_soc_min: float = 0.0,
        rest_seconds: float = 10.0,
    ) -> AsyncGenerator[DataPointCreate, None]:
        for _ in range(total_cycles):
            async for point in self.simulate_cycle(
                charge_current_a=charge_current_a,
                discharge_current_a=discharge_current_a,
                sample_interval_ms=sample_interval_ms,
                target_soc_max=target_soc_max,
                target_soc_min=target_soc_min,
                rest_seconds=rest_seconds,
            ):
                yield point
