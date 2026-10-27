# Kiến thức cốt lõi về option pricing

Tài liệu tham khảo để dùng khi làm việc: định nghĩa, các quy tắc no-arbitrage mà mọi model
phải tuân theo, binomial model và Black–Scholes, Greeks, implied volatility và realized
volatility, cùng code Python chạy được. Các mục cuối nối lý thuyết với dữ liệu VN30 trong thư
mục này (`vn30_ohlcv.ipynb`) và với chứng quyền có bảo đảm (CW) ở Việt Nam.

Ký hiệu dùng xuyên suốt:

| ký hiệu | ý nghĩa |
|---|---|
| `S` | spot của underlying |
| `K` | strike |
| `T` | time to expiry, **tính bằng năm** |
| `r` | risk-free rate, continuous compounding |
| `q` | continuous dividend yield |
| `σ` | volatility (vol): annualized standard deviation của log return |
| `N(·)`, `φ(·)` | CDF và PDF của phân phối chuẩn tắc |

---

## 1. Hợp đồng và payoff

- **Call**: quyền (không phải nghĩa vụ) **mua** ở giá `K`. Payoff khi đáo hạn: `max(S_T − K, 0)`.
- **Put**: quyền **bán** ở giá `K`. Payoff khi đáo hạn: `max(K − S_T, 0)`.
- **European**: chỉ exercise được vào ngày đáo hạn. **American**: exercise được bất cứ lúc nào cho đến ngày đáo hạn.
- Người mua trả trước **premium**; writer thu premium này và gánh nghĩa vụ.

**Moneyness** (cho call; với put thì đảo ngược):

| moneyness | điều kiện | ý nghĩa |
|---|---|---|
| ITM (in the money) | `S > K` | có giá trị dương nếu exercise ngay |
| ATM (at the money) | `S ≈ K` | time value lớn nhất, gamma cao nhất |
| OTM (out of the money) | `S < K` | vô giá trị nếu exercise ngay |

**Premium = intrinsic value + time value.**
Intrinsic value = giá trị nếu exercise ngay (`max(S − K, 0)` với call).
Time value = toàn bộ phần còn lại: khả năng option sẽ kết thúc deep ITM hơn.
Time value lớn nhất khi ATM và giảm dần về 0 khi đáo hạn.

Ví dụ: call với `S = 100`, `K = 95` đang giao dịch ở giá 8,20.
Intrinsic value = 5,00, time value = 3,20.

---

## 2. Các quy tắc no-arbitrage, model-free

Các quy tắc này đúng với **mọi** pricing model. Model price nào vi phạm chúng là sai.

**Put–call parity** (European, cùng `K` và `T`):

```
C − P = S·e^(−qT) − K·e^(−rT)
```

Lý do: long một call cộng short một put cho payoff `S_T − K` trong mọi trạng thái, đúng bằng
một forward. Hai portfolio có payoff giống hệt nhau thì hôm nay phải có giá như nhau.

Dùng để: đổi giá call thành giá put, suy ngược ra implied forward hoặc implied dividend, và
kiểm tra độ hợp lý của báo giá (vi phạm parity lớn hơn chi phí giao dịch là một cơ hội
arbitrage).

**Price bounds** (European):

```
max(S·e^(−qT) − K·e^(−rT), 0)  ≤  C  ≤  S·e^(−qT)
max(K·e^(−rT) − S·e^(−qT), 0)  ≤  P  ≤  K·e^(−rT)
```

**Hình dạng theo strike** (cùng ngày đáo hạn):
- Giá call **giảm** theo `K`; giá put **tăng** theo `K`.
- Giá là hàm **convex** theo `K`. Butterfly `C(K−h) − 2C(K) + C(K+h)` phải ≥ 0.
  (Breeden–Litzenberger: `∂²C/∂K²·e^(rT)` là risk-neutral density của `S_T`.)

**American option:**
- Không bao giờ early exercise một American call trên cổ phiếu không trả cổ tức:
  nó có giá trị ít nhất `S − K·e^(−rT) > S − K`. Vì vậy American call = European call khi `q = 0`.
- American put có thể đáng early exercise (deep ITM, `r` cao), nên
  American put ≥ European put.

---

## 3. Binomial model: định giá bằng replication

**Một bước.** Cổ phiếu đi từ `S` lên `S·u` hoặc xuống `S·d`. Nắm giữ `Δ` cổ phiếu và `B` tiền mặt
sao cho portfolio khớp với option ở cả hai trạng thái:

```
Δ = (V_u − V_d) / (S·u − S·d)
```

Option phải có giá bằng portfolio này. Biến đổi lại ta được công thức định giá
trông giống một kỳ vọng:

```
V = e^(−rΔt) · [ p·V_u + (1 − p)·V_d ],     p = (e^((r−q)Δt) − d) / (u − d)
```

`p` là **risk-neutral probability**. Đó không phải xác suất thật
của một bước tăng giá. Đó là xác suất mà dưới nó cổ phiếu sinh lời đúng bằng risk-free rate.
Drift ngoài thực tế **không xuất hiện**: bạn có thể hedge để loại bỏ nó, nên
nó không thể ảnh hưởng tới giá. Đây là ý tưởng trung tâm của toàn bộ derivatives pricing.

**Nhiều bước (Cox–Ross–Rubinstein).** Chia `T` thành `n` bước với `Δt = T/n`,
`u = e^(σ√Δt)`, `d = 1/u`. Điền payoff ở các terminal node và lùi ngược về bằng
công thức trên. Với **American option**, tại mỗi node lấy
`max(continuation value, exercise value)`. Khi `n → ∞` giá European hội tụ về
Black–Scholes.

Ví dụ một bước: `S = 100`, `u = 1.2`, `d = 0.8`, `r = 0`, call với `K = 100`.
`V_u = 20`, `V_d = 0`. `p = (1 − 0.8)/(1.2 − 0.8) = 0.5`, nên `V = 0.5·20 = 10`.
Hedge: `Δ = 20/40 = 0.5` cổ phiếu. Kiểm tra: mua 0,5 cổ phiếu với giá 50 và vay 40.
Ở trạng thái tăng, số cổ phiếu trị giá 60, trừ 40 nợ = 20 ✓. Ở trạng thái giảm
40 − 40 = 0 ✓. Chi phí ròng 50 − 40 = 10 ✓.

---

## 4. Black–Scholes(–Merton)

**Giả định:** cổ phiếu theo geometric Brownian motion với `σ` không đổi;
`r` và `q` không đổi; giao dịch liên tục và frictionless; không có arbitrage.

**PDE.** Một option được delta-hedge liên tục
thì không rủi ro, nên nó phải sinh lời đúng bằng `r`:

```
∂V/∂t + ½·σ²·S²·∂²V/∂S² + (r − q)·S·∂V/∂S − r·V = 0
```

**Closed form** cho European option:

```
d1 = [ ln(S/K) + (r − q + σ²/2)·T ] / (σ·√T)
d2 = d1 − σ·√T

C = S·e^(−qT)·N(d1) − K·e^(−rT)·N(d2)
P = K·e^(−rT)·N(−d2) − S·e^(−qT)·N(−d1)
```

**Cách đọc công thức:**
- `N(d2)` = risk-neutral probability để call kết thúc ITM.
- `K·e^(−rT)·N(d2)` = present value của việc trả strike, có trọng số theo xác suất đó.
- `S·e^(−qT)·N(d1)` = present value của việc nhận cổ phiếu khi call kết thúc ITM.
  `N(d1)` là xác suất kết thúc ITM dưới measure lấy cổ phiếu làm numeraire.
  Nó cũng chính là delta của call (nhân với `e^(−qT)`).
- Đầu vào duy nhất không quan sát trực tiếp được là **`σ`**. Toàn bộ việc option trading
  quy về một tham số này.

**Quy tắc kinh nghiệm:**
- Xấp xỉ ATM: `C ≈ P ≈ 0.4·S·σ·√T` (khi `r, q ≈ 0`).
  Ví dụ: `S = 100`, `σ = 30%`, `T = 1 tháng` → `0.4·100·0.3·√(1/12)` ≈ 3,46.
- Daily vol: `σ_daily ≈ σ_annual / √252`. Với vol 30% thì khoảng 1,9% mỗi ngày.

---

## 5. Greeks

Độ nhạy của giá option. Công thức cho Black–Scholes có dividend yield `q`.

| Greek | đo lường | call | put |
|---|---|---|---|
| **Delta** Δ | `∂V/∂S` | `e^(−qT)·N(d1)` | `−e^(−qT)·N(−d1)` |
| **Gamma** Γ | `∂²V/∂S²` | `e^(−qT)·φ(d1) / (S·σ·√T)` | như call |
| **Vega** ν | `∂V/∂σ` | `S·e^(−qT)·φ(d1)·√T` | như call |
| **Theta** Θ | `∂V/∂t` | `−S·e^(−qT)·φ(d1)·σ/(2√T) − r·K·e^(−rT)·N(d2) + q·S·e^(−qT)·N(d1)` | `−S·e^(−qT)·φ(d1)·σ/(2√T) + r·K·e^(−rT)·N(−d2) − q·S·e^(−qT)·N(−d1)` |
| **Rho** ρ | `∂V/∂r` | `K·T·e^(−rT)·N(d2)` | `−K·T·e^(−rT)·N(−d2)` |

Đơn vị: các công thức này cho vega trên 1,00 (= 100 vol point) và theta trên một năm. Các
desk thường báo vega trên 1 vol point (÷100) và theta trên một ngày (÷365 hoặc ÷252).

**Trực giác:**
- **Delta** chạy từ 0 đến 1 với call (−1 đến 0 với put). ATM khoảng 0,5. Delta là
  hedge ratio: số cổ phiếu cần short cho mỗi call đang long để trung hòa vị thế.
- **Gamma** là tốc độ thay đổi của delta. Nó đạt đỉnh ở ATM và nhọn hơn khi gần đáo hạn. Long
  option = long gamma: delta dịch chuyển có lợi cho bạn (bạn long nhiều hơn khi thị trường
  tăng và short nhiều hơn khi thị trường giảm).
- **Vega** lớn nhất ở ATM và với long-dated option.
- **Theta** là tiền thuê bạn trả để có gamma. Long option thì mất giá trị mỗi ngày
  thị trường đứng yên.

**Gamma–theta trade-off** (thế các Greek vào PDE, với `r ≈ q ≈ 0`):

```
Θ ≈ −½·σ²·S²·Γ
```

Long gamma nghĩa là bạn trả theta, short gamma nghĩa là bạn thu theta. Không bên nào được
miễn phí.

---

## 6. Hedge P&L: một vị thế option thực chất đặt cược vào điều gì

Nắm giữ một option và delta-hedge ở implied vol `σ_imp`. Trong một
khoảng thời gian ngắn, P&L xấp xỉ:

```
dP&L ≈ ½·Γ·S²·[ (dS/S)² − σ_imp²·dt ]
```

- Nếu bình phương của move thực tế `(dS/S)²` vượt quá mức mà implied vol đã định giá
  (`σ_imp²·dt`), bên long gamma thắng.
- Cộng dồn suốt vòng đời option: **một long option đã hedge có lãi khi realized vol
  > implied vol**, với trọng số `Γ·S²` (nên các move gần strike và
  gần ngày đáo hạn có ảnh hưởng nhiều nhất).
- Đó là lý do option, một khi đã hedge, là "đặt cược vào vol, không phải vào hướng đi".
  Bạn kiếm tiền khi mua option lúc implied vol rẻ so với
  realized vol diễn ra sau đó.

---

## 7. Implied volatility, smile và term structure

**Implied vol** = giá trị `σ` làm cho Black–Scholes bằng giá thị trường. Khi đó Black–Scholes
được dùng như một quoting convention ("option này giao dịch ở vol 28"), chứ không phải niềm tin
rằng vol không đổi. Giải bằng phương pháp số. Vì vega > 0 nên giá đơn điệu theo
`σ`, do đó Brent's method trên một khoảng như
`[1e-4, 5]` luôn tìm được nghiệm khi giá nằm trong các no-arbitrage bound.

**Smile / skew.** Vẽ implied vol theo strike: với cổ phiếu, đường này không phẳng.
Put OTM giao dịch ở vol cao hơn call OTM (**skew**), do crash risk, nhu cầu
hedge portfolio và return distribution có fat tails. Mô hình constant vol không khớp được điều này.
Các mô hình khớp được: local vol (Dupire), stochastic vol (Heston, SABR), jumps (Merton).

**Term structure.** Implied vol theo tenor. Thường dốc lên khi thị trường
yên ả và đảo ngược sau các cú sốc (short-dated vol tăng vọt mạnh nhất).

---

## 8. Ước lượng realized volatility (historical vol)

Bạn cần một con số vol để định giá, hoặc để so sánh với implied vol. Với các bar
OHLC theo ngày (thứ mà `vn30_ohlcv.ipynb` tạo ra):

| estimator | công thức (variance mỗi bar; × 252 để annualize) | dùng | ghi chú |
|---|---|---|---|
| close-to-close | `var( ln(C_t / C_{t−1}) )` | C | chuẩn mực; nhiễu |
| Parkinson | trung bình của `(ln(H/L))² / (4·ln 2)` | H, L | hiệu quả hơn ~5 lần; bỏ qua overnight gap |
| Garman–Klass | trung bình của `½(ln(H/L))² − (2ln2 − 1)(ln(C/O))²` | O, H, L, C | hiệu quả hơn nữa; bỏ qua gap |

Lưu ý thực hành:
- Annualize bằng `√252` (Việt Nam có khoảng 245–250 ngày giao dịch mỗi năm; 252 là quy ước).
- Window: 20 ngày (≈1 tháng) phản ứng nhanh, 60 ngày mượt hơn. Dùng window
  khớp với tenor của option.
- Các range-based estimator bỏ qua overnight gap (giá mở cửa so với
  giá đóng cửa hôm trước). Thêm thành phần gap (Yang–Zhang) nếu gap quan trọng.
- **Biên độ dao động giá ±7%/ngày của HOSE** cắt bỏ các move lớn. Vol đo được vào những ngày
  chạm trần/sàn thấp hơn vol thực.
- Dùng giá **đã điều chỉnh**, nếu không các ngày chia cổ tức và tách cổ phiếu sẽ hiện ra như những
  cú sập giả. Dữ liệu của notebook đã được điều chỉnh.

---

## 9. Monte Carlo

Giá = risk-neutral expectation của payoff, đã discount. Mô phỏng terminal price
theo GBM:

```
S_T = S·exp( (r − q − ½σ²)·T + σ·√T·Z ),   Z ~ N(0, 1)
V   ≈ e^(−rT) · mean( payoff(S_T) )
```

Standard error giảm theo `1/√n_paths`. Antithetic variates (dùng `Z` và `−Z`)
và control variates giảm sai số với chi phí thấp. Dùng Monte Carlo cho path-dependent payoff
(Asian, barrier, lookback) khi không có closed form. Với American option,
dùng binomial tree hoặc Longstaff–Schwartz.

---

## 10. Chứng quyền có bảo đảm ở Việt Nam (CW)

Sản phẩm niêm yết giống option trên HOSE. Hãy kiểm tra quy định hiện hành của HOSE / UBCKNN
trước khi dựa vào bất kỳ chi tiết nào.

- **Tổ chức phát hành**: một công ty chứng khoán, không phải tổ chức bù trừ của sở giao dịch.
  Bạn chịu credit risk của tổ chức phát hành, và tổ chức phát hành là market maker chính.
- **Loại**: đến nay là **call** trên cổ phiếu riêng lẻ (chủ yếu các mã VN30). **European**,
  **cash-settled**.
- **Tỷ lệ chuyển đổi `n:1`**: `n` chứng quyền cho payoff của 1 cổ phiếu. Fair value
  mỗi chứng quyền:

  ```
  CW price ≈ BlackScholesCall(S, K, T, r, q, σ) / n
  ```

  Delta của mỗi chứng quyền = `N(d1)/n`. Để hedge 1.000 chứng quyền với tỷ lệ 5:1 và
  `N(d1) = 0.6`, short `1000 · 0.6 / 5 = 120` cổ phiếu.
- **Giá thanh toán** = **bình quân giá đóng cửa** của underlying trong
  5 ngày giao dịch trước ngày đáo hạn (không tính ngày đáo hạn).
  Payoff mỗi chứng quyền = `max(S_settle − K, 0) / n`. Do lấy bình quân, những ngày cuối trước
  đáo hạn hoạt động như một Asian option ngắn hạn: gamma gần đáo hạn thấp hơn
  mức Black–Scholes thông thường cho ra.
- **Corporate actions** (cổ tức tiền mặt/cổ phiếu, quyền mua cổ phiếu phát
  hành thêm) điều chỉnh `K` và tỷ lệ chuyển đổi.
- Giá thị trường thường nằm **cao hơn** fair value tính theo historical vol (một khoản markup của
  tổ chức phát hành). Hãy suy ngược ra implied vol và so sánh với các realized vol estimator
  ở Mục 8.

---

## 11. Code Python tham khảo

Chạy được với `numpy`, `scipy`, `pandas`.

```python
import numpy as np
import pandas as pd
from scipy.optimize import brentq
from scipy.stats import norm


def bs_d1_d2(S, K, T, r, sigma, q=0.0):
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * np.sqrt(T))
    return d1, d1 - sigma * np.sqrt(T)


def bs_price(S, K, T, r, sigma, q=0.0, kind="call"):
    d1, d2 = bs_d1_d2(S, K, T, r, sigma, q)
    if kind == "call":
        return S * np.exp(-q * T) * norm.cdf(d1) - K * np.exp(-r * T) * norm.cdf(d2)
    return K * np.exp(-r * T) * norm.cdf(-d2) - S * np.exp(-q * T) * norm.cdf(-d1)


def bs_greeks(S, K, T, r, sigma, q=0.0, kind="call"):
    """Delta, gamma, vega (trên 1 vol point), theta (trên 1 calendar day), rho (trên 1%)."""
    d1, d2 = bs_d1_d2(S, K, T, r, sigma, q)
    dq, dr, pdf = np.exp(-q * T), np.exp(-r * T), norm.pdf(d1)
    gamma = dq * pdf / (S * sigma * np.sqrt(T))
    vega = S * dq * pdf * np.sqrt(T)
    decay = -S * dq * pdf * sigma / (2 * np.sqrt(T))
    if kind == "call":
        delta = dq * norm.cdf(d1)
        theta = decay - r * K * dr * norm.cdf(d2) + q * S * dq * norm.cdf(d1)
        rho = K * T * dr * norm.cdf(d2)
    else:
        delta = -dq * norm.cdf(-d1)
        theta = decay + r * K * dr * norm.cdf(-d2) - q * S * dq * norm.cdf(-d1)
        rho = -K * T * dr * norm.cdf(-d2)
    return {"delta": delta, "gamma": gamma, "vega": vega / 100,
            "theta": theta / 365, "rho": rho / 100}


def implied_vol(price, S, K, T, r, q=0.0, kind="call"):
    """Black-Scholes implied vol bằng Brent's method; NaN nếu giá vi phạm các no-arbitrage bound."""
    f = lambda s: bs_price(S, K, T, r, s, q, kind) - price
    try:
        return brentq(f, 1e-4, 5.0)
    except ValueError:
        return np.nan


def binomial_price(S, K, T, r, sigma, q=0.0, n=500, kind="call", american=False):
    """Cox-Ross-Rubinstein tree; american=True cho phép early exercise."""
    dt = T / n
    u = np.exp(sigma * np.sqrt(dt)); d = 1 / u
    p = (np.exp((r - q) * dt) - d) / (u - d)
    disc = np.exp(-r * dt)
    ST = S * u ** np.arange(n, -1, -1) * d ** np.arange(0, n + 1)
    payoff = (lambda s: np.maximum(s - K, 0)) if kind == "call" else (lambda s: np.maximum(K - s, 0))
    V = payoff(ST)
    for i in range(n - 1, -1, -1):
        V = disc * (p * V[:-1] + (1 - p) * V[1:])
        if american:
            Si = S * u ** np.arange(i, -1, -1) * d ** np.arange(0, i + 1)
            V = np.maximum(V, payoff(Si))
    return V[0]


def mc_price(S, K, T, r, sigma, q=0.0, n_paths=200_000, kind="call", seed=0):
    """Monte Carlo cho European option với antithetic variates. Trả về (giá, standard error)."""
    z = np.random.default_rng(seed).standard_normal(n_paths // 2)
    z = np.concatenate([z, -z])
    ST = S * np.exp((r - q - 0.5 * sigma**2) * T + sigma * np.sqrt(T) * z)
    pay = np.maximum(ST - K, 0) if kind == "call" else np.maximum(K - ST, 0)
    disc = np.exp(-r * T) * pay
    return disc.mean(), disc.std(ddof=1) / np.sqrt(len(disc))


def realized_vol(df, window=20, periods=252):
    """Rolling annualized vol từ DataFrame OHLC (một mã, đã sắp xếp theo thời gian)."""
    lr = np.log(df["close"] / df["close"].shift(1))
    hl = np.log(df["high"] / df["low"])
    co = np.log(df["close"] / df["open"])
    return pd.DataFrame({
        "close_to_close": lr.rolling(window).std() * np.sqrt(periods),
        "parkinson": np.sqrt((hl**2).rolling(window).mean() / (4 * np.log(2)) * periods),
        "garman_klass": np.sqrt((0.5 * hl**2 - (2 * np.log(2) - 1) * co**2).rolling(window).mean() * periods),
    }, index=df.index)


if __name__ == "__main__":
    S, K, T, r, q, sigma = 100.0, 100.0, 0.5, 0.04, 0.0, 0.30

    c = bs_price(S, K, T, r, sigma, q, "call")
    p = bs_price(S, K, T, r, sigma, q, "put")
    print(f"Giá BS: call {c:.4f}  put {p:.4f}")
    print(f"put-call parity gap: {c - p - (S*np.exp(-q*T) - K*np.exp(-r*T)):.2e}")
    print("Greeks:", {k: round(float(v), 4) for k, v in bs_greeks(S, K, T, r, sigma, q).items()})
    print(f"implied vol tìm lại được: {implied_vol(c, S, K, T, r, q):.4f}")
    print(f"binomial, European call {binomial_price(S, K, T, r, sigma, q):.4f}")
    print(f"binomial, American put  {binomial_price(S, K, T, r, sigma, q, kind='put', american=True):.4f}"
          f"  (European {p:.4f})")
    mc, se = mc_price(S, K, T, r, sigma, q)
    print(f"Monte Carlo, call {mc:.4f} ± {1.96*se:.4f}")
```

**Áp dụng cho dữ liệu của notebook**: ví dụ fair value của một call ATM kỳ hạn 3 tháng
trên FPT, định giá theo chính realized vol 60 ngày của nó:

```python
ohlcv = pd.read_csv("vn30_ohlcv_2025-01-01_2025-12-31_1D.csv", parse_dates=["time"])
fpt = ohlcv[ohlcv["symbol"] == "FPT"].set_index("time").sort_index()

vol = realized_vol(fpt, window=60).iloc[-1]
S = fpt["close"].iloc[-1]                 # nghìn VND
sigma = vol["close_to_close"]
print(vol.round(3).to_dict())
print(f"S={S}, call ATM 3 tháng ≈ {bs_price(S, S, 0.25, 0.03, sigma):.2f} (nghìn VND mỗi cổ phiếu)")
```

(`r = 0.03` chỉ là placeholder. Hãy dùng lợi suất trái phiếu chính phủ VND hiện hành cho kỳ hạn tương ứng.)

---

## 12. Những lỗi thường gặp

- **Đơn vị của `T`**: năm, không phải ngày. 30 calendar day = `30/365`. Nếu vol được
  đo theo trading day thì dùng trading day cho `T`: `21/252`.
- **Đơn vị vol**: 0,30, không phải 30.
- **Trộn lẫn đơn vị giá**: giá trong notebook tính bằng *nghìn* VND; strike và
  spot phải dùng cùng một đơn vị.
- **Cổ tức**: bỏ qua `q` (hoặc discrete dividend) làm định giá sai call và khiến
  put–call parity trông như bị vi phạm.
- **Implied vol trên stale quote hoặc quote kém thanh khoản** cho ra kết quả vô nghĩa. Dùng mid,
  lọc bỏ bid–ask spread rộng, và kiểm tra các price bound trước.
- **Ngoại suy flat vol**: định giá các strike OTM xa bằng vol ATM sẽ định giá thấp
  tail risk (Mục 7).
- **Hedge frequency**: Black–Scholes giả định continuous hedging. Discrete hedging
  thêm P&L noise cỡ `vega·σ/√(2·n_rebalances)`, và chi phí giao dịch tăng theo
  số lần rebalance.

---

## Đọc thêm

- Hull, *Options, Futures, and Other Derivatives*: giáo trình chuẩn.
- Natenberg, *Option Volatility and Pricing*: trực giác của trader, Greeks, spread strategy.
- Sinclair, *Volatility Trading*: realized vol estimator, hedge P&L, edge.
- Gatheral, *The Volatility Surface*: smile, local vol và stochastic vol.
