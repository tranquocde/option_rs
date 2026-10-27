#!/usr/bin/env python3
"""Backtest the WRITER of a principal-protected note on one stock, delta-hedged daily.

The note (sold to a client, non-transferable, held to maturity):
    client pays N at t0 and receives at maturity
        N * protection + N * participation * min(max(R, 0), cap),     R = S_T / S_0 - 1

How the writer prices it (per note, using only data up to t0's close):
    bond leg   = N * protection * e^(-rT)                       cash that grows back to the guarantee
    option leg = short `participation` call spreads on N / S0 shares,
                 strikes K1 = S0, K2 = S0 * (1 + cap)           Black-Scholes at the pricing vol
    edge       = N - bond leg - option leg                      writer's margin, locked at t0
    The pricing vol is trailing close-to-close realized vol (+ optional markup); there is no
    listed implied vol to use. Give two of {participation, cap, margin} and the third is solved.

How the writer runs it:
    buys Black-Scholes delta (at the pricing vol) in shares at every daily close, cash earns r,
    pays commission + sell tax + slippage (half the bid-ask spread) on every hedge trade,
    liquidates the hedge and pays the client at maturity.

Execution constraints (on by default, each note treated as its own sub-account):
    limit lock : on a limit-up close no hedge BUY fills, on a limit-down close no hedge SELL fills;
                 the position stays as it is until a later close allows the trade.
    T+2        : shares bought at a close can only be sold from the second close after it.
    Shares that cannot be sold at maturity are sold at the first later close that allows it;
    the price difference is part of hedge P&L ("carry").

    writer P&L at maturity = edge * e^(rT) + hedge P&L - costs      (costs include slippage)
    hedge P&L              = V0 * e^(rT) - option payoff + sum_t h_t * (S_t+1 - e^(r dt) * S_t)
                             (positive when realized vol < pricing vol; this is the risk)

Ledger check: P&L is computed twice, from the running cash account and from the gains
decomposition above, and the two must agree to 1e-6 VND on every note.

Prices are Vietcap's adjusted daily closes (dividends/splits folded in), so q = 0.
Usage:
    python3 note_backtest.py                                   # solve participation, no cap
    python3 note_backtest.py --participation 0.5               # solve the cap
    python3 note_backtest.py --participation 0.5 --cap 0.2     # fixed terms, edge = residual
    python3 note_backtest.py --show-note 2025-03-03            # daily ledger of one note
"""
import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from scipy.optimize import brentq

HERE = Path(__file__).resolve().parent
DATA_DIR = HERE / "data"
DAYS = 252          # trading days per year (T, vol and rate accrual all use this clock)
LIMIT_BANDS = (("2013-01-15", 0.07),)   # HOSE daily price band: 5% before (from 2010 on), 7% from this date
VCI_URL = "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36",
    "Referer": "https://trading.vietcap.com.vn/",
    "Origin": "https://trading.vietcap.com.vn",
}


# ---------------------------------------------------------------- data

def load_daily(symbol, refresh=False):
    """Full daily history (adjusted, VND), cached in data/<symbol>_1D.csv."""
    path = DATA_DIR / f"{symbol}_1D.csv"
    if path.exists() and not refresh:
        return pd.read_csv(path, parse_dates=["time"])
    to = int((pd.Timestamp.now(tz="Asia/Ho_Chi_Minh") + pd.Timedelta(days=1)).timestamp())
    payload = {"timeFrame": "ONE_DAY", "symbols": [symbol], "to": to, "countBack": 10000}
    r = requests.post(VCI_URL, json=payload, headers=HEADERS, timeout=60)
    r.raise_for_status()
    item = r.json()[0]
    df = pd.DataFrame({
        "time": pd.to_datetime(pd.Series(item["t"], dtype="int64"), unit="s").dt.normalize(),
        "open": item["o"], "high": item["h"], "low": item["l"], "close": item["c"], "volume": item["v"],
    })
    DATA_DIR.mkdir(exist_ok=True)
    df.to_csv(path, index=False)
    return df


# ---------------------------------------------------------------- Black-Scholes (q = 0)

def ncdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def call(S, K, T, r, vol):
    """(value, delta) of a European call."""
    if T <= 0:
        return max(S - K, 0.0), float(S > K)
    sd = vol * math.sqrt(T)
    d1 = (math.log(S / K) + (r + 0.5 * vol * vol) * T) / sd
    return S * ncdf(d1) - K * math.exp(-r * T) * ncdf(d1 - sd), ncdf(d1)


def spread(S, S0, cap, T, r, vol):
    """(value, delta) per share of C(K1=S0) - C(K2=S0*(1+cap)); cap=None means a plain call."""
    v1, d1 = call(S, S0, T, r, vol)
    if cap is None:
        return v1, d1
    v2, d2 = call(S, S0 * (1 + cap), T, r, vol)
    return v1 - v2, d1 - d2


# ---------------------------------------------------------------- note terms

def solve_terms(S0, T, r, vol, args):
    """Return (participation, cap) for a note struck today. Raises if the budget is negative."""
    N, prot = args.notional_vnd, args.protection
    budget = N - N * prot * math.exp(-r * T) - N * args.margin
    if args.participation is not None and args.cap is not None:
        return args.participation, args.cap
    if budget <= 0:
        raise ValueError(f"no option budget: protection {prot:.0%} + margin {args.margin:.2%} "
                         f"exceed 1 - e^(-rT) headroom")
    unit = N / S0                                   # shares per 100% participation
    if args.participation is None:                  # solve participation for given (or no) cap
        return budget / (unit * spread(S0, S0, args.cap, T, r, vol)[0]), args.cap
    p = args.participation                          # solve cap for given participation
    if p * unit * spread(S0, S0, None, T, r, vol)[0] <= budget:
        return p, None                              # uncapped already fits
    cap = brentq(lambda c: p * unit * spread(S0, S0, c, T, r, vol)[0] - budget, 1e-6, 10.0)
    return p, cap


# ---------------------------------------------------------------- one note

def trade_cost(trade, price, args):
    """(total cost, slippage part) of trading `trade` shares at `price` (works on arrays too).

    commission on both sides + sell tax on sales + slippage: half the bid-ask spread, both sides.
    """
    value = np.abs(trade) * price
    slip = value * args.slippage_bps / 1e4
    return value * args.tc_bps / 1e4 + np.maximum(-trade, 0.0) * price * args.sell_tax_bps / 1e4 + slip, slip


def limit_flags(df, tol=0.003):
    """+1 on a limit-up close, -1 on a limit-down close, 0 otherwise.

    A limit close = the day's move is within `tol` of the band AND the close is the day's extreme
    (close == high for limit-up, close == low for limit-down). No order book is available, so a close
    at the limit is treated as fully locked (conservative).
    """
    band = np.full(len(df), 0.05)
    for start, b in LIMIT_BANDS:
        band[(df["time"] >= pd.Timestamp(start)).to_numpy()] = b
    c, h, lo = (df[col].to_numpy(float) for col in ("close", "high", "low"))
    ret = df["close"].pct_change().to_numpy()
    up = (ret >= band - tol) & (c >= h * (1 - 1e-9))
    dn = (ret <= -band + tol) & (c <= lo * (1 + 1e-9))
    return np.where(up, 1, np.where(dn, -1, 0))


def executable(want, shares, bought_prev, limit, args):
    """(part of the wanted hedge trade that fills today, reason the rest does not)."""
    if limit == 1 and want > 0:
        return 0.0, "limit-up"
    if limit == -1 and want < 0:
        return 0.0, "limit-down"
    if args.t2 and want < 0:
        sellable = max(shares - bought_prev, 0.0)   # shares bought at the previous close are not settled
        if -want > sellable + 1e-9:
            return -sellable, "T+2"
    return want, ""


def run_note(df, i0, args, ledger=False):
    S = df["close"].to_numpy(float)
    lim = df["limit"].to_numpy() if args.limit_lock else np.zeros(len(S), dtype=int)
    n = args.maturity_days
    N, prot, r = args.notional_vnd, args.protection, args.rate
    dt, T = 1.0 / DAYS, n / DAYS
    g = math.exp(r * dt)

    S0 = S[i0]
    vol = df["trail_vol"].iat[i0] + args.vol_markup
    p, cap = solve_terms(S0, T, r, vol, args)
    units = N * p / S0                              # call spreads sold (share-equivalents)
    V0 = units * spread(S0, S0, cap, T, r, vol)[0]
    bond0 = N * prot * math.exp(-r * T)
    edge0 = N - bond0 - V0

    cash, shares, cost_fv, slip_fv, gains_fv, turnover, rows = float(N), 0.0, 0.0, 0.0, 0.0, 0.0, []
    cash_x = float(N)                               # cash ex transaction costs, for the book view
    path_sh, path_mtm = np.zeros(n + 1), np.zeros(n + 1)
    bought_prev, n_limit, n_t2 = 0.0, 0, 0
    for k in range(n):                              # hedge at closes t0 .. t_{n-1}
        i = i0 + k
        val, dlt = spread(S[i], S0, cap, (n - k) * dt, r, vol)
        target = units * dlt if args.hedge else 0.0
        if args.lot:
            target = round(target / args.lot) * args.lot
        want = target - shares
        trade, blocked = executable(want, shares, bought_prev, lim[i], args)
        n_limit += blocked.startswith("limit")
        n_t2 += blocked == "T+2"
        cost, slip = trade_cost(trade, S[i], args)
        cash -= trade * S[i] + cost
        cash_x -= trade * S[i]
        cost_fv += cost * g ** (n - k)
        slip_fv += slip * g ** (n - k)
        turnover += abs(trade) * S[i]
        shares += trade
        bought_prev = max(trade, 0.0)
        path_sh[k] = shares                         # mark: hedge + cash - option at pricing vol - bond PV
        path_mtm[k] = cash_x + shares * S[i] - units * val - N * prot * math.exp(-r * (n - k) * dt)
        cash_x *= g
        if ledger:
            rows.append(dict(date=df["time"].iat[i].date(), close=S[i], days_left=n - k,
                             delta=round(dlt, 4), want=round(want, 1), trade=round(trade, 1), blocked=blocked,
                             shares=round(shares, 1), cost=cost, cash=cash, option_value=units * val,
                             mtm_pnl=cash + shares * S[i] - units * val - N * prot * math.exp(-r * (n - k) * dt)))
        gains_fv += shares * (S[i + 1] - g * S[i]) * g ** (n - k - 1)
        cash *= g

    iT = i0 + n
    ST = S[iT]
    sell, blocked_T = executable(-shares, shares, bought_prev, lim[iT], args)
    n_limit += blocked_T.startswith("limit")
    n_t2 += blocked_T == "T+2"
    residual = shares + sell                        # shares that cannot be sold at the maturity close
    j = iT
    if residual > 1e-12:                            # first later close that allows the sale (T+2 is met by then)
        j = next((m for m in range(iT + 1, len(S)) if lim[m] != -1), iT)
    exit_px = S[j]
    cost1, slip1 = trade_cost(sell, ST, args)
    cost2, slip2 = trade_cost(-residual, exit_px, args)
    cash += -sell * ST + residual * exit_px - cost1 - cost2
    cash_x += -sell * ST + residual * exit_px
    cost_fv += cost1 + cost2
    slip_fv += slip1 + slip2
    turnover += -sell * ST + residual * exit_px
    carry = residual * (exit_px - ST)               # price move on shares held past maturity
    R = ST / S0 - 1
    opt_pay = N * p * min(max(R, 0.0), cap if cap is not None else math.inf)
    client = N * prot + opt_pay
    cash -= client
    cash_x -= client
    path_sh[n] = residual                           # book view: residual sold after maturity (P&L booked at maturity)
    path_mtm[n] = cash_x

    hedge_pnl = V0 * math.exp(r * T) - opt_pay + gains_fv + carry
    pnl = edge0 * math.exp(r * T) + hedge_pnl - cost_fv
    if abs(pnl - cash) > 1e-6:
        raise AssertionError(f"ledger mismatch on {df['time'].iat[i0].date()}: cash {cash} vs gains {pnl}")
    if ledger:
        rows.append(dict(date=df["time"].iat[iT].date(), close=ST, days_left=0, delta=None,
                         want=round(-shares, 1), trade=round(sell, 1), blocked=blocked_T, shares=round(residual, 1),
                         cost=cost1, cash=cash if residual <= 1e-12 else np.nan, option_value=opt_pay,
                         mtm_pnl=cash if residual <= 1e-12 else np.nan))
        if residual > 1e-12:
            rows.append(dict(date=df["time"].iat[j].date(), close=exit_px, days_left=iT - j, delta=None,
                             want=round(-residual, 1), trade=round(-residual, 1), blocked="carried", shares=0.0,
                             cost=cost2, cash=cash, option_value=0.0, mtm_pnl=cash))

    lr = np.diff(np.log(S[i0:iT + 1]))
    M = 1e6
    out = dict(
        start=df["time"].iat[i0].date(), end=df["time"].iat[iT].date(), S0=S0, ST=ST, R=R,
        pricing_vol=vol, realized_vol=lr.std(ddof=1) * math.sqrt(DAYS),
        participation=p, cap=cap if cap is not None else np.nan,
        option_value=V0 / M, edge=edge0 * math.exp(r * T) / M,
        client_payoff=client / M, option_payoff=opt_pay / M,
        hedge_pnl=hedge_pnl / M, costs=cost_fv / M, slippage=slip_fv / M, pnl=pnl / M,
        unhedged_pnl=(N * math.exp(r * T) - client) / M, turnover=turnover / M,
        blocked_limit=n_limit, blocked_t2=n_t2, carried=residual > 1e-12, carry_pnl=carry / M,
    )
    out["client_return"] = client / N - 1
    return out, pd.DataFrame(rows), (np.arange(i0, iT + 1), path_sh, path_mtm)


# ---------------------------------------------------------------- the writer's book

def build_book(df, paths, notes, args):
    """Daily book of all live notes: summed marks, hedge NETTED across notes, costs on net trades."""
    S = df["close"].to_numpy(float)
    d_mtm, shares, live = np.zeros(len(df)), np.zeros(len(df)), np.zeros(len(df))
    for idx, sh, mtm in paths:
        d_mtm[idx[0]] += mtm[0]                     # edge booked at sale (locked at pricing vol)
        d_mtm[idx[1:]] += np.diff(mtm)
        shares[idx] += sh
        live[idx[:-1]] += 1
    first, last = paths[0][0][0], paths[-1][0][-1]
    if abs(d_mtm.sum() - 1e6 * (notes["pnl"] + notes["costs"]).sum()) > 1e-3:
        raise AssertionError("book P&L (ex costs) does not reconcile with the sum of note P&Ls")
    trade = np.diff(shares, prepend=0.0)
    cost, slip = trade_cost(trade, S, args)
    sl = slice(first, last + 1)
    M = 1e6
    book = pd.DataFrame({"time": df["time"].iloc[sl].to_numpy(), "close": S[sl], "live_notes": live[sl],
                         "notional_out": live[sl] * args.notional, "hedge_shares": shares[sl],
                         "hedge_value": shares[sl] * S[sl] / M, "net_trade": trade[sl],
                         "pnl_ex_cost": d_mtm[sl] / M, "cost": cost[sl] / M, "slippage": slip[sl] / M})
    book["pnl"] = book["pnl_ex_cost"] - book["cost"]
    book["cum_pnl"] = book["pnl"].cumsum()
    return book


# ---------------------------------------------------------------- reporting

def stats(x):
    x = np.asarray(x, float)
    return dict(mean=x.mean(), median=np.median(x), std=x.std(ddof=1), win=(x > 0).mean(),
                p5=np.percentile(x, 5), worst=x.min(), best=x.max())


def tstat(x):
    x = np.asarray(x, float)
    return x.mean() / (x.std(ddof=1) / math.sqrt(len(x))) if len(x) > 1 else np.nan


def report(notes, args):
    k = max(1, math.ceil(args.maturity_days / args.step))
    indep = notes.iloc[::k]                         # non-overlapping subset for the t-stat
    cap_txt = "none" if notes["cap"].isna().all() else f"{notes['cap'].median():.1%} (median)"
    print(f"\n{args.symbol}: {len(notes)} notes {notes['start'].iat[0]} -> {notes['start'].iat[-1]}, "
          f"new note every {args.step}d, maturity {args.maturity_days}d, notional {args.notional:g}M VND")
    print(f"terms: protection {args.protection:.0%}, participation {notes['participation'].median():.1%} (median), "
          f"cap {cap_txt}, margin {args.margin:.2%}, r {args.rate:.1%}, hedge {'on' if args.hedge else 'OFF'}, "
          f"costs {args.tc_bps:g}bps + {args.sell_tax_bps:g}bps sell tax + {args.slippage_bps:g}bps slippage, "
          f"lot {args.lot or 'fractional'}, limit lock {'on' if args.limit_lock else 'off'}, "
          f"T+2 {'on' if args.t2 else 'off'}")
    print(f"pricing vol median {notes['pricing_vol'].median():.1%}, realized over note life median "
          f"{notes['realized_vol'].median():.1%}")

    print(f"\nwriter P&L per note (M VND per {args.notional:g}M notional)")
    print(f"{'':>14}{'mean':>8}{'median':>8}{'std':>8}{'win%':>7}{'5%ile':>8}{'worst':>8}{'best':>8}{'t(indep)':>10}")
    for label, col in (("delta-hedged", "pnl"), ("unhedged", "unhedged_pnl")):
        s = stats(notes[col])
        print(f"{label:>14}{s['mean']:8.2f}{s['median']:8.2f}{s['std']:8.2f}{s['win']:7.0%}"
              f"{s['p5']:8.2f}{s['worst']:8.2f}{s['best']:8.2f}{tstat(indep[col]):10.2f}")
    print(f"  (t-stat on {len(indep)} non-overlapping notes)")

    print(f"\nhedged P&L decomposition (mean): edge {notes['edge'].mean():+.2f}  "
          f"hedge {notes['hedge_pnl'].mean():+.2f}  costs {-notes['costs'].mean():+.2f} "
          f"(of which slippage {-notes['slippage'].mean():+.2f})  "
          f"= {notes['pnl'].mean():+.2f}   | turnover {notes['turnover'].mean():.0f}M per note")
    hit = notes["blocked_limit"] > 0
    print(f"execution constraints: limit lock blocked {notes['blocked_limit'].sum()} hedge trades on {hit.sum()} notes "
          f"(their mean P&L {notes.loc[hit, 'pnl'].mean() if hit.any() else float('nan'):+.2f}); "
          f"T+2 cut {notes['blocked_t2'].sum()} sells; {notes['carried'].sum()} notes sold shares after maturity "
          f"(carry P&L {notes['carry_pnl'].sum():+.2f}M total)")

    gap = notes["realized_vol"] - notes["pricing_vol"]
    bins = pd.cut(gap, [-np.inf, -0.10, -0.05, 0, 0.05, 0.10, np.inf])
    tab = notes.groupby(bins, observed=True).agg(n=("pnl", "size"), hedge_pnl=("hedge_pnl", "mean"),
                                                 pnl=("pnl", "mean"), win=("pnl", lambda x: (x > 0).mean()))
    print("\nby realized - pricing vol (the bet the writer is short):")
    print(tab.to_string(float_format=lambda v: f"{v:.2f}"))

    yr = notes.groupby(pd.to_datetime(notes["start"]).dt.year).agg(
        n=("pnl", "size"), part=("participation", "median"), pricing_vol=("pricing_vol", "median"),
        realized_vol=("realized_vol", "median"), stock_R=("R", "mean"), pnl=("pnl", "mean"),
        win=("pnl", lambda x: (x > 0).mean()), worst=("pnl", "min"), unhedged=("unhedged_pnl", "mean"))
    print("\nby start year:")
    print(yr.to_string(float_format=lambda v: f"{v:.2f}"))


def report_client(notes, args):
    """Each note = one client, judged only by what they get back vs. what else they could have done."""
    T = args.maturity_days / DAYS
    dep = math.exp(args.rate * T) - 1
    c, R = notes["client_return"], notes["R"]
    floor = args.protection - 1
    print(f"\n{'=' * 30} CLIENT VIEW: {len(notes)} clients, {args.notional:g}M each, "
          f"{args.maturity_days}d ({T * 12:.1f} months)")
    print(f"alternative: bank deposit at {args.rate:.1%} -> {dep:+.2%} over the term; or buy {args.symbol} outright")
    print(f"client return  mean {c.mean():+.2%}  median {c.median():+.2%}  75%ile {c.quantile(.75):+.2%}  "
          f"90%ile {c.quantile(.9):+.2%}  best {c.max():+.2%}  (annualized mean {(1 + c.mean()) ** (1 / T) - 1:+.1%})")
    print(f"  got only the protected amount ({args.protection:.0%}): {(c <= floor + 1e-12).mean():5.0%}")
    print(f"  beat the bank deposit:                   {(c > dep).mean():5.0%}")
    print(f"  beat holding {args.symbol} (stock return {R.mean():+.2%} mean, worst {R.min():+.1%}): "
          f"{(c > R).mean():5.0%}")
    print(f"  price paid for the protection: fair value at sale = {args.notional:g}M - writer edge "
          f"({notes['edge'].mean():.2f}M avg)")
    yr = notes.groupby(pd.to_datetime(notes["start"]).dt.year).agg(
        clients=("client_return", "size"), participation=("participation", "median"),
        client_mean=("client_return", "mean"), only_principal=("client_return", lambda x: (x <= floor + 1e-12).mean()),
        beat_deposit=("client_return", lambda x: (x > dep).mean()), stock_mean=("R", "mean"), stock_worst=("R", "min"))
    print("\nclients by start year:")
    print(yr.to_string(float_format=lambda v: f"{v:+.2%}" if abs(v) < 5 else f"{v:.0f}"))


def report_book(book, notes, args):
    """The writer's whole book: every live note marked daily, hedges netted, costs on net trades."""
    daily = book.set_index("time")["pnl"]
    cum = daily.cumsum()
    dd = cum - cum.cummax()
    trough = dd.idxmin()
    peak = cum.loc[:trough].idxmax()
    years = len(book) / DAYS
    monthly = daily.resample("ME").sum()
    print(f"\n{'=' * 30} WRITER BOOK VIEW: {book['time'].iat[0].date()} -> {book['time'].iat[-1].date()} "
          f"({years:.1f} years), a new {args.notional:g}M client every {args.step} trading days")
    print(f"live notes avg {book['live_notes'].mean():.1f} (max {book['live_notes'].max():.0f}) -> notional outstanding "
          f"avg {book['notional_out'].mean():,.0f}M; hedge inventory avg {book['hedge_value'].mean():,.0f}M "
          f"(max {book['hedge_value'].max():,.0f}M)")
    print(f"total P&L {cum.iat[-1]:+,.1f}M = {cum.iat[-1] / years:+.1f}M/yr = "
          f"{cum.iat[-1] / years / book['notional_out'].mean():+.2%}/yr on avg notional outstanding")
    print(f"daily P&L: annualized vol {daily.std() * math.sqrt(DAYS):.2f}M, Sharpe {daily.mean() / daily.std() * math.sqrt(DAYS):.2f}, "
          f"worst day {daily.min():+.2f}M ({daily.idxmin().date()}), worst 21d {daily.rolling(21).sum().min():+.2f}M")
    print(f"max drawdown {dd.min():+.2f}M ({peak.date()} -> {trough.date()}); "
          f"positive months {(monthly > 0).mean():.0%}, worst month {monthly.min():+.2f}M ({monthly.idxmin():%Y-%m})")
    per_note = notes["costs"].sum()
    print(f"costs: hedging each note separately {per_note:,.1f}M vs netted book {book['cost'].sum():,.1f}M "
          f"(saves {1 - book['cost'].sum() / per_note:.0%}); slippage {book['slippage'].sum():,.1f}M of the netted total")
    yr = book.groupby(book["time"].dt.year).agg(
        notional_out=("notional_out", "mean"), pnl=("pnl", "sum"), cost=("cost", "sum"),
        worst_day=("pnl", "min"), hedge_max=("hedge_value", "max"))
    yr["pnl_%_out"] = yr["pnl"] / yr["notional_out"] * 100
    print("\nbook by calendar year (M VND; pnl_%_out = P&L / avg notional outstanding):")
    print(yr.to_string(float_format=lambda v: f"{v:,.2f}"))


# ---------------------------------------------------------------- API (CLI and notebook)

def build_parser():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="FPT")
    ap.add_argument("--start", default="2010-01-01", help="first note start date")
    ap.add_argument("--end", default=None, help="last note start date (default: latest that has matured)")
    ap.add_argument("--notional", type=float, default=100.0, help="M VND per note")
    ap.add_argument("--maturity-days", type=int, default=63, help="trading days (63 ~ 3 months)")
    ap.add_argument("--protection", type=float, default=1.0, help="fraction of notional guaranteed")
    ap.add_argument("--participation", type=float, default=None, help="share of upside paid (solved if omitted)")
    ap.add_argument("--cap", type=float, default=None, help="max stock return paid on, e.g. 0.2 (none if omitted)")
    ap.add_argument("--margin", type=float, default=0.005, help="writer edge as fraction of notional when solving terms")
    ap.add_argument("--rate", type=float, default=0.05, help="annual cc rate: bond, cash and pricing")
    ap.add_argument("--vol-window", type=int, default=60, help="trailing days for pricing vol")
    ap.add_argument("--vol-markup", type=float, default=0.0, help="added to trailing vol, e.g. 0.05 = +5 vol pts")
    ap.add_argument("--tc-bps", type=float, default=10.0, help="commission per side, bps of traded value")
    ap.add_argument("--sell-tax-bps", type=float, default=10.0, help="tax on sales, bps")
    ap.add_argument("--slippage-bps", type=float, default=9.0,
                    help="half the bid-ask spread paid on every hedge trade, bps (FPT ~57k: 100 VND tick / 2)")
    ap.add_argument("--lot", type=int, default=0, help="round hedge to lots of this many shares (0 = fractional)")
    ap.add_argument("--step", type=int, default=5, help="trading days between new notes")
    ap.add_argument("--no-hedge", dest="hedge", action="store_false", help="hold no shares (bond-only writer)")
    ap.add_argument("--no-limit-lock", dest="limit_lock", action="store_false",
                    help="let hedge trades fill on limit-up/limit-down closes")
    ap.add_argument("--no-t2", dest="t2", action="store_false", help="allow selling shares bought at the previous close")
    ap.add_argument("--show-note", default=None, help="print the daily ledger of the note starting on/after this date")
    ap.add_argument("--refresh", action="store_true", help="re-download price history")
    ap.add_argument("--out", default=None, help="per-note CSV (default notes_<symbol>.csv)")
    return ap


def make_args(**overrides):
    """CLI defaults with keyword overrides (underscored names), e.g. make_args(protection=0.98)."""
    args = build_parser().parse_args([])
    for k, v in overrides.items():
        if not hasattr(args, k):
            raise TypeError(f"unknown parameter {k!r}")
        setattr(args, k, v)
    args.notional_vnd = args.notional * 1e6
    return args


def prepare(df, args):
    """Add the trailing pricing vol and return (df, index positions where a note may start)."""
    df = df.copy()
    df["trail_vol"] = np.log(df["close"]).diff().rolling(args.vol_window).std() * math.sqrt(DAYS)
    df["limit"] = limit_flags(df)
    last_start = len(df) - 1 - args.maturity_days
    eligible = df.index[(df["time"] >= pd.Timestamp(args.start)) & df["trail_vol"].notna() & (df.index <= last_start)]
    if args.end:
        eligible = eligible[df.loc[eligible, "time"] <= pd.Timestamp(args.end)]
    return df, eligible


def simulate(df, args):
    """Run every note in the population. Returns (notes, book)."""
    df, eligible = prepare(df, args)
    results = [run_note(df, i, args) for i in eligible[::args.step]]
    notes = pd.DataFrame([res[0] for res in results])
    return notes, build_book(df, [res[2] for res in results], notes, args)


def note_ledger(df, args, date):
    """(note summary, daily ledger) of the note starting on/after `date`."""
    df, eligible = prepare(df, args)
    i0 = eligible[df.loc[eligible, "time"] >= pd.Timestamp(date)][0]
    note, led, _ = run_note(df, i0, args, ledger=True)
    led[["cost", "cash", "option_value", "mtm_pnl"]] /= 1e6
    return note, led


# ---------------------------------------------------------------- main

def main():
    args = build_parser().parse_args()
    args.notional_vnd = args.notional * 1e6
    df = load_daily(args.symbol, args.refresh)

    if args.show_note:
        note, led = note_ledger(df, args, args.show_note)
        cap_txt = "none" if np.isnan(note["cap"]) else f"{note['cap']:.2%}"
        print(f"note {note['start']} -> {note['end']}: S0 {note['S0']:,.0f}, pricing vol {note['pricing_vol']:.1%}, "
              f"participation {note['participation']:.2%}, cap {cap_txt}, option sold {note['option_value']:.3f}M, "
              f"edge {note['edge']:.3f}M")
        pd.set_option("display.width", 200)
        print(led.to_string(index=False, float_format=lambda v: f"{v:,.3f}"))
        print(f"\nstock {note['R']:+.2%}, realized vol {note['realized_vol']:.1%}; client gets {note['client_payoff']:.3f}M")
        print(f"writer P&L {note['pnl']:+.3f}M = edge {note['edge']:+.3f} + hedge {note['hedge_pnl']:+.3f} "
              f"- costs {note['costs']:.3f}   (unhedged would be {note['unhedged_pnl']:+.3f}M)")
        return

    notes, book = simulate(df, args)
    out = args.out or f"notes_{args.symbol}.csv"
    notes.to_csv(HERE / out, index=False)
    book.to_csv(HERE / f"book_{args.symbol}.csv", index=False)
    report(notes, args)
    report_client(notes, args)
    report_book(book, notes, args)
    print(f"\nper-note results -> {out}, daily book -> book_{args.symbol}.csv  "
          f"(ledger identity checked on all {len(notes)} notes; book reconciles to their sum)")


if __name__ == "__main__":
    main()
