"""
Python package for semantic-equivalent C transforms
"""

# To register a transform in this package you have to define to things
# 1. Enter a name into the available transforms list
# 2. Add logic to transform_by_name to load the requested transform
# A transform is a function that transforms C-code (string) into C-code (string)

# A GLOBAL list of all available transforms
import _thread
import itertools
import multiprocessing
import os.path
import shutil
import threading

from semtransforms import util
from semtransforms.framework import Transformer
from semtransforms.pretransformation import support_extensions
from semtransforms.transformation import FindNodes
# importing subclasses of FindNodes, which are not directly called
from semtransforms.transformations import *


SINGLE_TRANSFORMS = [t for t in FindNodes.all.values() if t not in (add_compound,)]


def _build(*trans, number=(10,)):
    return lambda x, n=number: transform(x, Transformer(*trans), *n)


def _build_except(*trans, number=(10,)):
    return lambda x, n=number: transform(x, Transformer(*[t for t in SINGLE_TRANSFORMS if t not in trans]), *n)


MIXED_TRANSFORMS = {
    "identity": lambda x: (x, ""),
    "random": _build_except(number=1),
    "mixed": _build_except(number=50),
    "no_recursion": _build_except(to_recursive, number=50),
    "no_pointers": _build_except(re_ref, re_ref_no_methods, to_method, insert_method, to_recursive, number=50),
    "no_fpointers": _build_except(re_ref, to_method, insert_method, to_recursive, number=50),
    "arrays": _build(to_array),
    "re_ref": _build(re_ref),
    "loops": _build(deepen_while, for2while, break2goto),
    "methods": _build(add_compound, to_method, insert_method),
    "recursive": _build(for2while, to_recursive),
}
AVAILABLE_TRANSFORMS = list(MIXED_TRANSFORMS.keys())  # + list(FindNodes.all.keys())


def transform_by_name(name):
    assert name in AVAILABLE_TRANSFORMS, f"Transform {name} is not available"

    if name in MIXED_TRANSFORMS:
        return MIXED_TRANSFORMS[name]
    return lambda x: transform(x, Transformer(FindNodes.all[name]))


def all_transformer():
    return Transformer(*FindNodes.all.values())


def transform(program, transformer, *number):
    splits = [number[0]] + [number[i + 1] - number[i] for i in range(len(number) - 1)]
    return support_extensions(program, lambda x: on_ast(x, *[(lambda ast: transformer.transform(ast, split)) for split in splits]))


def trace(program, trace, *number):
    parts = trace.split('\n')
    splits = [(0, number[0])] + [(number[i], number[i + 1]) for i in range(len(number) - 1)]
    parts = ['\n'.join(parts[start:end]) for start, end in splits]
    return support_extensions(program, lambda x: on_ast(x, *[(lambda ast: _trace(ast, part)) for part in parts]))


def add_empty_lists(ast: Node):
    match ast:
        case Case(stmts=None) | Default(stmts=None) as case:
            case.stmts = []
        case Compound(block_items=None) as compound:
            compound.block_items = []
    for c in ast:
        add_empty_lists(c)


def must_be_first(ast: Node):
    match ast:
        case Typedef():
            return True
        case Decl(type=type) if not isinstance(type, FuncDecl):
            return True
    return False


def decl_first(ast: FileAST):
    ast.ext = [node for node in ast if must_be_first(node)] + [node for node in ast if not must_be_first(node)]


def add_necessities(ast: Node):
    def to_compound(child):
        return Compound([child] if child else [])
    if isinstance(ast, If):
        if not isinstance(ast.iftrue, Compound):
            ast.iftrue = to_compound(ast.iftrue)
        if not isinstance(ast.iffalse, Compound):
            ast.iffalse = to_compound(ast.iffalse)
    match ast:
        case Case(stmts=[]) as case:
            case.stmts.append(EmptyStatement())
    for c in ast:
        add_necessities(c)


def on_ast(program, *operations):
    ast = util.parse(program)
    add_empty_lists(ast)
    results = []
    for op in operations:
        result = op(ast)
        ast_copy = deepcopy(ast)
        add_necessities(ast_copy)
        decl_first(ast_copy)
        results.append((util.generate(ast_copy), result))
    return results


def _trace(ast: Node, run: str):
    for line in run.split("\n"):
        name, index = line.split(": ")
        FindNodes.all[name].all_transforms(ast)[int(index)]()
    return run


def collect(results, f="/*\n{1}\n*/\n\n{0}"):
    return [f.format(code, '\n'.join(trace for _, trace in results[:i + 1]))
            for i, (code, _) in enumerate(results)]


def task(name: str, program: str, *number: int, f="/*\n{1}\n*/\n\n{0}"):
    if ":" in name:
        return collect(trace(program, name.replace(';', '\n'), *number), f)
    elif name in MIXED_TRANSFORMS:
        return collect(MIXED_TRANSFORMS[name](program, number))
    elif name in FindNodes.all:
        return collect(transform(program, Transformer(*[FindNodes.all[n] for n in name.split(";")]), *number))


def limit(task, timeout=100):
    if timeout < 0:
        return task()
    timer = threading.Timer(timeout, lambda: _thread.interrupt_main())
    timer.start()
    try:
        result = task()
        timer.cancel()
        return result
    except KeyboardInterrupt:
        raise Exception('Timeout')
    finally:
        timer.cancel()


def trans(root, base_len, output, file, task_name, *number, timeout=-1):
    out = os.path.abspath(output)
    file_in = os.path.join(root, file)
    file_out = os.path.join(out, "{}/", os.path.abspath(root)[base_len:], file)
    with open(file_in, "r") as i:
        code = i.read()
    if file_in[-2:] not in (".c", ".i") or "#include" in code or "#if" in code:
        for n in number:
            with open(file_out.format(n), "w+") as o:
                o.write(code)
        return
    try:
        result = zip(number, limit(lambda: task(task_name, code, *number), timeout))
        for n, content in result:
            with open(file_out.format(n), "w+") as o:
                o.write(content)
    except Exception as e:
        # o.write(f"/*Error parsing file:\n{e}\n*/\n{code}")
        with open(f"{output}/exceptions.txt", "a+") as eo:
            eo.write(f"{file_in} -> {os.path.abspath(root)[base_len:]}\\{file}\n{e}\n{'*' * 100}\n")


def transform_folder(input, output, task_name, numbers, parallel):
    base_len = len(os.path.abspath(input)) + 1
    out = os.path.abspath(output)
    print(os.path.abspath(input), os.path.abspath(output), task_name, numbers)
    for root, folder, files in os.walk(input):
        if files:
            for n in numbers:
                folder = os.path.join(out, f"{n}/", os.path.abspath(root)[base_len:])
                if not os.path.exists(folder):
                    os.makedirs(folder)
    if parallel:
        pool = multiprocessing.Pool(multiprocessing.cpu_count() - 2)
        pool.starmap(trans, ((root, base_len, output, f, task_name, *numbers)
                             for root, _, files in os.walk(input) for f in files))
    else:
        for root, _, files in os.walk(input):
            for file in files:
                trans(root, base_len, output, file, task_name, *numbers)


def arg_value(names, default, args=sys.argv):
    for a in names:
        if a not in args[:-1]:
            continue
        return args[args.index(a) + 1]
    return default


def __main__(parallel=False):
    prefix = "../" if __name__ == "__main__" else ""
    program = arg_value(["-p", "--program"], None)
    input = arg_value(["-f", "--file"], f"{prefix}benchmark/generation/input")
    output = arg_value(["-o", "--out"], f"{prefix}benchmark/generation/output")
    task_name = arg_value(["-t", "--task"], "no_recursion")
    recursion_limit = arg_value(["-r", "--recurion-limit"], "10000")
    numbers = arg_value(["-n", "--number"], len(task_name.split("\n")) if ":" in task_name else "100")

    result = []
    for n in numbers.split(","):
        result += range(*[int(i) for i in n.split(":")]) if ":" in n else [int(n)]
    numbers = result

    sys.setrecursionlimit(int(recursion_limit))

    if task_name == "trace_wrong":
        results = arg_value(["-r", "--results"], r"..\benchmark\benchmark_results\cpa-comp.no_pointers_100_2_missing"
                            r"\cpa-comp.no_pointers_100_2_missing.2022-08-19_13-19-13.results.SEMTRANS_unreach-call.csv")
        input = arg_value(["-f", "--file"], r"..\benchmark\no_pointers_100")
        with open(results, "r") as results:
            def ground_truth(filename, expected_verdicts={}):
                if not expected_verdicts:
                    with open("../benchmark/benchmark_results/cpa-pred-original-finished/"
                              "cpa-pred.original.2022-08-12_14-11-55.results.SEMTRANS_unreach-call.csv", "r") as r:
                        for line in r.read().splitlines()[3:]:
                            expected_verdicts[line.split("\t")[0]] = line.split("\t")[1]
                return expected_verdicts[filename] if filename in expected_verdicts else None

            def wrong(line: str):
                rows = line.split("\t")
                if len(rows) == 7:
                    file, expected_verdict, status, cpu_time_s, wall_time_s, memory_mb, host = rows
                elif len(rows) == 5:
                    file, status, cpu_time_s, wall_time_s, memory_mb = rows
                    expected_verdict = ground_truth(file)
                    if expected_verdict is None:
                        return False
                    host = "TowerOfFlo"
                else:
                    return False
                if (expected_verdict == "true"  and status == "false(unreach-call)") or\
                   (expected_verdict == "false" and status == "true"):
                    return file, expected_verdict, status, cpu_time_s, wall_time_s, memory_mb, host

            files = [wrong(line) for line in results.read().splitlines()[3:]]
            files = [file[0] for file in files if file]
            for file in files:
                file = file[:-3] + "i"
                if not os.path.exists(os.path.join(r"..\benchmark\original", file)):
                    file = file[:-1] + "c"
                only_file = file[file.rfind("/") + 1:]
                base_path = r"..\benchmark\generation\input\temp"
                path = os.path.join(base_path, only_file)
                shutil.copy(os.path.join(r"..\benchmark\original", file), path)
                with open(os.path.join(input, file)) as i:
                    t = i.read()
                    t = t[3:t.find("\n*/")]
                transform_folder(base_path, os.path.join(r"..\benchmark\generation\output", only_file[:-2]),
                                 t, range(1, len(t.split("\n")) + 1), parallel)
                os.remove(path)
    elif program:
        with open(output, "w") as o:
            o.write(task(task_name, program, numbers[0])[0])
    elif os.path.isfile(input):
        with open(input, "r") as i, open(output, "w") as o:
            o.write(task(task_name, i.read(), numbers[0])[0])
    else:
        transform_folder(input, output, task_name, numbers, parallel)


if __name__ == "__main__":
    __main__(True)

