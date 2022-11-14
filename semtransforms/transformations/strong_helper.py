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
    if isinstance(stmts, Nodes) and stmts.end == len(stmts.nodes) \
            or not any(isinstance(stmt, Decl) for stmt in stmts):
        return lambda: stmts.replace(Compound(stmts.content()))


@find_statements(modifiable_length=False, min_length=-1)
def fast_compound(self, parents: List[Node], stmts: Content, context: ContextVisitor):
    if not isinstance(stmts, Nodes):
        return lambda: stmts.replace(Compound(stmts.content()))

    possibilities = 0  # total number of possibilities
    streak = 1  # number of sequential non-declaration statements + 1
    for child in stmts:
        if isinstance(child, Decl):
            possibilities += streak * (streak + 1) // 2  # adding the number of possibilities in this block
            streak = 1  # resetting the number of sequential non-declaration statements
        else:
            streak += 1  # increase the number of sequential non-declaration statements
    possibilities += streak * (streak + 1) // 2  # adding the number of possibilities in the last block
    # adding the number of possibilities which go to the end and are not covered by the last block
    possibilities += len(stmts.nodes) + 1 - streak

    def transform(index):
        start = 0  # start of the current non-declaration sequence
        streak = 1  # number of sequential non-declaration statements + 1
        for child in stmts:
            if isinstance(child, Decl):
                possibilities = streak * (streak + 1) // 2
                if index < possibilities:
                    break  # compound should go in current block
                start += streak  # this is the start of the next block
                index -= possibilities  # removing the possibilities of this block
                streak = 1  # resetting the number of sequential non-declaration statements
            else:
                streak += 1  # increase the number of sequential non-declaration statements

        possibilities = streak * (streak + 1) // 2
        if index < possibilities:
            # the index is smaller than the number of possibilities in the current block
            end = start
            while index > end - start:
                end += 1
                index -= end - start
            start += index
        else:
            # the index is bigger than the number of possibilities in the last block
            # thus, this compound should go to the end and not overlap with a possibility of the last block
            start = index - possibilities
            end = len(stmts.nodes)
        stmts.nodes[start:end] = [Compound(stmts.nodes[start:end])]

    def call_transform(index):  # this is in a function so that the index is not updated
        return lambda: transform(index)

    return [call_transform(i) for i in range(possibilities)]


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
                loop = While(f.cond, Compound([f.stmt, f.next]))
                stmts.replace(Compound((f.init.decls if f.init.__class__ is DeclList else [f.init]) + [loop])
                              if f.init else loop)
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


