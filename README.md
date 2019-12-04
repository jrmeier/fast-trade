# Fast Trade
A library to do do back-testing on currency data quickly.

# Goals
- run in less than 30s
- outputs in the form of JSON or CSV
- headless (a react app is coming, just not now)`

# Install
On macOS
- brew install ta-lib

After TA-LIB is installed
```
python -m venv .fast_trade
source .fast_trade/bin/activate
pip install -r requirements.txt
```

# How to use
1. Provide a path for the data file.
2. Set your interval (this of this like a charting period). The default is 1 minute.
3. 
