import random
import networkx as nx
import matplotlib.pyplot as plt

def generate_bipartite_graph(*n_sets, p_edge=0.5):
    G = nx.Graph()
    sets = []
    color = 1
    start_node_id = 0  
    for n in n_sets:
        current_set = list(range(start_node_id, start_node_id + n))  
        sets.append(current_set)
        for node in current_set:
            G.add_node(node, color=color)
        start_node_id += n  
        color += 1
    for i in range(len(sets)):
        for j in range(i + 1, len(sets)):
            for node1 in sets[i]:
                for node2 in sets[j]:
                    if random.random() < p_edge:
                        G.add_edge(node1, node2)

    return G

def draw_multipartite_graph(G):
    subset_key = {}
    max_color = max([G.nodes[n]['color'] for n in G.nodes()])
    for color in range(1, max_color + 1):
        subset_key[color] = [n for n in G.nodes() if G.nodes[n]['color'] == color]
    pos = nx.multipartite_layout(G, subset_key=subset_key)
    colors = [G.nodes[n]['color'] for n in G.nodes()]
    
    plt.figure(figsize=(12, 8))
    nx.draw(G, pos, with_labels=True, node_color=colors, node_size=500, font_size=10, font_weight='bold', cmap=plt.cm.Paired)
    plt.show()

n_sets = [5, 6, 4, 3, 7, 8, 9, 3 , 7 , 5 ,2, 4]  
p_edge = 0.6  
G = generate_bipartite_graph(*n_sets, p_edge=p_edge)
draw_multipartite_graph(G)

print("Edges in the generated graph:")
for edge in G.edges():
    print(edge)
