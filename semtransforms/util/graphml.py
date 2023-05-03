import networkx as nx
import networkx.readwrite.graphml as graphml
import matplotlib.pyplot as plt


def show(graph: nx.Graph):
    layout = nx.spring_layout(graph, iterations=50)
    plt.figure(figsize=(15, 15), dpi=80)
    nx.draw(graph, layout, with_labels=True)
    nx.draw_networkx_edge_labels(graph, layout, label_pos=.4, rotate=False)
    plt.show()


def parse(file) -> nx.Graph:
    """
    This is vulnerable to malicious xml files:
    https://networkx.org/documentation/stable/reference/readwrite/graphml.html

    """
    return graphml.read_graphml(file)


def write(graph: nx.Graph, file: str):
    nx.write_graphml(graph, file, named_key_ids=True)

    # nx only knows the name of the nodes, some details need to be corrected in the file
    with open(file, 'r') as f:
        content = f.read()

    content = content.replace('True', 'true').replace('False', 'false')
    for old, new in (
            ('isEntryNode', 'entry'),
            ('sourcecodeLanguage', 'sourcecodelang'),
            ('programFile', 'programfile'),
            ('programHash', 'programhash'),
            ('creationTime', 'creationtime')
    ):
        content = content.replace(f'id="{old}"', f'id="{new}"').replace(f'key="{old}"', f'key="{new}"')

    with open(file, 'w+') as f:
        f.write(content)




