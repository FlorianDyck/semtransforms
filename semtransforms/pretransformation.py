import re
from typing import List


def remove_comments(text):
    """
    removes comments from a piece of source code.
    unchanged from original.

    source:
        https://stackoverflow.com/questions/241327/remove-c-and-c-comments-using-python
    licenses:
        CC BY-SA 3.0: https://creativecommons.org/licenses/by-sa/3.0/
        CC BY-SA 4.0: https://creativecommons.org/licenses/by-sa/4.0/
    """
    def replacer(match):
        s = match.group(0)
        if s.startswith('/'):
            return " "  # note: a space and not an empty string
        else:
            return s
    pattern = re.compile(
        r'//.*?$|/\*.*?\*/|\'(?:\\.|[^\\\'])*\'|"(?:\\.|[^\\"])*"',
        re.DOTALL | re.MULTILINE
    )
    return re.sub(pattern, replacer, text)


def regex(code: str) -> str:
    r"""
    creates a regex expression matching the code with changed whitespace

    does not support string and char values:
    "" would become "\s*", the same for ''
    """
    # shrink whitespace
    code = re.sub(r"\s+", " ", code)
    code = re.sub(r"(?! )(\W)(?! )(\W)", r"\1 \2", code)
    code = re.sub(r"(\w)(?! )(\W)", r"\1 \2", code)
    code = re.sub(r"(?! )(\W)(\w)", r"\1 \2", code)
    code = re.sub(r"(\w) (\w)", r"\1\n\n\2", code)

    # escape special symbols
    code = re.sub(r"(?=[\\(){}\[\].+$^*?|])", r"\\", code)

    # replace whitespace
    code = re.sub(r" ", r"\\s*", code)
    code = re.sub(r"\n\n", r"\\s+", code)

    return code


def unsupported_to_extern(code: str, replacings: List, unsupported: str) -> str:
    """replaces any method containing the unsupported string with an extern method"""
    while r := re.search(unsupported, code):
        start = open = code.find("{")
        depth = 1
        close = code.find("}")
        while True:
            if close < open:
                end = close
                close = code.find("}", close) + 1
                depth -= 1
                if depth == 0:
                    if start < r.start() < close:
                        break
                    start = open
                    depth = 1
            else:
                open = code.find("{", open + 1)
                depth += 1
        previous_end = max(code[:start].rfind(";"), code[:start].rfind("}")) + 1
        save = code[previous_end:end]
        code = ";".join([code[:start], code[end:]])
        code = "extern ".join([code[:previous_end], code[previous_end:]])
        replacings += [(regex(code[previous_end:start + 8]), save)]
    return code


def support_extensions(code: str, func):
    """remove code which can not be parsed by pycparser, do func and reconstruct incompatible code afterwards"""
    code = remove_comments(code)
    replacings = []  # pattern-string combinations which later must be replaced

    # remove unsupported parts
    code = unsupported_to_extern(code, replacings, "__extension__")

    for keyword in ("inline", "restrict"):
        if f"__{keyword} " in code and not re.search(f"(?<!__){keyword}", code):
            code = code.replace(f"__{keyword}", keyword)
            replacings += [(keyword, f"__{keyword}")]

    any = "[a-zA-Z0-9()_*, \n]*"
    attr_or_const = r"(__attribute__ *\(\([a-zA-Z0-9_, ]*\)\)|__const )"
    while r := re.search(f"extern{any}{attr_or_const}{any};", code):
        replacings += [(regex(re.sub(attr_or_const, "", r.group())), r.group())]
        code = re.sub(f"extern{any}{attr_or_const}{any};", re.sub(attr_or_const, " ", r.group()), code, 1)

    # execute func
    result = func(code)

    for i in range(len(result)):
        code, trace = result[i]
        # reconstruct incompatible code
        for pattern, replacing in replacings:
            code = re.sub(pattern, replacing, code)
        result[i:i+1] = [(code, trace)]

    return result
