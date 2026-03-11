# Technical Analysis Indicators

This document provides an overview of all the technical analysis indicators available in the library.

## Moving Averages

### Simple Moving Averages
- **SMA (Simple Moving Average)**
  - Description: Basic moving average calculated by taking the arithmetic mean over a period
  - Parameters:
    - `period`: (int, default=41) Number of periods to calculate the average
    - `column`: (str, default='close') Column to calculate SMA on

- **SMM (Simple Moving Median)**
  - Description: Alternative to SMA using median instead of mean, more robust to outliers
  - Parameters:
    - `period`: (int, default=9) Number of periods for median calculation
    - `column`: (str, default='close') Column to calculate SMM on

- **SSMA (Smoothed Simple Moving Average)**
  - Description: A smoothed version of the simple moving average
  - Parameters:
    - `period`: (int, default=9) Number of periods for smoothing
    - `column`: (str, default='close') Column to calculate SSMA on
    - `adjust`: (bool, default=True) Adjust the smoothing

### Exponential Moving Averages
- **EMA (Exponential Moving Average)**
  - Description: Moving average giving more weight to recent prices
  - Parameters:
    - `period`: (int, default=9) Number of periods for EMA calculation
    - `column`: (str, default='close') Column to calculate EMA on
    - `adjust`: (bool, default=True) Adjust the exponential weighting

- **DEMA (Double Exponential Moving Average)**
  - Description: Reduces lag by applying a double exponential smoothing
  - Parameters:
    - `period`: (int, default=9) Number of periods for DEMA calculation
    - `column`: (str, default='close') Column to calculate DEMA on
    - `adjust`: (bool, default=True) Adjust the exponential weighting

- **TEMA (Triple Exponential Moving Average)**
  - Description: Further reduces lag using triple exponential smoothing
  - Parameters:
    - `period`: (int, default=9) Number of periods for TEMA calculation
    - `adjust`: (bool, default=True) Adjust the exponential weighting

- **TRIMA (Triangular Moving Average)**
  - Description: Places more weight on middle values of the period
  - Parameters:
    - `period`: (int, default=18) Number of periods for TRIMA calculation

### Advanced Moving Averages
- **KAMA (Kaufman Adaptive Moving Average)**
  - Description: Adapts to market volatility, reducing lag in trending markets
  - Parameters:
    - `er`: (int, default=10) Efficiency ratio periods
    - `ema_fast`: (int, default=2) Fast EMA period
    - `ema_slow`: (int, default=30) Slow EMA period
    - `period`: (int, default=20) KAMA period
    - `column`: (str, default='close') Column to calculate KAMA on

- **ZLEMA (Zero Lag Exponential Moving Average)**
  - Description: Removes lag by using a special smoothing formula
  - Parameters:
    - `period`: (int, default=26) Number of periods for calculation
    - `adjust`: (bool, default=True) Adjust the exponential weighting
    - `column`: (str, default='close') Column to calculate ZLEMA on

- **WMA (Weighted Moving Average)**
  - Description: Assigns higher weights to recent data points
  - Parameters:
    - `period`: (int, default=9) Number of periods for WMA calculation
    - `column`: (str, default='close') Column to calculate WMA on

- **HMA (Hull Moving Average)**
  - Description: Provides significantly less lag than traditional moving averages
  - Parameters:
    - `period`: (int, default=16) Number of periods for HMA calculation

- **EVWMA (Elastic Volume Weighted Moving Average)**
  - Description: Volume-weighted moving average with elastic properties
  - Parameters:
    - `period`: (int, default=20) Number of periods for calculation

- **VWAP (Volume Weighted Average Price)**
  - Description: Average price weighted by volume
  - Parameters:
    - Requires OHLCV data

## Momentum Indicators

### Basic Momentum
- **MOM (Momentum)**
  - Description: Measures the change in price over a period
  - Parameters:
    - `period`: (int, default=10) Number of periods for momentum calculation
    - `column`: (str, default='close') Column to calculate momentum on

- **ROC (Rate of Change)**
  - Description: Shows the percentage change in price over a period
  - Parameters:
    - `period`: (int, default=12) Number of periods for ROC calculation
    - `column`: (str, default='close') Column to calculate ROC on

- **RSI (Relative Strength Index)**
  - Description: Measures speed and magnitude of recent price changes
  - Parameters:
    - `period`: (int, default=14) Number of periods for RSI calculation
    - `column`: (str, default='close') Column to calculate RSI on
    - `adjust`: (bool, default=True) Adjust the calculation

- **MACD (Moving Average Convergence Divergence)**
  - Description: Shows the relationship between two moving averages
  - Parameters:
    - `period_fast`: (int, default=12) Fast EMA period
    - `period_slow`: (int, default=26) Slow EMA period
    - `signal`: (int, default=9) Signal line period
    - `column`: (str, default='close') Column to calculate MACD on
    - `adjust`: (bool, default=True) Adjust the calculation

### Advanced Momentum
- **STOCH (Stochastic Oscillator)**
  - Description: Compares closing price to price range over a period
  - Parameters:
    - `period`: (int, default=14) Number of periods for calculation

- **STOCHRSI (Stochastic RSI)**
  - Description: Applies stochastic calculation to RSI values
  - Parameters:
    - `rsi_period`: (int, default=14) RSI calculation period
    - `stoch_period`: (int, default=14) Stochastic calculation period

- **WILLIAMS (Williams %R)**
  - Description: Shows where current price is relative to high-low range
  - Parameters:
    - `period`: (int, default=14) Number of periods for calculation

- **VBM (Volatility-Based-Momentum)**
  - Description: Similar to ROC but divides by historical volatility using ATR
  - Parameters:
    - `roc_period`: (int, default=12) ROC calculation period
    - `atr_period`: (int, default=26) ATR calculation period
    - `column`: (str, default='close') Column for calculations

- **DYMI (Dynamic Momentum Index)**
  - Description: Variable term RSI that adapts to volatility
  - Parameters:
    - `column`: (str, default='close') Column for calculations
    - `adjust`: (bool, default=True) Adjust the calculation

- **IFT_RSI (Inverse Fisher Transform RSI)**
  - Description: Modified RSI using inverse Fisher transform
  - Parameters:
    - `column`: (str, default='close') Column for calculations
    - `rsi_period`: (int, default=5) RSI calculation period
    - `wma_period`: (int, default=9) WMA calculation period

- **UO (Ultimate Oscillator)**
  - Description: Multi-timeframe momentum indicator
  - Parameters:
    - `column`: (str, default='close') Column for calculations

- **AO (Awesome Oscillator)**
  - Description: Shows market momentum using simple moving averages
  - Parameters:
    - `slow_period`: (int, default=34) Slow period
    - `fast_period`: (int, default=5) Fast period

- **MI (Mass Index)**
  - Description: Identifies trend reversals based on range expansions
  - Parameters:
    - `period`: (int, default=9) Calculation period
    - `adjust`: (bool, default=True) Adjust the calculation

- **BOP (Balance of Power)**
  - Description: Shows buying and selling pressure
  - Parameters:
    - Requires OHLC data

- **CMO (Chande Momentum Oscillator)**
  - Description: Shows directional movement strength
  - Parameters:
    - `period`: (int, default=9) Calculation period
    - `factor`: (int, default=100) Scaling factor
    - `column`: (str, default='close') Column for calculations
    - `adjust`: (bool, default=True) Adjust the calculation

- **KST (Know Sure Thing)**
  - Description: Momentum oscillator based on four different time frames
  - Parameters:
    - `r1`: (int, default=10) First ROC period
    - `r2`: (int, default=15) Second ROC period
    - `r3`: (int, default=20) Third ROC period
    - `r4`: (int, default=30) Fourth ROC period

- **TSI (True Strength Index)**
  - Description: Momentum oscillator based on double smoothing of price changes
  - Parameters:
    - `long`: (int, default=25) Long period
    - `short`: (int, default=13) Short period
    - `signal`: (int, default=13) Signal period
    - `column`: (str, default='close') Column for calculations
    - `adjust`: (bool, default=True) Adjust the calculation

## Volatility Indicators

### Bands and Channels
- **BBANDS (Bollinger Bands)**
  - Description: Shows volatility-based bands around a moving average
  - Parameters:
    - `period`: (int, default=20) Number of periods for calculation
    - `std_multiplier`: (float, default=2) Standard deviation multiplier
    - `column`: (str, default='close') Column to calculate bands on
    - `MA`: (Series, optional) Override internal MA calculation

- **KC (Keltner Channels)**
  - Description: Similar to Bollinger Bands but uses ATR for band width
  - Parameters:
    - `period`: (int, default=20) Number of periods for calculation
    - `atr_period`: (int, default=10) ATR calculation period
    - `kc_mult`: (float, default=2) Multiplier for channel width
    - `MA`: (Series, optional) Override internal MA calculation

### Volatility Measures
- **ATR (Average True Range)**
  - Description: Measures market volatility
  - Parameters:
    - `period`: (int, default=14) Number of periods for ATR calculation

- **TR (True Range)**
  - Description: Base calculation showing the greatest of various price ranges
  - Parameters:
    - Requires OHLC data

## Volume Indicators

- **OBV (On Balance Volume)**
  - Description: Cumulative volume indicator based on price direction
  - Parameters:
    - `column`: (str, default='close') Column to calculate OBV on

- **VZO (Volume Zone Oscillator)**
  - Description: Shows volume pressure with overbought/oversold levels
  - Parameters:
    - `period`: (int, default=14) Number of periods for calculation
    - `column`: (str, default='close') Column for calculations
    - `adjust`: (bool, default=True) Adjust the calculation

- **EFI (Elder's Force Index)**
  - Description: Measures the power behind price movements
  - Parameters:
    - `period`: (int, default=13) Number of periods for calculation
    - `column`: (str, default='close') Column for calculations
    - `adjust`: (bool, default=True) Adjust the calculation

- **WOBV (Weighted On Balance Volume)**
  - Description: OBV weighted by price changes
  - Parameters:
    - `column`: (str, default='close') Column for calculations

- **VPT (Volume Price Trend)**
  - Description: Combines volume with price changes
  - Parameters:
    - Requires OHLCV data

- **FVE (Fair Value Extension)**
  - Description: Advanced money flow indicator
  - Parameters:
    - `period`: (int, default=22) Calculation period
    - `factor`: (int, default=0.3) Price threshold factor

- **VFI (Volume Flow Indicator)**
  - Description: Tracks volume based on price direction
  - Parameters:
    - `period`: (int, default=130) Calculation period
    - `smoothing_factor`: (int, default=3) Smoothing period
    - `factor`: (int, default=0.2) Scaling factor
    - `vfactor`: (int, default=2.5) Volume cutoff factor
    - `adjust`: (bool, default=True) Adjust the calculation

- **MFI (Money Flow Index)**
  - Description: Volume-weighted RSI
  - Parameters:
    - `period`: (int, default=14) Calculation period

- **ADL (Accumulation/Distribution Line)**
  - Description: Shows money flow into/out of a security
  - Parameters:
    - Requires OHLCV data

- **CHAIKIN (Chaikin Oscillator)**
  - Description: Momentum of ADL line
  - Parameters:
    - `adjust`: (bool, default=True) Adjust the calculation

- **EMV (Ease of Movement)**
  - Description: Relates price change to volume
  - Parameters:
    - `period`: (int, default=14) Calculation period

## Trend Indicators

- **ADX (Average Directional Index)**
  - Description: Measures trend strength
  - Parameters:
    - `period`: (int, default=14) Number of periods for calculation
    - `adjust`: (bool, default=True) Adjust the calculation

- **DMI (Directional Movement Index)**
  - Description: Shows trend direction and strength
  - Parameters:
    - `period`: (int, default=14) Number of periods for calculation
    - `adjust`: (bool, default=True) Adjust the calculation

- **PSAR (Parabolic SAR)**
  - Description: Trend following indicator with stop and reverse signals
  - Parameters:
    - `iaf`: (float, default=0.02) Initial acceleration factor
    - `maxaf`: (float, default=0.2) Maximum acceleration factor

- **ICHIMOKU (Ichimoku Cloud)**
  - Description: Complete trading system showing support, resistance, and trend
  - Parameters:
    - `tenkan_period`: (int, default=9) Conversion line period
    - `kijun_period`: (int, default=26) Base line period
    - `senkou_period`: (int, default=52) Leading span B period
    - `chikou_period`: (int, default=26) Lagging span period

## Pattern Recognition

- **WILLIAMS_FRACTAL**
  - Description: Identifies potential turning points in the market
  - Parameters:
    - `period`: (int, default=2) Number of lower highs/higher lows

- **SQZMI (Squeeze Momentum)**
  - Description: Identifies periods of market consolidation
  - Parameters:
    - `period`: (int, default=20) Number of periods for calculation
    - `MA`: (Series, optional) Override internal MA calculation

## Price Transform Indicators

- **TP (Typical Price)**
  - Description: Average of high, low, and close
  - Parameters:
    - Requires OHLC data

- **PIVOT**
  - Description: Calculates pivot points and support/resistance levels
  - Parameters:
    - Requires OHLC data

- **PIVOT_FIB (Fibonacci Pivot Points)**
  - Description: Fibonacci-based pivot points
  - Parameters:
    - Requires OHLC data

- **VC (Value Chart)**
  - Description: Normalizes price into value zones
  - Parameters:
    - `period`: (int, default=5) Calculation period

## Market Strength

- **EBBP (Elder Bull Bear Power)**
  - Description: Shows buying and selling pressure
  - Parameters:
    - Requires OHLC data

- **BASP (Buying/Selling Pressure)**
  - Description: Identifies buying and selling pressure
  - Parameters:
    - `period`: (int, default=40) Calculation period
    - `adjust`: (bool, default=True) Adjust the calculation

- **BASPN (Normalized BASP)**
  - Description: Normalized version of BASP indicator
  - Parameters:
    - `period`: (int, default=40) Calculation period
    - `adjust`: (bool, default=True) Adjust the calculation

## Additional Indicators

- **CHANDELIER**
  - Description: Sets trailing stop-loss based on ATR
  - Parameters:
    - `short_period`: (int, default=22) Short period
    - `long_period`: (int, default=22) Long period
    - `k`: (int, default=3) ATR multiplier

- **QSTICK**
  - Description: Shows dominance of black or white candlesticks
  - Parameters:
    - `period`: (int, default=14) Calculation period

- **WTO (Wave Trend Oscillator)**
  - Description: Trend and momentum indicator
  - Parameters:
    - `channel_length`: (int, default=10) Channel length
    - `average_length`: (int, default=21) Average length
    - `adjust`: (bool, default=True) Adjust the calculation

- **FISH (Fisher Transform)**
  - Description: Converts prices into a Gaussian normal distribution
  - Parameters:
    - `period`: (int, default=10) Calculation period
    - `adjust`: (bool, default=True) Adjust the calculation

- **WAVEPM (Wave Price Mass)**
  - Description: Volatility-based oscillator
  - Parameters:
    - `period`: (int, default=14) Calculation period
    - `lookback_period`: (int, default=100) Lookback period
    - `column`: (str, default='close') Column for calculations

- **ROLLING_MAX**
  - Description: Highest value in a rolling window
  - Parameters:
    - `periods`: (int, default=10) Rolling window size
    - `column`: (str, default='close') Column for calculations

- **ROLLING_MIN**
  - Description: Lowest value in a rolling window
  - Parameters:
    - `periods`: (int, default=10) Rolling window size
    - `column`: (str, default='close') Column for calculations

## Notes

- Most indicators can be customized using different periods and parameters
- Many indicators work best in combination with others
- Different market conditions may require different indicators
- Always use indicators as part of a complete trading strategy
- All indicators require OHLC (Open, High, Low, Close) data unless specified otherwise
- Some indicators require volume data (OHLCV)

## References

For detailed information about each indicator, including formulas and usage examples, please refer to the source code documentation. 