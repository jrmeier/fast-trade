cd ~/
sudo apt install build-essential wget -y
wget https://artiya4u.keybase.pub/TA-lib/ta-lib-0.4.0-src.tar.gz
tar -xvf ta-lib-0.4.0-src.tar.gz
cd ta-lib/
./configure --prefix=/usr
make
sudo make install
cd ~/
rm -rf ./ta-lib
rm ta-lib-0.4.0-src.tar.gz




