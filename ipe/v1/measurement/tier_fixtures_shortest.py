"""Tier sensitivity fixtures — 가중 최단경로류 (dijkstra / bellman_ford / floyd_warshall).

step 4c 확장 (see ``tier_fixtures`` 모듈 docstring).

인덱싱 주의(verifier I/O 계약):
- dijkstra: **0-indexed** 정점 (V E s t + 'u v w').
- bellman_ford / floyd_warshall: **1-indexed**, 음수 가중치 허용, 도달 가능 음수 사이클 없음.

출력은 유일답(최단거리 / 거리행렬) → golden·brute 수렴. brute 는 golden 과
다른 구조 (Dijkstra↔relaxation, BF↔Floyd-Warshall, FW↔V회 단일출발 BF).
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

# --- dijkstra (0-indexed) --------------------------------------------------
# I/O: "V E s t" + E 줄 "u v w" (0-indexed, w>=0). 출력 s→t 최단거리 또는 -1.

_DIJ_GOLDEN = """\
import sys
import heapq
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
s = int(d[i]); i += 1
t = int(d[i]); i += 1
adj = [[] for _ in range(v)]
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    c = int(d[i]); i += 1
    adj[u].append((w, c))
INF = float("inf")
dist = [INF] * v
dist[s] = 0
pq = [(0, s)]
while pq:
    dd, node = heapq.heappop(pq)
    if dd > dist[node]:
        continue
    for (nxt, c) in adj[node]:
        if dd + c < dist[nxt]:
            dist[nxt] = dd + c
            heapq.heappush(pq, (dist[nxt], nxt))
print(dist[t] if dist[t] != INF else -1)
"""

# 구조 독립: 우선순위큐 대신 간선 V-1회 완화 (Bellman-Ford 식).
_DIJ_BRUTE = """\
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
    c = int(d[i]); i += 1
    edges.append((u, w, c))
INF = float("inf")
dist = [INF] * v
dist[s] = 0
for _ in range(max(0, v - 1)):
    for (u, w, c) in edges:
        if dist[u] != INF and dist[u] + c < dist[w]:
            dist[w] = dist[u] + c
print(dist[t] if dist[t] != INF else -1)
"""

# 버그: 가중치 무시(전부 1) → 간선수만 셈 → shortest_distance_optimal.
_DIJ_MUT_UNIT_WEIGHT = """\
import sys
import heapq
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
s = int(d[i]); i += 1
t = int(d[i]); i += 1
adj = [[] for _ in range(v)]
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    c = int(d[i]); i += 1
    adj[u].append((w, 1))
INF = float("inf")
dist = [INF] * v
dist[s] = 0
pq = [(0, s)]
while pq:
    dd, node = heapq.heappop(pq)
    if dd > dist[node]:
        continue
    for (nxt, c) in adj[node]:
        if dd + c < dist[nxt]:
            dist[nxt] = dd + c
            heapq.heappush(pq, (dist[nxt], nxt))
print(dist[t] if dist[t] != INF else -1)
"""

# 버그: 거리 +1 (off-by-one) → shortest_distance_optimal.
_DIJ_MUT_OFF_BY_ONE = """\
import sys
import heapq
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
s = int(d[i]); i += 1
t = int(d[i]); i += 1
adj = [[] for _ in range(v)]
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    c = int(d[i]); i += 1
    adj[u].append((w, c))
INF = float("inf")
dist = [INF] * v
dist[s] = 0
pq = [(0, s)]
while pq:
    dd, node = heapq.heappop(pq)
    if dd > dist[node]:
        continue
    for (nxt, c) in adj[node]:
        if dd + c < dist[nxt]:
            dist[nxt] = dd + c
            heapq.heappush(pq, (dist[nxt], nxt))
print(dist[t] + 1 if dist[t] != INF else -1)
"""

_DIJ_MUT_CRASH = """\
import sys
_ = 1 // 0
print(-1)
"""

_DIJ_SAMPLES = (
    ("2 1 0 1\n0 1 5", "5"),
    ("3 2 0 2\n0 1 1\n1 2 2", "3"),  # unit-weight → 2
    ("2 0 0 1", "-1"),  # 도달 불가
    ("4 4 0 3\n0 1 1\n1 3 5\n0 2 2\n2 3 1", "3"),  # 0→2→3=3 < 0→1→3=6
    ("3 3 0 2\n0 1 4\n0 2 10\n1 2 1", "5"),  # 0→1→2=5 < 직접 10
)


def dijkstra_fixture() -> AlgoFixture:
    """dijkstra: golden(heap) + brute(완화) + 3 mutants. 0-indexed."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.DIJKSTRA,
        title="Dijkstra Shortest Path",
        description="Shortest path distance from s to t in a non-negative weighted directed graph.",
        io_contract=IOContract(
            input_format="V E s t on first line, then E lines 'u v w' (0-indexed, w>=0)",
            output_format="single integer (distance) or -1 if unreachable",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _DIJ_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Dijkstra",
        complexity_target=ComplexityBound(time_big_o="O((V+E) log V)", space_big_o="O(V+E)"),
        pseudocode="dist[s]=0; min-heap; pop nearest, relax outgoing edges.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_DIJ_GOLDEN,
        brute_code=_DIJ_BRUTE,
        mutants=(
            ("mut-unit-weight", _DIJ_MUT_UNIT_WEIGHT),
            ("mut-off-by-one", _DIJ_MUT_OFF_BY_ONE),
            ("mut-crash", _DIJ_MUT_CRASH),
        ),
    )


# --- bellman_ford (1-indexed, 음수 가중치) ---------------------------------
# I/O: "V E s t" + E 줄 "u v w" (1-indexed). 출력 d[s][t] 단일 정수 또는 -1.

_BF_GOLDEN = """\
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
    c = int(d[i]); i += 1
    edges.append((u, w, c))
INF = float("inf")
dist = [INF] * (v + 1)
dist[s] = 0
for _ in range(max(0, v - 1)):
    for (u, w, c) in edges:
        if dist[u] != INF and dist[u] + c < dist[w]:
            dist[w] = dist[u] + c
print(dist[t] if dist[t] != INF else -1)
"""

# 구조 독립: 간선 완화 대신 Floyd-Warshall 행렬 후 [s][t].
_BF_BRUTE = """\
import sys
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
s = int(d[i]); i += 1
t = int(d[i]); i += 1
INF = float("inf")
dm = [[INF] * (v + 1) for _ in range(v + 1)]
for x in range(1, v + 1):
    dm[x][x] = 0
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    c = int(d[i]); i += 1
    if c < dm[u][w]:
        dm[u][w] = c
for k in range(1, v + 1):
    for x in range(1, v + 1):
        for y in range(1, v + 1):
            if dm[x][k] + dm[k][y] < dm[x][y]:
                dm[x][y] = dm[x][k] + dm[k][y]
res = dm[s][t]
print(res if res != INF else -1)
"""

# 버그: 음수 무시(abs) → 음수 간선 경로 왜곡 → distance_matches_floyd_warshall.
_BF_MUT_ABS_WEIGHT = """\
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
    c = int(d[i]); i += 1
    edges.append((u, w, abs(c)))
INF = float("inf")
dist = [INF] * (v + 1)
dist[s] = 0
for _ in range(max(0, v - 1)):
    for (u, w, c) in edges:
        if dist[u] != INF and dist[u] + c < dist[w]:
            dist[w] = dist[u] + c
print(dist[t] if dist[t] != INF else -1)
"""

# 버그: 거리 +1 (off-by-one) → distance_matches_floyd_warshall.
_BF_MUT_OFF_BY_ONE = """\
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
    c = int(d[i]); i += 1
    edges.append((u, w, c))
INF = float("inf")
dist = [INF] * (v + 1)
dist[s] = 0
for _ in range(max(0, v - 1)):
    for (u, w, c) in edges:
        if dist[u] != INF and dist[u] + c < dist[w]:
            dist[w] = dist[u] + c
print(dist[t] + 1 if dist[t] != INF else -1)
"""

_BF_MUT_CRASH = """\
import sys
_ = 1 // 0
print(-1)
"""

_BF_SAMPLES = (
    ("4 5 1 4\n1 2 1\n2 3 -2\n3 4 1\n1 3 4\n2 4 5", "0"),  # 1→2→3→4 = 0
    ("3 2 1 3\n1 2 5\n2 3 -3", "2"),  # abs → 8
    ("3 1 1 3\n1 2 1", "-1"),  # 도달 불가
    ("3 3 1 3\n1 2 5\n2 3 -2\n1 3 10", "3"),  # 음수 경유가 직접보다 우월
    ("2 1 1 2\n1 2 5", "5"),
)


def bellman_ford_fixture() -> AlgoFixture:
    """bellman_ford: golden(완화) + brute(Floyd-Warshall) + 3 mutants. 1-indexed, 음수 허용."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BELLMAN_FORD,
        title="Bellman-Ford Shortest Path",
        description="Shortest path d[s][t], weights may be negative (no reachable neg cycle).",
        io_contract=IOContract(
            input_format="V E s t first line, then E edges 'u v w' (1-indexed, w may be negative)",
            output_format="single integer d[s][t], or -1 if unreachable",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _BF_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Bellman-Ford",
        complexity_target=ComplexityBound(time_big_o="O(VE)", space_big_o="O(V)"),
        pseudocode="dist[s]=0; relax all edges V-1 times.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_BF_GOLDEN,
        brute_code=_BF_BRUTE,
        mutants=(
            ("mut-abs-weight", _BF_MUT_ABS_WEIGHT),
            ("mut-off-by-one", _BF_MUT_OFF_BY_ONE),
            ("mut-crash", _BF_MUT_CRASH),
        ),
    )


# --- floyd_warshall (1-indexed, 음수 가중치) -------------------------------
# I/O: "V E" + E 줄 "u v w" (1-indexed). 출력 V×V 거리행렬(대각 0, 불가 -1).

_FW_GOLDEN = """\
import sys
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
INF = float("inf")
dm = [[INF] * (v + 1) for _ in range(v + 1)]
for x in range(1, v + 1):
    dm[x][x] = 0
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    c = int(d[i]); i += 1
    if c < dm[u][w]:
        dm[u][w] = c
for k in range(1, v + 1):
    for x in range(1, v + 1):
        for y in range(1, v + 1):
            if dm[x][k] + dm[k][y] < dm[x][y]:
                dm[x][y] = dm[x][k] + dm[k][y]
rows = []
for x in range(1, v + 1):
    rows.append(" ".join(str(dm[x][y]) if dm[x][y] != INF else "-1" for y in range(1, v + 1)))
print("\\n".join(rows))
"""

# 구조 독립: 삼중루프 대신 V회 단일출발 Bellman-Ford 로 행 구성.
_FW_BRUTE = """\
import sys
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
edges = []
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    c = int(d[i]); i += 1
    edges.append((u, w, c))
INF = float("inf")
rows = []
for s in range(1, v + 1):
    dist = [INF] * (v + 1)
    dist[s] = 0
    for _ in range(max(0, v - 1)):
        for (u, w, c) in edges:
            if dist[u] != INF and dist[u] + c < dist[w]:
                dist[w] = dist[u] + c
    rows.append(" ".join(str(dist[y]) if dist[y] != INF else "-1" for y in range(1, v + 1)))
print("\\n".join(rows))
"""

# 버그: 음수 무시(abs) → 음수 간선 거리 왜곡 → matches_bellman_ford_golden.
# (k 루프 위치 오류는 전진 체인 샘플에서 출력동등이라 신호 0 → 음수왜곡으로 교체.)
_FW_MUT_ABS_WEIGHT = """\
import sys
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
INF = float("inf")
dm = [[INF] * (v + 1) for _ in range(v + 1)]
for x in range(1, v + 1):
    dm[x][x] = 0
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    c = int(d[i]); i += 1
    if abs(c) < dm[u][w]:
        dm[u][w] = abs(c)
for k in range(1, v + 1):
    for x in range(1, v + 1):
        for y in range(1, v + 1):
            if dm[x][k] + dm[k][y] < dm[x][y]:
                dm[x][y] = dm[x][k] + dm[k][y]
rows = []
for x in range(1, v + 1):
    rows.append(" ".join(str(dm[x][y]) if dm[x][y] != INF else "-1" for y in range(1, v + 1)))
print("\\n".join(rows))
"""

# 버그: 대각 원소 1 로 강제 (off-by-one 식) → diagonal_is_zero.
_FW_MUT_NONZERO_DIAG = """\
import sys
d = sys.stdin.read().split()
i = 0
v = int(d[i]); i += 1
e = int(d[i]); i += 1
INF = float("inf")
dm = [[INF] * (v + 1) for _ in range(v + 1)]
for x in range(1, v + 1):
    dm[x][x] = 0
for _ in range(e):
    u = int(d[i]); i += 1
    w = int(d[i]); i += 1
    c = int(d[i]); i += 1
    if c < dm[u][w]:
        dm[u][w] = c
for k in range(1, v + 1):
    for x in range(1, v + 1):
        for y in range(1, v + 1):
            if dm[x][k] + dm[k][y] < dm[x][y]:
                dm[x][y] = dm[x][k] + dm[k][y]
for x in range(1, v + 1):
    dm[x][x] = 1
rows = []
for x in range(1, v + 1):
    rows.append(" ".join(str(dm[x][y]) if dm[x][y] != INF else "-1" for y in range(1, v + 1)))
print("\\n".join(rows))
"""

_FW_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_FW_SAMPLES = (
    ("3 3\n1 2 5\n2 3 -2\n1 3 10", "0 5 3\n-1 0 -2\n-1 -1 0"),
    ("2 1\n1 2 7", "0 7\n-1 0"),
    ("3 0", "0 -1 -1\n-1 0 -1\n-1 -1 0"),
    ("4 3\n1 2 1\n2 3 1\n3 4 1", "0 1 2 3\n-1 0 1 2\n-1 -1 0 1\n-1 -1 -1 0"),  # 3-hop 체인
    ("3 2\n1 2 1\n2 3 1", "0 1 2\n-1 0 1\n-1 -1 0"),
)


def floyd_warshall_fixture() -> AlgoFixture:
    """floyd_warshall: golden(삼중루프) + brute(V회 BF) + 3 mutants. 1-indexed, 음수 허용."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FLOYD_WARSHALL,
        title="Floyd-Warshall All-Pairs Shortest Path",
        description="All-pairs shortest distance matrix (diagonal 0, -1 if unreachable).",
        io_contract=IOContract(
            input_format="V E on first line, then E edges 'u v w' (1-indexed, w may be negative)",
            output_format="V lines x V tokens — d[i][j] matrix, -1 if unreachable",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _FW_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Floyd-Warshall",
        complexity_target=ComplexityBound(time_big_o="O(V^3)", space_big_o="O(V^2)"),
        pseudocode="triple loop k,i,j: dm[i][j] = min(dm[i][j], dm[i][k] + dm[k][j]).",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_FW_GOLDEN,
        brute_code=_FW_BRUTE,
        mutants=(
            ("mut-abs-weight", _FW_MUT_ABS_WEIGHT),
            ("mut-nonzero-diag", _FW_MUT_NONZERO_DIAG),
            ("mut-crash", _FW_MUT_CRASH),
        ),
    )


SHORTEST_FIXTURES = (dijkstra_fixture, bellman_ford_fixture, floyd_warshall_fixture)
"""가중 최단경로류 fixture (step 4c)."""
