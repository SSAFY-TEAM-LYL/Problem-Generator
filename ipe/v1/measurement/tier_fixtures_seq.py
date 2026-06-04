"""Tier sensitivity fixtures — 수열/DP류 (sort / lis / knapsack / coin_change).

step 4c 확장 (see ``tier_fixtures`` 모듈 docstring). 모든 출력은 유일답
(정렬결과 / LIS 길이 / 최대가치 / 최소동전수) → golden·brute 수렴.
brute 는 golden 과 다른 구조 (merge↔selection, patience↔O(N^2)DP, DP↔subset-enum, DP↔BFS).
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

# --- sort ------------------------------------------------------------------
# I/O: "N" + N 정수. 출력: 오름차순 공백구분. N>=1 (빈 출력 회피).

_SORT_GOLDEN = """\
import sys
d = sys.stdin.read().split()
n = int(d[0])
a = [int(x) for x in d[1:1 + n]]


def merge_sort(arr):
    if len(arr) <= 1:
        return arr
    mid = len(arr) // 2
    left = merge_sort(arr[:mid])
    right = merge_sort(arr[mid:])
    res = []
    i = j = 0
    while i < len(left) and j < len(right):
        if left[i] <= right[j]:
            res.append(left[i]); i += 1
        else:
            res.append(right[j]); j += 1
    res.extend(left[i:])
    res.extend(right[j:])
    return res


print(" ".join(map(str, merge_sort(a))))
"""

# 구조 독립: merge sort 대신 selection sort (in-place O(N^2)).
_SORT_BRUTE = """\
import sys
d = sys.stdin.read().split()
n = int(d[0])
a = [int(x) for x in d[1:1 + n]]
for i in range(n):
    m = i
    for j in range(i + 1, n):
        if a[j] < a[m]:
            m = j
    a[i], a[m] = a[m], a[i]
print(" ".join(map(str, a)))
"""

# 버그: 정렬 안 함 (입력 그대로) → output_is_sorted_ascending.
_SORT_MUT_UNSORTED = """\
import sys
d = sys.stdin.read().split()
n = int(d[0])
a = [int(x) for x in d[1:1 + n]]
print(" ".join(map(str, a)))
"""

# 버그: 마지막 원소 누락 (off-by-one) → output_length_matches_n / multiset.
_SORT_MUT_DROP_LAST = """\
import sys
d = sys.stdin.read().split()
n = int(d[0])
a = sorted(int(x) for x in d[1:1 + n])
print(" ".join(map(str, a[:-1])))
"""

_SORT_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_SORT_SAMPLES = (
    ("5\n3 1 4 1 5", "1 1 3 4 5"),
    ("4\n-2 -5 3 0", "-5 -2 0 3"),
    ("3\n7 7 7", "7 7 7"),
    ("5\n5 4 3 2 1", "1 2 3 4 5"),
    ("1\n42", "42"),
)


def sort_fixture() -> AlgoFixture:
    """sort: golden(merge) + brute(selection) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SORT,
        title="Comparison Sort",
        description="Sort N integers in ascending order.",
        io_contract=IOContract(
            input_format="N on first line, then N integers",
            output_format="N integers sorted ascending, space-separated",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _SORT_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Merge Sort",
        complexity_target=ComplexityBound(time_big_o="O(N log N)", space_big_o="O(N)"),
        pseudocode="divide in half, sort each, merge.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_SORT_GOLDEN,
        brute_code=_SORT_BRUTE,
        mutants=(
            ("mut-unsorted", _SORT_MUT_UNSORTED),
            ("mut-drop-last", _SORT_MUT_DROP_LAST),
            ("mut-crash", _SORT_MUT_CRASH),
        ),
    )


# --- lis -------------------------------------------------------------------
# I/O: "N" + N 정수. 출력: LIS 길이(strictly increasing) 단일 정수.

_LIS_GOLDEN = """\
import sys
import bisect
d = sys.stdin.read().split()
n = int(d[0])
a = [int(x) for x in d[1:1 + n]]
tails = []
for x in a:
    i = bisect.bisect_left(tails, x)
    if i == len(tails):
        tails.append(x)
    else:
        tails[i] = x
print(len(tails))
"""

# 구조 독립: patience sort 대신 O(N^2) DP.
_LIS_BRUTE = """\
import sys
d = sys.stdin.read().split()
n = int(d[0])
a = [int(x) for x in d[1:1 + n]]
if n == 0:
    print(0)
else:
    dp = [1] * n
    for i in range(n):
        for j in range(i):
            if a[j] < a[i] and dp[j] + 1 > dp[i]:
                dp[i] = dp[j] + 1
    print(max(dp))
"""

# 버그: non-strict (bisect_right) → 같은 값 중복 카운트 → length_optimal.
_LIS_MUT_NON_STRICT = """\
import sys
import bisect
d = sys.stdin.read().split()
n = int(d[0])
a = [int(x) for x in d[1:1 + n]]
tails = []
for x in a:
    i = bisect.bisect_right(tails, x)
    if i == len(tails):
        tails.append(x)
    else:
        tails[i] = x
print(len(tails))
"""

# 버그: 길이 +1 (off-by-one) → length_optimal / length_le_input_size.
_LIS_MUT_OFF_BY_ONE = """\
import sys
import bisect
d = sys.stdin.read().split()
n = int(d[0])
a = [int(x) for x in d[1:1 + n]]
tails = []
for x in a:
    i = bisect.bisect_left(tails, x)
    if i == len(tails):
        tails.append(x)
    else:
        tails[i] = x
print(len(tails) + 1)
"""

_LIS_MUT_CRASH = """\
import sys
_ = 1 // 0
print("1")
"""

_LIS_SAMPLES = (
    ("4\n1 3 2 4", "3"),
    ("5\n5 4 3 2 1", "1"),
    ("3\n10 20 30", "3"),
    ("3\n7 7 7", "1"),  # strict: 동일값 → 1 (non-strict mutant 노출)
    ("6\n1 2 1 2 3 4", "4"),
)


def lis_fixture() -> AlgoFixture:
    """lis: golden(patience sort) + brute(O(N^2) DP) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.LIS,
        title="Longest Strictly Increasing Subsequence",
        description="Output the length of the longest strictly increasing subsequence.",
        io_contract=IOContract(
            input_format="N on first line, then N integers",
            output_format="single integer (LIS length, strictly increasing)",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _LIS_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="LIS (patience sort)",
        complexity_target=ComplexityBound(time_big_o="O(N log N)", space_big_o="O(N)"),
        pseudocode="maintain tails[]; bisect_left to place each element.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_LIS_GOLDEN,
        brute_code=_LIS_BRUTE,
        mutants=(
            ("mut-non-strict", _LIS_MUT_NON_STRICT),
            ("mut-off-by-one", _LIS_MUT_OFF_BY_ONE),
            ("mut-crash", _LIS_MUT_CRASH),
        ),
    )


# --- knapsack --------------------------------------------------------------
# I/O: "N C" + N 줄 "w v". 출력: 최대 가치 단일 정수. N 작게(subset-enum brute).

_KNAP_GOLDEN = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
c = int(d[i]); i += 1
items = []
for _ in range(n):
    w = int(d[i]); i += 1
    val = int(d[i]); i += 1
    items.append((w, val))
dp = [0] * (c + 1)
for (w, val) in items:
    for cap in range(c, w - 1, -1):
        if dp[cap - w] + val > dp[cap]:
            dp[cap] = dp[cap - w] + val
print(dp[c])
"""

# 구조 독립: DP 대신 2^N subset 전수 (N<=~5 샘플).
_KNAP_BRUTE = """\
import sys
from itertools import combinations
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
c = int(d[i]); i += 1
items = []
for _ in range(n):
    w = int(d[i]); i += 1
    val = int(d[i]); i += 1
    items.append((w, val))
best = 0
for r in range(n + 1):
    for combo in combinations(range(n), r):
        tw = sum(items[k][0] for k in combo)
        tv = sum(items[k][1] for k in combo)
        if tw <= c and tv > best:
            best = tv
print(best)
"""

# 버그: capacity 오름차순 (1D DP) → item 재사용(unbounded) → value_optimal_via_brute 초과.
_KNAP_MUT_UNBOUNDED = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
c = int(d[i]); i += 1
items = []
for _ in range(n):
    w = int(d[i]); i += 1
    val = int(d[i]); i += 1
    items.append((w, val))
dp = [0] * (c + 1)
for (w, val) in items:
    for cap in range(w, c + 1):
        if dp[cap - w] + val > dp[cap]:
            dp[cap] = dp[cap - w] + val
print(dp[c])
"""

# 버그: 마지막 item 누락 (off-by-one) → value_optimal_via_brute 미달.
_KNAP_MUT_SKIP_LAST = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
c = int(d[i]); i += 1
items = []
for _ in range(n):
    w = int(d[i]); i += 1
    val = int(d[i]); i += 1
    items.append((w, val))
dp = [0] * (c + 1)
for (w, val) in items[:-1]:
    for cap in range(c, w - 1, -1):
        if dp[cap - w] + val > dp[cap]:
            dp[cap] = dp[cap - w] + val
print(dp[c])
"""

_KNAP_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_KNAP_SAMPLES = (
    ("3 5\n2 3\n3 4\n4 5", "7"),
    ("4 10\n5 10\n4 40\n6 30\n3 50", "90"),  # skip-last → 70
    ("3 100\n2 3\n3 4\n4 5", "12"),  # 전부 적재
    ("4 8\n2 3\n3 4\n4 5\n5 6", "10"),  # unbounded → 12
    ("2 0\n1 100\n1 200", "0"),  # 용량 0
)


def knapsack_fixture() -> AlgoFixture:
    """knapsack(0/1): golden(DP) + brute(subset enum) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.KNAPSACK,
        title="0/1 Knapsack",
        description="Maximum total value of a subset of items with total weight <= C.",
        io_contract=IOContract(
            input_format="N C on first line, then N lines 'w_i v_i' (1-indexed)",
            output_format="single integer — maximum value",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _KNAP_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="0/1 Knapsack DP",
        complexity_target=ComplexityBound(time_big_o="O(N*C)", space_big_o="O(C)"),
        pseudocode="1D dp[cap], iterate capacity descending per item (no reuse).",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_KNAP_GOLDEN,
        brute_code=_KNAP_BRUTE,
        mutants=(
            ("mut-unbounded", _KNAP_MUT_UNBOUNDED),
            ("mut-skip-last", _KNAP_MUT_SKIP_LAST),
            ("mut-crash", _KNAP_MUT_CRASH),
        ),
    )


# --- coin_change -----------------------------------------------------------
# I/O: "N A" + N 동전(c>=1, unbounded). 출력: 최소 동전수, 불가능 시 -1. A 작게.

_COIN_GOLDEN = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
a = int(d[i]); i += 1
coins = [int(d[i + k]) for k in range(n)]
INF = float("inf")
dp = [0] + [INF] * a
for amt in range(1, a + 1):
    for c in coins:
        if c <= amt and dp[amt - c] + 1 < dp[amt]:
            dp[amt] = dp[amt - c] + 1
print(dp[a] if dp[a] != INF else -1)
"""

# 구조 독립: 전방 DP 대신 금액 그래프 BFS (0→A 최단 간선수).
_COIN_BRUTE = """\
import sys
from collections import deque
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
a = int(d[i]); i += 1
coins = [int(d[i + k]) for k in range(n)]
dist = [-1] * (a + 1)
dist[0] = 0
q = deque([0])
while q:
    cur = q.popleft()
    for c in coins:
        nxt = cur + c
        if nxt <= a and dist[nxt] == -1:
            dist[nxt] = dist[cur] + 1
            q.append(nxt)
print(dist[a])
"""

# 버그: 동전수 +1 (off-by-one) → count_matches_dp_optimal.
_COIN_MUT_OFF_BY_ONE = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
a = int(d[i]); i += 1
coins = [int(d[i + k]) for k in range(n)]
INF = float("inf")
dp = [0] + [INF] * a
for amt in range(1, a + 1):
    for c in coins:
        if c <= amt and dp[amt - c] + 1 < dp[amt]:
            dp[amt] = dp[amt - c] + 1
print(dp[a] + 1 if dp[a] != INF else -1)
"""

# 버그: greedy 최대동전 우선 (비정규 동전계에서 suboptimal) → count_matches_dp_optimal.
_COIN_MUT_GREEDY = """\
import sys
d = sys.stdin.read().split()
i = 0
n = int(d[i]); i += 1
a = int(d[i]); i += 1
coins = sorted((int(d[i + k]) for k in range(n)), reverse=True)
cnt = 0
rem = a
for c in coins:
    while rem >= c:
        rem -= c
        cnt += 1
print(cnt if rem == 0 else -1)
"""

_COIN_MUT_CRASH = """\
import sys
_ = 1 // 0
print("-1")
"""

_COIN_SAMPLES = (
    ("3 11\n1 2 5", "3"),
    ("1 3\n2", "-1"),  # 불가능
    ("3 6\n1 3 4", "2"),  # greedy 실패: 4+1+1=3 vs 3+3=2
    ("4 7\n1 5 10 25", "3"),
    ("1 5\n1", "5"),  # unbounded
)


def coin_change_fixture() -> AlgoFixture:
    """coin_change: golden(DP) + brute(금액 BFS) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.COIN_CHANGE,
        title="Coin Change (min coins)",
        description="Minimum number of coins (unbounded) summing to A, or -1 if impossible.",
        io_contract=IOContract(
            input_format="N A on first line, then N coin denominations (c_i >= 1)",
            output_format="single integer — min coin count, or -1 if impossible",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _COIN_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Coin Change DP",
        complexity_target=ComplexityBound(time_big_o="O(N*A)", space_big_o="O(A)"),
        pseudocode="dp[amt] = min(dp[amt-c]+1 for c in coins if c<=amt).",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_COIN_GOLDEN,
        brute_code=_COIN_BRUTE,
        mutants=(
            ("mut-off-by-one", _COIN_MUT_OFF_BY_ONE),
            ("mut-greedy", _COIN_MUT_GREEDY),
            ("mut-crash", _COIN_MUT_CRASH),
        ),
    )


SEQ_FIXTURES = (sort_fixture, lis_fixture, knapsack_fixture, coin_change_fixture)
"""수열/DP류 fixture (step 4c)."""
