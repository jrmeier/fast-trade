from build_data_frame import build_data_frame
import unittest

class TestBuildDataFrame(unittest.TestCase):
    def test_build_data_frame_1(self):
        csv_base = "/Users/jedmeier/2017_standard/BTCUSDT.csv"

        res = build_data_frame(csv_base)
        print(res)


if __name__ == "__main__":
    unittest.main()