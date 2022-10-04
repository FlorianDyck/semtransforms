import itertools
import typing

from pycparser.c_ast import *


def typecast(type1: str, type2: str) -> typing.Set[IdentifierType]:
    """
    Returns possible types of an operation that combines the given types according to the automatic C type conversion.
    As behaviour depends on the size of different types, a set of possible types is returned.
    """
    for type_name in ("long double", "double", "float"):
        if type_name in (type1, type2):
            return {IdentifierType([type_name])}
    result = set()
    for types in itertools.product(_integral_promotion(type1), _integral_promotion(type2)):
        if "unsigned long int" in types:
            result.add("unsigned long int")
        elif "long int" in types:
            if "unsigned int" in types:
                # if int and long int are the same size, this is unsigned long int
                # if long int is bigger than int, this is long int
                result.update(("long int", "unsigned long int"))
            else:
                result.add("long int")
        elif "unsigned int" in types:
            result.add("unsigned int")
        else:
            result.add("int")
    result = {IdentifierType([name]) for name in result}
    return result


def _integral_promotion(type: str):
    if type in ("char", "short"):
        return {"int"}
    if type in ("unsigned char", "unsigned short"):
        # if the type is smaller than int, the result is int, otherwise unsigned int
        return {"int", "unsigned int"}
    return {type}