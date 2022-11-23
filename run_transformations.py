import os
import sys
import argparse
import yaml
import random

from glob import glob
from time import time

from mapreduce import mapreduce

from semtransforms import AVAILABLE_TRANSFORMS
from semtransforms import transform_by_name


# Transformer ---------------------------------------------------------------------------

class FileTransformer:

    def __init__(self, config):
        self._transforms = []
        self._output_dir = config.output_dir
        self._num_transforms = config.num_transforms

        for transform_name in AVAILABLE_TRANSFORMS:
            if getattr(config, transform_name, False):
                self._transforms.append(transform_by_name(transform_name))

        assert len(self._transforms) > 0, f"You have to select at least one transform from {AVAILABLE_TRANSFORMS}"

    def __call__(self, file_name):
        if len(self._transforms) == 1:
            transform = self._transforms[0]
        else:
            transform = random.choice(self._transforms)

        with open(file_name, 'r') as f:
            source_code = f.read()

        start_time = time()

        output_files = []
        for i, (transformed, trace) in enumerate(transform(source_code)):
            output_path = os.path.join(self._output_dir, os.path.basename(file_name))
            
            if i > 0:
                output_path, ext = os.path.splitext(output_path)
                output_path = output_path + f"-{i}" + ext
            
            with open(output_path, "w") as o:
                o.write(transformed)
            
            output_files.append({"file_path": output_path, "trace": trace})

        return [{
            "source_file": file_name, 
            "output"     : output_files,
            "walltime"   : time() - start_time
        }]
        


# Parsing input arguments ----------------------------------------------------------------

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
    parser.add_argument("-o", "--output_dir", type = str, required = True)
    parser.add_argument("--num_transforms", type = int, default = 1)

    for transform_name in AVAILABLE_TRANSFORMS:
        parser.add_argument(f"--{transform_name}", action = "store_true")

    parser.add_argument("--parallel", action = "store_true")

    return parser


def main(argv = None):
    if argv is None: argv = sys.argv
    args = prepare_parser().parse_args(args = argv[1:])

    print("Search for input files...")


    input_files = parse_input_files(args.input_files)

    # Gurantees that files of similar complexity are batched together
    input_files = sorted(input_files, key = lambda path: os.stat(path).st_size)

    print(f"Found {len(input_files)} files...")
    print("Start transformation...")
    
    transformer = FileTransformer(args)
    
    # Run mapreduce
    mapreduce(transformer, input_files, reduce_fn = args.output_dir, parallel = args.parallel)



if __name__ == '__main__':
    main()