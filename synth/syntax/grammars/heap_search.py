from collections import defaultdict
from heapq import heappush, heappop
from typing import (
    Any,
    Dict,
    Generator,
    Generic,
    List,
    Optional,
    Set,
    Tuple,
    TypeVar,
    Union,
)
from dataclasses import dataclass, field
from abc import ABC, abstractmethod

from synth.syntax.program import Program, Function, Variable
from synth.syntax.grammars.tagged_det_grammar import ProbDetGrammar
from synth.syntax.type_system import Type
from synth.utils.ordered import Ordered

U = TypeVar("U")
V = TypeVar("V")
W = TypeVar("W")


@dataclass(order=True, frozen=True)
class HeapElement:
    priority: Ordered
    program: Program = field(compare=False)

    def __repr__(self) -> str:
        return f"({self.priority}, {self.program})"


class HSEnumerator(ABC, Generic[U, V, W]):
    def __init__(self, G: ProbDetGrammar[U, V, W]) -> None:
        self.current: Optional[Program] = None

        self.G = G
        self.start = G.start
        self.rules = G.rules
        symbols = [S for S in self.rules]

        # self.heaps[S] is a heap containing programs generated from the non-terminal S
        self.heaps: Dict[Tuple[Type, U], List[HeapElement]] = {S: [] for S in symbols}

        # the same program can be pushed in different heaps, with different probabilities
        # however, the same program cannot be pushed twice in the same heap

        # self.succ[S][P] is the successor of P from S
        self.succ: Dict[Tuple[Type, U], Dict[int, Program]] = {S: {} for S in symbols}

        # self.hash_table_program[S] is the set of hashes of programs
        # ever added to the heap for S
        self.hash_table_program: Dict[Tuple[Type, U], Set[int]] = {
            S: set() for S in symbols
        }

        # self.hash_table_global[hash] = P maps
        # hashes to programs for all programs ever added to some heap
        self.hash_table_global: Dict[int, Program] = {}

        self._init: Set[Tuple[Type, U]] = set()

        self.max_priority: Dict[
            Union[Tuple[Type, U], Tuple[Tuple[Type, U], Program]], Program
        ] = {}

    def __return_unique__(self, P: Program) -> Program:
        """
        ensures that if a program appears in several heaps,
        it is represented by the same object,
        so we do not evaluate it several times
        """
        hash_P = hash(P)
        if hash_P in self.hash_table_global:
            return self.hash_table_global[hash_P]
        else:
            self.hash_table_global[hash_P] = P
            return P

    def generator(self) -> Generator[Program, None, None]:
        """
        A generator which outputs the next most probable program
        """
        while True:
            program = self.query(self.start, self.current)
            if program is None:
                break
            self.current = program
            yield program

    def __iter__(self) -> Generator[Program, None, None]:
        return self.generator()

    def __init_non_terminal__(self, S: Tuple[Type, U]) -> None:
        if S in self._init:
            return
        self._init.add(S)
        # 1) Compute max probablities
        best_program = None
        best_priority: Optional[Ordered] = None
        for P in self.rules[S]:
            nargs = self.G.arguments_length_for(S, P)
            P_unique: Program = P
            if nargs > 0:
                arguments = []
                information, current = self.G.derive(self.G.start_information(), S, P)
                for _ in range(nargs):
                    self.__init_non_terminal__(current)
                    # Try to init sub Tuple[Type, U] in case they were not initialised
                    arguments.append(self.max_priority[current])
                    information, lst = self.G.derive_all(
                        information, current, arguments[-1]
                    )
                    current = lst[-1]

                new_program = Function(
                    function=P_unique,
                    arguments=arguments,
                )
                P_unique = new_program
            priority = self.compute_priority(S, P_unique)
            self.max_priority[(S, P)] = P_unique
            if not best_priority or priority < best_priority:
                best_program = P_unique
                best_priority = priority
        assert best_program
        self.max_priority[S] = best_program

        # 2) add P(max(S1),max(S2), ...) to self.heaps[S]
        for P in self.rules[S]:
            program = self.max_priority[(S, P)]
            hash_program = hash(program)
            # Remark: the program cannot already be in self.heaps[S]
            assert hash_program not in self.hash_table_program[S]
            self.hash_table_program[S].add(hash_program)
            # we assume that the programs from max_probability
            # are represented by the same object
            self.hash_table_global[hash_program] = program
            priority = self.compute_priority(S, program)
            heappush(
                self.heaps[S],
                HeapElement(priority, program),
            )

        # 3) Do the 1st query
        self.query(S, None)

    def query(self, S: Tuple[Type, U], program: Optional[Program]) -> Optional[Program]:
        """
        computing the successor of program from S
        """
        if S not in self._init:
            self.__init_non_terminal__(S)
        if program:
            hash_program = hash(program)
        else:
            hash_program = 123891

        # if we have already computed the successor of program from S, we return its stored value
        if hash_program in self.succ[S]:
            return self.succ[S][hash_program]

        # otherwise the successor is the next element in the heap
        try:
            element = heappop(self.heaps[S])
            succ = element.program
        except:
            return None  # the heap is empty: there are no successors from S

        self.succ[S][hash_program] = succ  # we store the successor

        # now we need to add all potential successors of succ in heaps[S]
        if isinstance(succ, Function):
            F = succ.function
            information, lst = self.G.derive_all(self.G.start_information(), S, F)
            S2 = lst[-1]
            for i in range(self.G.arguments_length_for(S, F)):  # type: ignore
                # S2 is non-terminal symbol used to derive the i-th argument
                succ_sub_program = self.query(S2, succ.arguments[i])
                if succ_sub_program:
                    new_arguments = succ.arguments[:]
                    new_arguments[i] = succ_sub_program

                    new_program = self.__return_unique__(Function(F, new_arguments))
                    hash_new_program = hash(new_program)

                    if hash_new_program not in self.hash_table_program[S]:
                        self.hash_table_program[S].add(hash_new_program)

                        priority: Ordered = self.compute_priority(S, new_program)
                        heappush(self.heaps[S], HeapElement(priority, new_program))
                information, lst = self.G.derive_all(information, S2, succ.arguments[i])
                S2 = lst[-1]

        if isinstance(succ, Variable):
            return succ  # if succ is a variable, there is no successor so we stop here

        return succ

    @abstractmethod
    def compute_priority(self, S: Tuple[Type, U], new_program: Program) -> Ordered:
        pass


class HeapSearch(HSEnumerator[U, V, W]):
    def __init__(self, G: ProbDetGrammar[U, V, W]) -> None:
        super().__init__(G)
        self.probabilities: Dict[Program, Dict[Tuple[Type, U], float]] = defaultdict(
            lambda: {}
        )

    def compute_priority(self, S: Tuple[Type, U], new_program: Program) -> float:
        if isinstance(new_program, Function):
            F = new_program.function
            # We guarantee that F is a Primitive
            new_arguments = new_program.arguments
            probability = self.G.probabilities[S][F]  # type: ignore
            information, lst = self.G.derive_all(self.G.start_information(), S, F)
            S2 = lst[-1]
            for i in range(self.G.arguments_length_for(S, F)):  # type: ignore
                arg = new_arguments[i]
                probability *= self.probabilities[arg][S2]
                information, lst = self.G.derive_all(information, S2, arg)
                S2 = lst[-1]
        else:
            probability = self.G.probabilities[S][new_program]  # type: ignore
        self.probabilities[new_program][S] = probability
        return -probability


def enumerate_prob_grammar(G: ProbDetGrammar[U, V, W]) -> HeapSearch[U, V, W]:
    return HeapSearch(G)


class Bucket(Ordered):
    def __init__(self, size: int = 3):
        self.elems = [0 for _ in range(size)]
        self.size = size

    def __str__(self) -> str:
        s = "("
        for elem in self.elems:
            s += "{},".format(elem)
        s = s[:-1] + ")"
        return s

    def __repr__(self) -> str:
        return str(self)

    def __lt__(self, other: "Bucket") -> bool:
        if self.size == 0:
            return False
        for i in range(self.size):
            if self.elems[i] < other.elems[i]:
                return True
            elif self.elems[i] > other.elems[i]:
                return False
        return False

    def __gt__(self, other: "Bucket") -> bool:
        return other.__lt__(self)

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Bucket) and all(
            self.elems[i] == other.elems[i] for i in range(self.size)
        )

    def __le__(self, other: "Bucket") -> bool:
        return self.__lt__(other) or self.__eq__(other)

    def __ge__(self, other: "Bucket") -> bool:
        return self.__gt__(other) or self.__eq__(other)

    def __iadd__(self, other: "Bucket") -> "Bucket":
        if self.size == other.size:
            for i in range(self.size):
                self.elems[i] += other.elems[i]
            return self
        else:
            raise RuntimeError(
                "size mismatch, Bucket{}: {}, Bucket{}: {}".format(
                    self, self.size, other, other.size
                )
            )

    def add_prob_uniform(self, probability: float) -> "Bucket":
        """
        Given a probability add 1 in the relevant bucket assuming buckets are linearly distributed.
        """
        index = self.size - int(probability * self.size) - 1
        self.elems[index] += 1
        return self


class BucketSearch(HSEnumerator[U, V, W]):
    def __init__(self, G: ProbDetGrammar[U, V, W], bucket_size: int) -> None:
        super().__init__(G)
        self.bucket_tuples: Dict[Program, Dict[Tuple[Type, U], Bucket]] = defaultdict(
            lambda: {}
        )
        self.bucket_size = bucket_size

    def compute_priority(self, S: Tuple[Type, U], new_program: Program) -> Bucket:
        new_bucket = Bucket(self.bucket_size)
        if isinstance(new_program, Function):
            F = new_program.function
            new_arguments = new_program.arguments
            new_bucket.add_prob_uniform(self.G.probabilities[S][F])  # type: ignore

            information, lst = self.G.derive_all(self.G.start_information(), S, F)
            S2 = lst[-1]
            for i in range(self.G.arguments_length_for(S, F)):  # type: ignore
                arg = new_arguments[i]
                new_bucket += self.bucket_tuples[arg][S2]
                information, lst = self.G.derive_all(information, S2, arg)
                S2 = lst[-1]
        else:
            probability = self.G.probabilities[S][new_program]  # type: ignore
            new_bucket.add_prob_uniform(probability)
        self.bucket_tuples[new_program][S] = new_bucket
        return new_bucket


def enumerate_bucket_prob_grammar(
    G: ProbDetGrammar[U, V, W], bucket_size: int
) -> BucketSearch[U, V, W]:
    return BucketSearch(G, bucket_size)
