import unittest

from pycparser import c_generator, c_parser

from semtransforms import on_ast, insert_method, FindStatements, FindExpression, parse, generate


class RegexTest(unittest.TestCase):
    def setUp(self) -> None:
        self.parser = c_parser.CParser()
        self.generator = c_generator.CGenerator()

    def _test(self, transformation: FindStatements | FindExpression, code: str, *results):

        self.assertEqual(len(results), on_ast(code, lambda ast: len(transformation.all_transforms(ast)))[0][1])

        for i, result in enumerate(results):
            # with self.subTest(transform_name=transformation.func.__name__):
            test = on_ast(code, lambda ast: transformation.all_transforms(ast)[i]())[0][0]
            self.assertEqual(generate(parse(result)), test)

    def test_insert_method_impossible(self):
        self._test(insert_method, '''
            extern void other();
            int main() {
                other();
                return 0;
            }
        ''')

    def test_insert_method_possible(self):
        self._test(insert_method, '''
            void other(int * i) {
                ++(*i);
            }
            int main() {
                int i = -1;
                other(&i);
                return i;
            }
        ''', '''
            void other(int *i)
            {
              ++(*i);
            }
            
            int main()
            {
              int i = -1;
              {
                int *param_insert_method_line_7_to_7_0 = &i;
                {
                  int *i = param_insert_method_line_7_to_7_0;
                  {
                    ++(*i);
                  }
                }
              }
              return i;
            }
        ''')

