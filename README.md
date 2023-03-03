# SemTransform
> Benchmark Generation for Software Verifiers via Reachability-Preserving Transformations

Benchmarking of software verifiers is difficult. Existing verification benchmarks are often too small to test every little detail of the verifier implementation and extended the benchmark often requires a significant manual effort. With SemTransform, we introduce an easy way to improve an existing benchmark for C software verifiers by Reachability-Preserving Transformations. 

SemTransform expects a verification task (especially those focused on the reachability of an error location) and then applies several transformations that do not alter the reachability of an error location. As a result, SemTransform can be used to create new benchmarks for C verifiers that test a larger variety of C features. 

## Installation
The package is tested under Python 3.10. It can be installed by cloning this repository and installing all requirements via:
```
pip install -r requirements.txt
```

## Quick start
SemTransform implement several reachability preserving transformations. To transform an existing benchmark (in the [SV-COMP](https://sv-comp.sosy-lab.org/2023/rules.php) format), you can run the following script:
```bash
$ python run_transformations.py [input_files] -o [output_dir] --num_transforms 100 --spin_config [--parallel]
```
The script applies one of several transformation randomly to the given input files. Transformations are applied one after another (up to certain limit; here 100 transformations). The input files may contain .c, .i and .set files. If you transform multiple files, it can be beneficial to run the transformation in parallel (via the `--parallel` option).

The following scripts generated the examples.
They and their input files are a minimal example for how a benchmark might look like.

```bash
$ python run_transformations.py examples/in/main.c examples/in/main.i -o examples/out/source --num_transforms 100 --spin_config
```

```bash
$ python run_transformations.py examples/in/main.set -o examples/out/set --num_transforms 100 --spin_config
```

SemTransforms support a number of predefined transformation configurations. You can get a full list by running:
```bash
$ python run_transformations.py --help
```

## Project Info
This is currently developed as a helper library for internal research projects. Therefore, it will only be updated as needed.

Feel free to open an issue if anything unexpected
happens. 

Distributed under the Attribution-ShareAlike 4.0 license. See ``license.text`` for more information.