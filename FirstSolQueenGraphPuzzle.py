import numpy as np

def initial_solution(n):

    board = np.zeros((n, n), dtype=int)
    
    # Particular case
    if n == 1:
        board[0, 0] = 1
        return board
    if n in [2, 3]:
        raise ValueError("No Solution for n = 2 ou n = 3.")
    
    r = n % 6
    positions = []  

    # first case : n = 6k ou n = 6k+4
    if r in [0, 4]:
        half = n // 2
        for i in range(1, half + 1):
            positions.append((2 * i, i))  
        for i in range(1, half + 1):
            positions.append((2 * i - 1, half + i))
        print("The use of the first class: A (A₁ et A₂)")

    # second case : n = 6k+1 ou n = 6k+5
    elif r in [1, 5]:
        half = (n - 1) // 2
        positions.append((n, 1))  # B1 = {(n, 1)}
        for i in range(1, half + 1):
            positions.append((2 * i, i + 1))  # B2 = {(2i, i+1)}
        for i in range(1, half + 1):
            positions.append((2 * i - 1, half + i + 1))  # B3 = {(2i-1, (n+1)/2 + i)}
        print("The use of the second class B (B₁, B₂ et B₃)")

    # third case: n = 6k+2
    elif r == 2:
        half = n // 2
        positions.extend([(4, 1), (n, half - 1), (2, half), (n - 1, half + 1), 
                           (1, half + 2), (n - 3, n)])  # C1 to C6
        # C7 
        for i in range(1, half - 2):
            positions.append((n - 2 * i, i + 1))
        # C8 
        for i in range(1, half - 2):
            positions.append((n - 2 * i - 3, half + i + 2))
        print("The use of the third class C (C₁ à C₈)")

    # Fourth case : n = 6k+3
    elif r == 3:
        smaller_board = initial_solution(n - 1)  #recursif call of (n-1)x(n-1)
        for i in range(n - 1):
            for j in range(n - 1):
                if smaller_board[i, j] == 1:
                    positions.append((i + 1, j + 1))
        positions.append((n, n))  # add the queen in the top right
        print("The use of the fourth class D")

    # fulling the matrix by the indexes calculated
    for row, col in positions:
        board[row - 1, col - 1] = 1  # convert with 0 index for python



    return board

n = 14
solution = initial_solution(n)
print(solution)
