from xml.etree.ElementTree import Element

import pycparser.plyparser
from pycparser import c_ast
from xml.etree import ElementTree

from semtransforms import parse


def search(ast: c_ast.Node):
    yield ast
    for child in ast:
        yield from search(child)


class Node:
    def __init__(self, element: Element):
        self._element = element
        self.id = element.attrib['id']
        self.data = {node.attrib['key']: node.text for node in element}

    def __repr__(self):
        return f'{self.id} {self.data}'


class Edge:
    def __init__(self, element: Element, nodes: dict[str, Node]):
        self._element = element
        self.source = nodes[element.attrib['source']]
        self.target = nodes[element.attrib['target']]
        self.data = {node.attrib['key']: node.text for node in element}
        self.startline = int(self.data.pop('startline'))
        self.endline = int(self.data.pop('endline'))
        self.startoffset = int(self.data.pop('startoffset'))
        self.endoffset = int(self.data.pop('endoffset'))

    def __repr__(self):
        return (f'{self.source} -> {self.target} '
                f'(lines {self.startline}-{self.endline}, '
                f'offset {self.startoffset}-{self.endoffset}, '
                f'{self.data})')


def matching_edges(coord: pycparser.plyparser.Coord, edges: list[Edge]):
    return


class Witness:
    def __init__(self, ast: c_ast.Node, file):
        """
        This is vulnerable to malicious xml files:
        https://docs.python.org/3/library/xml.etree.elementtree.html

        """
        self._element_tree = ElementTree.parse(file)
        self._root = [node for node in self._element_tree.getroot() if node.tag.endswith('graph')][0]
        self.nodes = [Node(node) for node in self._root if node.tag.endswith('node')]
        self.nodes = {node.id: node for node in self.nodes}
        self.edges = [Edge(node, self.nodes) for node in self._root if node.tag.endswith('edge')]
        # TODO: map the id of every node in the ast to the nodes in the witness graph which need to be changed with it
        self.map = {id(node): (node, [edge for edge in self.edges
                                      if edge.startline <= node.coord.line <= edge.endline])
                    for node in search(ast) if node.coord}
        pass


    def write(self, file: str):
        # TODO: put the lines into the witness and save it to the file
        self._element_tree.write(file)


with open('examples/witnesses/proofwitness1.c', 'r') as r:
    ast = parse(r.read())
witness_file = 'examples/witnesses/proofwitness1.graphml'
result = Witness(ast, witness_file)
pass


