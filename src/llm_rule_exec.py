"""Validate and run an LLM-written selection rule in restricted Python.

The rule is the source of a module that defines choose(sub, design) and may
define helper functions.  Only the syntax in ALLOWED_NODES, the builtins in
SAFE_BUILTINS and the methods in ALLOWED_METHODS are accepted; names and
attributes that start with an underscore are rejected.  There are no imports,
no I/O and no attribute access other than whitelisted method calls.

Run as a script (python3 -I llm_rule_exec.py), it reads {"source", "design",
"subs"} as JSON from stdin, validates the source again, applies choose to every
sub-property under CPU and memory limits, and writes {"results": [...]} with
one {"name", "output"} or {"name", "error"} per sub-property to stdout.  It
uses only the standard library, so that it runs with -I.
"""
import ast
import json
import sys

SAFE_BUILTINS = {
    "abs": abs, "all": all, "any": any, "bool": bool, "dict": dict, "enumerate": enumerate, "int": int,
    "len": len, "list": list, "max": max, "min": min, "range": range, "reversed": reversed, "set": set,
    "sorted": sorted, "str": str, "sum": sum, "tuple": tuple, "zip": zip,
}
ALLOWED_METHODS = {
    "add", "append", "count", "discard", "endswith", "extend", "get", "index", "isdigit", "items", "join",
    "keys", "lower", "remove", "replace", "split", "startswith", "strip", "union", "intersection",
    "difference", "update", "upper", "values",
}
ALLOWED_NODES = (
    ast.Module, ast.FunctionDef, ast.arguments, ast.arg, ast.Return, ast.Assign, ast.AugAssign, ast.If, ast.For,
    ast.Pass, ast.Break, ast.Continue, ast.Expr, ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare, ast.Call,
    ast.IfExp, ast.Name, ast.Constant, ast.List, ast.Tuple, ast.Dict, ast.Set, ast.Subscript, ast.Slice,
    ast.Attribute, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp, ast.comprehension, ast.Lambda,
    ast.JoinedStr, ast.FormattedValue, ast.keyword, ast.Load, ast.Store,
    ast.And, ast.Or, ast.Not, ast.USub, ast.UAdd, ast.Add, ast.Sub, ast.Mult, ast.FloorDiv, ast.Mod,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE, ast.In, ast.NotIn, ast.Is, ast.IsNot,
)
ENTRY = "choose"
CPU_SECONDS = 20
MEMORY_BYTES = 1 << 30


def validate(source):
    """Return the reasons why source is not an acceptable rule; an empty list means it is acceptable."""
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        return ["syntax error: {:s}".format(str(e))]
    errors = []
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            errors.append("line {:d}: only function definitions are allowed at top level".format(node.lineno))
    if not any(isinstance(node, ast.FunctionDef) and node.name == ENTRY for node in tree.body):
        errors.append("no top-level function " + ENTRY)
    for node in ast.walk(tree):
        line = getattr(node, "lineno", 0)
        if not isinstance(node, ALLOWED_NODES):
            errors.append("line {:d}: {:s} is not allowed".format(line, type(node).__name__))
            continue
        if isinstance(node, ast.FunctionDef) and (node.decorator_list or node.returns):
            errors.append("line {:d}: decorators and annotations are not allowed".format(line))
        if isinstance(node, ast.arguments) and (node.defaults or node.kw_defaults or node.vararg or node.kwarg
                                                or node.kwonlyargs or node.posonlyargs):
            errors.append("line {:d}: only plain positional arguments are allowed".format(line))
        if isinstance(node, ast.arg) and node.annotation:
            errors.append("line {:d}: annotations are not allowed".format(line))
        name = node.id if isinstance(node, ast.Name) else node.arg if isinstance(node, ast.arg) else \
            node.name if isinstance(node, ast.FunctionDef) else None
        if name is not None and name.startswith("_"):
            errors.append("line {:d}: name {:s} starts with an underscore".format(line, name))
        if isinstance(node, ast.Attribute) and node.attr not in ALLOWED_METHODS:
            errors.append("line {:d}: attribute {:s} is not allowed".format(line, node.attr))
        if isinstance(node, ast.Call) and not isinstance(node.func, (ast.Name, ast.Attribute)):
            errors.append("line {:d}: only named functions and whitelisted methods may be called".format(line))
    called = {id(n.func) for n in ast.walk(tree) if isinstance(n, ast.Call)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and id(node) not in called:
            errors.append("line {:d}: attribute {:s} must be called".format(node.lineno, node.attr))
    return errors


def load(source):
    """Compile a validated rule and return its choose function."""
    errors = validate(source)
    if errors:
        raise ValueError("; ".join(errors))
    namespace = {"__builtins__": SAFE_BUILTINS}
    exec(compile(source, "<rule>", "exec"), namespace)
    return namespace[ENTRY]


def main():
    import resource
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))
    resource.setrlimit(resource.RLIMIT_AS, (MEMORY_BYTES, MEMORY_BYTES))
    request = json.load(sys.stdin)
    choose = load(request["source"])
    results = []
    for sub in request["subs"]:
        design = json.loads(json.dumps(request["design"]))
        try:
            output = choose(json.loads(json.dumps(sub)), design)
            results.append({"name": sub["name"], "output": json.loads(json.dumps(output))})
        except (ArithmeticError, LookupError, TypeError, ValueError, AttributeError, RecursionError) as e:
            results.append({"name": sub["name"], "error": "{:s}: {:s}".format(type(e).__name__, str(e))})
    json.dump({"results": results}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
