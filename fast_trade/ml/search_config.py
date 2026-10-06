"""YAML search contracts and disjoint, half-open date ranges (Polars only)."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import timezone
import hashlib
import itertools
import math
from pathlib import Path
from typing import Any, Mapping, Sequence

import polars as pl
import yaml

from fast_trade.build_data_frame import parse_date_bound
from fast_trade.frames import freq_to_timedelta


DEFAULT_BASELINES = ("buy_hold", "rsi", "random")


def _utc_bound(value):
    bound = parse_date_bound(value)
    if bound is None:
        raise ValueError("Date bounds must be nonempty")
    return bound.astimezone(timezone.utc).replace(tzinfo=None) if bound.tzinfo else bound


@dataclass(frozen=True)
class DataSplit:
    search_start: str | None = None
    search_stop: str | None = None
    holdout_start: str | None = None
    holdout_stop: str | None = None

    def validate(self) -> None:
        if not self.holdout_start:
            raise ValueError("data.holdout_start is required")
        holdout = _utc_bound(self.holdout_start)
        stop = _utc_bound(self.search_stop) if self.search_stop else holdout
        if stop > holdout:
            raise ValueError("data.search_stop must be <= data.holdout_start")
        if self.search_start and _utc_bound(self.search_start) >= stop:
            raise ValueError("Search start must precede its exclusive stop")
        if self.holdout_stop and _utc_bound(self.holdout_stop) <= holdout:
            raise ValueError("Holdout start must precede its exclusive stop")


@dataclass(frozen=True)
class SearchSpace:
    horizons: tuple[int, ...] = (5,)
    thresholds: tuple[float, ...] = (0.01,)
    train_sizes: tuple[int, ...] = (400,)
    test_sizes: tuple[int, ...] = (100,)
    use_ta: tuple[bool, ...] = (True,)
    include_basic: tuple[bool, ...] = (True,)
    freqs: tuple[str, ...] = ("1h",)

    def validate(self) -> None:
        values = asdict(self)
        if any(not value or len(set(value)) != len(value) for value in values.values()):
            raise ValueError("Search-space lists must be nonempty and contain distinct values")
        if len(self.test_sizes) != 1 or len(self.freqs) != 1:
            raise ValueError("Use one test size and frequency per search for comparable test windows")
        if any(type(v) is not int or v < 1 for v in self.horizons + self.train_sizes + self.test_sizes):
            raise ValueError("Horizons and window sizes must be positive integers")
        if (min(self.train_sizes) - max(self.horizons) < 20 or min(self.test_sizes) <= max(self.horizons)
                or min(self.test_sizes) < 5):
            raise ValueError("Windows must leave 20 training rows after purge and exceed the label horizon")
        if any(not math.isfinite(v) for v in self.thresholds):
            raise ValueError("Thresholds must be finite")
        if any(type(v) is not bool for v in self.use_ta + self.include_basic):
            raise ValueError("Feature flags must be YAML booleans")
        if not any(self.use_ta) and not any(self.include_basic):
            raise ValueError("Enable use_ta and/or include_basic")
        if freq_to_timedelta(self.freqs[0]).total_seconds() <= 0:
            raise ValueError("Frequency must be positive")


@dataclass(frozen=True)
class StageRules:
    baselines: tuple[str, ...] = DEFAULT_BASELINES
    min_trades: int = 5
    top_n: int = 5
    must_beat: tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.baselines or set(self.baselines) - set(DEFAULT_BASELINES):
            raise ValueError("Select known, nonempty baselines")
        if set(self.must_beat) - set(self.baselines):
            raise ValueError("must_beat must be a subset of evaluated baselines")
        if type(self.min_trades) is not int or self.min_trades < 0:
            raise ValueError("min_trades must be a nonnegative integer")
        if type(self.top_n) is not int or self.top_n < 1:
            raise ValueError("top_n must be a positive integer")


@dataclass(frozen=True)
class TrialConfig:
    trial_id: str
    horizon: int
    threshold: float
    train_size: int
    test_size: int
    step_size: int
    use_ta: bool
    include_basic: bool
    freq: str
    comission: float
    random_state: int
    baselines: tuple[str, ...]
    signal_lag: int = 1
    base_balance: float = 1000.0
    stage: str = "screen"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def walk_forward_kwargs(self) -> dict[str, Any]:
        return {key: value for key, value in self.to_dict().items() if key not in {"trial_id", "stage"}}


@dataclass(frozen=True)
class SearchSpec:
    name: str
    symbol: str
    exchange: str
    freq: str
    comission: float
    random_state: int
    data: DataSplit
    space: SearchSpace
    screen: StageRules
    promote: StageRules
    holdout: StageRules
    output_dir: str
    signal_lag: int = 1
    base_balance: float = 1000.0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["output"] = {"dir": result.pop("output_dir")}
        return result

    def validate(self) -> None:
        self.data.validate()
        self.space.validate()
        for stage in (self.screen, self.promote, self.holdout):
            stage.validate()
        if self.screen.must_beat or self.promote.must_beat:
            raise ValueError("must_beat is only supported for holdout confirmation")
        if self.freq != self.space.freqs[0]:
            raise ValueError("space.freqs must match the input freq")
        if not self.name or Path(self.name).name != self.name or self.name in {".", ".."}:
            raise ValueError("name must be a single directory name")
        if not math.isfinite(self.comission) or not 0 <= self.comission < 100:
            raise ValueError("comission must be finite and between 0 and 100")
        if not math.isfinite(self.base_balance) or self.base_balance <= 0:
            raise ValueError("base_balance must be positive and finite")
        if type(self.signal_lag) is not int or self.signal_lag < 1:
            raise ValueError("signal_lag must be a positive integer")
        if type(self.random_state) is not int or self.random_state < 0:
            raise ValueError("random_state must be a nonnegative integer")


def _values(value: Any, kind: type) -> tuple:
    items = value if isinstance(value, (list, tuple)) else [value]
    if any(not isinstance(v, kind) or (kind is int and isinstance(v, bool)) for v in items):
        # Float parameters also accept ordinary YAML integers.
        if kind is not float or any(type(v) not in (int, float) for v in items):
            raise ValueError(f"Expected {kind.__name__} values in search space")
    return tuple(kind(v) for v in items)


def load_search_spec(source: Mapping[str, Any] | str | Path) -> SearchSpec:
    raw = dict(source) if isinstance(source, Mapping) else yaml.safe_load(Path(source).read_text())
    if not isinstance(raw, Mapping):
        raise ValueError("Search spec must be a mapping")
    allowed = {"name", "symbol", "exchange", "freq", "comission", "random_state", "data", "space",
               "screen", "promote", "holdout", "output", "signal_lag", "base_balance"}
    if set(raw) - allowed:
        raise ValueError(f"Unknown search spec fields: {sorted(set(raw) - allowed)}")
    freq = raw.get("freq", "1h")
    defaults = asdict(SearchSpace(freqs=(freq,)))
    space_raw = raw.get("space", {})
    if not isinstance(space_raw, Mapping) or set(space_raw) - set(defaults):
        raise ValueError("Unknown search-space fields or invalid mapping")
    kinds = dict(horizons=int, thresholds=float, train_sizes=int, test_sizes=int,
                 use_ta=bool, include_basic=bool, freqs=str)
    space = SearchSpace(**{key: _values(space_raw.get(key, value), kinds[key]) for key, value in defaults.items()})

    def rules(name, default):
        values = {**asdict(default), **raw.get(name, {})}
        values["baselines"] = _values(values["baselines"], str)
        values["must_beat"] = _values(values["must_beat"], str)
        return StageRules(**values)

    spec = SearchSpec(
        name=raw.get("name", "ml_search"), symbol=raw.get("symbol", "BTC-USD"),
        exchange=raw.get("exchange", "coinbase"), freq=freq, comission=raw.get("comission", 0.01),
        random_state=raw.get("random_state", 42), data=DataSplit(**raw.get("data", {})), space=space,
        screen=rules("screen", StageRules(baselines=("buy_hold",), top_n=20)),
        promote=rules("promote", StageRules(min_trades=10)),
        holdout=rules("holdout", StageRules(must_beat=("buy_hold", "rsi"))),
        output_dir=raw.get("output", {}).get("dir", "ft_archive/ml_search"),
        signal_lag=raw.get("signal_lag", 1), base_balance=raw.get("base_balance", 1000.0),
    )
    spec.validate()
    return spec


def trial_id_for(payload: Mapping[str, Any]) -> str:
    return hashlib.sha256(yaml.safe_dump(dict(payload), sort_keys=True).encode()).hexdigest()[:16]


def expand_trials(spec: SearchSpec, *, limit: int | None = None, stage: str = "screen",
                  baselines: Sequence[str] | None = None) -> list[TrialConfig]:
    spec.validate()
    if limit is not None and (type(limit) is not int or limit < 1):
        raise ValueError("limit must be a positive integer")
    rules = {"screen": spec.screen, "promote": spec.promote, "holdout": spec.holdout}[stage]
    used = tuple(rules.baselines if baselines is None else baselines)
    StageRules(baselines=used).validate()
    trials = []
    for horizon, threshold, train, test, ta, basic, freq in itertools.product(*asdict(spec.space).values()):
        if not ta and not basic:
            continue
        values = dict(horizon=horizon, threshold=threshold, train_size=train, test_size=test,
                      step_size=test, use_ta=ta, include_basic=basic, freq=freq,
                      comission=spec.comission, random_state=spec.random_state,
                      signal_lag=spec.signal_lag, base_balance=spec.base_balance)
        trials.append(TrialConfig(trial_id=trial_id_for(values), baselines=used, stage=stage, **values))
        if limit is not None and len(trials) >= limit:
            break
    return trials


def slice_by_split(df: pl.DataFrame, start: str | None, stop: str | None) -> pl.DataFrame:
    if df.is_empty() or "date" not in df.columns or not isinstance(df.schema["date"], pl.Datetime):
        raise ValueError("Nonempty dataframe with datetime date column is required")
    out = df.sort("date")
    # Date bounds are UTC; Polars handles conversion to the column's timezone.
    tz = df.schema["date"].time_zone
    for value, upper in ((start, False), (stop, True)):
        if value:
            bound = _utc_bound(value)
            literal = pl.lit(bound).dt.replace_time_zone("UTC").dt.convert_time_zone(tz) if tz else pl.lit(bound)
            out = out.filter(pl.col("date") < literal if upper else pl.col("date") >= literal)
    if out.is_empty():
        raise ValueError(f"No rows in range start={start!r} stop={stop!r}")
    return out


def slice_search_df(df: pl.DataFrame, spec: SearchSpec) -> pl.DataFrame:
    spec.data.validate()
    return slice_by_split(df, spec.data.search_start, spec.data.search_stop or spec.data.holdout_start)


def slice_holdout_df(df: pl.DataFrame, spec: SearchSpec) -> pl.DataFrame:
    spec.data.validate()
    return slice_by_split(df, spec.data.holdout_start, spec.data.holdout_stop)
