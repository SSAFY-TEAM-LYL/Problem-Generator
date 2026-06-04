"""Tier sensitivity 측정 fixture (Phase 3 M1 step 4) — golden/brute/mutants.

각 알고리즘마다 ``AlgoFixture`` 를 구성: golden(정석) + brute(구조 독립 naive) +
mutants(golden 에 버그 1개 주입). 모두 손작성 코드 — LLM 0.

mutation 전략(범용): 모든 알고리즘에 공통 적용 가능한 버그 클래스로 confusion
matrix 의 각 셀을 채운다.
- off-by-one / index base 오류 (출력 형식·범위 invariant 가 잡음)
- 핵심 관계 오류 (optimality/sum/feasibility invariant 가 잡음)
- crash (metamorphic well_formed 가 잡음)

step 4a: two_sum 1개로 파이프라인 실증. 4b 에서 binary_search/sieve, 4c 19 확장.
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
from .tier_fixtures_opt import OPT_FIXTURES
from .tier_fixtures_seq import SEQ_FIXTURES
from .tier_fixtures_shortest import SHORTEST_FIXTURES
from .tier_fixtures_struct import STRUCT_FIXTURES
from .tier_fixtures_traverse import TRAVERSE_FIXTURES
from .tier_measure import AlgoFixture

# --- two_sum --------------------------------------------------------------
# I/O: "N T" 첫 줄 + 배열 a_1..a_N. 출력 "i j"(1-indexed, i<j) 또는 "-1".
# 모든 sample 은 유일 pair 또는 no-pair → golden·brute 가 동일 답으로 수렴
# (differential 이 golden 을 false-reject 하지 않도록).

_TWO_SUM_GOLDEN = """\
import sys
d = sys.stdin.read().split()
n = int(d[0]); t = int(d[1])
a = [int(x) for x in d[2:2 + n]]
seen = {}
out = "-1"
for j in range(n):
    need = t - a[j]
    if need in seen:
        out = f"{seen[need] + 1} {j + 1}"
        break
    seen.setdefault(a[j], j)
print(out)
"""

# 구조 독립: O(N^2) 전수 (golden 은 hash map). 동일 I/O, 최소 i·최소 j 수렴.
_TWO_SUM_BRUTE = """\
import sys
d = sys.stdin.read().split()
n = int(d[0]); t = int(d[1])
a = [int(x) for x in d[2:2 + n]]
out = "-1"
done = False
for i in range(n):
    for j in range(i + 1, n):
        if a[i] + a[j] == t:
            out = f"{i + 1} {j + 1}"
            done = True
            break
    if done:
        break
print(out)
"""

# 버그: 0-indexed 출력 (off-by-one) → 범위/형식 invariant + differential 이 잡음.
_TWO_SUM_MUT_ZERO_INDEX = """\
import sys
d = sys.stdin.read().split()
n = int(d[0]); t = int(d[1])
a = [int(x) for x in d[2:2 + n]]
seen = {}
out = "-1"
for j in range(n):
    need = t - a[j]
    if need in seen:
        out = f"{seen[need]} {j}"
        break
    seen.setdefault(a[j], j)
print(out)
"""

# 버그: 보수 계산 부호 오류 (t + a[j]) → 잘못된 관계 → 존재성/합 invariant + diff.
_TWO_SUM_MUT_WRONG_COMPLEMENT = """\
import sys
d = sys.stdin.read().split()
n = int(d[0]); t = int(d[1])
a = [int(x) for x in d[2:2 + n]]
seen = {}
out = "-1"
for j in range(n):
    need = t + a[j]
    if need in seen:
        out = f"{seen[need] + 1} {j + 1}"
        break
    seen.setdefault(a[j], j)
print(out)
"""

# 버그: crash (ZeroDivisionError) → metamorphic well_formed 가 잡음.
_TWO_SUM_MUT_CRASH = """\
import sys
_ = 1 // 0
d = sys.stdin.read().split()
print("-1")
"""

_TWO_SUM_SAMPLES = (
    ("4 9\n2 7 11 15", "1 2"),  # 2+7=9 유일
    ("3 6\n3 2 4", "2 3"),  # 2+4=6 유일
    ("2 100\n1 2", "-1"),  # 없음
    ("5 8\n1 2 5 7 9", "1 4"),  # 1+7=8 유일
    ("4 0\n-2 5 2 8", "1 3"),  # -2+2=0 유일
)


def two_sum_fixture() -> AlgoFixture:
    """two_sum: golden(hash) + brute(O(N^2)) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.TWO_SUM,
        title="Two Sum",
        description="Find two 1-indexed indices i<j with a[i]+a[j]=T, else -1.",
        io_contract=IOContract(
            input_format="N T on first line, array a_1..a_N",
            output_format="'i j' (1-indexed, i<j) or '-1'",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _TWO_SUM_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Two Sum",
        complexity_target=ComplexityBound(time_big_o="O(N)", space_big_o="O(N)"),
        pseudocode="hash map: seen[T-a_j] returns earlier index.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_TWO_SUM_GOLDEN,
        brute_code=_TWO_SUM_BRUTE,
        mutants=(
            ("mut-zero-index", _TWO_SUM_MUT_ZERO_INDEX),
            ("mut-wrong-complement", _TWO_SUM_MUT_WRONG_COMPLEMENT),
            ("mut-crash", _TWO_SUM_MUT_CRASH),
        ),
    )


# --- binary_search --------------------------------------------------------
# I/O: "N T" + 오름차순 배열. 출력 1-indexed 인덱스 또는 -1.
# 샘플은 유일-타깃 또는 부재 → golden(이분) 과 brute(선형) 가 동일 인덱스 수렴.

_BSEARCH_GOLDEN = """\
import sys
d = sys.stdin.read().split()
n = int(d[0]); t = int(d[1])
a = [int(x) for x in d[2:2 + n]]
lo, hi = 0, n - 1
ans = -1
while lo <= hi:
    mid = (lo + hi) // 2
    if a[mid] == t:
        ans = mid + 1
        break
    if a[mid] < t:
        lo = mid + 1
    else:
        hi = mid - 1
print(ans)
"""

# 구조 독립: O(N) 선형 스캔.
_BSEARCH_BRUTE = """\
import sys
d = sys.stdin.read().split()
n = int(d[0]); t = int(d[1])
a = [int(x) for x in d[2:2 + n]]
ans = -1
for i in range(n):
    if a[i] == t:
        ans = i + 1
        break
print(ans)
"""

# 버그: 0-indexed 반환 (ans = mid) → 잘못된 인덱스 → value/range invariant + diff.
_BSEARCH_MUT_ZERO_INDEX = """\
import sys
d = sys.stdin.read().split()
n = int(d[0]); t = int(d[1])
a = [int(x) for x in d[2:2 + n]]
lo, hi = 0, n - 1
ans = -1
while lo <= hi:
    mid = (lo + hi) // 2
    if a[mid] == t:
        ans = mid
        break
    if a[mid] < t:
        lo = mid + 1
    else:
        hi = mid - 1
print(ans)
"""

# 버그: 비교 방향 반전 → 존재하는 T 를 놓침 → 존재성 invariant + diff.
_BSEARCH_MUT_WRONG_COMPARE = """\
import sys
d = sys.stdin.read().split()
n = int(d[0]); t = int(d[1])
a = [int(x) for x in d[2:2 + n]]
lo, hi = 0, n - 1
ans = -1
while lo <= hi:
    mid = (lo + hi) // 2
    if a[mid] == t:
        ans = mid + 1
        break
    if a[mid] > t:
        lo = mid + 1
    else:
        hi = mid - 1
print(ans)
"""

_BSEARCH_MUT_CRASH = """\
import sys
_ = 1 // 0
print(-1)
"""

_BSEARCH_SAMPLES = (
    ("5 7\n1 3 5 7 9", "4"),  # 유일
    ("4 100\n1 2 3 4", "-1"),  # 부재
    ("6 5\n1 2 5 8 9 11", "3"),  # 유일
    ("7 1\n1 3 5 7 9 11 13", "1"),  # 유일(첫)
    ("5 13\n2 4 6 8 10", "-1"),  # 부재
)


def binary_search_fixture() -> AlgoFixture:
    """binary_search: golden(이분) + brute(선형) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.BINARY_SEARCH,
        title="Binary Search",
        description="Find 1-indexed position of T in sorted array, else -1.",
        io_contract=IOContract(
            input_format="N T on first line, sorted ascending array",
            output_format="1-indexed index or -1",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _BSEARCH_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Binary Search",
        complexity_target=ComplexityBound(time_big_o="O(log N)", space_big_o="O(1)"),
        pseudocode="lo=0,hi=N-1; while lo<=hi: mid; compare a[mid] with T.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_BSEARCH_GOLDEN,
        brute_code=_BSEARCH_BRUTE,
        mutants=(
            ("mut-zero-index", _BSEARCH_MUT_ZERO_INDEX),
            ("mut-wrong-compare", _BSEARCH_MUT_WRONG_COMPARE),
            ("mut-crash", _BSEARCH_MUT_CRASH),
        ),
    )


# --- sieve -----------------------------------------------------------------
# I/O: N (단일 정수) → N 이하 소수 오름차순 공백구분. 샘플은 N>=2 (빈 출력 회피).

_SIEVE_GOLDEN = """\
import sys
n = int(sys.stdin.read().split()[0])
sieve = [True] * (n + 1)
sieve[0] = sieve[1] = False
i = 2
while i * i <= n:
    if sieve[i]:
        for j in range(i * i, n + 1, i):
            sieve[j] = False
    i += 1
print(" ".join(str(k) for k in range(2, n + 1) if sieve[k]))
"""

# 구조 독립: 수마다 trial division.
_SIEVE_BRUTE = """\
import sys
n = int(sys.stdin.read().split()[0])


def is_prime(x):
    if x < 2:
        return False
    d = 2
    while d * d <= x:
        if x % d == 0:
            return False
        d += 1
    return True


print(" ".join(str(k) for k in range(2, n + 1) if is_prime(k)))
"""

# 버그: 소수 2 누락 (출력 range 3 시작) → 완전성 invariant + diff.
_SIEVE_MUT_MISS_TWO = """\
import sys
n = int(sys.stdin.read().split()[0])
sieve = [True] * (n + 1)
sieve[0] = sieve[1] = False
i = 2
while i * i <= n:
    if sieve[i]:
        for j in range(i * i, n + 1, i):
            sieve[j] = False
    i += 1
print(" ".join(str(k) for k in range(3, n + 1) if sieve[k]))
"""

# 버그: 1 을 소수로 포함 (sieve[1] 미표기 + range 1 시작) → 소수성 invariant + diff.
_SIEVE_MUT_INCLUDE_ONE = """\
import sys
n = int(sys.stdin.read().split()[0])
sieve = [True] * (n + 1)
sieve[0] = False
i = 2
while i * i <= n:
    if sieve[i]:
        for j in range(i * i, n + 1, i):
            sieve[j] = False
    i += 1
print(" ".join(str(k) for k in range(1, n + 1) if sieve[k]))
"""

_SIEVE_MUT_CRASH = """\
import sys
_ = 1 // 0
print("2")
"""

_SIEVE_SAMPLES = (
    ("10", "2 3 5 7"),
    ("20", "2 3 5 7 11 13 17 19"),
    ("2", "2"),
    ("30", "2 3 5 7 11 13 17 19 23 29"),
    ("7", "2 3 5 7"),
)


def sieve_fixture() -> AlgoFixture:
    """sieve: golden(체) + brute(trial division) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SIEVE,
        title="Sieve of Eratosthenes",
        description="Ascending primes <= N, space-separated.",
        io_contract=IOContract(
            input_format="N (single integer, N >= 2)",
            output_format="ascending primes <= N, space-separated",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _SIEVE_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Sieve of Eratosthenes",
        complexity_target=ComplexityBound(time_big_o="O(N log log N)", space_big_o="O(N)"),
        pseudocode="Mark multiples of each prime as composite.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_SIEVE_GOLDEN,
        brute_code=_SIEVE_BRUTE,
        mutants=(
            ("mut-miss-two", _SIEVE_MUT_MISS_TWO),
            ("mut-include-one", _SIEVE_MUT_INCLUDE_ONE),
            ("mut-crash", _SIEVE_MUT_CRASH),
        ),
    )


THREE_ALGO_FIXTURES = (two_sum_fixture, binary_search_fixture, sieve_fixture)
"""step 4a~4b 실증 대상 (3-algo proof). 하위호환 유지."""

ALL_FIXTURES = (
    THREE_ALGO_FIXTURES
    + TRAVERSE_FIXTURES
    + SEQ_FIXTURES
    + SHORTEST_FIXTURES
    + STRUCT_FIXTURES
    + OPT_FIXTURES
)
"""step 4c 완료: 전체 19-algo (3 + 16). 각 항목은 () → AlgoFixture 팩토리.

구성: two_sum/binary_search/sieve(기존) + bfs/toposort/union_find(traverse)
+ sort/lis/knapsack/coin_change(seq) + dijkstra/bellman_ford/floyd_warshall(shortest)
+ segtree/fenwick/heap(struct) + kruskal_mst/maxflow/stringmatch(opt).
"""
