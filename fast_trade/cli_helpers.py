# flake8: noqa
import datetime
import json
import os
import re

import pandas as pd
import plotly.graph_objects as go
import requests

from fast_trade.archive.db_helpers import connect_to_db

ARCHIVE_PATH = os.getenv("ARCHIVE_PATH", "ft_archive")


class MissingStrategyFile(Exception):
    pass


def _load_json_or_yaml(fp: str):
    if fp.endswith((".yml", ".yaml")):
        try:
            import yaml
        except Exception as exc:
            raise MissingStrategyFile(f"PyYAML is required to load {fp}: {exc}")
        with open(fp, "r") as fh:
            return yaml.safe_load(fh)
    with open(fp, "r") as fh:
        return json.load(fh)


def open_strat_file(fp):
    reg = r"https?:\/\/(www\.)?[-a-zA-Z0-9@:%._\+~#=]{1,256}\.[a-zA-Z0-9()]{1,6}\b([-a-zA-Z0-9()@:%_\+.~#?&//=]*)"

    is_url = re.search(reg, fp)
    if is_url:
        # url
        req = requests.get(fp)
        if req.status_code in [200, 201, 202, 301]:
            return req.json()
        else:
            raise MissingStrategyFile(
                "Could not open strategy file at url: {}".format(fp)
            )

    strat_obj = {}
    try:
        strat_obj = _load_json_or_yaml(fp)
        return strat_obj

    except FileNotFoundError:
        raise MissingStrategyFile("Could not open strategy file at path: {}".format(fp))


def create_plot(df, trade_df, show: bool = True):
    fig = go.Figure()
    if "close" in df.columns:
        fig.add_trace(
            go.Scatter(
                x=df.index,
                y=df["close"],
                mode="lines",
                name="close",
                line=dict(color="#6EE7B7", width=1),
            )
        )

    if trade_df is not None and not trade_df.empty and "close" in trade_df.columns:
        colors = ["#22C55E" if row["in_trade"] else "#EF4444" for _, row in trade_df.iterrows()]
        fig.add_trace(
            go.Scatter(
                x=trade_df.index,
                y=trade_df["close"],
                mode="markers",
                name="trades",
                marker=dict(size=6, color=colors),
            )
        )

    fig.update_layout(
        template="plotly_dark",
        title="Backtest Price & Trades",
        xaxis_title="Date",
        yaxis_title="Price",
        margin=dict(l=40, r=40, t=50, b=40),
        height=500,
    )

    if show:
        fig.show()
    return fig


def render_plot_preview_from_data(df, trade_df, width: int = 80, height: int = 12) -> None:
    if df is None or df.empty or "close" not in df.columns:
        return
    series = df["close"].values
    if len(series) == 0:
        return

    import math

    min_val = float(series.min())
    max_val = float(series.max())
    span = max(max_val - min_val, 1e-9)

    step = max(1, int(len(series) / width))
    sampled = series[::step][:width]

    grid = [[" " for _ in range(len(sampled))] for _ in range(height)]
    for x, val in enumerate(sampled):
        y = int((val - min_val) / span * (height - 1))
        y = height - 1 - y
        grid[y][x] = "#"

    # mark trades if available
    if trade_df is not None and not trade_df.empty and "close" in trade_df.columns:
        trade_series = trade_df["close"].values
        trade_idx = trade_df.index
        # map trade points to sampled x positions
        for idx, val in zip(trade_idx, trade_series):
            # approximate position by index in df
            try:
                pos = df.index.get_loc(idx)
            except Exception:
                continue
            x = int(pos / step)
            if x < 0 or x >= len(sampled):
                continue
            y = int((val - min_val) / span * (height - 1))
            y = height - 1 - y
            grid[y][x] = "x"

    for row in grid:
        print("".join(row))


def save(result, save_all: bool = False):
    """
    Save the dataframe, backtest, and plot into the specified path
    """

    save_path = ARCHIVE_PATH
    if not os.path.exists(save_path):
        os.mkdir(save_path)
    if not os.path.exists(f"{save_path}/backtests"):
        os.mkdir(f"{save_path}/backtests")
    # dir exists, now make a new dir with the files
    new_dir = (
        f"{datetime.datetime.strftime(datetime.datetime.now(), '%Y_%m_%d_%H_%M_%S')}"
    )

    new_save_dir = f"{save_path}/backtests/{new_dir}"

    os.mkdir(new_save_dir)

    # save the backtest args
    # summary file
    try:
        import yaml
    except Exception:
        yaml = None

    summary_path = f"{new_save_dir}/summary.yml"
    with open(summary_path, "w") as summary_file:
        if yaml is not None:
            yaml.safe_dump(result["summary"], summary_file, sort_keys=False)
        else:
            summary_file.write(json.dumps(result["summary"], indent=2))

    # dataframe
    # result["df"].to_csv(f"{new_save_dir}/dataframe.csv")
    # result["trade_df"].to_csv(f"{new_save_dir}/trade_dataframe.csv")
    if save_all:
        result["df"].to_parquet(
            f"{new_save_dir}/dataframe.parquet", index=True
        )
        result["trade_df"].to_parquet(
            f"{new_save_dir}/trade_log.parquet", index=True
        )

    # plot
    fig = create_plot(result["df"], result["trade_df"], show=False)
    plot_path = f"{new_save_dir}/plot.png"
    plot_format = "png"
    try:
        fig.write_image(plot_path, scale=2)
    except Exception:
        plot_path = f"{new_save_dir}/plot.html"
        plot_format = "html"
        fig.write_html(plot_path)

    return {"path": new_save_dir, "plot_path": plot_path, "plot_format": plot_format}
def render_plot_preview(path: str, width: int = 80) -> None:
    try:
        from PIL import Image
    except Exception:
        return

    chars = " .:-=+*#%@"
    try:
        img = Image.open(path).convert("L")
        aspect_ratio = img.height / img.width if img.width else 1
        height = max(1, int(width * aspect_ratio * 0.55))
        img = img.resize((width, height))
        pixels = img.getdata()
        lines = []
        for i in range(0, len(pixels), width):
            line = "".join(chars[p * (len(chars) - 1) // 255] for p in pixels[i : i + width])
            lines.append(line)
        print("\n".join(lines))
    except Exception:
        return
