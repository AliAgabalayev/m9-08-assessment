import ast
import calendar
import json
import operator
import os
from datetime import date

from google.genai import types

DATA_FILE = os.path.join(os.path.dirname(__file__), "orders.json")

WARRANTY_MONTHS = {
    "Aerolite Running Shoes": 6,
    "Cobalt Smart Watch": 12,
    "Nimbus Wireless Headphones": 24,
}

_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}


def _load_orders():
    with open(DATA_FILE) as handle:
        return json.load(handle)


def lookup_order(customer):
    orders = [row for row in _load_orders() if row["customer"] == customer.lower()]
    if not orders:
        return {"error": "no orders for that customer"}
    latest = max(orders, key=lambda row: row["purchase_date"])
    return latest


def _eval(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _OPERATORS:
        return _OPERATORS[type(node.op)](_eval(node.operand))
    raise ValueError("unsupported expression")


def calculate(expression):
    try:
        tree = ast.parse(expression, mode="eval")
        value = _eval(tree.body)
    except (ValueError, SyntaxError, TypeError, ZeroDivisionError):
        return {"error": "rejected an unsafe or invalid expression", "expression": expression}
    return {"expression": expression, "value": round(float(value), 2)}


def _add_months(start, months):
    index = start.month - 1 + months
    year = start.year + index // 12
    month = index % 12 + 1
    day = min(start.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


def check_warranty(product, purchase_date):
    months = WARRANTY_MONTHS.get(product)
    if months is None:
        return {"error": "unknown product, cannot determine warranty"}
    try:
        start = date.fromisoformat(purchase_date)
    except ValueError:
        return {"error": "purchase_date must be ISO format YYYY-MM-DD"}
    expires = _add_months(start, months)
    remaining = (expires - date.today()).days
    return {
        "product": product,
        "warranty_months": months,
        "expires_on": expires.isoformat(),
        "days_remaining": remaining,
        "covered": remaining > 0,
    }


DISPATCH = {
    "lookup_order": lookup_order,
    "calculate": calculate,
    "check_warranty": check_warranty,
}


def dispatch(name, args):
    handler = DISPATCH.get(name)
    if handler is None:
        return {"error": f"unknown tool {name}"}
    try:
        return handler(**args)
    except TypeError:
        return {"error": f"bad arguments for {name}", "args": args}


def declarations():
    return [
        types.FunctionDeclaration(
            name="lookup_order",
            description="Find a customer's most recent order with its product, price and purchase date.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"customer": types.Schema(type="STRING", description="customer handle, e.g. ali")},
                required=["customer"],
            ),
        ),
        types.FunctionDeclaration(
            name="calculate",
            description="Evaluate a plain arithmetic expression and return the number. Use this for any math.",
            parameters=types.Schema(
                type="OBJECT",
                properties={"expression": types.Schema(type="STRING", description="e.g. 149.0 * 2")},
                required=["expression"],
            ),
        ),
        types.FunctionDeclaration(
            name="check_warranty",
            description="Check whether a product bought on a given date is still under warranty.",
            parameters=types.Schema(
                type="OBJECT",
                properties={
                    "product": types.Schema(type="STRING"),
                    "purchase_date": types.Schema(type="STRING", description="ISO date YYYY-MM-DD"),
                },
                required=["product", "purchase_date"],
            ),
        ),
    ]
