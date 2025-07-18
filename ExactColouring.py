import numpy as np
from scipy.sparse import lil_matrix
import pyomo.environ as pm
import matplotlib.pyplot as plt
from time import perf_counter
import math

def erdos_renyi_partitioned(n, p, P):
    """
    Creates an Erdős-Rényi graph with n nodes and edge probability p,
    with no edges between nodes in the same partition.

    Args:
        n (int): The number of nodes in the graph.
        p (float): The probability of an edge existing between two nodes
                   in different partitions.
        P (list or numpy.ndarray): A list or array of length n, where P[i]
                                   represents the partition assignment of node i.

    Returns:
        scipy.sparse.lil_matrix: A sparse matrix representing the graph's
                                  adjacency matrix.  The matrix is symmetric.
    """
    # Initialize an empty sparse matrix in LIL format for efficient modification.
    A = lil_matrix((n, n))

    # Iterate over all pairs of nodes (i, j) with i < j
    for i in range(n):
        for j in range(i + 1, n):
            # Check if nodes i and j are in different partitions
            if P[i] != P[j]:
                # Generate a random number between 0 and 1
                if np.random.rand() < p:
                    # Add edges (i, j) and (j, i) to the graph.  Since A is a
                    # sparse matrix, assigning to A[i,j] and A[j,i] is efficient.
                    A[i, j] = 1
                    A[j, i] = 1  # Ensure symmetry

    return A

###########################################################################

def erdos_renyi(n, p):
    """
    Creates an Erdős-Rényi graph with n nodes and edge probability p,

    Args:
        n (int): The number of nodes in the graph.
        p (float): The probability of an edge existing between two nodes
                   in different partitions.

    Returns:
        scipy.sparse.lil_matrix: A sparse matrix representing the graph's
                                  adjacency matrix.  The matrix is symmetric.
    """
    # Initialize an empty sparse matrix in LIL format for efficient modification.
    A = lil_matrix((n, n))

    # Iterate over all pairs of nodes (i, j) with i < j
    for i in range(n):
        for j in range(i + 1, n):
            # Generate a random number between 0 and 1
            if np.random.rand() < p:
                # Add edges (i, j) and (j, i) to the graph.  Since A is a
                # sparse matrix, assigning to A[i,j] and A[j,i] is efficient.
                A[i, j] = 1
                A[j, i] = 1  # Ensure symmetry

    return A

###########################################################################


def check_coloring(A, colors, verbose = True):
    """
    Verifies if a proposed coloring is correct
    """
    correct = True
    n = A.shape[0]
    for i in range(n):
        for j in range(n):
            if A[i,j] != 0:
                if colors[i] == colors[j]:
                    if verbose:
                        print(f"Violation ({i},{j}):{ilp_colors[i]}")
                    correct = False
    if correct and verbose:
        print("Coloring is valid")
    return correct   

###########################################################################

def dsatur_coloring(adjacency_matrix):
    """
    Applies the Dsatur algorithm to color the graph represented by the
    adjacency matrix.

    Args:
        adjacency_matrix (scipy.sparse.lil_matrix):  The adjacency matrix of the graph.
            It is assumed to be symmetric.

    Returns:
        list: A list of integers, where the i-th element represents the color
              assigned to the i-th node. Colors are represented by non-negative
              integers (0, 1, 2, ...).
    """
    n = adjacency_matrix.shape[0]  # Number of nodes
    colors = [-1] * n  # Initialize all nodes to be uncolored (-1)
    saturation_degrees = [0] * n  # Initialize saturation degrees to 0
    available_colors = [set() for _ in range(n)] # Keep track of available colors for each node.

    # Find the node with the maximum degree (number of neighbors)
    degrees = [adjacency_matrix[i].getnnz() for i in range(n)]
    max_degree_node = np.argmax(degrees)

    # Color the node with the maximum degree with the first color (0)
    colors[max_degree_node] = 0
    available_colors[max_degree_node].add(0)

    # Update saturation degrees of neighbors
    for neighbor in adjacency_matrix[max_degree_node].nonzero()[1]:
        saturation_degrees[neighbor] += 1
        available_colors[neighbor].add(0)

    # Color the remaining nodes
    for _ in range(1, n):
        # Find the node with the maximum saturation degree
        max_sat_node = -1
        max_sat_degree = -1
        max_degree = -1
        for i in range(n):
            if colors[i] == -1 and saturation_degrees[i] >= max_sat_degree:
                if saturation_degrees[i]>max_sat_degree:
                    max_degree = degrees[i]
                    max_sat_degree = saturation_degrees[i]
                    max_sat_node = i
                elif degrees[i]>max_degree:
                    max_degree = degrees[i]
                    max_sat_node = i

        # Color the node with the smallest available color
        min_color = 0
        while min_color in available_colors[max_sat_node]:
            min_color += 1
        colors[max_sat_node] = min_color
        #available_colors[max_sat_node].add(min_color)

        # Update saturation degrees of neighbors
        for neighbor in adjacency_matrix[max_sat_node].nonzero()[1]:
            if colors[neighbor] == -1:
                saturation_degrees[neighbor] += 1
                available_colors[neighbor].add(min_color)

    return colors

#####################################################
# Representative constraint satifaction model for graph coloring

# The constraints
def col_con(model, i):
    return sum(model.x[i, :]) == 1

def edge_con(model, i, j, c):
    return model.x[i, c] + model.x[j, c] <= model.y[c]

def break_symmetry(model, c):
    if model.C.first() == c:
        return 0 <= model.y[c]
    else:
        c_prev = model.C.prev(c)
        return model.y[c] <= model.y[c_prev]
    
def break_symmetry_agg(model, c):
    if model.C.first() == c:
        return 0 <= sum(model.x[:, c])
    else:
        c_prev = model.C.prev(c)
        return sum(model.x[:, c]) <= sum(model.x[:, c_prev])

# The objective function - minimize the number of colors    
def obj(model):
    return sum(model.y[:])

def ass_colors(n, edges, k, node_colors):
    # n is the number nodes, k the maximum number of colors to consider
    # edges encodes the graph, and node_colors is an approximate initial coloring

    model = pm.ConcreteModel()

    model.C = pm.Set(initialize=range(k))
    model.N = pm.Set(initialize=range(n))
    model.E = pm.Set(initialize=edges)

    model.x = pm.Var(model.N, model.C, within=pm.Binary)
    model.y = pm.Var(model.C, within=pm.Binary)

    model.col_con = pm.Constraint(model.N, rule=col_con)
    model.edge_con = pm.Constraint(model.E, model.C, rule=edge_con)
    model.break_symmetry = pm.Constraint(model.C, rule=break_symmetry)

    model.obj = pm.Objective(rule = obj)

    solver = pm.SolverFactory("appsi_highs")

    # Encode the initial colors
    for i in range(n):
        for c in range(k):
            if node_colors[i] == c:
                model.x[i, c].value = 1.0
            else:
                model.x[i, c].value = 0.0

    for c in range(k):
        model.y[c].value = 1.0

    # Solve the problem
    res = solver.solve(model)

    # Decode the found colors
    colors=[-1] * n
    for i in range(n):
        for c in range(k):
            if round(model.x[i,c].value) == 1:
                if colors[i] != -1:
                    print("Error: repeated color") 
                colors[i] = c
    
    return colors
#########################################################

#####################################################
# Partial order model for graph coloring

# The constraints
def z_con(model, v):
    return model.z[v, 0] == 0

def yorder_con(model, i, v):
    return model.y[i,v]-model.y[i+1,v] >= 0

def yzorder_con(model, i, v):
    return model.y[i,v]+model.z[v,i+1] == 1

def edge_con1(model, i, u, v):
    return model.y[i, u] + model.z[u,i] + model.y[i,v] + model.z[v,i] >= 1



    
def pop_colors(n, edges, k, node_colors):
    # n is the number nodes, k the maximum number of colors to consider
    # edges encodes the graph, and node_colors is an approximate initial coloring

    q = 0

    # Additional constraints that depend on k and q
    def y_con(model, v):
        return model.y[k-1, v] == 0
    
    def pop_obj(model):
        return 1+sum(model.y[:,q])
    
    def q_con(model, i, v):
        return model.y[i,q]-model.y[i,v] >= 0


    model = pm.ConcreteModel()

    model.C = pm.Set(initialize=range(k))
    model.CM1 = pm.Set(initialize=range(k-1))
    model.N = pm.Set(initialize=range(n))
    model.E = pm.Set(initialize=edges)

    model.y = pm.Var(model.C, model.N, within=pm.Binary)
    model.z = pm.Var(model.N, model.C, within=pm.Binary)

    model.y_con = pm.Constraint(model.N, rule=y_con)
    model.z_con = pm.Constraint(model.N, rule=z_con)
    model.yorder_con = pm.Constraint(model.CM1, model.N, rule=yorder_con)
    model.yzorder_con = pm.Constraint(model.CM1, model.N, rule=yzorder_con)
    model.edge_con = pm.Constraint(model.C, model.E, rule=edge_con1)
    model.q_con = pm.Constraint(model.C, model.N, rule=q_con)

    model.obj = pm.Objective(rule = pop_obj)
    
    solver = pm.SolverFactory("appsi_highs")
 
    # Solve the problem
    res = solver.solve(model)

    # decode the colors
    colors=[-1] * n
    for v in range(n):
        for i in range(k):
            if round(model.y[i,v].value) == 0 and round(model.z[v,i].value) == 0:
                if colors[v] != -1:
                    print("Error: repeated color") 
                colors[v] = i
    
    return colors
#########################################################

if __name__ == '__main__':
    s = 0.5  # Edge probability
    
    samples = 1

    f = open("output.txt","w")
    f.write("n planted_k desatur_k exact_k exact_t status\n")

    #y = 3.9892e0.2743x

    # Compare inexact desatur algorithm with exact partial order model solution
    for n in range(54,150,1):
        for i in range(samples):
            # Find the empirically derived k for this size graph
            k=round(3.646*math.log(0.251*n))

            # Graph partitions
            popt = math.ceil(n/k)
            P = [i for j in range(popt) for i in range(k)]  # Partition assignments for each node
            P = P[:n]

            # Calculate corrected edge probabilty
            S=0
            for i in range(k):
                ni=P.count(i)
                S+=ni*(ni-1)
            p=s*n*(n-1)/(n*(n-1)-S)

            # Generate the planted graph
            graph_matrix = erdos_renyi_partitioned(n, p, P)
            
            # Apply Dsatur coloring
            node_colors = dsatur_coloring(graph_matrix)
            print("c",end="")

            # Find exact solution (k>=10 takes a long time)
            if k<10:
                # generate graph edges
                edges = []
                n = graph_matrix.shape[0]
                for i in range(n):
                    for j in graph_matrix[i].nonzero()[1]:
                        if j > i:  # Avoid duplicate edges in undirected graph
                            edges.append((i, j))

                time = perf_counter()
                ilp_colors = pop_colors(n, edges, max(node_colors)+1, node_colors)
                time = perf_counter() - time
            else:
                ilp_colors=[0] * n
                time = 0
 
            print(".",end="")

            f.write(f"{n} {k} {len(set(node_colors))} {len(set(ilp_colors))} {time} ")
            if not check_coloring(graph_matrix,ilp_colors, verbose = False):
                f.write("failed\n")
            else:
                f.write("ok\n")
            
            f.flush()
        print(f" Finished n={n}")

 
    f.close()           
