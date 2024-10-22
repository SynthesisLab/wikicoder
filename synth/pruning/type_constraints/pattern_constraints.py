from collections import defaultdict
from typing import Any, Optional, Dict, Iterable, Set, Tuple, List as TList

import tqdm

from synth.syntax import Type, Arrow, FunctionType
from synth.pruning.type_constraints.utils import (
    SYMBOL_DUPLICATA,
    SYMBOL_VAR_EXPR,
    Syntax,
    map_type,
    get_prefix,
    parse_choices,
    SYMBOL_SEPARATOR,
    SYMBOL_FORBIDDEN,
    SYMBOL_ANYTHING,
    clean,
    parse_specification,
    producers_of_using,
    types_produced_directly_by,
)


def __add_variable_constraint__(
    content: str,
    parent: str,
    argno: int,
    arg_type: Type,
    syntax: Syntax,
    nconstraints: Dict[str, int],
    type_request: Optional[Arrow],
    level: int = 0,
) -> Arrow:
    assert type_request, "A type request is needed for variable constraints!"
    content = content.strip(f"{SYMBOL_VAR_EXPR}()")
    variables = set(map(int, parse_choices(content.replace("var", ""))))
    var_types = set(type_request.arguments()[i] for i in variables)
    varno2type = {no: type_request.arguments()[no] for no in variables}
    # print("\t" * level,  "Variables:", variables, "types:", var_types)
    # Always assume there are other variables of the same types

    to_duplicate = producers_of_using(syntax, arg_type, var_types)
    # add constants of same types
    to_duplicate |= {
        p
        for p, ptype in syntax.syntax.items()
        if not isinstance(ptype, Arrow) and ptype in var_types
    }
    types_to_duplicate = types_produced_directly_by(to_duplicate, syntax)
    # print("\t" * level,  "To duplicate:", to_duplicate)
    # print("\t" * level,  "Types to duplicate:", types_to_duplicate)

    # Compute the mapping of types
    types_map = {}
    # variables first
    for var_type in sorted(var_types, key=str):
        concerned = {i for i in variables if varno2type[i] == var_type}
        if any(nconstraints[f"var{i}"] > 0 for i in concerned):
            already_defined = [i for i in concerned if nconstraints[f"var{i}"] > 0]
            assert len(already_defined) == 1
            types_map[var_type] = var_type
        else:
            types_map[var_type] = syntax.duplicate_type(var_type)
    # rest
    for dtype in sorted(types_to_duplicate.difference(var_types), key=str):
        types_map[dtype] = syntax.duplicate_type(dtype)

    # Duplicate primitives
    for primitive in sorted(to_duplicate, key=str):
        syntax.duplicate_primitive(primitive, map_type(syntax[primitive], types_map))

    # Add casts
    for var_type in var_types:
        syntax.add_cast(var_type, types_map[var_type])

    # Fix parent type
    args = syntax[parent].arguments()
    args[argno] = map_type(args[argno], types_map)
    syntax[parent] = FunctionType(*args, syntax[parent].returns())

    # Fix type request
    args = type_request.arguments()
    for i in variables:
        args[i] = map_type(args[i], types_map)
        # Add constraints
        nconstraints[f"var{i}"] += 1
    return FunctionType(*args, type_request.returns())  # type: ignore


def __add_primitive_constraint__(
    content: str,
    parent: str,
    argno: int,
    syntax: Syntax,
    level: int = 0,
) -> str:
    prim = content.strip("()")
    equiv = [prim]
    if SYMBOL_DUPLICATA not in prim:
        equiv = sorted(syntax.equivalent_primitives(prim))
    for primitive in equiv:
        ptype = syntax[primitive]
        rtype = ptype.returns()
        new_type_needed = any(
            get_prefix(p) != get_prefix(prim) for p in syntax.producers_of(rtype)
        )
        # If there are other ways to produce the same thing
        if new_type_needed:
            new_return_type = syntax.duplicate_type(rtype)
            ntype = new_return_type
            if isinstance(ptype, Arrow):
                ntype = FunctionType(*ptype.arguments(), new_return_type)
            # We do not need a duplicate
            if SYMBOL_DUPLICATA in prim:
                new_primitive = primitive
                syntax[primitive] = ntype
            else:
                new_primitive = syntax.duplicate_primitive(primitive, ntype)

            if primitive == prim:
                prim = new_primitive
            # print("\t" * level, "Added:", new_primitive, ":", syntax[new_primitive])
            # Update parent signature
            parent_type = syntax[parent]
            assert isinstance(parent_type, Arrow)
            old_types = parent_type.arguments() + [parent_type.returns()]
            old_types[argno] = new_return_type
            syntax[parent] = FunctionType(*old_types)
    return prim


def __add_primitives_constraint__(
    content: str,
    parent: str,
    argno: int,
    syntax: Syntax,
    level: int = 0,
) -> None:
    primitives = parse_choices(content)
    primitives = syntax.filter_out_forbidden(parent, argno, primitives)
    if len(primitives) <= 0:
        return
    # print("\t" * level, "content:", content)
    # print("\t" * level, "primitives:", primitives)
    # 1) Simply do it for all primitives in the list
    new_primitives = [
        __add_primitive_constraint__(p, parent, argno, syntax, level + 1)
        for p in primitives
    ]
    # 2) Make them coherent
    ttype = syntax[new_primitives[0]].returns()
    for new_primitive in new_primitives:
        ntype = syntax[new_primitive]
        syntax[new_primitive] = (
            FunctionType(*ntype.arguments(), ttype)
            if isinstance(ntype, Arrow)
            else ttype
        )
        # print("\t" * level, "\tCoherent:", new_primitive, ":", syntax[new_primitive])

    # Update parent signature
    parent_type = syntax[parent]
    old_types = parent_type.arguments() + [parent_type.returns()]
    old_types[argno] = ttype
    syntax[parent] = FunctionType(*old_types)
    # print("\t" * level, "parent:", parent, ":", syntax[parent])

    # Now small thing to take into account
    # if parent is the same as one of our primitive we need to fix the children
    for p in new_primitives:
        if get_prefix(p) == parent:
            ptype = syntax[p]
            old_types = ptype.arguments() + [ptype.returns()]
            old_types[argno] = ttype
            syntax[p] = FunctionType(*old_types)
            # print("\t" * level, "\tRefix:", p, ":", syntax[p])


def __add_forbidden_constraint__(
    content: str,
    parent: str,
    argno: int,
    syntax: Syntax,
    *args: Any,
    level: int = 0,
    **kwargs: Any,
) -> None:
    # print("\t" * level, "\tcontent:", content)
    primitives = parse_choices(content[1:])
    primitives = syntax.filter_out_forbidden(parent, argno, primitives)
    if len(primitives) == 0:
        return
    all_forbidden = set()
    for p in primitives:
        all_forbidden |= syntax.equivalent_primitives(p)
    all_producers = syntax.producers_of(syntax[parent].arguments()[argno])
    remaining = all_producers - all_forbidden
    # print("\t" * level, "\tallowed:", remaining)

    __add_primitives_constraint__(
        SYMBOL_SEPARATOR.join(remaining), parent, argno, syntax, *args, **kwargs
    )


def __process__(
    constraint: TList[str],
    syntax: Syntax,
    nconstraints: Dict[str, int],
    parents: TList[str],
    type_request: Optional[Arrow],
    level: int = 0,
) -> Tuple[TList[str], Optional[Arrow]]:
    # If one element then there is nothing to do.
    if len(constraint) == 1:
        return constraint, type_request
    # If we have parents then we need to keep the original use of all of these primitives and make a copy of them that can only be used the right way
    function = sorted(syntax.equivalent_primitives(constraint.pop(0)))
    if len(parents) > 0:
        function = [syntax.duplicate_primitive(f, syntax[f]) for f in function]
    args = []
    # We need to process all arguments first
    for arg in constraint:
        new_el, type_request = __process__(
            parse_specification(arg),
            syntax,
            nconstraints,
            function,
            type_request,
            level + 1,
        )
        args.append(new_el)
    # If there are only stars there's nothing to do at our level
    if all(len(arg) == 1 and arg[0] == SYMBOL_ANYTHING for arg in args):
        return function, type_request

    # print("\t" * level, "functions:", function)
    # print("\t" * level, "processing:", args)
    for parent in function:
        fun_tr = syntax[get_prefix(parent)]
        assert isinstance(fun_tr, Arrow)
        for argno, (eq_args, arg_type) in enumerate(zip(args, fun_tr.arguments())):
            if len(eq_args) > 1:
                __add_primitives_constraint__(
                    SYMBOL_SEPARATOR.join(eq_args), parent, argno, syntax, level
                )
            else:
                content: str = eq_args[0]
                if content == SYMBOL_ANYTHING:
                    continue
                elif content[0] == SYMBOL_VAR_EXPR:
                    type_request = __add_variable_constraint__(
                        content,
                        parent,
                        argno,
                        arg_type,
                        syntax,
                        nconstraints,
                        type_request,
                        level,
                    )
                elif content[0] == SYMBOL_FORBIDDEN:
                    __add_forbidden_constraint__(content, parent, argno, syntax, level)
                else:
                    __add_primitives_constraint__(content, parent, argno, syntax, level)

    return function, type_request


def produce_new_syntax_for_constraints(
    syntax: Dict[str, Type],
    constraints: Iterable[str],
    type_request: Optional[Arrow] = None,
    forbidden: Optional[Dict[Tuple[str, int], Set[str]]] = None,
    progress: bool = True,
) -> Tuple[Dict[str, Type], Optional[Arrow]]:
    """
    Add type constraints on the specified syntax in order to enforce the given constraints.

    If no constraint depends on variables the type request is ignored.
    if progress is set to True use a tqdm progress bar.
    """
    new_syntax = Syntax({k: v for k, v in syntax.items()}, forbidden)
    constraint_plus = [(int("var" in c), c) for c in constraints]
    constraint_plus.sort(reverse=True)
    parsed_constraints = [
        parse_specification(constraint) for _, constraint in constraint_plus
    ]

    if progress:
        pbar = tqdm.tqdm(total=len(parsed_constraints), desc="constraints", smoothing=1)

    for constraint in parsed_constraints:
        _, type_request = __process__(
            constraint, new_syntax, defaultdict(int), [], type_request
        )
        if progress:
            pbar.update(1)
            pbar.set_postfix_str("cleaning...")
        clean(new_syntax, type_request)
        if progress:
            pbar.set_postfix_str(f"+{len(new_syntax)/ len(syntax) - 1:.0%} DSL size")
    if progress:
        pbar.close()
    return new_syntax.syntax, type_request


if __name__ == "__main__":
    from synth.syntax import DSL, CFG, INT, FunctionType, ProbDetGrammar, List
    from synth.pruning.type_constraints.utils import export_syntax_to_python

    # from examples.pbe.towers.towers_base import syntax, BLOCK

    # type_request = FunctionType(INT, INT, BLOCK)

    # patterns = [
    #     "ifX $(var0) ifY,elifY",
    #     "ifY * 1x3,3x1",
    #     "elifY ifY EMPTY,elifY",
    #     "elifX ifX EMPTY,elifX",
    #     "not ^not,and",
    #     "and ^and *",
    #     "or ^or,and ^and",
    #     "+ ^+,0 ^0",
    #     "not ^not,and",
    #     "* ^*,0,1 ^0,1",
    #     "- * ^0",
    # ]

    from examples.pbe.deepcoder.deepcoder import pruned_version, dsl as old_dsl  # type: ignore

    type_request = FunctionType(List(INT), List(INT))

    max_depth = 4
    # original_size = CFG.depth_constraint(DSL(syntax), type_request, max_depth).size()
    original_size = CFG.depth_constraint(old_dsl, type_request, max_depth).size()

    dsl, _ = pruned_version(True)

    # Print
    print(f"[PATTERNS] New syntax with {len(dsl.list_primitives)} primitives")
    # for P in dsl.list_primitives:
    #     prim, type = P.primitive, P.type
    #     print("\t", prim, ":", type)
    new_size = CFG.depth_constraint(
        dsl,
        type_request,
        max_depth
        # DSL(new_syntax),
        # type_request,
        # max_depth,
    ).size()
    pc = (original_size - new_size) / original_size
    print(
        f"Removed {original_size - new_size:.2E} ({pc:%}) programs at depth", max_depth
    )
    print(f"New size {new_size:.2E} programs at depth", max_depth)
    print("New TR:", type_request)

    # pcfg = ProbDetGrammar.uniform(
    #     CFG.from_dsl(DSL(new_syntax), type_request, max_depth)
    # )
    # pcfg.init_sampling(2)
    # for i in range(30):
    #     print(pcfg.sample_program())

    # with open("deepcoder2.py", "w") as fd:
    # fd.write(export_syntax_to_python(new_syntax))
