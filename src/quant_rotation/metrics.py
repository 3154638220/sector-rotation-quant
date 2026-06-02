from __future__ import annotations

from datetime import date
from math import sqrt


TRADING_DAYS_PER_YEAR = 252


def equity_to_returns(equity: list[float]) -> list[float]:
    return [equity[i] / equity[i - 1] - 1.0 for i in range(1, len(equity))]


def annualized_return(equity: list[float]) -> float:
    if len(equity) < 2 or equity[0] <= 0:
        return 0.0
    periods = len(equity) - 1
    return (equity[-1] / equity[0]) ** (TRADING_DAYS_PER_YEAR / periods) - 1.0


def max_drawdown(equity: list[float]) -> float:
    peak = equity[0]
    worst = 0.0
    for value in equity:
        if value > peak:
            peak = value
        if peak > 0:
            worst = min(worst, value / peak - 1.0)
    return worst


def sharpe_ratio(returns: list[float]) -> float:
    if not returns:
        return 0.0
    mean_value = sum(returns) / len(returns)
    variance = sum((value - mean_value) ** 2 for value in returns) / len(returns)
    std = sqrt(variance)
    if std == 0:
        return 0.0
    return mean_value / std * sqrt(TRADING_DAYS_PER_YEAR)


def calmar_ratio(equity: list[float]) -> float:
    drawdown = abs(max_drawdown(equity))
    if drawdown == 0:
        return 0.0
    return annualized_return(equity) / drawdown


def monthly_returns(dates: list[date], equity: list[float]) -> dict[str, float]:
    if len(dates) != len(equity):
        raise ValueError("dates and equity length mismatch")
    result: dict[str, float] = {}
    month_start = equity[0]
    current_month = f"{dates[0].year:04d}-{dates[0].month:02d}"

    for day, value in zip(dates[1:], equity[1:], strict=True):
        month = f"{day.year:04d}-{day.month:02d}"
        if month != current_month:
            previous_value = equity[dates.index(day) - 1]
            result[current_month] = previous_value / month_start - 1.0
            current_month = month
            month_start = previous_value

    result[current_month] = equity[-1] / month_start - 1.0
    return result


def monthly_win_rate(dates: list[date], equity: list[float]) -> float:
    returns = list(monthly_returns(dates, equity).values())
    if not returns:
        return 0.0
    wins = sum(1 for value in returns if value > 0)
    return wins / len(returns)


def max_consecutive_losing_months(dates: list[date], equity: list[float]) -> int:
    longest = 0
    current = 0
    for value in monthly_returns(dates, equity).values():
        if value < 0:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest


def annual_returns(dates: list[date], equity: list[float]) -> dict[int, float]:
    result: dict[int, float] = {}
    year_start = equity[0]
    current_year = dates[0].year

    for i in range(1, len(dates)):
        if dates[i].year != current_year:
            result[current_year] = equity[i - 1] / year_start - 1.0
            current_year = dates[i].year
            year_start = equity[i - 1]

    result[current_year] = equity[-1] / year_start - 1.0
    return result


def summarize_performance(
    dates: list[date],
    strategy_equity: list[float],
    benchmark_equity: list[float] | None,
    equal_weight_equity: list[float],
    turnovers: list[float],
    costs: list[float],
) -> dict[str, float]:
    returns = equity_to_returns(strategy_equity)
    metrics = {
        "final_equity": strategy_equity[-1],
        "annualized_return": annualized_return(strategy_equity),
        "max_drawdown": max_drawdown(strategy_equity),
        "sharpe_ratio": sharpe_ratio(returns),
        "calmar_ratio": calmar_ratio(strategy_equity),
        "monthly_win_rate": monthly_win_rate(dates, strategy_equity),
        "max_consecutive_losing_months": float(
            max_consecutive_losing_months(dates, strategy_equity)
        ),
        "average_turnover": sum(turnovers) / len(turnovers) if turnovers else 0.0,
        "total_transaction_cost": sum(costs),
        "equal_weight_final_equity": equal_weight_equity[-1],
        "excess_return_vs_equal_weight": strategy_equity[-1] / equal_weight_equity[-1]
        - 1.0,
    }
    if benchmark_equity is not None:
        metrics["benchmark_final_equity"] = benchmark_equity[-1]
        metrics["excess_return_vs_benchmark"] = strategy_equity[-1] / benchmark_equity[-1] - 1.0
    return metrics
