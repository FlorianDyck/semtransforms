import logging
import math
import typing
from functools import cache
from typing import List, Union, Callable, Optional

from pycparser import c_ast
from pycparser.c_ast import Node

from semtransforms.context import ContextVisitor, decl_type
from semtransforms.util import NoNode, fnn


class Content:
    """Baseclass to contain a Node"""
    def content(self) -> List[Node]:
        raise NotImplementedError("Not implemented in baseclass")

    def replace(self, content: Union[Node, List[Node]]):
        raise NotImplementedError("Not implemented in baseclass")

    def __iter__(self):
        raise NotImplementedError("Not implemented in baseclass")

    def __getitem__(self, item):
        return self.content()[item]

    def __repr__(self):
        return self.content().__repr__()


class Nodes(Content):
    """contains any number of Nodes which are in a List"""
    def __init__(self, nodes: List[Node], start: int = None, end: int = None):
        self.nodes = nodes
        self.start = fnn(start, 0)
        self.end = fnn(end, len(nodes))

    def content(self) -> List[Node]:
        return self.nodes[self.start:self.end]

    def replace(self, content: Union[List[Node], Node] = []):
        if issubclass(content.__class__, Node):
            content = [content]
        self.nodes[self.start:self.end] = content
        self.end = self.start + len(content)

    def insert_before(self, content: Union[List[Node], Node] = []):
        if issubclass(content.__class__, Node):
            content = [content]
        self.nodes[self.start:self.start] = content
        self.start = self.start + len(content)
        self.end = self.end + len(content)

    def insert_after(self, content: Union[List[Node], Node] = []):
        if issubclass(content.__class__, Node):
            content = [content]
        self.nodes[self.end:self.end] = content

    def __iter__(self):
        for i in range(self.start, self.end):
            yield self.nodes[i]


class SingleNode(Content):
    """contains a Node which is in a Node"""
    def __init__(self, parent: Node, attr_name: str):
        self.parent = parent
        self.attr_name = attr_name

    def content(self) -> List[Node]:
        return [getattr(self.parent, self.attr_name)]

    def replace(self, content: Node):
        setattr(self.parent, self.attr_name, content)

    def __iter__(self):
        yield getattr(self.parent, self.attr_name)


class FindNodes:
    """Baseclass for transformations"""
    all = {}

    def __init__(self, func, context: bool):
        """signature of func:
        (self, parents: List[Node], stmts: Content, context: ContextVisitor, index: int)
            -> Union[List[Callable], Callable, None]"""
        self.func = func
        self.context = context
        FindNodes.all[func.__name__] = self

    def __repr__(self):
        return self.func.__name__

    def _transforms(self, parents: List[Node], stmts: Content, context: ContextVisitor) -> List[Callable]:
        """creates an appropriate list for each return of transforms"""
        try:
            result = self.func(self, parents, stmts, context)
            if not result:
                return []
            if isinstance(result, List):
                return result
            if callable(result):
                return [result]
            logging.warning("Unhandled type: " + result.__class__)
            return []
        except Exception:
            return []

    def _all_transforms(self, ast: Node, parents: List[Node], context: Optional[ContextVisitor], child_index: int) -> \
    List[Callable]:
        """finds for one child all valid transforms"""
        raise NotImplementedError("Not implemented in baseclass")

    def all_transforms(self, ast: Node, parents: List[Node] = [], index: int = 0) -> List[Callable]:
        """iterates through all childs and finds where the AST can be transformed"""
        if not parents:
            self.has_side_effects.cache_clear()
            self.has_node.cache_clear()
        if self.context:
            result = []

            def visit_node(visitor: ContextVisitor, current: Node, parents: typing.List[Node], index):
                result.extend(self._all_transforms(current, parents, visitor, index))

            ContextVisitor(ast, visit_node)
            return result
        else:
            result = self._all_transforms(ast, parents, None, index)
            parents = [] + parents + [ast]
            i = 0
            for c in ast:
                result += self.all_transforms(c, parents, i)
                i += 1
            if ast.__class__ in (c_ast.Compound, c_ast.Case, c_ast.Default):
                result += self.all_transforms(NoNode(), parents, i)
            return result

    @cache
    def has_side_effects(self, node: Node) -> bool:
        match node:
            case c_ast.Assignment():
                return True
            case c_ast.UnaryOp(op=op, expr=expr):
                return op in "p++p--" or self.has_side_effects(expr)
        for child in node:
            if self.has_side_effects(child):
                return True
        return False

    def has_break(self, node: Node) -> bool:
        return self.has_node(node, (c_ast.Break,), (c_ast.Switch, c_ast.While, c_ast.For))

    def has_return(self, node: Node) -> bool:
        return self.has_node(node, (c_ast.Return,))

    def has_jumps(self, node: Node) -> bool:
        return self.has_node(node, (c_ast.Label, c_ast.Goto))

    @cache
    def has_node(self, node: Node, true=(), false=()):
        """
        Searches recursively through the node.
        Returns True iff there is a Node with a class in true before there is one with a class in false
        """
        if node.__class__ in true:
            return True
        if node.__class__ in false:
            return False
        for child in node:
            if self.has_node(child, true, false):
                return True
        return False


def find_statements(context: bool = False, modifiable_length: bool = True,
                    min_length: int = None, max_length: int = None, length: int = None):
    """
    Parameters
    ----------
    context boolean whether the context is needed
    modifiable_length boolean whether the length of the list of statements must be modifiable
    min_length the minimum length of the list of Nodes
    max_length the maximum length of the list of Nodes
    length sets both min_length and max_length

    Returns a wrapper for Transformations
    -------
    annotation for transformations on statements
    """
    return lambda func: FindStatements(func, context, modifiable_length, min_length, max_length, length)


class FindStatements(FindNodes):
    """Iterates over all statements in a node"""
    def __init__(self, func, context: bool = False, modifiable_length: bool = True,
                 min_length: int = None, max_length: int = None, length: int = None):
        FindNodes.__init__(self, func, context)
        self.modifiable_length = modifiable_length
        self.min_length = fnn(min_length, length, 0)
        self.max_length = fnn(max_length, length, 99**99) # inf would be better, but can not be used in range

    def __call__(self, *args, **kwargs):
        return self.method

    def names_if_modifiable(self, parents: List[Node], ast: Node, context: ContextVisitor = None, *names: str):
        """returns transforms on childs if modifiable_length is fullfilled (or not necessary)"""
        if self.modifiable_length and (self.min_length or 0) <= 1 <= (self.max_length or 1):
            return []
        return [t for transforms in [self._transforms(parents, SingleNode(ast, name), context) for name in names] for t
                in transforms]

    def _all_transforms(self, ast: Node, parents: List[Node], context: ContextVisitor, child_index: int) -> List:
        """finds statements in a node"""
        result = []
        if parents:
            match parents[-1]:
                case c_ast.Case(stmts=all) | c_ast.Default(stmts=all) | c_ast.Compound(block_items=all):
                    for end in range(child_index + self.min_length, min(child_index + self.max_length, len(all)) + 1):
                        result += self._transforms(parents, Nodes(all, child_index, end), context)
        match ast:
            case c_ast.DoWhile(), c_ast.For(), c_ast.While():
                return result + self.names_if_modifiable(parents, ast, context, "stmt")
            case c_ast.If(iffalse=None):
                return result + self.names_if_modifiable(parents, ast, context, "iftrue")
            case c_ast.If():
                return result + self.names_if_modifiable(parents, ast, context, "iftrue", "iffalse")
            case _:
                return result


def find_expressions(context: bool = False):
    """
    Parameters
    ----------
    context boolean whether the context is needed
    Returns a wrapper for Transformations
    -------
    annotation for transformations on expressions
    """
    return lambda func: FindExpression(func, context)


class FindExpression(FindNodes):
    def __init__(self, func, context: bool = False):
        FindNodes.__init__(self, func, context)

    def _all_transforms(self, ast: Node, parents: List[Node], context: ContextVisitor, child_index: int) -> List:
        """finds expressions in a node"""
        result = []
        if parents:
            for slot in parents[-1].__slots__:
                attr = getattr(parents[-1], slot)
                if isinstance(attr, Node):
                    child_index -= 1
                    if child_index < 0:
                        break
                if isinstance(attr, list) and len(attr) > child_index and attr[child_index] is ast:
                    result += self._transforms(parents, Nodes(attr, child_index, child_index + 1), context)
                    break

        for slot in ast.__slots__:
            child = getattr(ast, slot)
            if issubclass(child.__class__, Node):
                result += self._transforms(parents + [ast], SingleNode(ast, slot), context)
        return result


def references(parent: Node, decl: c_ast.Decl) -> typing.List[typing.Tuple[SingleNode, List[Node]]]:
    """finds all references to decl in parent,
    assuming the name of the declaration is valid at the beginning of the node"""
    result = []

    @find_expressions(context=True)
    def inner(visitor: FindExpression, parents: typing.List[Node], stmts: SingleNode, context: ContextVisitor):
        match parents[-1]:
            case c_ast.StructRef(field=field) if field is stmts[0]:
                return
        match stmts[0]:
            case c_ast.ID(name=decl.name) if context.value(decl.name, decl_type(decl)) is decl:
                result.append((stmts, parents))
    inner.all_transforms(parent)
    return result


def unknown_references(parent: Node) -> typing.List[typing.Tuple[SingleNode, List[Node]]]:
    """finds all references in parent for which there is no declaration in parent"""
    result = []

    @find_expressions(context=True)
    def inner(visitor: FindExpression, parents: typing.List[Node], stmts: SingleNode, context: ContextVisitor):
        if stmts[0].__class__ is c_ast.ID and not context.value(stmts[0].name):
            match stmts:
                case SingleNode(parent=c_ast.StructRef(field=f)) if f is stmts[0]:
                    return
            result.append((stmts, parents))
        pass
    inner.all_transforms(parent)
    return result