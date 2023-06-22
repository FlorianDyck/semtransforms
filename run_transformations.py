import os
import shutil
import sys
import argparse

import pycparser.plyparser
import yaml
import random
import traceback

from glob import glob
from time import time

from mapreduce import mapreduce

from semtransforms import TRANSFORM_NAMES, transform_by_name, _TransformerFN, MIXED_TRANSFORMS


# Transformer ---------------------------------------------------------------------------

class FileTransformer:

    def __init__(self, config):
        self._output_dir = config.output_dir
        self._num_transforms = config.num_transforms
        self._recursion_limit = config.recursion_limit
        self._generate_benchmark = config.generate_benchmark
        self._benchmark_comparison = config.benchmark_comparison
        self._prefix = config.prefix
        self._suffix = config.suffix
        self._header = config.header
        if config.header_file:
            with open(config.header_file, 'r') as r:
                self._header = r.read()

        self._transforms = [transform_by_name(name, pretty_names=config.pretty_names)
                            for name in TRANSFORM_NAMES if getattr(config, name, False)]
        self._trace = config.trace
        if config.trace:
            self._transforms = [MIXED_TRANSFORMS['random']]

        self._required_transforms = config.required_transforms
        self._pretty_names = config.pretty_names

        assert len(self._transforms) > 0, f"You have to select at least one transform from {TRANSFORM_NAMES}"

    def __call__(self, file_name):
        sys.setrecursionlimit(self._recursion_limit)

        if len(self._transforms) == 1:
            transform = self._transforms[0]
        else:
            transform = random.choice(self._transforms)

        with open(file_name, 'r') as f:
            source_code = f.read()

        start_time = time()

        try:
            if self._trace:
                # this import does not work if it is at the start of the file.
                from semtransforms import trace
                transforms = trace(source_code, '\n'.join(self._trace), self._pretty_names, *self._num_transforms)
            else:
                transforms = transform(source_code, pretty_names = self._pretty_names, n = self._num_transforms)
        except pycparser.plyparser.ParseError as pe:
            print(f"\ncould not parse '{file_name}' because of {pe}. See statistics for detailed info.")
            return [{
                "source_file": file_name,
                "exception"  : traceback.format_exc(),
                "walltime"   : time() - start_time,
            }]
        except Exception:
            traceback.print_exc()
            return [{
                "source_file": file_name,
                "exception"  : traceback.format_exc(),
                "walltime"   : time() - start_time,
            }]
        trace = ';'.join(trace for code, trace in transforms)
        for required_transform in self._required_transforms:
            if required_transform not in trace:
                print(f'Missing {required_transform} in {trace}')
                return [{
                    "source_file": file_name,
                    "exception"  : f"missing required transformation '{required_transform}' in '{transforms[-1][1]}'",
                    "walltime"   : time() - start_time,
                }]

        output_files = []
        transform_count = 0
        full_trace = ''
        for i, (transformed, trace) in enumerate(transforms):
            if not trace:
                break
            transform_count += trace.count('\n') + 1
            full_trace = f'{full_trace}\n{trace}' if full_trace else trace
            input_path, ext = os.path.splitext(file_name)
            basename = os.path.basename(input_path)

            path_parts = [self._output_dir]
            if self._benchmark_comparison:
                path_parts.append(str(i))
            if self._generate_benchmark:
                path_parts.append(self._prefix + os.path.basename(os.path.dirname(file_name)) + self._suffix)
            path_parts.append(self._prefix + basename + self._suffix)
            output_path = os.path.join(*path_parts)
            if len(transforms) > 1 and not self._benchmark_comparison:
                output_path += f"-{transform_count}"

            if self._generate_benchmark:
                with open(input_path + '.yml', 'r') as r:
                    yml = yaml.safe_load(r)
                original_files = yml['input_files']
                yml['input_files'] = os.path.basename(output_path) + ext
                with open(output_path + '.yml', 'w+') as w:
                    yaml.dump(yml, w)
                    w.write(f"\n# original_yaml_file: {os.path.basename(input_path)}.yml"
                            f"\n# original_input_files: {original_files}\n")
            
            with open(output_path + ext, "w") as o:
                def original_header() -> str:
                    for file in f'{input_path}{ext}', f'{input_path}.c':
                        if not os.path.exists(file):
                            continue
                        with open(file, 'r') as r:
                            content = r.read().splitlines()
                        header = []
                        while content:
                            line_content = content[0].lstrip()
                            if not line_content or line_content.startswith('//'):
                                header.append(content.pop(0))
                            elif line_content.startswith('/*'):
                                while True:
                                    header.append(content[0])
                                    if '*/' in content.pop(0): break
                            else:
                                break
                        if any(header):
                            return '\n'.join(header)
                    return ''
                try:
                    git_hash = os.popen('git rev-parse --short head').read().splitlines()[0]
                except IndexError:
                    git_hash = 'unknown'
                o.write(
                    self._header
                        .replace('\\n', '\n').replace('\\r', '\r')
                        .replace('{input_file}', os.path.basename(input_path) + ext)
                        .replace('{output_file}', os.path.basename(output_path) + ext)
                        .replace('{trace}', full_trace.replace(': ', ':').replace('\n', ' '))
                        .replace('{commit_hash}', git_hash)
                        .replace('{original_header}', original_header())
                )
                o.write(transformed)
            
            output_files.append({"file_path": output_path + ext, "trace": trace})

        return [{
            "source_file": file_name, 
            "output"     : output_files,
            "walltime"   : time() - start_time
        }]
        


# Parsing input arguments ----------------------------------------------------------------

def dedup_input_files(args, input_files):
    
    def _exists(file_name):
        output_path = os.path.join(args.output_dir, os.path.basename(file_name))
        return not os.path.exists(output_path)

    return list(filter(_exists, input_files))


def _parse_task_file(task_file_path):
    with open(task_file_path, 'r') as task_file:
        task_file = yaml.safe_load(task_file)

    return os.path.join(os.path.dirname(task_file_path), task_file["input_files"])


def _parse_set_files(path_to_set):
    with open(path_to_set, "r") as f:
        input_files = [line.strip() for line in f.readlines()]
    
    output = []
    for file_name in input_files:
        file_name  = os.path.join(os.path.dirname(path_to_set), file_name)
        file_names = glob(file_name)
        
        for subfile_name in file_names:
            if subfile_name.endswith(".c")     : output.append(subfile_name)
            elif subfile_name.endswith(".i")   : output.append(subfile_name)
            elif subfile_name.endswith(".yml") : output.append(_parse_task_file(subfile_name))
            else                               : raise ValueError(f"Unsupported file type: {subfile_name}")


    return output


def parse_input_files(input_files):
    output = []
    for input_file in input_files:
        if input_file.endswith(".set")  : output.extend(_parse_set_files(input_file))
        elif input_file.endswith(".c")  : output.append(input_file)
        elif input_file.endswith(".i")  : output.append(input_file)
        else                            : raise ValueError(f"Unsupported file type: {input_file}")
    
    return output


def prepare_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_files", nargs = "+",
                        help = ".c or .i file to transform or .set file pointing to several .yml files")
    parser.add_argument("--required_transforms", type = str, default = (), nargs = "+",
                        help = "a required transformation not being executed will be treated as an error")
    parser.add_argument("-o", "--output_dir", type = str, required = True,
                        help = "file to put the transformed files into")
    parser.add_argument("--num_transforms", type = int, default = [None], nargs = "+",
                        help = "the number of consecutive transformations to do on each file")
    parser.add_argument("--trace", type = str, default = None, nargs = "+",
                        help = "a trace to reproduce a sequence of transformations")
    parser.add_argument("--recursion_limit", type = int, default = 5000,
                        help = "limits the recursion depht while traversing the abstract syntax tree")
    parser.add_argument("--prefix", type = str, default = '', help = "prefix for folder and file names")
    parser.add_argument("--suffix", type = str, default = '', help = "suffix for folder and file names")
    parser.add_argument("--header", type = str, default = '', help = "header prefixed to transformed sources files")
    parser.add_argument("--header_file", type = str, default = '', help = "path to header text")
    parser.add_argument("--no_dedup", action = "store_true", help = "prevents overriding of already existing files")
    parser.add_argument("--pretty_names", action = "store_true", help = "creates pretty names which are not obfuscated")

    for transform_name in TRANSFORM_NAMES:
        help = f"transformation {transform_name}"
        transform = transform_by_name(transform_name)
        if isinstance(transform, _TransformerFN):
            help += ' composed of: ' + ', '.join(transform.func.__name__ for transform, _ in transform._transformer.trans)
        parser.add_argument(f"--{transform_name}", action = "store_true", help = help)

    parser.add_argument("--parallel", action = "store_true",
                        help = "makes the transformation of different files run in parallel")
    parser.add_argument("--generate_benchmark", action = "store_true",
                        help = "keeps the folder structure of the original and copies .yml files")
    parser.add_argument("--benchmark_comparison", action = "store_true",
                        help = "creates a folder for each number in --num_transforms")

    return parser


def copy_info_files(folder, folder_out):
    if not os.path.exists(folder_out):
        os.makedirs(folder_out)
    for file in os.listdir(folder):
        if 'license' in os.path.basename(file).lower():
            shutil.copy(os.path.join(folder, file), os.path.join(folder_out, file))
        if 'readme' in os.path.basename(file).lower():
            with open(os.path.join(folder, file), 'r') as r:
                readme = r.read()
            with open(os.path.join(folder_out, file), 'w+') as w:
                w.write(f'{readme}\n\ntransformed with semtransforms\n'
                        f'https://github.com/Flo0112358/semtransforms')


def main(*args):
    args = prepare_parser().parse_args(args)

    print("Search for input files...")

    input_files = parse_input_files(args.input_files)

    if args.no_dedup:
        input_files = dedup_input_files(args, input_files)

    # Guarantees that files of similar complexity are batched together
    input_files = sorted(input_files, key = lambda path: os.stat(path).st_size)

    print(f"Found {len(input_files)} files...\n"
          f"Start transformation...")
    
    transformer = FileTransformer(args)

    if args.generate_benchmark:
        folders = {os.path.dirname(file) for file in input_files}
        for folder in folders:
            basename = args.prefix + os.path.basename(folder) + args.suffix
            if args.benchmark_comparison:
                for i in range(len(args.num_transforms)):
                    copy_info_files(folder, os.path.join(args.output_dir, str(i), basename))
            else:
                copy_info_files(folder, os.path.join(args.output_dir, basename))

    # Run mapreduce
    mapreduce(input_files, transformer, reducer_fn = args.output_dir, parallel = args.parallel, report = True)


if __name__ == '__main__':
    main(*sys.argv[1:])
