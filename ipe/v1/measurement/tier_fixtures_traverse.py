"""Tier sensitivity fixtures — 그래프 순회류 (bfs / toposort / union_find).

step 4c 확장 (see ``tier_fixtures`` 모듈 docstring). 각 fixture 는 golden(정석) +
**구조 독립** brute + mutants 3종(off-by-one·index / 핵심관계 오류 / crash).

설계 규율(실측에서 학습):
- 유일답 샘플만 (golden·brute 가 동일 출력으로 수렴해야 differential 이 golden 을
  false-reject 하지 않음). toposort 는 **유일 위상순서**(전순서 강제) 샘플만 사용.
- golden 출력은 모든 샘플에서 비어있지 않음 (metamorphic well_formed).
- brute 는 golden 과 다른 알고리즘 구조 (BFS↔relaxation, Kahn↔DFS, 포인터DSU↔flat relabel).
"""

from __future__ import annotations

from ..schema import (
    AlgorithmDesign,
    ComplexityBound,
    IOContract,
    ProblemSpec,
    SampleTestCase,
    TargetAlgorithm,
)
from .tier_measure import AlgoFixture

# --- bfs -------------------------------------------------------------------
# I/O: "V E s t" 첫 줄 + E 줄 directed edge "u w" (1-indexed). 출력 s→t 최단 간선수 또는 -1.

_BFS_GOLDEN = """\
import sys
from collections import deque
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
s = int(d[i]); i += 1
t = int(d[i]); i += 1
adj = [[] for _ in range(v + 1)]
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    adj[u].append(w)
dist = [-1] * (v + 1)
dist[s] = 0
q = deque([s])
while q:
    cur = q.popleft()
    for nxt in adj[cur]:
        if dist[nxt] == -1:
            dist[nxt] = dist[cur] + 1
            q.append(nxt)
print(dist[t])
"""

# 구조 독립: 큐 대신 간선 반복 완화 (Bellman-Ford 식, 단위 가중치). 정수 sentinel.
_BFS_BRUTE = """\
import sys
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
s = int(d[i]); i += 1
t = int(d[i]); i += 1
edges = []
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    edges.append((u, w))
INF = 10 ** 9
dist = [INF] * (v + 1)
dist[s] = 0
for _ in range(v):
    for (u, w) in edges:
        if dist[u] + 1 < dist[w]:
            dist[w] = dist[u] + 1
print(dist[t] if dist[t] < INF else -1)
"""

# 버그: 출발 거리 1 부터 (off-by-one) → 도달 거리 전부 +1 → source_zero/distance_optimal.
_BFS_MUT_OFF_BY_ONE = """\
import sys
from collections import deque
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
s = int(d[i]); i += 1
t = int(d[i]); i += 1
adj = [[] for _ in range(v + 1)]
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    adj[u].append(w)
dist = [-1] * (v + 1)
dist[s] = 1
q = deque([s])
while q:
    cur = q.popleft()
    for nxt in adj[cur]:
        if dist[nxt] == -1:
            dist[nxt] = dist[cur] + 1
            q.append(nxt)
print(dist[t])
"""

# 버그: 방향 무시(역간선 추가) → 방향 그래프를 무향 취급 → reachability_consistent.
_BFS_MUT_UNDIRECTED = """\
import sys
from collections import deque
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
s = int(d[i]); i += 1
t = int(d[i]); i += 1
adj = [[] for _ in range(v + 1)]
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    adj[u].append(w)
    adj[w].append(u)
dist = [-1] * (v + 1)
dist[s] = 0
q = deque([s])
while q:
    cur = q.popleft()
    for nxt in adj[cur]:
        if dist[nxt] == -1:
            dist[nxt] = dist[cur] + 1
            q.append(nxt)
print(dist[t])
"""

_BFS_MUT_CRASH = """\
import sys
_ = 1 // 0
print(-1)
"""

_BFS_SAMPLES = (
    ("2 1 1 2\n1 2", "1"),  # 1 간선
    ("3 2 1 3\n1 2\n2 3", "2"),  # 2 간선 (off-by-one→3)
    ("2 0 1 2", "-1"),  # 도달 불가
    ("2 1 2 1\n1 2", "-1"),  # 방향성: 1→2 인데 2→1 질의 (undirected→1)
    ("4 3 1 4\n1 2\n2 3\n3 4", "3"),  # 체인
)


def bfs_fixture() -> AlgoFixture:
    """bfs: golden(큐) + brute(완화) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BFS,
        title="BFS Shortest Edge Count",
        description="Shortest number of edges from s to t in a directed unweighted graph, else -1.",
        io_contract=IOContract(
            input_format="V E s t on first line, then E directed edges 'u w' (1-indexed)",
            output_format="single integer (edge count) or -1",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _BFS_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Breadth-First Search",
        complexity_target=ComplexityBound(time_big_o="O(V+E)", space_big_o="O(V+E)"),
        pseudocode="queue + dist[]; dist[s]=0; relax unvisited neighbors.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_BFS_GOLDEN,
        brute_code=_BFS_BRUTE,
        mutants=(
            ("mut-off-by-one", _BFS_MUT_OFF_BY_ONE),
            ("mut-undirected", _BFS_MUT_UNDIRECTED),
            ("mut-crash", _BFS_MUT_CRASH),
        ),
    )


# --- toposort --------------------------------------------------------------
# I/O: "N M" + M 간선 "u v" (1-indexed DAG). 출력 1..N 위상순서.
# **유일 위상순서**(전순서 강제) 샘플만 → golden(Kahn)·brute(DFS) 동일 출력 수렴.

_TOPO_GOLDEN = """\
import sys
from collections import deque
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
m = int(d[i]); i += 1
adj = [[] for _ in range(n + 1)]
indeg = [0] * (n + 1)
for _ in range(m):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    adj[u].append(w)
    indeg[w] += 1
q = deque(sorted(x for x in range(1, n + 1) if indeg[x] == 0))
order = []
while q:
    cur = q.popleft()
    order.append(cur)
    for nxt in adj[cur]:
        indeg[nxt] -= 1
        if indeg[nxt] == 0:
            q.append(nxt)
print(" ".join(map(str, order)))
"""

# 구조 독립: Kahn(in-degree) 대신 DFS post-order 역순.
_TOPO_BRUTE = """\
import sys
sys.setrecursionlimit(10000)
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
m = int(d[i]); i += 1
adj = [[] for _ in range(n + 1)]
for _ in range(m):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    adj[u].append(w)
visited = [False] * (n + 1)
post = []


def dfs(node):
    visited[node] = True
    for nxt in adj[node]:
        if not visited[nxt]:
            dfs(nxt)
    post.append(node)


for start in range(1, n + 1):
    if not visited[start]:
        dfs(start)
post.reverse()
print(" ".join(map(str, post)))
"""

# 버그: 0-indexed 출력 (각 노드 -1) → output_is_permutation (범위 이탈).
_TOPO_MUT_ZERO_INDEX = """\
import sys
from collections import deque
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
m = int(d[i]); i += 1
adj = [[] for _ in range(n + 1)]
indeg = [0] * (n + 1)
for _ in range(m):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    adj[u].append(w)
    indeg[w] += 1
q = deque(sorted(x for x in range(1, n + 1) if indeg[x] == 0))
order = []
while q:
    cur = q.popleft()
    order.append(cur - 1)
    for nxt in adj[cur]:
        indeg[nxt] -= 1
        if indeg[nxt] == 0:
            q.append(nxt)
print(" ".join(map(str, order)))
"""

# 버그: 위상순서 역순 출력 → edges_respect_order 위반.
_TOPO_MUT_REVERSED = """\
import sys
from collections import deque
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
m = int(d[i]); i += 1
adj = [[] for _ in range(n + 1)]
indeg = [0] * (n + 1)
for _ in range(m):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    adj[u].append(w)
    indeg[w] += 1
q = deque(sorted(x for x in range(1, n + 1) if indeg[x] == 0))
order = []
while q:
    cur = q.popleft()
    order.append(cur)
    for nxt in adj[cur]:
        indeg[nxt] -= 1
        if indeg[nxt] == 0:
            q.append(nxt)
order.reverse()
print(" ".join(map(str, order)))
"""

_TOPO_MUT_CRASH = """\
import sys
_ = 1 // 0
print("1")
"""

_TOPO_SAMPLES = (
    ("3 2\n1 2\n2 3", "1 2 3"),  # 체인
    ("4 3\n1 2\n2 3\n3 4", "1 2 3 4"),
    ("4 4\n1 2\n2 3\n3 4\n1 3", "1 2 3 4"),  # 잉여 간선 일관, 여전히 유일
    ("5 4\n1 2\n2 3\n3 4\n4 5", "1 2 3 4 5"),
    ("3 3\n1 2\n1 3\n2 3", "1 2 3"),  # 1→2,1→3,2→3 → 유일
)


def toposort_fixture() -> AlgoFixture:
    """toposort: golden(Kahn) + brute(DFS post-order) + 3 mutants. 유일순서 샘플."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TOPOSORT,
        title="Topological Sort (unique order)",
        description="Output the topological order of a DAG (samples force a unique total order).",
        io_contract=IOContract(
            input_format="N M on first line, then M directed edges 'u v' (1-indexed DAG)",
            output_format="N integers — a topological permutation of 1..N",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _TOPO_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Topological Sort",
        complexity_target=ComplexityBound(time_big_o="O(V+E)", space_big_o="O(V+E)"),
        pseudocode="Kahn: repeatedly pop in-degree-0 node, decrement successors.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_TOPO_GOLDEN,
        brute_code=_TOPO_BRUTE,
        mutants=(
            ("mut-zero-index", _TOPO_MUT_ZERO_INDEX),
            ("mut-reversed", _TOPO_MUT_REVERSED),
            ("mut-crash", _TOPO_MUT_CRASH),
        ),
    )


# --- union_find ------------------------------------------------------------
# I/O: "N Q" + Q ops ("U x y" 합집합 | "Q x y" same-set 질의), 1-indexed.
# 출력: Q op 마다 0/1 한 줄. 결정론적 시퀀스 → 유일답.

_UF_GOLDEN = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
q = int(d[i]); i += 1
parent = list(range(n + 1))
rank = [0] * (n + 1)


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(a, b):
    ra, rb = find(a), find(b)
    if ra == rb:
        return
    if rank[ra] < rank[rb]:
        ra, rb = rb, ra
    parent[rb] = ra
    if rank[ra] == rank[rb]:
        rank[ra] += 1


out = []
for _ in range(q):
    op = d[i]; i += 1
    x = int(d[i]); i += 1
    y = int(d[i]); i += 1
    if op == "U":
        union(x, y)
    else:
        out.append("1" if find(x) == find(y) else "0")
print("\\n".join(out))
"""

# 구조 독립: 포인터 DSU 대신 flat label 배열, union 시 O(N) relabel.
_UF_BRUTE = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
q = int(d[i]); i += 1
label = list(range(n + 1))
out = []
for _ in range(q):
    op = d[i]; i += 1
    x = int(d[i]); i += 1
    y = int(d[i]); i += 1
    if op == "U":
        lx, ly = label[x], label[y]
        if lx != ly:
            for k in range(n + 1):
                if label[k] == ly:
                    label[k] = lx
    else:
        out.append("1" if label[x] == label[y] else "0")
print("\\n".join(out))
"""

# 버그: union no-op → 합쳤어야 할 원소가 분리 유지 → same_set_correctness.
_UF_MUT_UNION_NOOP = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
q = int(d[i]); i += 1
parent = list(range(n + 1))


def find(x):
    while parent[x] != x:
        x = parent[x]
    return x


out = []
for _ in range(q):
    op = d[i]; i += 1
    x = int(d[i]); i += 1
    y = int(d[i]); i += 1
    if op == "U":
        pass
    else:
        out.append("1" if find(x) == find(y) else "0")
print("\\n".join(out))
"""

# 버그: 질의 결과 반전 (same→0, diff→1) → same_set_correctness.
_UF_MUT_INVERTED = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
q = int(d[i]); i += 1
parent = list(range(n + 1))


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def union(a, b):
    ra, rb = find(a), find(b)
    parent[rb] = ra


out = []
for _ in range(q):
    op = d[i]; i += 1
    x = int(d[i]); i += 1
    y = int(d[i]); i += 1
    if op == "U":
        union(x, y)
    else:
        out.append("0" if find(x) == find(y) else "1")
print("\\n".join(out))
"""

_UF_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_UF_SAMPLES = (
    ("4 4\nU 1 2\nU 3 4\nQ 1 2\nQ 1 3", "1\n0"),
    ("3 3\nQ 1 1\nU 1 2\nQ 1 2", "1\n1"),
    ("5 5\nU 1 2\nU 2 3\nU 4 5\nQ 1 3\nQ 1 4", "1\n0"),
    ("4 4\nU 1 2\nQ 1 2\nU 2 3\nQ 1 3", "1\n1"),  # 추이성
    ("3 2\nQ 1 2\nU 1 2", "0"),  # 합치기 전 질의 → 0
)


def union_find_fixture() -> AlgoFixture:
    """union_find: golden(포인터 DSU) + brute(flat relabel) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.UNION_FIND,
        title="Disjoint Set Union",
        description="Process union/same-set-query ops; output 0/1 per query.",
        io_contract=IOContract(
            input_format="N Q on first line, then Q ops 'U x y' or 'Q x y' (1-indexed)",
            output_format="0 or 1 per Q op, one per line",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _UF_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Union-Find",
        complexity_target=ComplexityBound(time_big_o="O(Q alpha(N))", space_big_o="O(N)"),
        pseudocode="parent[] self-init; union by rank; path compression; find roots to compare.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_UF_GOLDEN,
        brute_code=_UF_BRUTE,
        mutants=(
            ("mut-union-noop", _UF_MUT_UNION_NOOP),
            ("mut-inverted", _UF_MUT_INVERTED),
            ("mut-crash", _UF_MUT_CRASH),
        ),
    )


TRAVERSE_FIXTURES = (bfs_fixture, toposort_fixture, union_find_fixture)
"""그래프 순회류 fixture (step 4c)."""
