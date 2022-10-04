import os
import re
import unittest

from pycparser import c_generator, c_parser

from semtransforms import pretransformation, support_extensions
from semtransforms.pretransformation import regex


class Settable:
    value: str

    def set(self, value):
        self.value = value
        return "", ""


class RegexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = c_parser.CParser()
        self.generator = c_generator.CGenerator()

    def _test_regex(self, path_to_file):
        current_file_path = os.path.abspath(os.path.dirname(__file__))
        path_to_file = os.path.join(current_file_path, path_to_file)

        with open(path_to_file, "r") as i:
            file_contents = i.read()

        settable = Settable()
        support_extensions(file_contents, settable.set)
        code = settable.value
        with self.subTest(transform_name="normal"):
            self.assertTrue(re.search(regex(code), code))

        reformatted = self.generator.visit(self.parser.parse(code))
        with self.subTest(transform_name="reformatted"):
            self.assertTrue(re.search(regex(reformatted), reformatted))

    def test_regex_base_noreach(self):
        self._test_regex("./benchmarks/base_noreach.c")

    def test_regex_base_reach(self):
        self._test_regex("./benchmarks/base_reach.c")

    def test_regex_array1(self):
        self._test_regex("./benchmarks/array-1.c")

    def test_regex_array2(self):
        self._test_regex("./benchmarks/array-2.c")

    def test_regex_bubblesort1(self):
        self._test_regex("./benchmarks/bubblesort-1.c")