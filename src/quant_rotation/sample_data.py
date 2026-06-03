from __future__ import annotations

import csv
import math
import random
from datetime import date, timedelta
from pathlib import Path


INDUSTRIES = [
    "Agriculture",
    "Coal",
    "Petrochemical",
    "Steel",
    "Nonferrous",
    "Electronics",
    "HomeAppliance",
    "FoodBeverage",
    "Textile",
    "LightManufacturing",
    "Pharma",
    "Utilities",
    "Transportation",
    "RealEstate",
    "Retail",
    "SocialService",
    "Media",
    "Bank",
    "NonBankFinance",
    "Automotive",
    "Machinery",
    "Defense",
    "Computer",
    "Communication",
    "Chemical",
    "BuildingMaterials",
    "Construction",
    "PowerEquipment",
    "Environmental",
    "BeautyCare",
    "Integrated",
]

STOCKS_PER_INDUSTRY = 5


def business_dates(start: date, days: int) -> list[date]:
    result: list[date] = []
    current = start
    while len(result) < days:
        if current.weekday() < 5:
            result.append(current)
        current += timedelta(days=1)
    return result


def _bounded(value: float, low: float = 0.05, high: float = 0.95) -> float:
    return max(low, min(high, value))


def generate_sample_data(output_dir: str | Path, days: int = 520, seed: int = 7) -> None:
    if days < 180:
        raise ValueError("days must be at least 180")
    rng = random.Random(seed)
    breadth_rng = random.Random(seed + 17)
    market_rng = random.Random(seed + 31)
    stock_rng = random.Random(seed + 43)
    path = Path(output_dir)
    path.mkdir(parents=True, exist_ok=True)

    dates = business_dates(date(2023, 1, 2), days)
    industry_prices = {industry: [1000.0 + 8.0 * i] for i, industry in enumerate(INDUSTRIES)}
    stocks_by_industry = {
        industry: [
            f"{industry}_{number:02d}"
            for number in range(1, STOCKS_PER_INDUSTRY + 1)
        ]
        for industry in INDUSTRIES
    }
    stock_industry_map = {
        stock: industry
        for industry, stocks in stocks_by_industry.items()
        for stock in stocks
    }
    stock_prices = {
        stock: [20.0 + 0.7 * industry_index + 0.3 * stock_index]
        for industry_index, industry in enumerate(INDUSTRIES)
        for stock_index, stock in enumerate(stocks_by_industry[industry])
    }
    stock_amounts = {
        stock: [120_000_000.0 + 4_000_000.0 * industry_index + 1_000_000.0 * stock_index]
        for industry_index, industry in enumerate(INDUSTRIES)
        for stock_index, stock in enumerate(stocks_by_industry[industry])
    }
    stock_alphas = {
        stock: stock_rng.gauss(0.0, 0.00025)
        for stock in stock_industry_map
    }
    industry_amounts = {
        industry: [800_000_000.0 + 25_000_000.0 * i]
        for i, industry in enumerate(INDUSTRIES)
    }
    industry_breadth20 = {industry: [0.50] for industry in INDUSTRIES}
    industry_breadth60 = {industry: [0.50] for industry in INDUSTRIES}
    industry_valuation = {
        industry: [_bounded(0.55 - 0.012 * (i % 7), low=0.02, high=0.98)]
        for i, industry in enumerate(INDUSTRIES)
    }
    industry_prosperity = {industry: [0.0] for industry in INDUSTRIES}
    benchmark = [4000.0]
    market_prices = {
        "CSI300": [4000.0],
        "CSIAll": [3600.0],
        "ChiNext": [2500.0],
    }

    for t in range(1, len(dates)):
        regime = 0.00045 if (t // 120) % 3 != 1 else -0.00015
        benchmark_noise = rng.gauss(0.0, 0.006)
        benchmark_ret = regime + 0.0012 * math.sin(t / 45.0) + benchmark_noise
        benchmark.append(max(100.0, benchmark[-1] * (1.0 + benchmark_ret)))
        market_prices["CSI300"].append(benchmark[-1])
        all_market_ret = (
            regime
            + 0.0010 * math.sin(t / 50.0)
            + 0.55 * benchmark_noise
            + market_rng.gauss(0.0, 0.0045)
        )
        chinext_ret = (
            1.15 * regime
            + 0.0018 * math.sin(t / 34.0)
            + 0.35 * benchmark_noise
            + market_rng.gauss(0.0, 0.0075)
        )
        market_prices["CSIAll"].append(
            max(100.0, market_prices["CSIAll"][-1] * (1.0 + all_market_ret))
        )
        market_prices["ChiNext"].append(
            max(100.0, market_prices["ChiNext"][-1] * (1.0 + chinext_ret))
        )

        leadership_bucket = (t // 40) % 6
        for idx, industry in enumerate(INDUSTRIES):
            bucket = idx % 6
            leadership = 0.0018 if bucket == leadership_bucket else -0.0002
            cycle = 0.0012 * math.sin(t / 28.0 + idx * 0.55)
            idiosyncratic = rng.gauss(0.0, 0.0085)
            ret = regime + leadership + cycle + idiosyncratic
            industry_prices[industry].append(
                max(50.0, industry_prices[industry][-1] * (1.0 + ret))
            )
            activity = 1.35 if bucket == leadership_bucket else 0.95
            activity += 16.0 * abs(ret) + 0.08 * math.sin(t / 17.0 + idx)
            amount_noise = max(0.55, 1.0 + rng.gauss(0.0, 0.10))
            base_amount = 800_000_000.0 + 25_000_000.0 * idx
            industry_amounts[industry].append(
                max(10_000_000.0, base_amount * activity * amount_noise)
            )
            for stock_index, stock in enumerate(stocks_by_industry[industry]):
                stock_ret = ret + stock_alphas[stock] + stock_rng.gauss(0.0, 0.011)
                stock_prices[stock].append(
                    max(1.0, stock_prices[stock][-1] * (1.0 + stock_ret))
                )
                stock_base_amount = 120_000_000.0 + 4_000_000.0 * idx + 1_000_000.0 * stock_index
                stock_activity = activity + 18.0 * abs(stock_ret)
                stock_amounts[stock].append(
                    max(
                        5_000_000.0,
                        stock_base_amount
                        * stock_activity
                        * max(0.45, 1.0 + stock_rng.gauss(0.0, 0.16)),
                    )
                )
            breadth_base = 0.68 if bucket == leadership_bucket else 0.42
            breadth20 = (
                breadth_base
                + 9.0 * ret
                + 0.08 * math.sin(t / 13.0 + idx * 0.4)
                + breadth_rng.gauss(0.0, 0.06)
            )
            breadth60 = (
                0.52
                + 0.65 * (breadth20 - 0.50)
                + 0.06 * math.sin(t / 31.0 + idx * 0.3)
                + breadth_rng.gauss(0.0, 0.035)
            )
            industry_breadth20[industry].append(_bounded(breadth20))
            industry_breadth60[industry].append(_bounded(breadth60))
            valuation = (
                industry_valuation[industry][-1]
                - 1.8 * ret
                + 0.01 * math.sin(t / 37.0 + idx * 0.2)
                + breadth_rng.gauss(0.0, 0.012)
            )
            industry_valuation[industry].append(_bounded(valuation, low=0.02, high=0.98))
            prosperity = (
                0.55 * (breadth20 - 0.50)
                + 0.35 * (activity - 1.0)
                + 18.0 * ret
            )
            industry_prosperity[industry].append(prosperity)

    with (path / "industry_close.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", *INDUSTRIES])
        for row_index, day in enumerate(dates):
            writer.writerow(
                [
                    day.isoformat(),
                    *[
                        f"{industry_prices[industry][row_index]:.4f}"
                        for industry in INDUSTRIES
                    ],
                ]
            )

    with (path / "benchmark_close.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "close"])
        for day, close in zip(dates, benchmark, strict=True):
            writer.writerow([day.isoformat(), f"{close:.4f}"])

    with (path / "market_close.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        assets = list(market_prices)
        writer.writerow(["date", *assets])
        for row_index, day in enumerate(dates):
            writer.writerow(
                [
                    day.isoformat(),
                    *[
                        f"{market_prices[asset][row_index]:.4f}"
                        for asset in assets
                    ],
                ]
            )

    with (path / "industry_amount.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", *INDUSTRIES])
        for row_index, day in enumerate(dates):
            writer.writerow(
                [
                    day.isoformat(),
                    *[
                        f"{industry_amounts[industry][row_index]:.2f}"
                        for industry in INDUSTRIES
                    ],
                ]
            )

    stock_assets = list(stock_prices)
    with (path / "stock_close.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", *stock_assets])
        for row_index, day in enumerate(dates):
            writer.writerow(
                [
                    day.isoformat(),
                    *[f"{stock_prices[stock][row_index]:.4f}" for stock in stock_assets],
                ]
            )

    with (path / "stock_amount.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", *stock_assets])
        for row_index, day in enumerate(dates):
            writer.writerow(
                [
                    day.isoformat(),
                    *[f"{stock_amounts[stock][row_index]:.2f}" for stock in stock_assets],
                ]
            )

    with (path / "stock_industry_map.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["stock", "industry"])
        for stock in stock_assets:
            writer.writerow([stock, stock_industry_map[stock]])

    for file_name, breadth in (
        ("industry_breadth20.csv", industry_breadth20),
        ("industry_breadth60.csv", industry_breadth60),
    ):
        with (path / file_name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", *INDUSTRIES])
            for row_index, day in enumerate(dates):
                writer.writerow(
                    [
                        day.isoformat(),
                        *[
                            f"{breadth[industry][row_index]:.6f}"
                            for industry in INDUSTRIES
                        ],
                    ]
                )

    for file_name, values in (
        ("industry_valuation.csv", industry_valuation),
        ("industry_prosperity.csv", industry_prosperity),
    ):
        with (path / file_name).open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(["date", *INDUSTRIES])
            for row_index, day in enumerate(dates):
                writer.writerow(
                    [
                        day.isoformat(),
                        *[
                            f"{values[industry][row_index]:.6f}"
                            for industry in INDUSTRIES
                        ],
                    ]
                )
