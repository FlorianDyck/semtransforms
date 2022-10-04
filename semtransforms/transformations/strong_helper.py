from copy import deepcopy

from pycparser.c_ast import *

from semtransforms.transformation import *
from semtransforms.util import simple_declaration, replace


@find_statements(length=1, modifiable_length=False)
def flip_if(self, parents: List[Node], stmts: Nodes, context: ContextVisitor):
    match stmts[0]:
        case If() as part:
            def transform():
                part.cond = UnaryOp('!', part.cond)
                part.iftrue, part.iffalse = part.iffalse or Compound([]), part.iftrue
            return transform


@find_statements(modifiable_length=False)
def add_compound(self, parents: List[Node], stmts: Content, context: ContextVisitor):
    def transform():
        stmts.replace(Compound(stmts.content()))

    if isinstance(stmts, Nodes) and stmts.end == len(stmts.nodes) \
            or not any(isinstance(stmt, Decl) for stmt in stmts):
        return transform


@find_statements(context=True, length=1)
def extract_if(self, parents: List[Node], stmts: Content, context: ContextVisitor):
    match stmts[0]:
        case If() as part:
            name = context.free_name()
            type = context.type(part.cond, name)
            if len(type) != 1:
                return
            type = next(iter(type))

            def transform():
                stmts.replace(Compound([simple_declaration(name, type, part.cond), stmts[0]]))
                part.cond = ID(name)
            return transform


@find_expressions()
def expand_assignment(self, parents: List[Node], expr: SingleNode, context: ContextVisitor):
    """expands += -= *= /= %= &= ^= |= <<= >>="""
    match expr[0]:
        case c_ast.Assignment(op=op, lvalue=left) as assignment if op != "=" and not self.has_side_effects(left):
            def transform():
                assignment.rvalue = BinaryOp(assignment.op[:-1], deepcopy(assignment.lvalue), assignment.rvalue)
                assignment.op = assignment.op[-1:]
            return transform


@find_expressions()
def swap_binary(self, parents: List[Node], expr: SingleNode, context: ContextVisitor):
    match expr[0]:
        case c_ast.BinaryOp(op=op) as binary if op in "+*&|^!==":
            def transform():
                binary.left, binary.right = binary.right, binary.left
            return transform


@find_statements(context=True, length=1)
def extract_unary(self, parents: List[Node], stmts: Content, context: ContextVisitor):
    attr_name = None
    match stmts[0]:
        case c_ast.Return(expr=c_ast.UnaryOp(op=op, expr=expr)):
            attr_name = "expr"
        case c_ast.Assignment(rvalue=c_ast.UnaryOp(op=op, expr=expr)):
            attr_name = "rvalue"
    if attr_name and op in "&*+-!~":
        if op == "&" and isinstance(context.type(stmts[0].expr), FuncDecl):
            return
        name = context.free_name()
        type = context.type(expr, name)
        if len(type) == 1:
            def transform():
                part = getattr(stmts[0], attr_name)
                stmts.replace(Compound([simple_declaration(name, next(iter(type)), part.expr), stmts[0]]))
                part.expr = ID(name)
            return transform


@find_statements(length=1)
def for2while(self, parents: List[Node], stmts: Content, context: ContextVisitor):
    match stmts[0]:
        case For(cond=cond) as f if not self.has_side_effects(cond):
            def transform():
                stmts.replace(Compound([
                    *(f.init.decls if f.init.__class__ is DeclList else (f.init,)),
                    While(f.cond, Compound([f.stmt, f.next]))
                ]))
            return transform


@find_statements(length=1, modifiable_length=False, context=True)
def break2goto(self, parents: List[Node], stmts: Content, context: ContextVisitor):
    if isinstance(stmts[0], Break):
        name = context.free_name("label")

        def transform():
            for i in range(len(parents) - 1, 0, -1):
                if parents[i].__class__ in (Switch, For, While):
                    replace(parents[i - 1], parents[i], Compound([parents[i], Label(name, EmptyStatement())]))
                    stmts.replace(Goto(name))
                    break
        return transform


