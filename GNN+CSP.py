import torch
import torch.nn.functional as F
from torch.nn import Module, Linear
import networkx as nx
import matplotlib.pyplot as plt
import numpy as np
from constraint import Problem, AllDifferentConstraint  

class MPNN(Module):
    def __init__(self, num_features, hidden_dim, num_classes):
        super(MPNN, self).__init__()
        torch.manual_seed(12345)

        self.input_mlp = Linear(num_features, hidden_dim)
        self.message_mlp = Linear(hidden_dim, hidden_dim)
        self.update_mlp = Linear(2 * hidden_dim, hidden_dim)
        self.output_mlp = Linear(hidden_dim, num_classes)

    def forward(self, x, edge_index):
        h = F.relu(self.input_mlp(x)) 
        
        for _ in range(3): 
            row, col = edge_index  
            m = F.relu(self.message_mlp(h[col]))  
            m_agg = torch.zeros_like(h).scatter_add_(0, row.unsqueeze(-1).expand_as(m), m)  
            
            h = F.relu(self.update_mlp(torch.cat([h, m_agg], dim=1)))  

        out = self.output_mlp(h)
        return out

def gumbel_softmax(logits, tau=1, hard=False):
    gumbels = -torch.empty_like(logits).exponential_().log()  
    logits = (logits + gumbels) / tau
    y_soft = F.softmax(logits, dim=-1)
    
    if hard:
        index = y_soft.max(dim=-1, keepdim=True)[1]
        y_hard = torch.zeros_like(logits).scatter_(-1, index, 1.0)
        ret = y_hard - y_soft.detach() + y_soft
    else:
        ret = y_soft
    return ret

def potts_model_loss_with_degree(probs, edge_index, degree):
    row, col = edge_index
    
    same_color_prob = torch.sum(probs[row] * probs[col], dim=1)
    
    conflict_weight = (1 - 1 / degree[row])
    conflict_loss = torch.mean(same_color_prob * conflict_weight)  

    entropy_loss = -torch.mean(torch.sum(probs * torch.log(probs + 1e-10), dim=1))
    
    total_loss = conflict_loss + 0.01 * entropy_loss
    return total_loss

def train_with_gumbel(model, x, edge_index, degree, optimizer, temperature=0.5):
    model.train()
    optimizer.zero_grad()
    out = model(x, edge_index)
    
    probs = gumbel_softmax(out, tau=temperature, hard=False)
    loss = potts_model_loss_with_degree(probs, edge_index, degree)
    
    preds = probs.argmax(dim=1)
    
    loss.backward()
    optimizer.step()
    return loss.item(), preds

def remap_colors(preds):
    unique_colors = preds.unique(sorted=True)
    color_mapping = {old_color.item(): new_color for new_color, old_color in enumerate(unique_colors)}
    remapped_preds = preds.clone()
    for old_color, new_color in color_mapping.items():
        remapped_preds[preds == old_color] = new_color
    return remapped_preds, color_mapping

def compute_conflicts(preds, edge_index):
    row, col = edge_index
    conflicts = (preds[row] == preds[col]).sum().item()
    return conflicts

def constraint_refinement(preds, edge_index, num_colors):
    num_nodes = preds.size(0)
    
    problem = Problem()

    for node in range(num_nodes):
        problem.addVariable(node, range(num_colors))

    row, col = edge_index
    for r, c in zip(row.tolist(), col.tolist()):
        problem.addConstraint(AllDifferentConstraint(), [r, c])
    
    solution = problem.getSolution()
    
    if solution:
        refined_preds = torch.tensor([solution[i] for i in range(num_nodes)], dtype=torch.long)
        return refined_preds
    else:
        print("No valid solution found.")
        return preds  

def visualize_colored_graph(graph, colors, title):
    unique_colors = np.unique(colors)
    num_colors = len(unique_colors)

    color_list = plt.cm.tab20(np.linspace(0, 1, num_colors))

    color_mapping = {color: color_list[idx % len(color_list)] for idx, color in enumerate(unique_colors)}

    node_colors = [color_mapping[color] for color in colors]

    pos = nx.circular_layout(graph)

    nx.draw_networkx(
        graph,
        pos,
        node_color=node_colors,
        with_labels=True,
        edge_color='gray'
    )
    plt.title(title)
    plt.show()

def train_and_evaluate():
    n_vertices = 25
    hidden_dim = 64  

    G = nx.Graph()
    for i in range(5):
        for j in range(5):
            G.add_node((i, j))
            for k in range(5):
                if k != i:
                    G.add_edge((i, j), (k, j))  
                if k != j:
                    G.add_edge((i, j), (i, k))  
            for d in range(1, 5):
                if (i + d < 5) and (j + d < 5):
                    G.add_edge((i, j), (i + d, j + d))
                if (i + d < 5) and (j - d >= 0):
                    G.add_edge((i, j), (i + d, j - d)) 
                if (i - d >= 0) and (j + d < 5):
                    G.add_edge((i, j), (i - d, j + d))  
                if (i - d >= 0) and (j - d >= 0):
                    G.add_edge((i, j), (i - d, j - d))  

    G = nx.convert_node_labels_to_integers(G)
    edge_index = torch.tensor(list(G.edges)).t().contiguous()

    if edge_index.size(0) == 0:
        print("Graph has no edges.")
        return

    x = torch.eye(n_vertices)

    degree = torch.tensor([G.degree[i] for i in range(n_vertices)], dtype=torch.float32)

    model = MPNN(num_features=n_vertices, hidden_dim=hidden_dim, num_classes=n_vertices)
    optimizer = torch.optim.Adam(model.parameters(), lr=0.005)  
    num_epochs = 1000
    for epoch in range(num_epochs):  
        loss, preds = train_with_gumbel(model, x, edge_index, degree, optimizer, temperature=0.5)

        num_conflicts = compute_conflicts(preds, edge_index)

        remapped_preds, _ = remap_colors(preds)

        if epoch % 100 == 0:
            print(f"Epoch {epoch}, Loss: {loss:.4f}, Conflicts: {num_conflicts}")
            print(f"Predicted colors: {remapped_preds.numpy()}")

    print(f"Final predicted colors before refinement: {remapped_preds.numpy()}")

    refined_preds = constraint_refinement(preds, edge_index, n_vertices)  
    remapped_refined_preds, _ = remap_colors(refined_preds)
    print(f"Refined colors after constraint refinement: {remapped_refined_preds.numpy()}")

    visualize_colored_graph(G, remapped_refined_preds.numpy(), "Graph Coloring with GNN + Constraint Refinement")

    predicted_colors = len(remapped_refined_preds.unique())
    print(f"Predicted number of colors: {predicted_colors}")

    # comparison with the known chromatic number
    known_chromatic_number = 5 
    error = abs(predicted_colors - known_chromatic_number) / known_chromatic_number * 100
    print(f"Error in number of colors: {error:.2f}%")

train_and_evaluate()
