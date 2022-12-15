import argparse
import os
import yaml
import shutil

from glob import glob


def _parse_task_file(task_file_path):
    with open(task_file_path, 'r') as task_file:
        task_file = yaml.safe_load(task_file)

    return os.path.join(os.path.dirname(task_file_path), task_file["input_files"])


def _parse_set_file(path_to_set):
    with open(path_to_set, "r") as f:
        input_files = [line.strip() for line in f.readlines()]

    for file_name in input_files:
        file_name  = os.path.join(os.path.dirname(path_to_set), file_name)
        file_names = glob(file_name)
        
        for subfile_name in file_names:
            yield subfile_name
            if subfile_name.endswith(".yml") : yield _parse_task_file(subfile_name)


def _iter_files(input_files):
    for input_file in input_files:
        yield input_file

        if input_file.endswith(".set"):
            for file_path in _parse_set_file(input_file):
                yield file_path



def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("transformed_dir")
    parser.add_argument("output_dir")
    parser.add_argument("input_files", nargs="+")
    args = parser.parse_args()

    if os.path.exists(args.output_dir):
        shutil.rmtree(args.output_dir)
    os.makedirs(args.output_dir)

    count = 0
    transfer = 0

    for input_file_path in _iter_files(args.input_files):
        output_dir = os.path.basename(os.path.dirname(input_file_path))
        if output_dir == "c": output_dir = ""
        output_dir = os.path.join(args.output_dir, "c", output_dir)
        if not os.path.exists(output_dir): os.makedirs(output_dir)
        output_path = os.path.join(output_dir, os.path.basename(input_file_path))

        transfer_path = os.path.join(args.transformed_dir, os.path.basename(input_file_path))
        if not os.path.exists(transfer_path):
            transfer_path = input_file_path
        else:
            transfer += 1
        
        shutil.copy(transfer_path, output_path)
        count += 1
        if count % 100 == 0 and count > 0: print(f"Copied {count} files")

    print(f"Copied {count} files")
    print(f"Transfered {transfer} / {count} files")


if __name__ == '__main__':
    main()