import copy
import typing
from functools import wraps, cache

from pycparser import c_ast

from semtransforms.transformation import Content
from semtransforms.context import ContextVisitor
from semtransforms.util import equals, parse


@cache
def nondet_signature(type: str) -> c_ast.Node:
    return parse(f"extern {type} {nondet_name(type)}();").ext[0]


def nondet_name(type: str):
    """
    Creates a call to a __VERIFIER_nondet_... function.
    Should be always used in combination with nondet to ensure that the function exists.
    """
    return f"__VERIFIER_nondet_{type}"


def nondet_call(type: str):
    return c_ast.FuncCall(c_ast.ID(nondet_name(type)), None)


def nondet(*types: str):
    """
    Wraps a function to add the definitions for the given __VERIFIER_nondet_... for the types.
    Call to this function can be created with nondet_call.
    """
    types = [(nondet_name(t), nondet_signature(t)) for t in types]

    def wrapper(func):
        @wraps(func)
        def wrapper2(transform, parents: typing.List[c_ast.Node], stmts: Content, context: ContextVisitor):
            # find missing nondet definitions
            missing_types = []
            names = context.all_levels()
            for name, t in types:
                if name not in names:
                    missing_types.append(t)
                elif not equals(names[name], t):
                    return
            result = func(transform, parents, stmts, context)
            if result:
                def enable():
                    # add nondet definitions which are not already there
                    parents[0].ext[0:0] = copy.deepcopy(missing_types)
                    result()
                return enable
        return wrapper2
    return wrapper


_ERROR_SIGNATURE = parse("extern void __assert_fail(const char *, const char *, unsigned int, const char *);").ext[0]
ERROR_NAME = f"__assert_fail"
_ERROR_CALL = c_ast.FuncCall(c_ast.ID(ERROR_NAME), c_ast.ExprList([
    c_ast.Constant('string', '"0"'), c_ast.Constant('string', '""'),
    c_ast.Constant('int', '3'), c_ast.Constant('string', '"reach_error"')
]))


def error_call():
    """
    Creates a call to the reach_error function.
    Should be always used in combination with error to ensure that the function exists.
    """
    return copy.deepcopy(_ERROR_CALL)


def error(func):
    """
    Wraps a function to add the definition for thereach_error function.
    Call to this function can be created with error_call.
    """
    @wraps(func)
    def wrapper(transform, parents: typing.List[c_ast.Node], stmts: Content, context: ContextVisitor):
        names = context.all_levels()
        definition_available = ERROR_NAME in names
        if definition_available and not equals(names[ERROR_NAME], _ERROR_SIGNATURE):
            return False
        result = func(transform, parents, stmts, context)
        if result:
            def enable():
                if not definition_available:
                    parents[0].ext.insert(0, copy.deepcopy(_ERROR_SIGNATURE))
                result()
            return enable
    return wrapper

