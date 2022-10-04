import pycparser
from pycparser import c_ast, c_generator
from pycparser.c_ast import Node


class NoNode(Node):
    """used instead of None for Nodes, because this doesn't throw an exception when iterated"""
    def __iter__(self):
        return
        yield


def fnn(*args):
    """first not none: returns first argument which is not None"""
    for arg in args:
        if arg is not None:
            return arg
    return None


def parse(code: str, parser=pycparser.CParser()) -> Node:
    return parser.parse(code)


def generate(node: Node, generator=c_generator.CGenerator()) -> str:
    return generator.visit(node)


def simple_declaration(name: str, type: Node, init: Node):
    return c_ast.Decl(name, [], [], [], [], c_ast.TypeDecl(name, [], None, type), init, None)


def identifier_declaration(name: str, type: str, init: Node):
    return simple_declaration(name, c_ast.IdentifierType([type]), init)


def equals(n1, n2) -> bool:
    """recursively checks whether to nodes are the same"""
    if n1.__class__ is not n2.__class__:
        return False
    if not issubclass(n1.__class__, Node):
        return n1 == n2
    for name in n1.__slots__:
        if name == "coord":
            continue
        a1, a2 = getattr(n1, name), getattr(n2, name)
        if a1.__class__ is list:
            for i1, i2 in zip(a1, a2):
                if not equals(i1, i2):
                    return False
        else:
            if not equals(a1, a2):
                return False
    return True


def replace(parent: Node, old_child: Node, new_child: Node):
    """searches the parent for old_child and replaces it with new_child"""
    for name in parent.__slots__:
        attr = getattr(parent, name)
        if attr is old_child:
            setattr(parent, name, new_child)
            break
        elif isinstance(attr, list) and old_child in attr:
            index = attr.index(old_child)
            attr[index:index + 1] = [new_child]


def duplicateable(node: Node, ignore_case=False):
    """
    returns whether this code segment may exist twice in a method.
    labels and case statements outside a switch may not be duplicated
    """
    match node:
        case c_ast.Switch():
            for child in node:
                if not duplicateable(child, True):
                    return False
            return True
        case c_ast.Case() | c_ast.Default() if not ignore_case:
            return False
        case c_ast.Label():
            return False
    for child in node:
        if not duplicateable(child, ignore_case):
            return False
    return True


def has_variable_array_size(node: Node):
    return (isinstance(node, c_ast.ArrayDecl) and not isinstance(node.dim, c_ast.Constant)) \
           or any(has_variable_array_size(child) for child in node)


def can_rename(node: Node):
    return not (isinstance(node, c_ast.ArrayDecl), isinstance(node, c_ast.FuncDecl))\
           and (not (hasattr(node, "type") and can_rename(node.type)))


def rename(node: Node, name: str):
    if isinstance(node, c_ast.Decl):
        node.name = name
    elif isinstance(node, c_ast.TypeDecl):
        node.declname = name
    if hasattr(node, "type"):
        rename(node.type, name)









