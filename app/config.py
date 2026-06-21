from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "锂电池化成效率分析系统"
    database_url: str = "sqlite:///./data/battery_test.db"
    api_prefix: str = "/api/v1"

    nominal_capacity_ah: float = 2.5
    nominal_voltage_v: float = 3.7
    charge_cutoff_voltage_v: float = 4.2
    discharge_cutoff_voltage_v: float = 2.75
    sample_interval_ms: int = 100

    grid_electricity_price_yuan_per_kwh: float = 0.85
    default_energy_recovery_ratio: float = 0.92
    top_saving_rank_count: int = 5
    saving_report_log_file: str = "./data/cabinet_savings_ranking.log"


settings = Settings()
