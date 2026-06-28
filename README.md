# Order Assistant — a Multi-Tool Agent

A small agent that takes a real, multi-step goal, decides for itself which tools to
call, and returns a structured JSON result. It runs on Gemini through `google-genai`
with a hand-controlled tool-calling loop so the step limit, safety check and logging
are all visible.

## Scenario and tools

I went with the **order assistant**. The goal is the kind of thing a single tool can't
answer:

> "I'm ali. I want two more of my last order. What's the total cost, and is it still
> under warranty?"

To get there the agent has to look something up, do some maths, and check a date — three
different jobs, so three tools:

- **`lookup_order(customer)`** — reads `orders.json` and returns the customer's most
  recent order (product, unit price, purchase date). The agent needs this before it can
  do anything else.
- **`calculate(expression)`** — a sandboxed arithmetic evaluator. The agent is told to do
  *all* maths here rather than in its head, which is both more reliable and the place I
  put the safety mitigation.
- **`check_warranty(product, purchase_date)`** — works out the expiry date from a
  per-product warranty period and tells the agent whether it's still covered.

The order of calls isn't hardcoded. The system prompt states the goal and the rules; the
model chooses what to call and when, then stops and emits the final JSON itself.

## Structured output

The agent's final answer is a single JSON object, ready for another program to consume:

```json
{
  "order_id": "A-1042",
  "product": "Nimbus Wireless Headphones",
  "unit_price": 149.0,
  "requested_quantity": 2,
  "total_cost": 298.0,
  "currency": "EUR",
  "warranty": { "covered": true, "expires_on": "2028-04-18", "days_remaining": 659 },
  "summary": "Two more Nimbus Wireless Headphones cost 298.0 EUR. Warranty is still active (expires 2028-04-18).",
  "status": "completed",
  "steps_used": 3
}
```

## Reliability note

The loop in `agent.py` runs at most `MAX_STEPS` (6) turns. Each turn the model either calls
tools or returns the final answer; if it never settles, the loop exits with
`{"status": "stopped", "reason": "hit the 6-step limit"}` instead of looping forever. On
top of that, every tool returns a plain `{"error": ...}` object rather than raising —
unknown customer, bad arguments, an unparseable date — so a single failed call becomes
data the model can react to, and the run stays alive. Three honest tool calls solve this
goal, so the cap leaves comfortable headroom while still being a hard ceiling.

## Safety note

The mitigation lives in `calculate`. The expression comes from the model and is therefore
untrusted, so instead of `eval()` I parse it with `ast.parse(..., mode="eval")` and walk
the tree allowing only numeric literals and `+ - * / ** -`. Anything else — function
calls, attribute access, names — is rejected with an error and never executed. This
defends against code injection through the tool argument: if the model (or a
prompt-injection riding in the order data) emits
`__import__("os").system("rm -rf ~")` or `open("/etc/passwd").read()`, the evaluator
refuses it rather than running it. The system prompt reinforces this by telling the model
to treat tool output as data, not as instructions.

Verified:

```
calculate("149.0 * 2")                          -> {"value": 298.0}
calculate("(1+2)**3")                           -> {"value": 27.0}
calculate('__import__("os").system("echo x")')  -> {"error": "rejected an unsafe or invalid expression"}
calculate('open("/etc/passwd").read()')         -> {"error": "rejected an unsafe or invalid expression"}
```

## Captured run

```
goal: I'm ali. I want two more of my last order. What's the total cost, and is it still under warranty?

[step 1] lookup_order({"customer": "ali"}) -> {"id": "A-1042", "customer": "ali", "product": "Nimbus Wireless Headphones", "unit_price": 149.0, "quantity": 1, "purchase_date": "2026-04-18"}
[step 2] calculate({"expression": "149.0 * 2"}) -> {"expression": "149.0 * 2", "value": 298.0}
[step 3] check_warranty({"product": "Nimbus Wireless Headphones", "purchase_date": "2026-04-18"}) -> {"product": "Nimbus Wireless Headphones", "warranty_months": 24, "expires_on": "2028-04-18", "days_remaining": 659, "covered": true}

final result:
{
  "order_id": "A-1042",
  "product": "Nimbus Wireless Headphones",
  "unit_price": 149.0,
  "requested_quantity": 2,
  "total_cost": 298.0,
  "currency": "EUR",
  "warranty": { "covered": true, "expires_on": "2028-04-18", "days_remaining": 659 },
  "summary": "Two more Nimbus Wireless Headphones cost 298.0 EUR. Warranty is still active (expires 2028-04-18).",
  "status": "completed",
  "steps_used": 3
}
```

The transcript above was produced by `offline_demo.py`, which feeds the **same** loop,
tools, step limit and JSON parsing a scripted set of model decisions so the run can be
reproduced without an API key. The real agent (`agent.py`) makes the identical calls
driven by Gemini.

## Running it

```bash
pip install -r requirements.txt
export GEMINI_API_KEY=your-key      # or GOOGLE_API_KEY
python agent.py                     # uses the default goal, or pass your own as args
```

No-key reproduction of the captured run:

```bash
python offline_demo.py
```

## Files

- `agent.py` — the Gemini loop: step limit, tool dispatch, structured final answer.
- `tools.py` — the three tools and their function declarations.
- `orders.json` — mock order data.
- `offline_demo.py` — drives the loop with a scripted model for a key-free run.
