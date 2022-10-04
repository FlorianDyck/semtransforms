from copy import deepcopy

from pycparser.c_ast import *

from semtransforms.transformation import *
from semtransforms.util import identifier_declaration, simple_declaration, replace, equals, verifier


def is_dereferenced(nodes: Content):
    return isinstance(nodes, SingleNode) and isinstance(nodes.parent, UnaryOp) and nodes.parent.op == "&"


@find_expressions(context=True)
def arithmetic_nothing(self, parents: List[Node], expr: SingleNode, context: ContextVisitor):
    if is_dereferenced(expr):
        return
    if context.basic_type(expr[0]) in ("double", "float", "unsigned long", "long", "unsigned int", "int"):
        return [
            lambda: expr.replace(BinaryOp("+", expr[0], Constant("int", "0"))),
            lambda: expr.replace(BinaryOp("-", expr[0], Constant("int", "0"))),
            lambda: expr.replace(BinaryOp("*", expr[0], Constant("int", "1"))),
            lambda: expr.replace(BinaryOp("/", expr[0], Constant("int", "1"))),
            lambda: expr.replace(UnaryOp("-", UnaryOp("-", expr[0]))),
        ]


@find_expressions(context=True)
def logic_nothing(self, parents: List[Node], expr: SingleNode, context: ContextVisitor):
    if is_dereferenced(expr):
        return
    if context.basic_type(expr[0]) in ("unsigned long", "long", "unsigned int", "int"):
        return [
            lambda: expr.replace(BinaryOp("<<", expr[0], Constant("int", "0"))),
            lambda: expr.replace(BinaryOp(">>", expr[0], Constant("int", "0"))),
            lambda: expr.replace(UnaryOp("~", UnaryOp("~", expr[0]))),
        ]


@find_statements(length=0, context=True)
@verifier.nondet("int")
def add_nondet(finder: FindStatements, parents: List[Node], stmts: Content, context: ContextVisitor):
    return lambda: stmts.replace(verifier.nondet_call("int"))

