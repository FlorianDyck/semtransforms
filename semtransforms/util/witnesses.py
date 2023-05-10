import networkx as nx
import pycparser.plyparser
from networkx.classes.reportviews import OutMultiEdgeView
from pycparser import c_ast

import graphml
from semtransforms import parse


def search(ast: c_ast.Node):
    yield ast
    for child in ast:
        yield from search(child)


def matching_edges(coord: pycparser.plyparser.Coord, edges: OutMultiEdgeView):
    print(edges.__class__)
    print([edge for edge in edges.data()])
    return [edge for edge in edges.data() if
            edge[3]['startline'] <= coord.line and coord.line <= edge[3]['startline']]


def build_witness(ast: c_ast.Node, witness_file: str):
    witness = graphml.parse(witness_file)
    # TODO: map the id of every node in the ast to the nodes in the witness graph which need to be changed with it
    return {id(node): (node, matching_edges(node.coord, witness.edges)) for node in search(ast)}


def dump_witness(ast: c_ast.Node, lines: dict[c_ast.Node, int], node_mapping: dict[c_ast.Node, object],
                 witness: nx.Graph, file: str):
    # TODO: put the lines into the witness and save it to the file
    graphml.write(witness, file)


with open('../../examples/witnesses/proofwitness1.c', 'r') as r:
    ast = parse(r.read())
witness_file = '../../examples/witnesses/proofwitness1.graphml'
result = build_witness(ast, witness_file)



