from collections import deque
from math import prod
from typing import Deque, Dict, Literal, Set, Tuple, List

from synth.syntax.dsl import DSL
from synth.syntax.grammars.det_grammar import DerivableProgram
from synth.syntax.grammars.ttcfg import TTCFG, NGram
from synth.syntax.program import Constant, Primitive, Variable
from synth.syntax.type_system import Arrow, Type


NoneType = Literal[None]
CFGState = Tuple[NGram, int]
CFGNonTerminal = Tuple[Type, Tuple[CFGState, NoneType]]


class CFG(TTCFG[CFGState, NoneType]):
    """
    Represents a deterministic Context Free Grammar (CFG).
    """

    def max_program_depth(self) -> int:
        return max(S[1][0][1] for S in self.rules) + 1

    def __hash__(self) -> int:
        return hash((self.start, str(self.rules)))

    def size(self) -> int:
        total_programs: Dict[Tuple[Type, Tuple[CFGState, NoneType]], int] = {}
        for S in sorted(self.rules, key=lambda nt: nt[1][0][1], reverse=True):
            total = 0
            for P in self.rules[S]:
                args_P = self.rules[S][P][0]
                if len(args_P) == 0:
                    total += 1
                else:
                    total += prod(total_programs[(C[0], (C[1], None))] for C in args_P)
            total_programs[S] = total
        return total_programs[self.start]

    def clean(self) -> None:
        self._remove_non_productive_()
        self._remove_non_reachable_()

    def _remove_non_reachable_(self) -> None:
        """
        remove non-terminals which are not reachable from the initial non-terminal
        """
        reachable: Set[CFGNonTerminal] = set()
        reachable.add(self.start)

        reach: Set[CFGNonTerminal] = set()
        new_reach: Set[CFGNonTerminal] = set()
        reach.add(self.start)

        for _ in range(self.max_program_depth()):
            new_reach.clear()
            for S in reach:
                for P in self.rules[S]:
                    args_P = self.rules[S][P][0]
                    for arg in args_P:
                        nctx = (arg[0], (arg[1], None))
                        new_reach.add(nctx)
                        reachable.add(nctx)
            reach.clear()
            reach = new_reach.copy()

        for S in set(self.rules):
            if S not in reachable:
                del self.rules[S]

    def _remove_non_productive_(self) -> None:
        """
        remove non-terminals which do not produce programs
        """
        new_rules: Dict[
            CFGNonTerminal,
            Dict[DerivableProgram, Tuple[List[Tuple[Type, CFGState]], NoneType]],
        ] = {}
        for S in sorted(self.rules, key=lambda rule: rule[1][0][1], reverse=True):
            for P in self.rules[S]:
                args_P = self.rules[S][P][0]
                if all((arg[0], (arg[1], None)) in new_rules for arg in args_P):
                    if S not in new_rules:
                        new_rules[S] = {}
                    new_rules[S][P] = self.rules[S][P]

        for S in set(self.rules):
            if S in new_rules:
                self.rules[S] = new_rules[S]
            else:
                del self.rules[S]

    def __rule_to_str__(
        self, P: DerivableProgram, out: Tuple[List[Tuple[Type, CFGState]], NoneType]
    ) -> str:
        args = out[0]
        return "{}: {}".format(P, args)

    def name(self) -> str:
        return "CFG"

    @classmethod
    def depth_constraint(
        cls,
        dsl: DSL,
        type_request: Type,
        max_depth: int,
        upper_bound_type_size: int = 10,
        min_variable_depth: int = 1,
        n_gram: int = 2,
        recursive: bool = False,
        constant_types: Set[Type] = set(),
    ) -> "CFG":
        """
        Constructs a CFG from a DSL imposing bounds on size of the types
        and on the maximum program depth.

        max_depth: int - is the maxium depth of programs allowed
        uppder_bound_size_type: int - is the maximum size type allowed for polymorphic type instanciations
        min_variable_depth: int - min depth at which variables and constants are allowed
        n_gram: int - the context, a bigram depends only in the parent node
        recursvie: bool - allows the generated programs to call themselves
        constant_types: Set[Type] - the set of of types allowed for constant objects
        """
        dsl.instantiate_polymorphic_types(upper_bound_type_size)

        dsl.instantiate_forbidden()
        forbidden_sets = dsl.forbidden_patterns

        if isinstance(type_request, Arrow):
            return_type = type_request.returns()
            args = type_request.arguments()
        else:
            return_type = type_request
            args = []

        rules: Dict[
            CFGNonTerminal,
            Dict[DerivableProgram, Tuple[List[Tuple[Type, CFGState]], NoneType]],
        ] = {}

        list_to_be_treated: Deque[CFGNonTerminal] = deque()
        initital_ctx = (return_type, ((NGram(n_gram), 0), None))
        list_to_be_treated.append(initital_ctx)

        while len(list_to_be_treated) > 0:
            non_terminal = list_to_be_treated.pop()
            depth = non_terminal[1][0][1]
            current_type = non_terminal[0]
            # Create rule if non existent
            if non_terminal not in rules:
                rules[non_terminal] = {}

            if depth < max_depth:
                # Try to add variables rules
                if depth >= min_variable_depth:
                    for i in range(len(args)):
                        if current_type == args[i]:
                            var = Variable(i, current_type)
                            rules[non_terminal][var] = ([], None)
                    if current_type in constant_types:
                        cst = Constant(current_type)
                        rules[non_terminal][cst] = ([], None)
                # Try to add constants from the DSL
                for P in dsl.list_primitives:
                    type_P = P.type
                    if not isinstance(type_P, Arrow) and type_P == current_type:
                        rules[non_terminal][P] = ([], None)
                # Function call
                if depth < max_depth - 1:
                    predecessors = non_terminal[1][0][0]
                    last_pred = predecessors.last() if len(predecessors) > 0 else None
                    forbidden = forbidden_sets.get(
                        (last_pred[0].primitive, last_pred[1])
                        if last_pred and isinstance(last_pred[0], Primitive)
                        else ("", 0),
                        set(),
                    )
                    # DSL Primitives
                    for P in dsl.list_primitives:
                        if P.primitive in forbidden:
                            continue
                        type_P = P.type
                        arguments_P = type_P.ends_with(current_type)
                        if arguments_P is not None:
                            decorated_arguments_P = []
                            for i, arg in enumerate(arguments_P):
                                new_predecessors = predecessors.successor((P, i))
                                new_context = (
                                    arg,
                                    ((new_predecessors, depth + 1), None),
                                )
                                decorated_arguments_P.append(
                                    (arg, (new_predecessors, depth + 1))
                                )
                                if new_context not in list_to_be_treated:
                                    list_to_be_treated.appendleft(new_context)

                            rules[non_terminal][P] = (decorated_arguments_P, None)

                    # Try to use variable as if there were functions
                    if depth >= min_variable_depth:
                        for vi, varg in enumerate(args):
                            arguments_V = varg.ends_with(current_type)
                            if arguments_V is not None:
                                V = Variable(vi, varg)
                                decorated_arguments_V = []
                                for i, arg in enumerate(arguments_V):
                                    new_predecessors = predecessors.successor((V, i))
                                    new_context = (
                                        arg,
                                        ((new_predecessors, depth + 1), None),
                                    )
                                    decorated_arguments_V.append(
                                        (arg, (new_predecessors, depth + 1))
                                    )
                                    if new_context not in list_to_be_treated:
                                        list_to_be_treated.appendleft(new_context)

                                rules[non_terminal][V] = (decorated_arguments_V, None)
                    # Try to call self
                    if recursive:
                        arguments_self = type_request.ends_with(current_type)
                        if arguments_self is not None:
                            P = Primitive("@self", type_request)
                            decorated_arguments_self = []
                            for i, arg in enumerate(arguments_self):
                                new_predecessors = predecessors.successor((P, i))
                                new_context = (
                                    arg,
                                    ((new_predecessors, depth + 1), None),
                                )
                                decorated_arguments_self.append(
                                    (arg, (new_predecessors, depth + 1))
                                )
                                if new_context not in list_to_be_treated:
                                    list_to_be_treated.appendleft(new_context)

                            rules[non_terminal][P] = (decorated_arguments_self, None)

        return CFG(
            start=initital_ctx,
            rules=rules,
        )
