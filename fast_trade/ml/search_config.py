"""Search-space config, frozen date split, and trial expansion.

Problem 1: one trial is a small, serializable knob set.
Problem 2: search vs holdout dates are locked before any run.
"""

from __future__ import annotations

import hashlib
import itertools
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

import pandas as pd
import yaml


DEFAULT_BASELINES = ("buy_hold", "rsi", "random")


@dataclass(frozen=True)
class DataSplit:
    search_start: Optional[str] = None
    search_stop: Optional[str] = None
    holdout_start: Optional[str] = None
    holdout_stop: Optional[str] = None

    def validate(self) -> None:
        if not self.holdout_start:
            raise ValueError("data.holdout_start is required to lock the confirmation window")
        if self.search_stop and self.holdout_start:
            if pd.Timestamp(self.search_stop) > pd.Timestamp(self.holdout_start):
                raise ValueError("data.search_stop must be <= data.holdout_start")


@dataclass(frozen=True)
class SearchSpace:
    horizons: Tuple[int, ...] = (5,)
    thresholds: Tuple[float, ...] = (0.01,)
    train_sizes: Tuple[int, ...] = (400,)
    test_sizes: Tuple[int, ...] = (100,)
    use_ta: Tuple[bool, ...] = (True,)
    include_basic: Tuple[bool, ...] = (True,)
    freqs: Tuple[str, ...] = ()

    def validate(self) -> None:
        if not self.horizons or not self.thresholds or not self.train_sizes or not self.test_sizes:
            raise ValueError("space.horizons/thresholds/train_sizes/test_sizes must be non-empty")
        if not any(self.use_ta) and not any(self.include_basic):
            raise ValueError("space must enable use_ta and/or include_basic")


@dataclass(frozen=True)
class StageRules:
    baselines: Tuple[str, ...] = DEFAULT_BASELINES
    min_trades: int = 5
    top_n: int = 5
    must_beat: Tuple[str, ...] = ()

    def validate(self) -> None:
        unknown = set(self.baselines) - {"buy_hold", "rsi", "random"}
        if unknown:
            raise ValueError(f"Unknown baselines: {sorted(unknown)}")
        unknown_beat = set(self.must_beat) - {"buy_hold", "rsi", "random"}
        if unknown_beat:
            raise ValueError(f"Unknown must_beat values: {sorted(unknown_beat)}")
        if self.min_trades < 0:
            raise ValueError("min_trades must be >= 0")
        if self.top_n < 1:
            raise ValueError("top_n must be >= 1")


@dataclass(frozen=True)
class TrialConfig:
    trial_id: str
    horizon: int
    threshold: float
    train_size: int
    test_size: int
    step_size: Optional[int]
    use_ta: bool
    include_basic: bool
    freq: str
    comission: float
    random_state: int
    baselines: Tuple[str, ...]
    stage: str = "screen"

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    def walk_forward_kwargs(self) -> Dict[str, Any]:
        return {
            "train_size": self.train_size,
            "test_size": self.test_size,
            "step_size": self.step_size,
            "horizon": self.horizon,
            "threshold": self.threshold,
            "use_ta": self.use_ta,
            "include_basic": self.include_basic,
            "freq": self.freq,
            "comission": self.comission,
            "random_state": self.random_state,
            "baselines": self.baselines,
        }


@dataclass
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
    extras: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        self.data.validate()
        self.space.validate()
        self.screen.validate()
        self.promote.validate()
        self.holdout.validate()


def _as_tuple(value: Any, cast=None) -> Tuple:
    if value is None:
        return tuple()
    if isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]
    if cast is not None:
        items = [cast(v) for v in items]
    return tuple(items)


def _load_mapping(source: Any) -> Dict[str, Any]:
    if isinstance(source, Mapping):
        return dict(source)
    path = Path(source)
    if not path.is_file():
        raise FileNotFoundError(f"Search spec not found: {path}")
    with path.open() as fh:
        loaded = yaml.safe_load(fh) or {}
    if not isinstance(loaded, Mapping):
        raise ValueError("Search spec must be a mapping")
    return dict(loaded)


def load_search_spec(source: Any) -> SearchSpec:
    raw = _load_mapping(source)
    data_raw = raw.get("data") or {}
    space_raw = raw.get("space") or {}
    screen_raw = raw.get("screen") or {}
    promote_raw = raw.get("promote") or {}
    holdout_raw = raw.get("holdout") or {}
    outputs = raw.get("output") or raw.get("outputs") or {}

    freq = str(raw.get("freq") or "1h")
    space = SearchSpace(
        horizons=_as_tuple(space_raw.get("horizons", 5), int) or (5,),
        thresholds=_as_tuple(space_raw.get("thresholds", 0.01), float) or (0.01,),
        train_sizes=_as_tuple(space_raw.get("train_sizes", 400), int) or (400,),
        test_sizes=_as_tuple(space_raw.get("test_sizes", 100), int) or (100,),
        use_ta=_as_tuple(space_raw.get("use_ta", True), bool) or (True,),
        include_basic=_as_tuple(space_raw.get("include_basic", True), bool) or (True,),
        freqs=_as_tuple(space_raw.get("freqs"), str) or (freq,),
    )
    spec = SearchSpec(
        name=str(raw.get("name") or "ml_search"),
        symbol=str(raw.get("symbol") or "BTCUSDT"),
        exchange=str(raw.get("exchange") or "binanceus"),
        freq=freq,
        comission=float(raw.get("comission", 0.01)),
        random_state=int(raw.get("random_state", 42)),
        data=DataSplit(
            search_start=data_raw.get("search_start"),
            search_stop=data_raw.get("search_stop"),
            holdout_start=data_raw.get("holdout_start"),
            holdout_stop=data_raw.get("holdout_stop"),
        ),
        space=space,
        screen=StageRules(
            baselines=_as_tuple(screen_raw.get("baselines", ("buy_hold",)), str)
            or ("buy_hold",),
            min_trades=int(screen_raw.get("min_trades", 5)),
            top_n=int(screen_raw.get("top_n", 20)),
        ),
        promote=StageRules(
            baselines=_as_tuple(promote_raw.get("baselines", DEFAULT_BASELINES), str)
            or DEFAULT_BASELINES,
            min_trades=int(promote_raw.get("min_trades", 10)),
            top_n=int(promote_raw.get("top_n", 5)),
        ),
        holdout=StageRules(
            baselines=_as_tuple(holdout_raw.get("baselines", DEFAULT_BASELINES), str)
            or DEFAULT_BASELINES,
            min_trades=int(holdout_raw.get("min_trades", 5)),
            top_n=int(holdout_raw.get("top_n", 5)),
            must_beat=_as_tuple(holdout_raw.get("must_beat", ("buy_hold", "rsi")), str),
        ),
        output_dir=str(outputs.get("dir") or "ft_archive/ml_search"),
        extras={k: v for k, v in raw.items() if k not in {
            "name", "symbol", "exchange", "freq", "comission", "random_state",
            "data", "space", "screen", "promote", "holdout", "output", "outputs",
        }},
    )
    spec.validate()
    return spec


def trial_id_for(payload: Mapping[str, Any]) -> str:
    blob = yaml.safe_dump(dict(payload), sort_keys=True)
    return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:10]


def expand_trials(
    spec: SearchSpec,
    *,
    limit: Optional[int] = None,
    stage: str = "screen",
    baselines: Optional[Sequence[str]] = None,
) -> List[TrialConfig]:
    """Cartesian product of the search space (Problem 1)."""
    spec.validate()
    used_baselines = tuple(baselines or spec.screen.baselines)
    trials: List[TrialConfig] = []
    product = itertools.product(
        spec.space.horizons,
        spec.space.thresholds,
        spec.space.train_sizes,
        spec.space.test_sizes,
        spec.space.use_ta,
        spec.space.include_basic,
        spec.space.freqs or (spec.freq,),
    )
    for horizon, threshold, train_size, test_size, use_ta, include_basic, freq in product:
        if not use_ta and not include_basic:
            continue
        payload = {
            "horizon": int(horizon),
            "threshold": float(threshold),
            "train_size": int(train_size),
            "test_size": int(test_size),
            "use_ta": bool(use_ta),
            "include_basic": bool(include_basic),
            "freq": str(freq),
            "comission": spec.comission,
            "random_state": spec.random_state,
        }
        trials.append(
            TrialConfig(
                trial_id=trial_id_for(payload),
                horizon=int(horizon),
                threshold=float(threshold),
                train_size=int(train_size),
                test_size=int(test_size),
                step_size=int(test_size),
                use_ta=bool(use_ta),
                include_basic=bool(include_basic),
                freq=str(freq),
                comission=spec.comission,
                random_state=spec.random_state,
                baselines=used_baselines,
                stage=stage,
            )
        )
        if limit is not None and len(trials) >= limit:
            break
    if not trials:
        raise ValueError("Search space produced no trials")
    return trials


def _align_timestamp(index: pd.Index, value: str) -> pd.Timestamp:
    ts = pd.Timestamp(value)
    tz = getattr(index, "tz", None)
    if tz is not None:
        if ts.tzinfo is None:
            return ts.tz_localize(tz)
        return ts.tz_convert(tz)
    if ts.tzinfo is not None:
        return ts.tz_convert("UTC").tz_localize(None)
    return ts


def slice_by_split(
    df: pd.DataFrame,
    start: Optional[str],
    stop: Optional[str],
) -> pd.DataFrame:
    if df.empty:
        raise ValueError("Cannot slice an empty dataframe")
    out = df.sort_index()
    if start:
        out = out[out.index >= _align_timestamp(out.index, start)]
    if stop:
        # holdout_start is exclusive of search when used as search_stop
        out = out[out.index < _align_timestamp(out.index, stop)]
    if out.empty:
        raise ValueError(f"No rows in range start={start!r} stop={stop!r}")
    return out


def slice_search_df(df: pd.DataFrame, spec: SearchSpec) -> pd.DataFrame:
    stop = spec.data.search_stop or spec.data.holdout_start
    return slice_by_split(df, spec.data.search_start, stop)


def slice_holdout_df(df: pd.DataFrame, spec: SearchSpec) -> pd.DataFrame:
    return slice_by_split(df, spec.data.holdout_start, spec.data.holdout_stop)
