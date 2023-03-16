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

from semtransforms import TRANSFORM_NAMES, transform_by_name


# Transformer ---------------------------------------------------------------------------

class FileTransformer:

    def __init__(self, config):
        self._output_dir = config.output_dir
        self._num_transforms = config.num_transforms
        self._recursion_limit = config.recursion_limit
        self._generate_benchmark = config.generate_benchmark
        self._prefix = config.prefix
        self._suffix = config.suffix

        self._transforms = [transform_by_name(name) for name in TRANSFORM_NAMES if getattr(config, name, False)]
        self._required_transforms = config.required_transforms

        assert len(self._transforms) > 0, f"You have to select at least one transform from {TRANSFORM_NAMES}"

    def __call__(self, file_name):
        sys.setrecursionlimit(self._recursion_limit)

        if len(self._transforms) == 1:
            transform = self._transforms[0]
        else:
            transform = random.choice(self._transforms)

        with open(file_name, 'r') as f:
            source_code = f.read()

        num_transforms = None if self._num_transforms <= 0 else self._num_transforms

        start_time = time()

        try:
            transforms = transform(source_code, n = num_transforms)
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
        for required_transform in self._required_transforms:
            if required_transform not in transforms[-1][1]:
                return [{
                    "source_file": file_name,
                    "exception"  : f"missing required transformation '{required_transform}' in '{transforms[-1][1]}'",
                    "walltime"   : time() - start_time,
                }]

        output_files = []
        for i, (transformed, trace) in enumerate(transforms):
            output_path = os.path.join(self._output_dir, os.path.basename(file_name))
            if self._generate_benchmark:
                output_path = os.path.join(self._output_dir,
                                           self._prefix + os.path.basename(os.path.dirname(file_name)) + self._suffix,
                                           os.path.basename(file_name))

            input_path, _ = os.path.splitext(file_name)
            output_path, ext = os.path.splitext(output_path)
            output_path = (output_path.removesuffix(os.path.basename(output_path)) +
                           self._prefix + os.path.basename(output_path) + self._suffix)
            if len(transforms) > 1:
                output_path += f"-{i}"

            if self._generate_benchmark:
                with open(input_path + '.yml', 'r') as r:
                    yml = yaml.safe_load(r)
                yml['input_files'] = os.path.basename(output_path) + ext
                with open(output_path + '.yml', 'w+') as w:
                    yaml.dump(yml, w)
            
            with open(output_path + ext, "w") as o:
                if not 'func_' in transformed:
                    print(f'weird: {file_name}, num: {num_transforms}, trace: {trace}')
                    o.write('weird\n')
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
    parser.add_argument("input_files", nargs = "+")
    parser.add_argument("--required_transforms", type = str, nargs = "+")
    parser.add_argument("-o", "--output_dir", type = str, required = True)
    parser.add_argument("--num_transforms", type = int, default = -1)
    parser.add_argument("--recursion_limit", type = int, default = 5000)
    parser.add_argument("--prefix", type = str, default = '')
    parser.add_argument("--suffix", type = str, default = '')
    parser.add_argument("--no_dedup", action = "store_true")

    for transform_name in TRANSFORM_NAMES:
        parser.add_argument(f"--{transform_name}", action = "store_true")

    parser.add_argument("--parallel", action = "store_true")
    parser.add_argument("--generate_benchmark", action = "store_true")

    return parser


def main(*args):
    args = prepare_parser().parse_args(args)

    print("Search for input files...")

    input_files = parse_input_files(args.input_files)

    if args.no_dedup:
        input_files = dedup_input_files(args, input_files)

    # Gurantees that files of similar complexity are batched together
    input_files = sorted(input_files, key = lambda path: os.stat(path).st_size)

    print(f"Found {len(input_files)} files...\n"
          f"Start transformation...")
    
    transformer = FileTransformer(args)

    if args.generate_benchmark:
        folders = {os.path.dirname(file) for file in input_files}
        for folder in folders:
            folder_out = os.path.join(args.output_dir, args.prefix + os.path.basename(folder) + args.suffix)
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

    # Run mapreduce
    mapreduce(input_files, transformer, reducer_fn = args.output_dir, parallel = args.parallel, report = True)


if __name__ == '__main__':
    main(*sys.argv[1:])
