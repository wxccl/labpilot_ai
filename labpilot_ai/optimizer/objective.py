import ast
import math
import re

import numpy as np


class ObjectiveError(ValueError):
    pass


ALLOWED_FUNCS = {
    "abs": abs,
    "sqrt": math.sqrt,
    "log": math.log,
    "exp": math.exp,
    "mean": np.mean,
    "std": np.std,
    "min": np.min,
    "max": np.max,
}


class SafeObjective:
    def __init__(self, expression: str):
        self.original_expression = (expression or "").strip()
        if not self.original_expression:
            raise ObjectiveError("objective expression is empty")
        self._name_map = {}
        self.expression = self._normalize_names(self.original_expression)
        self.tree = ast.parse(self.expression, mode="eval")
        self._validate(self.tree)

    def evaluate(self, values: dict) -> float:
        env = {}
        for key, value in (values or {}).items():
            env[key] = value
            env[self._safe_name(key)] = value
        result = self._eval(self.tree.body, env)
        return float(result)

    def _normalize_names(self, expression: str) -> str:
        pattern = re.compile(r"\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b")

        def replace(match):
            name = match.group(0)
            safe = self._safe_name(name)
            self._name_map[safe] = name
            return safe

        return pattern.sub(replace, expression)

    def _safe_name(self, name: str) -> str:
        return re.sub(r"[^A-Za-z0-9_]", "__", str(name))

    def _validate(self, node):
        allowed = (
            ast.Expression,
            ast.BinOp,
            ast.UnaryOp,
            ast.Call,
            ast.Name,
            ast.Load,
            ast.Constant,
            ast.Add,
            ast.Sub,
            ast.Mult,
            ast.Div,
            ast.Pow,
            ast.USub,
            ast.UAdd,
            ast.Mod,
        )
        if not isinstance(node, allowed):
            raise ObjectiveError(f"objective syntax {type(node).__name__} is not allowed")
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id not in ALLOWED_FUNCS:
                raise ObjectiveError("only approved math functions are allowed")
        for child in ast.iter_child_nodes(node):
            self._validate(child)

    def _eval(self, node, env):
        if isinstance(node, ast.Constant):
            if isinstance(node.value, (int, float)):
                return node.value
            raise ObjectiveError("only numeric constants are allowed")
        if isinstance(node, ast.Name):
            if node.id not in env:
                raise ObjectiveError(f"objective variable {node.id!r} is missing")
            return env[node.id]
        if isinstance(node, ast.UnaryOp):
            val = self._eval(node.operand, env)
            if isinstance(node.op, ast.USub):
                return -val
            if isinstance(node.op, ast.UAdd):
                return val
        if isinstance(node, ast.BinOp):
            left = self._eval(node.left, env)
            right = self._eval(node.right, env)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                return left**right
            if isinstance(node.op, ast.Mod):
                return left % right
        if isinstance(node, ast.Call):
            func = ALLOWED_FUNCS[node.func.id]
            args = [self._eval(arg, env) for arg in node.args]
            return func(*args)
        raise ObjectiveError(f"unsupported objective node {type(node).__name__}")
