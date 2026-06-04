"""Tier sensitivity fixtures — 자료구조류 (segtree / fenwick / heap).

step 4c 확장 (see ``tier_fixtures`` 모듈 docstring). 모두 1-indexed 연산 시퀀스,
출력은 질의/pop 결과의 유일 시퀀스 → golden·brute 수렴.
brute 는 golden 과 다른 구조 (segtree↔naive slice sum, BIT↔naive prefix, binary-heap↔linear-min).
각 fixture 는 질의/pop op 을 최소 1개 포함 (빈 출력 회피 → metamorphic well_formed).
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

# --- segtree (Range Sum + Point Update, 1-indexed) -------------------------
# I/O: "N Q" + 배열 + Q ops. "U i v"=A[i]=v (set), "Q l r"=sum A[l..r]. 출력 Q마다 한 줄.

_SEG_GOLDEN = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
q = int(data[idx]); idx += 1
arr = [int(data[idx + k]) for k in range(n)]
idx += n
size = 1
while size < n:
    size *= 2
tree = [0] * (2 * size)
for k in range(n):
    tree[size + k] = arr[k]
for k in range(size - 1, 0, -1):
    tree[k] = tree[2 * k] + tree[2 * k + 1]


def update(pos, val):
    p = size + pos
    tree[p] = val
    p //= 2
    while p >= 1:
        tree[p] = tree[2 * p] + tree[2 * p + 1]
        p //= 2


def query(lft, rgt):
    res = 0
    lo = size + lft
    hi = size + rgt + 1
    while lo < hi:
        if lo & 1:
            res += tree[lo]; lo += 1
        if hi & 1:
            hi -= 1; res += tree[hi]
        lo //= 2; hi //= 2
    return res


out = []
for _ in range(q):
    op = data[idx]; idx += 1
    a = int(data[idx]); idx += 1
    b = int(data[idx]); idx += 1
    if op == "U":
        update(a - 1, b)
    else:
        out.append(str(query(a - 1, b - 1)))
print("\\n".join(out))
"""

# 구조 독립: 트리 대신 평면 배열, Q 마다 slice 합 O(N).
_SEG_BRUTE = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
q = int(data[idx]); idx += 1
arr = [int(data[idx + k]) for k in range(n)]
idx += n
out = []
for _ in range(q):
    op = data[idx]; idx += 1
    a = int(data[idx]); idx += 1
    b = int(data[idx]); idx += 1
    if op == "U":
        arr[a - 1] = b
    else:
        out.append(str(sum(arr[a - 1:b])))
print("\\n".join(out))
"""

# 버그: 질의 우측 경계 제외 (off-by-one) → range_sum_optimal.
_SEG_MUT_OFF_BY_ONE = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
q = int(data[idx]); idx += 1
arr = [int(data[idx + k]) for k in range(n)]
idx += n
out = []
for _ in range(q):
    op = data[idx]; idx += 1
    a = int(data[idx]); idx += 1
    b = int(data[idx]); idx += 1
    if op == "U":
        arr[a - 1] = b
    else:
        out.append(str(sum(arr[a - 1:b - 1])))
print("\\n".join(out))
"""

# 버그: update 무시 → 갱신 후 질의가 옛 값 → range_sum_optimal.
_SEG_MUT_NO_UPDATE = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
q = int(data[idx]); idx += 1
arr = [int(data[idx + k]) for k in range(n)]
idx += n
out = []
for _ in range(q):
    op = data[idx]; idx += 1
    a = int(data[idx]); idx += 1
    b = int(data[idx]); idx += 1
    if op == "U":
        pass
    else:
        out.append(str(sum(arr[a - 1:b])))
print("\\n".join(out))
"""

_SEG_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_SEG_SAMPLES = (
    ("5 3\n1 2 3 4 5\nQ 1 5\nU 3 10\nQ 1 5", "15\n22"),
    ("3 2\n10 20 30\nQ 2 3\nQ 1 1", "50\n10"),
    ("4 3\n0 0 0 0\nU 1 5\nU 4 7\nQ 1 4", "12"),
    ("5 3\n1 2 3 4 5\nQ 2 4\nU 2 0\nQ 2 4", "9\n7"),  # 갱신 전후
    ("1 3\n7\nQ 1 1\nU 1 9\nQ 1 1", "7\n9"),
)


def segtree_fixture() -> AlgoFixture:
    """segtree: golden(iterative tree) + brute(slice sum) + 3 mutants. 1-indexed."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.SEGTREE,
        title="Segment Tree (Range Sum + Point Update)",
        description="Range sum queries with point updates over an array.",
        io_contract=IOContract(
            input_format="N Q on first line, array, then Q ops 'U i v' or 'Q l r' (1-indexed)",
            output_format="one integer per Q op",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _SEG_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Segment Tree",
        complexity_target=ComplexityBound(time_big_o="O((N+Q) log N)", space_big_o="O(N)"),
        pseudocode="build O(N); point update and range query in O(log N).",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_SEG_GOLDEN,
        brute_code=_SEG_BRUTE,
        mutants=(
            ("mut-off-by-one", _SEG_MUT_OFF_BY_ONE),
            ("mut-no-update", _SEG_MUT_NO_UPDATE),
            ("mut-crash", _SEG_MUT_CRASH),
        ),
    )


# --- fenwick (point-add + prefix-sum, 1-indexed) ---------------------------
# I/O: "N Q" + 배열 + Q ops. "A i v"=A[i]+=v (add), "Q i"=prefix sum A[1..i]. 출력 Q마다 한 줄.

_FEN_GOLDEN = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
q = int(data[idx]); idx += 1
bit = [0] * (n + 1)


def add(i, v):
    while i <= n:
        bit[i] += v
        i += i & (-i)


def prefix(i):
    s = 0
    while i > 0:
        s += bit[i]
        i -= i & (-i)
    return s


for k in range(n):
    add(k + 1, int(data[idx + k]))
idx += n
out = []
for _ in range(q):
    op = data[idx]; idx += 1
    if op == "A":
        i = int(data[idx]); idx += 1
        v = int(data[idx]); idx += 1
        add(i, v)
    else:
        i = int(data[idx]); idx += 1
        out.append(str(prefix(i)))
print("\\n".join(out))
"""

# 구조 독립: BIT 대신 평면 배열, Q 마다 prefix slice 합.
_FEN_BRUTE = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
q = int(data[idx]); idx += 1
arr = [0] * (n + 1)
for k in range(n):
    arr[k + 1] = int(data[idx + k])
idx += n
out = []
for _ in range(q):
    op = data[idx]; idx += 1
    if op == "A":
        i = int(data[idx]); idx += 1
        v = int(data[idx]); idx += 1
        arr[i] += v
    else:
        i = int(data[idx]); idx += 1
        out.append(str(sum(arr[1:i + 1])))
print("\\n".join(out))
"""

# 버그: add 를 set 으로 (point-add 의미 오류) → prefix_sum_matches_naive.
_FEN_MUT_SET_NOT_ADD = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
q = int(data[idx]); idx += 1
arr = [0] * (n + 1)
for k in range(n):
    arr[k + 1] = int(data[idx + k])
idx += n
out = []
for _ in range(q):
    op = data[idx]; idx += 1
    if op == "A":
        i = int(data[idx]); idx += 1
        v = int(data[idx]); idx += 1
        arr[i] = v
    else:
        i = int(data[idx]); idx += 1
        out.append(str(sum(arr[1:i + 1])))
print("\\n".join(out))
"""

# 버그: prefix 가 i 제외 (off-by-one) → prefix_sum_matches_naive.
_FEN_MUT_OFF_BY_ONE = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
q = int(data[idx]); idx += 1
arr = [0] * (n + 1)
for k in range(n):
    arr[k + 1] = int(data[idx + k])
idx += n
out = []
for _ in range(q):
    op = data[idx]; idx += 1
    if op == "A":
        i = int(data[idx]); idx += 1
        v = int(data[idx]); idx += 1
        arr[i] += v
    else:
        i = int(data[idx]); idx += 1
        out.append(str(sum(arr[1:i])))
print("\\n".join(out))
"""

_FEN_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_FEN_SAMPLES = (
    ("5 4\n1 2 3 4 5\nQ 3\nA 2 10\nQ 5\nA 1 -3", "6\n25"),
    ("3 3\n1 1 1\nQ 1\nQ 2\nQ 3", "1\n2\n3"),
    ("4 2\n0 0 0 0\nA 4 5\nQ 4", "5"),
    ("4 3\n1 2 3 4\nQ 4\nA 3 10\nQ 4", "10\n20"),  # add 후
    ("3 2\n5 5 5\nA 1 5\nQ 2", "15"),
)


def fenwick_fixture() -> AlgoFixture:
    """fenwick: golden(BIT) + brute(prefix slice) + 3 mutants. 1-indexed, point-add."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.FENWICK,
        title="Fenwick Tree (point-add + prefix-sum)",
        description="Point additions and prefix-sum queries over an array.",
        io_contract=IOContract(
            input_format="N Q on first line, array, then Q ops 'A i v' (add) or 'Q i' (1-indexed)",
            output_format="one integer (prefix sum) per Q op",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _FEN_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Fenwick Tree (BIT)",
        complexity_target=ComplexityBound(time_big_o="O(Q log N)", space_big_o="O(N)"),
        pseudocode="BIT: i += i & -i for add, i -= i & -i for prefix sum.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_FEN_GOLDEN,
        brute_code=_FEN_BRUTE,
        mutants=(
            ("mut-set-not-add", _FEN_MUT_SET_NOT_ADD),
            ("mut-off-by-one", _FEN_MUT_OFF_BY_ONE),
            ("mut-crash", _FEN_MUT_CRASH),
        ),
    )


# --- heap (min-heap, op 시퀀스) --------------------------------------------
# I/O: "N" + N ops. "P x"=push, "O"=pop-min(출력). 출력 O op 마다 popped value.

_HEAP_GOLDEN = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
heap = []


def push(x):
    heap.append(x)
    i = len(heap) - 1
    while i > 0:
        parent = (i - 1) // 2
        if heap[parent] <= heap[i]:
            break
        heap[parent], heap[i] = heap[i], heap[parent]
        i = parent


def pop():
    last = len(heap) - 1
    heap[0], heap[last] = heap[last], heap[0]
    val = heap.pop()
    i = 0
    size = len(heap)
    while True:
        left = 2 * i + 1
        right = 2 * i + 2
        smallest = i
        if left < size and heap[left] < heap[smallest]:
            smallest = left
        if right < size and heap[right] < heap[smallest]:
            smallest = right
        if smallest == i:
            break
        heap[i], heap[smallest] = heap[smallest], heap[i]
        i = smallest
    return val


out = []
for _ in range(n):
    op = data[idx]; idx += 1
    if op == "P":
        x = int(data[idx]); idx += 1
        push(x)
    else:
        out.append(str(pop()))
print("\\n".join(out))
"""

# 구조 독립: 이진 힙 대신 list + 선형 min 탐색.
_HEAP_BRUTE = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
items = []
out = []
for _ in range(n):
    op = data[idx]; idx += 1
    if op == "P":
        x = int(data[idx]); idx += 1
        items.append(x)
    else:
        m = min(items)
        items.remove(m)
        out.append(str(m))
print("\\n".join(out))
"""

# 버그: max 우선 pop (비교 반전) → matches_naive_min_heap_golden.
_HEAP_MUT_MAX = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
items = []
out = []
for _ in range(n):
    op = data[idx]; idx += 1
    if op == "P":
        x = int(data[idx]); idx += 1
        items.append(x)
    else:
        m = max(items)
        items.remove(m)
        out.append(str(m))
print("\\n".join(out))
"""

# 버그: pop 값 +1 (off-by-one) → push 되지 않은 값 → all_popped_in_pushed_multiset.
_HEAP_MUT_PLUS_ONE = """\
import sys
data = sys.stdin.read().split()
idx = 0
n = int(data[idx]); idx += 1
items = []
out = []
for _ in range(n):
    op = data[idx]; idx += 1
    if op == "P":
        x = int(data[idx]); idx += 1
        items.append(x)
    else:
        m = min(items)
        items.remove(m)
        out.append(str(m + 1))
print("\\n".join(out))
"""

_HEAP_MUT_CRASH = """\
import sys
_ = 1 // 0
print("0")
"""

_HEAP_SAMPLES = (
    ("5\nP 5\nP 3\nO\nP 7\nO", "3\n5"),
    ("4\nP 1\nP 2\nO\nO", "1\n2"),
    ("3\nP 10\nP -5\nO", "-5"),
    ("6\nP 5\nO\nP 3\nP 7\nO\nO", "5\n3\n7"),  # interleaved
    ("5\nP 5\nP 5\nP 5\nO\nO", "5\n5"),  # 중복
)


def heap_fixture() -> AlgoFixture:
    """heap(min): golden(binary heap) + brute(선형 min) + 3 mutants."""
    spec = ProblemSpec(
        target_algorithm=TargetAlgorithm.HEAP,
        title="Min-Heap (priority queue)",
        description="Process push/pop-min ops; output each popped minimum value.",
        io_contract=IOContract(
            input_format="N on first line, then N ops 'P x' (push) or 'O' (pop-min)",
            output_format="one integer (popped value) per pop op",
        ),
        sample_testcases=[
            SampleTestCase(input_text=inp, expected_output=out) for inp, out in _HEAP_SAMPLES
        ],
    )
    design = AlgorithmDesign(
        algorithm_name="Binary Min-Heap",
        complexity_target=ComplexityBound(time_big_o="O(N log N)", space_big_o="O(N)"),
        pseudocode="array heap: sift up on push, sift down on pop.",
    )
    return AlgoFixture(
        spec=spec,
        design=design,
        golden_code=_HEAP_GOLDEN,
        brute_code=_HEAP_BRUTE,
        mutants=(
            ("mut-max", _HEAP_MUT_MAX),
            ("mut-plus-one", _HEAP_MUT_PLUS_ONE),
            ("mut-crash", _HEAP_MUT_CRASH),
        ),
    )


STRUCT_FIXTURES = (segtree_fixture, fenwick_fixture, heap_fixture)
"""자료구조류 fixture (step 4c)."""
