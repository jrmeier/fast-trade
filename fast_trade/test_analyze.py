import unittest
from analyze import anaylze

class TestAnaylze(unittest.TestCase):
    def test_analyze1(self):
    """
    The actual test.
    Any method which starts with ``test_`` will considered as a test case.
    """
    res = anaylze(start_balance)
    
    
    self.assertEqual(res, 0)
