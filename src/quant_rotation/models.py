from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class PriceData:
    dates: list[date]
    closes: dict[str, list[float]]

    @property
    def assets(self) -> list[str]:
        return list(self.closes.keys())

    def __post_init__(self) -> None:
        if not self.dates:
            raise ValueError("PriceData requires at least one date")
        n = len(self.dates)
        for asset, values in self.closes.items():
            if len(values) != n:
                raise ValueError(
                    f"Asset {asset!r} has {len(values)} closes, expected {n}"
                )


@dataclass(frozen=True)
class FactorWeights:
    ret20: float = 0.40
    ret60: float = 0.40
    ret120: float = 0.20
    rel_ret60: float = 0.00
    rel_ret20: float = 0.00
    momentum_accel: float = 0.00
    consistency60: float = 0.00
    amount_strength: float = 0.25
    breadth20: float = 0.12
    breadth60: float = 0.08
    valuation: float = 0.00
    prosperity: float = 0.00
    vol20: float = -0.30
    ret5: float = -0.20


@dataclass(frozen=True)
class BreadthData:
    breadth20: PriceData | None = None
    breadth60: PriceData | None = None

    @property
    def available(self) -> bool:
        return self.breadth20 is not None or self.breadth60 is not None


@dataclass(frozen=True)
class StockIndustryMap:
    snapshots: dict[date, dict[str, str]]

    @classmethod
    def from_static(
        cls,
        mapping: dict[str, str],
        *,
        as_of: date = date.min,
    ) -> StockIndustryMap:
        return cls({as_of: mapping})

    @property
    def all_stocks(self) -> set[str]:
        return {
            stock
            for mapping in self.snapshots.values()
            for stock in mapping
        }

    def get_map_at(self, dt: date) -> dict[str, str]:
        available_dates = [
            snapshot_date
            for snapshot_date in self.snapshots
            if snapshot_date <= dt
        ]
        if not available_dates:
            raise ValueError(
                "No stock industry snapshot available on or before "
                f"{dt.isoformat()}"
            )
        return dict(self.snapshots[max(available_dates)])

    def __post_init__(self) -> None:
        if not self.snapshots:
            raise ValueError("StockIndustryMap requires at least one snapshot")
        for snapshot_date, mapping in self.snapshots.items():
            if not isinstance(snapshot_date, date):
                raise ValueError("StockIndustryMap snapshot keys must be dates")
            if not mapping:
                raise ValueError(
                    "StockIndustryMap snapshots must contain at least one mapping"
                )
            for stock, industry in mapping.items():
                if not stock or not industry:
                    raise ValueError("StockIndustryMap cannot contain blank values")


@dataclass(frozen=True)
class StockSelectionConfig:
    enabled: bool = False
    top_n_per_industry: int = 5
    min_stocks_per_industry: int = 1
    max_stock_weight: float = 0.10
    ret20: float = 0.45
    ret60: float = 0.25
    amount_strength: float = 0.10
    vol20: float = -0.20
    ret5: float = -0.10
    rel_ret60: float = 0.00
    consistency20: float = 0.00


@dataclass(frozen=True)
class StrategyConfig:
    rebalance_every: int = 20
    top_k: int = 5
    max_industry_weight: float = 0.30
    transaction_cost: float = 0.001
    risk_control: bool = True
    market_ma_window: int = 120
    market_score_control: bool = False
    market_score_window: int = 60
    market_score_threshold: float = 0.0
    risk_off_exposure: float = 0.50
    risk_control_mode: str = "hard"
    soft_exposure_min: float = 0.20
    soft_exposure_max: float = 1.00
    soft_exposure_center: float = 0.00
    soft_exposure_steepness: float = 20.0
    state_aware_risk_control: bool = False
    bull_exposure: float = 1.00
    sideways_exposure: float = 0.50
    bear_exposure: float = 0.10
    regime_aware_factors: bool = False
    bull_factor_weights: FactorWeights = field(default_factory=FactorWeights)
    sideways_factor_weights: FactorWeights = field(default_factory=FactorWeights)
    bear_factor_weights: FactorWeights = field(default_factory=FactorWeights)
    portfolio_mode: str = "equal"
    softmax_temperature: float = 1.0
    adaptive_top_k: bool = False
    adaptive_top_k_base: int = 5
    adaptive_top_k_concentration: float = 1.5
    risk_control_dual_ma: bool = False
    state_aware_bull_threshold: float = 1.5
    state_aware_bear_threshold: float = 0.0
    factor_weights: FactorWeights = field(default_factory=FactorWeights)
    stock_selection: StockSelectionConfig = field(default_factory=StockSelectionConfig)
    annual_budget_control: bool = False
    annual_budget_target: float = 0.12
    annual_budget_lock_trigger: float = 0.10
    annual_budget_min_exposure: float = 0.50
    vol_targeting: bool = False
    vol_target_level: float = 0.15
    vol_target_window: int = 20
    vol_target_min_exposure: float = 0.30
    defensive_mode: bool = False
    defensive_top_k: int = 3
    defensive_exposure_threshold: float = 0.50
    strategy_mode: str = "absolute"
    defensive_sector_filter: bool = False
    defensive_sector_cap: float = 0.50
    relative_excess_target: float = 0.05


@dataclass(frozen=True)
class AppConfig:
    industry_close_path: str
    industry_amount_path: str | None
    industry_breadth20_path: str | None
    industry_breadth60_path: str | None
    industry_valuation_path: str | None
    industry_prosperity_path: str | None
    market_close_path: str | None
    stock_close_path: str | None
    stock_amount_path: str | None
    stock_industry_map_path: str | None
    benchmark_close_path: str | None
    output_dir: str
    market_weights: dict[str, float] = field(default_factory=dict)
    strategy: StrategyConfig = field(default_factory=StrategyConfig)


@dataclass(frozen=True)
class FactorSnapshot:
    signal_date: date
    scores: dict[str, float]
    fields: dict[str, dict[str, float]]


@dataclass(frozen=True)
class RebalanceEvent:
    date: date
    signal_date: date
    holdings: list[str]
    weights: dict[str, float]
    exposure: float
    turnover: float
    cost: float
    market_trend: bool
    market_score: float | None = None
    market_score_ok: bool = True
    risk_on: bool = True
    selected_industries: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class BacktestResult:
    dates: list[date]
    strategy_equity: list[float]
    benchmark_equity: list[float] | None
    equal_weight_equity: list[float]
    daily_returns: list[float]
    rebalances: list[RebalanceEvent]
    metrics: dict[str, float]
    annual_returns: dict[int, float]
