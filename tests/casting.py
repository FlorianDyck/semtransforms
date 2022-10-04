import unittest
from typing import Iterable

from semtransforms.util.types import typecast


class RegexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.signed = ("long int", "int", "short", "char")
        self.unsigned = ("unsigned long int", "unsigned int", "unsigned short", "unsigned char")
        self.types = ("long double", "double", "float", "unsigned long int", "long int",
                      "unsigned int", "int", "unsigned short", "short", "unsigned char", "char")

    def _test(self, t1: str, t2: Iterable[str], *result: str):
        if not result:
            result = t1,
        for t in t2:
            self.assertEqual({id.names[0] for id in typecast(t1, t)}, set(result))
            self.assertEqual({id.names[0] for id in typecast(t, t1)}, set(result))

    def test_floating(self):
        self._test("long double", self.types)
        self._test("double", self.types[1:])
        self._test("float", self.types[2:])

    def test_long(self):
        self._test("unsigned long int", self.types[3:])
        self._test("long int", self.signed)
        self._test("long int", self.unsigned[1:], "long int", "unsigned long int")

    def test_int(self):
        self._test("unsigned int", self.types[5:])
        self._test("int", self.signed[1:])
        self._test("int", self.unsigned[2:], "int", "unsigned int")

    def test_short(self):
        self._test("unsigned short", self.types[6:], "int", "unsigned int")
        self._test("unsigned char", self.types[6:], "int", "unsigned int")
        self._test("short", self.signed[2:], "int")
        self._test("char", self.signed[2:], "int")






