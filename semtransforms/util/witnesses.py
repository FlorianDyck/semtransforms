import networkx as nx
from pycparser import c_ast

import graphml


def build_witness(ast: c_ast.Node, witness_file: str):
    graph = graphml.parse(witness_file)
    # TODO: map the id of every node in the ast to the nodes in the witness graph which need to be changed with it
    return {id: node for node in graph.nodes}


def dump_witness(ast: c_ast.Node, lines: dict[c_ast.Node, int], node_mapping: dict[c_ast.Node, object],
                 witness: nx.Graph, file: str):
    # TODO: put the lines into the witness and save it to the file
    graphml.write(witness, file)
