"""Tier sensitivity fixtures — 최적화/문자열류 (kruskal_mst / maxflow / stringmatch).

step 4c 확장 (see ``tier_fixtures`` 모듈 docstring). 출력은 유일답(MST 무게 /
최대유량 / 첫 출현 인덱스) → golden·brute 수렴. brute 는 golden 과 다른 구조
(Kruskal↔Prim, Edmonds-Karp↔min-cut 열거, KMP↔naive substring).

인덱싱: kruskal/maxflow 는 1-indexed. stringmatch 출력은 1-indexed.
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

# --- kruskal_mst (1-indexed, undirected, w>=0) -----------------------------
# I/O: "V E" + E 줄 "u v w". 출력 MST 총 무게, 비연결 시 -1.

_MST_GOLDEN = """\
import sys
data = sys.stdin.read().split()
i = 0
v = int(data[i]); i += 1
e = int(data[i]); i += 1
edges = []
for _ in range(e):
    a = int(data[i]); i += 1
    b = int(data[i]); i += 1
    w = int(data[i]); i += 1
    edges.append((w, a, b))
edges.sort()
parent = list(range(v + 1))


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


total = 0
used = 0
for (w, a, b) in edges:
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb
        total += w
        used += 1
print(total if used == v - 1 else -1)
"""

# 구조 독립: Kruskal(간선정렬+DSU) 대신 Prim(노드성장+힙).
_MST_BRUTE = """\
import sys
import heapq
data = sys.stdin.read().split()
i = 0
v = int(data[i]); i += 1
e = int(data[i]); i += 1
adj = [[] for _ in range(v + 1)]
for _ in range(e):
    a = int(data[i]); i += 1
    b = int(data[i]); i += 1
    w = int(data[i]); i += 1
    adj[a].append((w, b))
    adj[b].append((w, a))
visited = [False] * (v + 1)
total = 0
count = 0
pq = [(0, 1)]
while pq:
    w, node = heapq.heappop(pq)
    if visited[node]:
        continue
    visited[node] = True
    total += w
    count += 1
    for (ww, nb) in adj[node]:
        if not visited[nb]:
            heapq.heappush(pq, (ww, nb))
print(total if count == v else -1)
"""

# 버그: 간선 내림차순 정렬 → 최대신장트리 → weight_matches_prim_golden.
_MST_MUT_MAX_SPANNING = """\
import sys
data = sys.stdin.read().split()
i = 0
v = int(data[i]); i += 1
e = int(data[i]); i += 1
edges = []
for _ in range(e):
    a = int(data[i]); i += 1
    b = int(data[i]); i += 1
    w = int(data[i]); i += 1
    edges.append((w, a, b))
edges.sort(reverse=True)
parent = list(range(v + 1))


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


total = 0
used = 0
for (w, a, b) in edges:
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb
        total += w
        used += 1
print(total if used == v - 1 else -1)
"""

# 버그: 비연결 확인 누락 → 분리 그래프도 부분합 출력 → connectivity_consistent.
_MST_MUT_NO_CONNECTIVITY = """\
import sys
data = sys.stdin.read().split()
i = 0
v = int(data[i]); i += 1
e = int(data[i]); i += 1
edges = []
for _ in range(e):
    a = int(data[i]); i += 1
    b = int(data[i]); i += 1
    w = int(data[i]); i += 1
    edges.append((w, a, b))
edges.sort()
parent = list(range(v + 1))


def find(x):
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


total = 0
for (w, a, b) in edges:
    ra, rb = find(a), find(b)
    if ra != rb:
        parent[ra] = rb
        total += w
print(total)
"""

_MST_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_MST_SAMPLES = (
    ("4 5\n1 2 1\n2 3 2\n3 4 3\n1 4 10\n2 4 5", "6"),
    ("3 2\n1 2 5\n2 3 7", "12"),
    ("4 2\n1 2 1\n3 4 2", "-1"),  # 비연결 (no-connectivity → 3)
    ("3 3\n1 2 1\n2 3 2\n1 3 100", "3"),  # 사이클 (max-spanning → 102)
    ("2 1\n1 2 5", "5"),
)


def kruskal_mst_fixture() -> AlgoFixture:
    """kruskal_mst: golden(Kruskal) + brute(Prim) + 3 mutants. 1-indexed, undirected."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KRUSKAL_MST,
        title="Kruskal Minimum Spanning Tree",
        description="Total weight of the MST of an undirected graph, or -1 if disconnected.",
        io_contract=IOContract(
            input_format="V E on first line, then E undirected edges 'u v w' (1-indexed, w>=0)",
            output_format="single integer — MST weight, or -1 if disconnected",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _MST_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Kruskal MST",
        complexity_target=ComplexityBound(time_big_o="O(E log E)", space_big_o="O(V)"),
        pseudocode="sort edges ascending; union-find merge if endpoints differ.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_MST_GOLDEN,
        brute_code=_MST_BRUTE,
        mutants=(
            ("mut-max-spanning", _MST_MUT_MAX_SPANNING),
            ("mut-no-connectivity", _MST_MUT_NO_CONNECTIVITY),
            ("mut-crash", _MST_MUT_CRASH),
        ),
    )


# --- maxflow (1-indexed, directed capacities) ------------------------------
# I/O: "V E s t" + E 줄 "u v c". 출력 s→t 최대유량.

_FLOW_GOLDEN = """\
import sys
from collections import deque
data = sys.stdin.read().split()
i = 0
v = int(data[i]); i += 1
e = int(data[i]); i += 1
s = int(data[i]); i += 1
t = int(data[i]); i += 1
cap = [[0] * (v + 1) for _ in range(v + 1)]
for _ in range(e):
    a = int(data[i]); i += 1
    b = int(data[i]); i += 1
    c = int(data[i]); i += 1
    cap[a][b] += c
flow = 0
while True:
    parent = [0] * (v + 1)
    parent[s] = s
    q = deque([s])
    while q:
        u = q.popleft()
        for w in range(1, v + 1):
            if parent[w] == 0 and cap[u][w] > 0:
                parent[w] = u
                q.append(w)
    if parent[t] == 0:
        break
    aug = float("inf")
    node = t
    while node != s:
        aug = min(aug, cap[parent[node]][node])
        node = parent[node]
    node = t
    while node != s:
        cap[parent[node]][node] -= aug
        cap[node][parent[node]] += aug
        node = parent[node]
    flow += aug
print(flow)
"""

# 구조 독립: 증가경로 대신 max-flow min-cut 정리로 모든 s-t 컷 열거 (V 작음).
_FLOW_BRUTE = """\
import sys
from itertools import combinations
data = sys.stdin.read().split()
i = 0
v = int(data[i]); i += 1
e = int(data[i]); i += 1
s = int(data[i]); i += 1
t = int(data[i]); i += 1
cap = [[0] * (v + 1) for _ in range(v + 1)]
for _ in range(e):
    a = int(data[i]); i += 1
    b = int(data[i]); i += 1
    c = int(data[i]); i += 1
    cap[a][b] += c
others = [x for x in range(1, v + 1) if x != s and x != t]
best = float("inf")
for r in range(len(others) + 1):
    for combo in combinations(others, r):
        side = set(combo) | {s}
        cut = 0
        for u in side:
            for w in range(1, v + 1):
                if w not in side:
                    cut += cap[u][w]
        if cut < best:
            best = cut
print(best)
"""

# 버그: 증가경로 1회만 (루프 없음) → 준최적 유량 → flow_matches_brute_min_cut.
_FLOW_MUT_SINGLE_AUGMENT = """\
import sys
from collections import deque
data = sys.stdin.read().split()
i = 0
v = int(data[i]); i += 1
e = int(data[i]); i += 1
s = int(data[i]); i += 1
t = int(data[i]); i += 1
cap = [[0] * (v + 1) for _ in range(v + 1)]
for _ in range(e):
    a = int(data[i]); i += 1
    b = int(data[i]); i += 1
    c = int(data[i]); i += 1
    cap[a][b] += c
flow = 0
parent = [0] * (v + 1)
parent[s] = s
q = deque([s])
while q:
    u = q.popleft()
    for w in range(1, v + 1):
        if parent[w] == 0 and cap[u][w] > 0:
            parent[w] = u
            q.append(w)
if parent[t] != 0:
    aug = float("inf")
    node = t
    while node != s:
        aug = min(aug, cap[parent[node]][node])
        node = parent[node]
    flow += aug
print(flow)
"""

# 버그: 유량 2배 출력 (overcount) → flow_matches_brute_min_cut / flow_within_source_outflow.
_FLOW_MUT_DOUBLE = """\
import sys
from collections import deque
data = sys.stdin.read().split()
i = 0
v = int(data[i]); i += 1
e = int(data[i]); i += 1
s = int(data[i]); i += 1
t = int(data[i]); i += 1
cap = [[0] * (v + 1) for _ in range(v + 1)]
for _ in range(e):
    a = int(data[i]); i += 1
    b = int(data[i]); i += 1
    c = int(data[i]); i += 1
    cap[a][b] += c
flow = 0
while True:
    parent = [0] * (v + 1)
    parent[s] = s
    q = deque([s])
    while q:
        u = q.popleft()
        for w in range(1, v + 1):
            if parent[w] == 0 and cap[u][w] > 0:
                parent[w] = u
                q.append(w)
    if parent[t] == 0:
        break
    aug = float("inf")
    node = t
    while node != s:
        aug = min(aug, cap[parent[node]][node])
        node = parent[node]
    node = t
    while node != s:
        cap[parent[node]][node] -= aug
        cap[node][parent[node]] += aug
        node = parent[node]
    flow += aug
print(flow * 2)
"""

_FLOW_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_FLOW_SAMPLES = (
    ("4 5 1 4\n1 2 10\n1 3 5\n2 3 15\n2 4 10\n3 4 10", "15"),  # 2 경로 필요
    ("2 1 1 2\n1 2 7", "7"),
    ("3 2 1 3\n1 2 5\n2 3 3", "3"),
    ("4 4 1 4\n1 2 5\n1 3 5\n2 4 5\n3 4 5", "10"),  # 다이아몬드 (single-augment → 5)
    ("3 1 1 3\n1 2 5", "0"),  # 비연결
)


def maxflow_fixture() -> AlgoFixture:
    """maxflow: golden(Edmonds-Karp) + brute(min-cut 열거) + 3 mutants. 1-indexed."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.MAX_FLOW,
        title="Maximum Flow",
        description="Maximum flow from s to t in a directed capacitated graph.",
        io_contract=IOContract(
            input_format="V E s t on first line, then E edges 'u v c' (1-indexed, c>=0)",
            output_format="single integer — maximum flow s->t",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _FLOW_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Edmonds-Karp",
        complexity_target=ComplexityBound(time_big_o="O(VE^2)", space_big_o="O(V+E)"),
        pseudocode="repeatedly BFS for augmenting path in residual graph; sum bottlenecks.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_FLOW_GOLDEN,
        brute_code=_FLOW_BRUTE,
        mutants=(
            ("mut-single-augment", _FLOW_MUT_SINGLE_AUGMENT),
            ("mut-double", _FLOW_MUT_DOUBLE),
            ("mut-crash", _FLOW_MUT_CRASH),
        ),
    )


# --- stringmatch (KMP, 첫 출현) --------------------------------------------
# I/O: text + pattern (2 줄, 공백 없음). 출력 1-indexed 첫 출현 위치 또는 -1.

_SM_GOLDEN = """\
import sys
toks = sys.stdin.read().split()
text = toks[0]
pattern = toks[1]
n = len(text)
m = len(pattern)
fail = [0] * m
k = 0
for idx in range(1, m):
    while k > 0 and pattern[idx] != pattern[k]:
        k = fail[k - 1]
    if pattern[idx] == pattern[k]:
        k += 1
    fail[idx] = k
ans = -1
k = 0
for idx in range(n):
    while k > 0 and text[idx] != pattern[k]:
        k = fail[k - 1]
    if text[idx] == pattern[k]:
        k += 1
    if k == m:
        ans = idx - m + 2
        break
print(ans)
"""

# 구조 독립: 실패함수 대신 naive O(N*M) substring 비교.
_SM_BRUTE = """\
import sys
toks = sys.stdin.read().split()
text = toks[0]
pattern = toks[1]
n = len(text)
m = len(pattern)
ans = -1
for idx in range(n - m + 1):
    if text[idx:idx + m] == pattern:
        ans = idx + 1
        break
print(ans)
"""

# 버그: 0-indexed 출력 → index_valid_range / text_at_index_matches_pattern.
_SM_MUT_ZERO_INDEX = """\
import sys
toks = sys.stdin.read().split()
text = toks[0]
pattern = toks[1]
n = len(text)
m = len(pattern)
ans = -1
for idx in range(n - m + 1):
    if text[idx:idx + m] == pattern:
        ans = idx
        break
print(ans)
"""

# 버그: 위치 +1 시프트 (off-by-one) → text_at_index_matches_pattern.
_SM_MUT_SHIFT = """\
import sys
toks = sys.stdin.read().split()
text = toks[0]
pattern = toks[1]
n = len(text)
m = len(pattern)
ans = -1
for idx in range(n - m + 1):
    if text[idx:idx + m] == pattern:
        ans = idx + 2
        break
print(ans)
"""

_SM_MUT_CRASH = """\
import sys
_ = 1 // 0
print("-1")
"""

_SM_SAMPLES = (
    ("abracadabra\nabra", "1"),
    ("hello\nworld", "-1"),
    ("abcabcabc\ncab", "3"),
    ("abcdef\ndef", "4"),
    ("aaaa\naa", "1"),  # overlapping
)


def stringmatch_fixture() -> AlgoFixture:
    """stringmatch: golden(KMP) + brute(naive substring) + 3 mutants. 출력 1-indexed."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.STRING_MATCH,
        title="String Match (first occurrence)",
        description="1-indexed position of the first occurrence of pattern in text, or -1.",
        io_contract=IOContract(
            input_format="two lines (no whitespace): text, then pattern",
            output_format="single integer — 1-indexed first occurrence, or -1",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _SM_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="KMP",
        complexity_target=ComplexityBound(time_big_o="O(N+M)", space_big_o="O(M)"),
        pseudocode="build failure function, then linear scan over text.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_SM_GOLDEN,
        brute_code=_SM_BRUTE,
        mutants=(
            ("mut-zero-index", _SM_MUT_ZERO_INDEX),
            ("mut-shift", _SM_MUT_SHIFT),
            ("mut-crash", _SM_MUT_CRASH),
        ),
    )


OPT_FIXTURES = (kruskal_mst_fixture, maxflow_fixture, stringmatch_fixture)
"""최적화/문자열류 fixture (step 4c)."""
