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


THREE_ALGO_FIXTURES = (two_sum_fixture,)
"""step 4a 실증 대상. 4b 에서 binary_search/sieve 추가."""
