from __future__ import annotations
from dataclasses import dataclass
from typing import List, Tuple
import hashlib, hmac, secrets, math, time


def H(data: bytes) -> bytes:
    return hashlib.sha256(data).digest()

def encode_uint(x: int, size_bytes: int) -> bytes:
    if x < 0:
        raise ValueError("encode_uint: negative")
    return x.to_bytes(size_bytes, "big", signed=False)

def encode_varbytes(data: bytes) -> bytes:
    return encode_uint(len(data), 8) + data

def int_from_bytes(b: bytes) -> int:
    return int.from_bytes(b, "big", signed=False)

def encode_fs_input(tag: bytes,
                    E_sorted: List[Tuple[int,int]],
                    n: int, k: int,
                    roots: List[bytes],
                    message: bytes) -> bytes:
    if not tag:
        raise ValueError("tag must be non-empty")
    out = bytearray()
    out += tag
    out += encode_uint(n, 4)
    out += encode_uint(k, 4)
    m = len(E_sorted)
    out += encode_uint(m, 4)
    for (u, v) in E_sorted:
        out += encode_uint(u, 4) + encode_uint(v, 4)
    t = len(roots)
    out += encode_uint(t, 4)
    for r in roots:
        out += encode_varbytes(r)
    out += encode_varbytes(message)
    return bytes(out)



def commit_hash(alpha: int, r: bytes, alpha_bytes: int = 1) -> bytes:
    return H(b"commit" + encode_uint(alpha, alpha_bytes) + encode_varbytes(r))

def verify_commit_hash(c: bytes, alpha: int, r: bytes, alpha_bytes: int = 1) -> bool:
    return c == commit_hash(alpha, r, alpha_bytes)


def merkle_leaf(round_i: int, v: int, commit_bytes: bytes) -> bytes:
    return H(b"leaf" + encode_uint(round_i, 4) + encode_uint(v, 4) + encode_varbytes(commit_bytes))

def merkle_parent(left: bytes, right: bytes) -> bytes:
    return H(b"node" + left + right)

@dataclass
class MerkleProof:
    siblings: List[Tuple[bool, bytes]]  

class MerkleTree:
    def __init__(self, leaves: List[bytes]):
        if not leaves:
            raise ValueError("MerkleTree: empty leaves")
        self.levels: List[List[bytes]] = [leaves[:]]
        cur = leaves[:]
        while len(cur) > 1:
            nxt = []
            for i in range(0, len(cur), 2):
                if i+1 < len(cur):
                    nxt.append(merkle_parent(cur[i], cur[i+1]))
                else:
                    nxt.append(merkle_parent(cur[i], cur[i]))
            self.levels.append(nxt)
            cur = nxt

    def root(self) -> bytes:
        return self.levels[-1][0]

    def proof(self, index: int) -> MerkleProof:
        idx = index
        siblings: List[Tuple[bool, bytes]] = []
        for lvl in range(0, len(self.levels)-1):
            level = self.levels[lvl]
            if idx % 2 == 0:
                sib_idx = idx+1 if idx+1 < len(level) else idx
                siblings.append((sib_idx % 2 == 0, level[sib_idx]))
            else:
                sib_idx = idx-1
                siblings.append((sib_idx % 2 == 0, level[sib_idx]))
            idx //= 2
        return MerkleProof(siblings)

def merkle_verify(leaf: bytes, proof: MerkleProof, expected_root: bytes, index: int) -> bool:
    h = leaf
    idx = index
    for (is_left_sibling, sib) in proof.siblings:
        if is_left_sibling:
            h = merkle_parent(sib, h)
        else:
            h = merkle_parent(h, sib)
        idx //= 2
    return h == expected_root


def hash_to_edges(h_digest: bytes, t: int, E_sorted: List[Tuple[int,int]], lambda_bits: int = 256) -> List[Tuple[int,int]]:
    m = len(E_sorted)
    out = []
    M = (1 << lambda_bits) // m * m  
    for i in range(t):
        j = 0
        while True:
            B = H(b"EdgeDerive-v1" + h_digest + encode_uint(i, 4) + encode_uint(j, 4))
            x = int_from_bytes(B)
            j += 1
            if x < M:
                out.append(E_sorted[x % m])  # with replacement
                break
    return out


def prf(key: bytes, ctx: bytes) -> bytes:
    return hmac.new(key, ctx, hashlib.sha256).digest()

def derive_round_seed(master: bytes, i: int) -> bytes:
    return prf(master, b"round-seed|" + encode_uint(i, 4))

def derive_r(seed_i: bytes, v: int, outlen: int = 16) -> bytes:
    stream = prf(seed_i, b"r|" + encode_uint(v, 4))
    while len(stream) < outlen:
        stream += prf(seed_i, b"r+|" + stream[-32:])
    return stream[:outlen]

def derive_permutation(seed_i: bytes, k: int) -> list[int]:
    pairs = []
    for c in range(1, k+1):
        key = hmac.new(seed_i, b"perm|" + encode_uint(c, 2), hashlib.sha256).digest()
        pairs.append((key, c))
    pairs.sort(key=lambda t: (t[0], t[1]))
    return [c for _, c in pairs]



def canonicalize_edges(edges: List[Tuple[int,int]]) -> List[Tuple[int,int]]:
    E = []
    for (u, v) in edges:
        if u == v:
            continue
        if u > v:
            u, v = v, u
        E.append((u, v))
    E = sorted(set(E))
    return E

def planted_graph(*n_sets, p_density=0.8, rng=None):

    import secrets as _secrets

    if rng is None:
        rng = _secrets.SystemRandom()

    k = len(n_sets)
    sets = []
    phi = []
    start = 0
    for color_idx, size in enumerate(n_sets, start=1): 
        current = list(range(start, start + size))      
        sets.append(current)
        phi.extend([color_idx] * size)
        start += size

    n = sum(n_sets)
    if n == 0 or k == 0:
        return [], []

    max_possible_edges = n * (n - 1) // 2
    forbidden_edges = sum(s * (s - 1) // 2 for s in n_sets)  
    allowed_edges = max_possible_edges - forbidden_edges
    if allowed_edges <= 0:
        return phi, []

    adjusted_p = p_density * (max_possible_edges / allowed_edges)
    if adjusted_p > 1.0:
        adjusted_p = 1.0
    if adjusted_p < 0.0:
        adjusted_p = 0.0

    edges = []
    for i in range(k):
        for j in range(i + 1, k):
            for u in sets[i]:
                for v in sets[j]:
                    if rng.random() < adjusted_p:
                        edges.append((u, v))

    return phi, edges


# Signature types, Sign, Verify

@dataclass
class SignatureRoundOpen:
    alpha_u: int
    r_u: bytes
    path_u: List[Tuple[bool, bytes]]
    u_index: int

    alpha_v: int
    r_v: bytes
    path_v: List[Tuple[bool, bytes]]
    v_index: int

@dataclass
class Signature:
    roots: List[bytes]
    opens: List[SignatureRoundOpen]

def sign(
    G_edges: List[Tuple[int,int]],
    n: int,
    k: int,
    phi: List[int],
    message: bytes,
    t: int = 256,
    alpha_bytes: int = 1,
    lambda_bits: int = 256,
) -> Signature:

    assert len(phi) == n
    E_sorted = canonicalize_edges(G_edges)
    tag = b"FS-GkColor-v1"

    roots: List[bytes] = []
    round_data = []  
    master = secrets.token_bytes(32)  

    for i in range(t):
        seed_i = derive_round_seed(master, i)
        pi = derive_permutation(seed_i, k)  
        commits = []
        leaves = []
        for v in range(n):
            color = phi[v]                     
            alpha = pi[color-1]                
            r_v = derive_r(seed_i, v, outlen=16)   
            c_v = commit_hash(alpha, r_v, alpha_bytes=alpha_bytes)
            commits.append((alpha, r_v, c_v))
            leaves.append(merkle_leaf(i, v, c_v))
        tree = MerkleTree(leaves)
        roots.append(tree.root())
        round_data.append((tree, commits, leaves))

    fs_input = encode_fs_input(tag, E_sorted, n, k, roots, message)
    h = H(fs_input)
    challenges = hash_to_edges(h, t, E_sorted, lambda_bits=lambda_bits)

    opens: List[SignatureRoundOpen] = []
    for i, (u, v) in enumerate(challenges):
        tree, commits, leaves = round_data[i]
        alpha_u, r_u, _ = commits[u]
        alpha_v, r_v, _ = commits[v]
        path_u = tree.proof(u).siblings
        path_v = tree.proof(v).siblings
        opens.append(SignatureRoundOpen(
            alpha_u=alpha_u, r_u=r_u, path_u=path_u, u_index=u,
            alpha_v=alpha_v, r_v=r_v, path_v=path_v, v_index=v
        ))

    return Signature(roots=roots, opens=opens)

def verify(
    G_edges: List[Tuple[int,int]],
    n: int,
    k: int,
    message: bytes,
    sig: Signature,
    alpha_bytes: int = 1,
    lambda_bits: int = 256,
) -> bool:
    E_sorted = canonicalize_edges(G_edges)
    tag = b"FS-GkColor-v1"
    roots = sig.roots
    t = len(roots)

    fs_input = encode_fs_input(tag, E_sorted, n, k, roots, message)
    h = H(fs_input)
    challenges = hash_to_edges(h, t, E_sorted, lambda_bits=lambda_bits)

    if len(sig.opens) != t:
        return False

    for i, (u, v) in enumerate(challenges):
        op = sig.opens[i]
        if (op.u_index, op.v_index) != (u, v):
            return False

        c_u = commit_hash(op.alpha_u, op.r_u, alpha_bytes=alpha_bytes)
        c_v = commit_hash(op.alpha_v, op.r_v, alpha_bytes=alpha_bytes)
        leaf_u = merkle_leaf(i, u, c_u)
        leaf_v = merkle_leaf(i, v, c_v)

        if not merkle_verify(leaf_u, MerkleProof(op.path_u), roots[i], u):
            return False
        if not merkle_verify(leaf_v, MerkleProof(op.path_v), roots[i], v):
            return False

        if not (1 <= op.alpha_u <= k and 1 <= op.alpha_v <= k):
            return False
        if op.alpha_u == op.alpha_v:
            return False
    return True


def signature_size_bits(sig: Signature, alpha_bytes=1, lambda_bits=256) -> int:

    t = len(sig.roots)
    size = t * lambda_bits
    for op in sig.opens:
        size += 8 * (alpha_bytes + len(op.r_u))
        size += 8 * (alpha_bytes + len(op.r_v))
        # each sibling hash is lambda_bits
        size += len(op.path_u) * lambda_bits
        size += len(op.path_v) * lambda_bits
    return size

def human_bytes(num_bytes: int) -> str:
    if num_bytes < 1024:
        return f"{num_bytes} B"
    kb = num_bytes / 1024
    if kb < 1024:
        return f"{kb:.1f} KiB"
    mb = kb / 1024
    return f"{mb:.2f} MiB"


if __name__ == "__main__":
    rng = secrets.SystemRandom()

    n_sets = [6, 5, 5]          
    p_density = 0.5            
    t = 8                  

    phi, edges = planted_graph(*n_sets, p_density=p_density, rng=rng)
    n = len(phi)
    k = len(n_sets)
    msg = b"hello world"

    t0 = time.time()
    sig = sign(edges, n, k, phi, msg, t=t)
    t1 = time.time()
    ok = verify(edges, n, k, msg, sig)
    t2 = time.time()

    bits = signature_size_bits(sig, alpha_bytes=1, lambda_bits=256)
    print(f"[small] graph: n={n}, k={k}, m={len(edges)} edges")
    print(f"[small] verify: {ok}")
    print(f"[small] sign time: {(t1-t0)*1000:.1f} ms | verify time: {(t2-t1)*1000:.1f} ms")
    print(f"[small] size: {bits} bits = {bits//8} bytes = {human_bytes(bits//8)}")

    # --- Larger example (uncomment to run; slower in a notebook) ---
    # n_sets = [70, 65, 65]      # k=3, n=200
    # p_density = 0.30
    # t = 256
    # phi, edges = planted_graph(*n_sets, p_density=p_density, rng=rng)
    # n = len(phi)
    # k = len(n_sets)
    # msg = b"example message"
    # t0 = time.time()
    # sig = sign(edges, n, k, phi, msg, t=t)
    # t1 = time.time()
    # ok = verify(edges, n, k, msg, sig)
    # t2 = time.time()
    # bits = signature_size_bits(sig, alpha_bytes=1, lambda_bits=256)
    # print(f"[large] graph: n={n}, k={k}, m={len(edges)} edges")
    # print(f"[large] verify: {ok}")
    # print(f"[large] sign time: {(t1-t0):.2f} s | verify time: {(t2-t1):.2f} s")
    # print(f"[large] size: {bits} bits = {bits//8} bytes = {human_bytes(bits//8)}")
