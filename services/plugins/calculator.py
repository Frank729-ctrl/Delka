"""
Calculator plugin — safely evaluates arithmetic expressions.
Uses ast to avoid eval() security risks.
"""
import re
import ast
import operator

_TRIGGER = re.compile(
    r"\b(calculat\w*|compute|what is|what'?s|how much is|solve|evaluate|equals?)\b"
    r".{0,60}[\d\+\-\*\/\(\)\.\^%]"
    r"|[\d\+\-\*\/\(\)]{4,}"
    r"|\d+\s*(%|percent)\s+of\s+\d+",
    re.IGNORECASE,
)

_EXPR_RE = re.compile(r"[\d\s\+\-\*\/\(\)\.\^%,]+")

_OPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _eval_node(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError("Unsupported operator")
        return op(_eval_node(node.left), _eval_node(node.right))
    if isinstance(node, ast.UnaryOp):
        op = _OPS.get(type(node.op))
        if op is None:
            raise ValueError("Unsupported operator")
        return op(_eval_node(node.operand))
    raise ValueError(f"Unsupported node: {type(node)}")


def _safe_eval(expr: str) -> float:
    # Replace ^ with ** for exponentiation, remove commas
    expr = expr.replace("^", "**").replace(",", "")
    tree = ast.parse(expr, mode="eval")
    return _eval_node(tree.body)


def needs_calculator(message: str) -> bool:
    return bool(_TRIGGER.search(message))


def run_calculator(message: str) -> str:
    # Handle "X% of Y" first
    pct = re.search(
        r"(\d+(?:\.\d+)?)\s*(?:%|percent)\s+of\s+(\d+(?:\.\d+)?)",
        message, re.IGNORECASE
    )
    if pct:
        a, b = float(pct.group(1)), float(pct.group(2))
        result = a / 100 * b
        if result == int(result):
            result = int(result)
        return f"--- CALCULATOR ---\n{a}% of {b} = {result:,}\n--- END ---"

    # Extract a math expression that starts AND ends with a digit or paren
    candidates = re.findall(r"\d[\d\s\+\-\*\/\(\)\.\^%,]*\d|\d", message)
    if not candidates:
        return ""
    # Pick the longest candidate
    expr = max(candidates, key=len).strip()
    if len(expr) < 2:
        return ""
    try:
        result = _safe_eval(expr)
        if isinstance(result, float) and result == int(result):
            result = int(result)
        return f"--- CALCULATOR ---\n{expr.strip()} = {result:,}\n--- END ---"
    except Exception:
        return ""
