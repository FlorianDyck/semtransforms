import itertools
import random
import typing
from functools import cache

from pycparser.c_ast import *

from semtransforms.util import NoNode
from semtransforms.util.types import typecast

_beginnings = "_abcdefghijklmnopqrstuvwkyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
_letters = _beginnings + "0123456789"


def random_identifier(length: int = 8) -> str:
    """random identifier"""
    result = random.choice(_beginnings)
    for i in range(length - 1):
        result += random.choice(_letters)
    return result


def next_identifier(name: str) -> str:
    """next identifier after a given one"""
    result = list(reversed(name))
    for i in range(len(result)):
        letters = _letters if i < len(result) - 1 else _beginnings
        index = letters.find(result[i])
        result[i] = letters[(index + 1) % len(letters)]
        if index < len(letters) - 1:
            break
    result = "".join(reversed(result))
    if result == "_" * len(result):
        result += "_"
    return result


def decl_type(node: Node) -> str:
    """returns what kind of data structure a given declaration is"""
    match node:
        case Decl(type=Struct()):
            return "structs"
        case Decl(type=Enum()):
            return "enums"
        case Decl() | Enumerator():
            return "default"
        case _:
            return ""


class ContextLevelTime:
    """maps variables of differen name spaces"""
    def __init__(self):
        self.default: typing.Dict[str, Decl] = {}
        self.enums: typing.Dict[str, Decl] = {}
        self.structs: typing.Dict[str, Decl] = {}

    def __repr__(self):
        return {key for key in (self.default | self.enums | self.structs).keys()}.__repr__()


class ContextLevel:
    """maps variables which are or will be valid"""
    def __init__(self, root: Node = None):
        self.root = root
        self.past = ContextLevelTime()
        self.future = ContextLevelTime()

    def __repr__(self):
        return f"{self.past.__repr__()}|{self.future.__repr__()}"


def _no_decl_type(type: Node):
    return type.type.type if isinstance(type.type, TypeDecl) else type.type


class ContextVisitor:
    """visits the childs of a node with a valid ContextVisitor"""
    def __init__(self, node: Node, visit_node):
        """visit_node has to be callable with:
        (visitor: ContextVisitor, current: Node, parents: typing.List[Node], index: int)"""
        self._types = {}
        self.labels = {}
        self.func_defs = {}
        self.levels = [ContextLevel(node)]
        # initialize functions which are defined by the compiler
        self.levels[0].past.default['__PRETTY_FUNCTION__'] = Decl('__PRETTY_FUNCTION__', [], [], [], [],
                  PtrDecl([], TypeDecl('__PRETTY_FUNCTION__', [], None, IdentifierType(['char']))), None, None)
        self._build_context(node)
        self.visit_node = visit_node
        # run
        self._visit(node, [])
        self._build_labels.cache_clear()

    def _visit(self, current: Node, parents: typing.List[Node] = [], index: int = 0):
        """visit a Node and its child while adding variable names to the past once they are declared"""
        match current:
            case Compound() | While() | DoWhile() | If() | Switch():
                # These are a scope, a new ContextLevel has to be temporarily created
                self._build_context(current)
                self.visit_node(self, current, parents, index)
                parents = [] + parents + [current]
                i = 0
                for child in current:
                    self._visit(child, parents, i)
                    i += 1
                self.visit_node(self, NoNode(), parents, i)
                del self.levels[-1]
            case For(init=init, cond=cond, next=next, stmt=stmt):
                # This is 2 scopes, new Contextlevel have to be temporarily created
                self.visit_node(self, current, parents, index)
                parents = [] + parents + [current]
                if init:
                    self._build_context(init)
                i = 0
                for child in init, cond, next:
                    if child:
                        self._visit(child, parents, i)
                    i += 1
                self._build_context(stmt)
                self._visit(stmt, parents, i)
                if init:
                    del self.levels[-1]
                del self.levels[-1]
            case FuncDef(decl=Decl(name=name, type=type) as decl, body=body):
                # This a scope with parameters as variables, a new ContextLevel has to be temporarily created
                self.visit_node(self, current, parents, index)
                parents = [] + parents + [current]
                self._build_context(type)
                self._visit(decl, parents, 0)
                if name in self.levels[-2].future.default:
                    self.levels[-2].past.default[name] = self.levels[-2].future.default[name]
                    del self.levels[-2].future.default[name]
                self._visit(body, parents, 1)
                del self.levels[-1]
            case Typedef(name=name, type=type):
                # a typedef is declared and has to be added to the past
                self.visit_node(self, current, parents, index)
                self.levels[-1].past.default[name] = self._value(type.type if isinstance(type, TypeDecl) else type)
                del self.levels[-1].future.default[name]
            case _:
                # default: visit node and childs
                self.visit_node(self, current, parents, index)
                parents = [] + parents + [current]
                i = 0
                for child in current:
                    self._visit(child, parents, i)
                    i += 1
                # check if a identifier is declared and has to be added to the past
                name, future = self._name_and_map(current, self.levels[-1].future)
                if name:
                    _, past = self._name_and_map(current, self.levels[-1].past)
                    if name in future:
                        past[name] = future[name]
                        del future[name]

    def _build_context(self, current: Node, first=True):
        """creates a ContextLevel with all identifiers directly in this scope in the future"""
        if current.__class__ in (Compound, While, DoWhile, If, Switch, For) and not first:
            self.labels = self._build_labels(current)
            return  # stop because a new scope is created
        if first:
            self.levels += [ContextLevel(current)]
        # add identifiers to the future
        if isinstance(current, Label):
            self.labels[current.name] = current
        if isinstance(current, FuncDef):
            self.func_defs[current.decl.name] = current
        name, map = self._name_and_map(current, self.levels[-1].future)
        if name:
            map[name] = current
            return
        # run recursively
        for child in current:
            if child:
                self._build_context(child, False)

    @cache
    def _build_labels(self, current: Node) -> typing.Dict[str, Node]:
        if current.__class__ is Label:
            return {current.name: current}
        result = {}
        for child in current:
            result.update(self._build_labels(child))
        return result


    @staticmethod
    def _name_and_map(node: Node, clt: ContextLevelTime) -> typing.Tuple[str, typing.Dict[str, Node]]:
        """returns the map where a declaration should be put"""
        match node:
            case Decl(type=Struct(name=name)):
                return name, clt.structs
            case Decl(type=Enum(name=name)):
                return name, clt.enums
            case Decl(name=name) | Enumerator(name=name) | Typedef(name=name):
                return name, clt.default
            case _:
                return "", clt.default

    def all_levels(self, type="default", time="past"):
        """
        returns a map with all declarations of this type and time
        ----------
        possible values
        type: "default", "enums", "structs"
        time: "past", "future"
        """
        result = {}
        for level in self.levels:
            result |= getattr(getattr(level, time), type)
        return result

    def value(self, name: str, type="default") -> typing.Optional[Decl]:
        """returns the value of the declaration for a name"""
        for level in reversed(self.levels):
            if name in getattr(level.past, type):
                return getattr(level.past, type)[name]
        return None

    def _value(self, node: Node):
        """returns the value of the declaration for a node"""
        match node:
            case Struct():
                return self.value(node.name, "structs")
            case IdentifierType():
                return self.value(node.names[0])
            case _:
                return node

    def free_name(self, type="default"):
        """creates a free name which can be inserted into a program"""
        if type == "label":
            all_keys = self.labels
        else:
            all_keys = set([key for level in self.levels for key in getattr(level.past, type).keys()])
            all_keys |= set([key for key in getattr(self.levels[-1].future, type).keys()])
        name = random_identifier()
        while name in all_keys:
            name = next_identifier(name)
        return name

    def basic_type(self, node: Node) -> typing.Optional[str]:
        """returns the type of a node only if it always is the same IdentifierType"""
        type = self.type(node)
        if len(type) != 1:
            return None
        type = next(iter(type))
        if isinstance(type, TypeDecl):
            type = type.type
        if not isinstance(type, IdentifierType) or len(type.names) != 1:
            return None
        return type.names[0]

    def type(self, node: Node, name: str = None) -> typing.Set[Node]:
        """returns the possible types of a node"""
        if node in self._types:
            return self._types[node]
        if name is None and hasattr(node, "name"):
            name = node.name
        result = self._type(node, name)
        self._types[node] = result
        return result

    def _type(self, node: Node, name: str) -> typing.Set[Node]:
        """returns the possible types of a node"""
        match node:
            # may only be used if there is no declaration between the current statement and node
            case ID(name=name):
                return {_no_decl_type(self.value(name))}
            case ArrayRef(name=expr) | FuncCall(name=expr):
                return {_no_decl_type(t) for t in self.type(expr)}
            case StructRef(name=var, type="->", field=ID(name=field_name)):
                return {_no_decl_type([d for d in self._value(_no_decl_type(decl)).type.decls if d.name == field_name][0])
                        for decl in self.type(var)}
            case StructRef(name=var, field=ID(name=field_name)):
                return {_no_decl_type([d for d in self._value(decl).type.decls if d.name == field_name][0])
                        for decl in self.type(var)}

            case Cast(to_type=type):
                return {_no_decl_type(type)}
            case Constant(type=type):
                return {IdentifierType([type])}
            case Assignment(lvalue=left):
                return self.type(left, name)
            case ExprList(exprs=[*_, last]):
                return self.type(last, name)

            case UnaryOp(op="&", expr=expr):
                return {PtrDecl([], TypeDecl(name, [], None, t)) for t in self.type(expr, name)}
            case UnaryOp(op="*", expr=expr):
                type = self.type(expr, name)
                if len(type) == 1 and {t.__class__ for t in type} == {PtrDecl}:
                    return {_no_decl_type(t) for t in type}
                raise NotImplementedError(f"Pointers ({node.__repr__()}) need to have ONE well-defined type")
            case UnaryOp(expr=expr):
                return self.type(expr, name)

            case BinaryOp(op=op, left=left) if op in ("<<", ">>"):
                return self.type(left, name)
            case BinaryOp(op=op) if op in ("<", "<=", "==", "!=", ">=", ">"):
                return {IdentifierType(["int"])}
            case BinaryOp(left=node1, right=node2) | TernaryOp(iftrue=node1, iffalse=node2):
                return self._typecast(node1, node2, name)

            case _:
                return set()

    def _typecast(self, node1: Node, node2: Node, name) -> typing.Set[Node]:
        """builds types possible by combining 2 type possibilities"""
        result = set()
        for types in itertools.product(self.type(node1, name), self.type(node2, name)):
            result |= typecast(types[0].names[0], types[1].names[0])
        return result


