import os
import gzip
import json
import multiprocessing as mp

from pathos.pools import ProcessPool

from tqdm import tqdm
from contextlib import contextmanager

# Jsonl (GZ) handler --------------------------------------------------------------------

class JsonlSaver:

    def __init__(self, save_dir, gzip_compress = False, num_objects = 1e5):
        self.save_dir = save_dir
        self.num_objects = num_objects
        self.gzip_compress = gzip_compress
        
        self._file_ending = ".jsonl.gz" if gzip_compress else ".jsonl"

        self.object_count = 0
        self.file_count   = 0

        self.file_handler = None
        self._find_unique_index()
        self._update_handler()

    def _file_path(self):
        return os.path.join(self.save_dir, "statistics-%d%s" % (self.file_count, self._file_ending))

    def _find_unique_index(self):
        while os.path.exists(self._file_path()):
            self.file_count += 1

    def _open_file(self, file_path):
        if self.gzip_compress:
            return gzip.open(file_path, "wb")
        else:
            return open(file_path, "wb")

    def _update_handler(self):
        
        need_update = self.file_handler is None or self.object_count >= self.num_objects
        if not need_update: return

        file_path = self._file_path()

        if self.file_handler is not None: self.file_handler.close()

        self.file_handler = self._open_file(file_path)
        self.file_count += 1
        self.object_count = 0

    def save(self, obj):
        json_obj = json.dumps(obj) + "\n"
        self.file_handler.write(json_obj.encode("utf-8"))
        self.object_count += 1
        self._update_handler()

    def close(self):
        if self.file_handler is not None:
            self.file_handler.close()
        self.file_handler = None


@contextmanager
def jsonl_reduce_io(output_dir, compress = False):
    saver = JsonlSaver(output_dir, gzip_compress = compress)
    try:
        
        def call_save(obj):
            saver.save(obj)

        yield call_save
    finally:
        saver.close()


# Map multiprocessing ----------------------------------------------------------------

def pmap(map_fn, data):

    cpu_count = mp.cpu_count()

    if cpu_count <= 4: # Too few CPUs for multiprocessing
        for output in map(map_fn, data):
            yield output

    with ProcessPool(processes = cpu_count) as pool:
        for output in pool.uimap(map_fn, data, chunksize = 4 * cpu_count):
            yield output

# Helper ------------------------------------------------------------------


def _reduce_mapped_instances(mapped_instance_stream, reducer_fn):
    # Reduce all mapped instances
    for mapped_instances in mapped_instance_stream:
        if mapped_instances is None: continue

        for mapped_instance in mapped_instances:
            reducer_fn(mapped_instance)


def _reduce_to_file(mapped_instance_stream, dir_path, compress = False):
    with jsonl_reduce_io(dir_path, compress) as saver:
        _reduce_mapped_instances(mapped_instance_stream, saver)


def _reduce_generator(mapped_instance_stream):
    for mapped_instances in mapped_instance_stream:
        if mapped_instances is None: continue

        for mapped_instance in mapped_instances:
            yield mapped_instance


# API method ----------------------------------------------------------------
# Map step runs in parrallel / Reduce in single thread


def mapreduce(data, map_fn, reducer_fn = None, parallel = False, compress = False, report = False):
    """
    Map then reduce functions
    Output of map has to be always a collection
    reducer_fn == None: Same as pmap / map
    reducer_fn == file_path: Saves all entries to jsonl into a dir
    reducer_fn == callable : Calls reducer with the mapped results
    """

    if parallel:
        mapped_instance_stream = pmap(map_fn, data)
    else:
        mapped_instance_stream = map(map_fn, data)

    if report: mapped_instance_stream = tqdm(mapped_instance_stream, total = len(data))

    if isinstance(reducer_fn, str):
        _reduce_to_file(mapped_instance_stream, reducer_fn, compress)
    elif callable(reducer_fn):
        _reduce_mapped_instances(mapped_instance_stream, reducer_fn)
    else:
        return _reduce_generator(mapped_instance_stream)