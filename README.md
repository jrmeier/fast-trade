# Fast Trade
A library to do do back-testing on currency data quickly.

# Goals
- run in less than 30s
- outputs in the form of JSON or CSV
- headless (a react app is coming, just not now)`

# Install
On macOS
- brew install ta-lib

On Ubuntu (tested with 18.04.03)
```
sudo apt install build-essential wget -y
wget https://artiya4u.keybase.pub/TA-lib/ta-lib-0.4.0-src.tar.gz
tar -xvf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
```


After TA-LIB is installed
```
python -m venv .fast_trade
source .fast_trade/bin/activate
pip install -r requirements.txt
```

# How to use
1. Provide a path for the data file.
2. Build your strategy
3. ???
4. Profit


Available Indicators (graciously stolen from https://github.com/peerchemist/finta)