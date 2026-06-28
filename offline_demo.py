import json

from google.genai import types

import agent


class _Candidate:
    def __init__(self, content):
        self.content = content


class _Response:
    def __init__(self, content):
        self.candidates = [_Candidate(content)]


def _model(parts):
    return _Response(types.Content(role="model", parts=parts))


def _call(name, args):
    return _model([types.Part(function_call=types.FunctionCall(name=name, args=args))])


class FakeModels:
    def generate_content(self, model, contents, config):
        done = {}
        order = None
        for content in contents:
            for part in content.parts:
                if part.function_response:
                    name = part.function_response.name
                    result = part.function_response.response["result"]
                    done[name] = result
                    if name == "lookup_order":
                        order = result

        if "lookup_order" not in done:
            return _call("lookup_order", {"customer": "ali"})
        if "calculate" not in done:
            return _call("calculate", {"expression": f"{order['unit_price']} * 2"})
        if "check_warranty" not in done:
            return _call("check_warranty", {"product": order["product"], "purchase_date": order["purchase_date"]})

        warranty = done["check_warranty"]
        final = {
            "order_id": order["id"],
            "product": order["product"],
            "unit_price": order["unit_price"],
            "requested_quantity": 2,
            "total_cost": done["calculate"]["value"],
            "currency": "EUR",
            "warranty": {
                "covered": warranty["covered"],
                "expires_on": warranty["expires_on"],
                "days_remaining": warranty["days_remaining"],
            },
            "summary": (
                f"Two more {order['product']} cost {done['calculate']['value']} EUR. "
                f"Warranty {'is still active' if warranty['covered'] else 'has expired'} "
                f"(expires {warranty['expires_on']})."
            ),
        }
        return _model([types.Part(text=json.dumps(final))])


class FakeClient:
    def __init__(self):
        self.models = FakeModels()


if __name__ == "__main__":
    goal = "I'm ali. I want two more of my last order. What's the total cost, and is it still under warranty?"
    print(f"goal: {goal}\n")
    result, _ = agent.run(goal, client=FakeClient())
    print("\nfinal result:")
    print(json.dumps(result, indent=2))
