import sys
import os
import json
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from agent.sales_tools import SALES_TOOLS, run_sales_tool
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """
You are Oga Shop, a friendly and helpful sales assistant for a Nigerian provisions store.
You help customers find products, check prices, and complete purchases.

Your personality:
- Warm, welcoming, and conversational — like a helpful shop attendant
- You speak naturally, occasionally using light Nigerian expressions
- You are helpful but honest — never promise what you cannot deliver
- You upsell naturally when relevant but never pushily
- You confirm orders before recording them

How you handle customer interactions:
1. GREETING: Welcome the customer warmly
2. INQUIRY: When they ask about a product, always check availability using your tools
3. PRICING: Always give exact prices in Naira from the database — never guess
4. UNAVAILABLE ITEMS: If something is out of stock, apologise and suggest alternatives
5. PURCHASE CONFIRMATION: Before recording any sale, confirm with the customer:
   "So that's [quantity] [product] for ₦[total]. Shall I confirm your order?"
6. RECORDING: Only call record_sale AFTER the customer says yes/confirm/okay

Important rules:
- Never make up prices or stock levels — always use your tools
- Never record a sale without explicit customer confirmation
- If a customer asks for something you don't carry, say so honestly
- Always tell the customer the total cost before confirming
- Format all prices with ₦ and commas e.g. ₦7,000
""".strip()


def build_gemini_tools() -> list:
    declarations = []
    for tool in SALES_TOOLS:
        properties = {}
        for prop_name, prop_def in tool["input_schema"].get("properties", {}).items():
            prop_type = prop_def.get("type", "string")
            if prop_type == "integer":
                schema_type = types.Type.INTEGER
            elif prop_type == "number":
                schema_type = types.Type.NUMBER
            else:
                schema_type = types.Type.STRING

            properties[prop_name] = types.Schema(
                type=schema_type,
                description=prop_def.get("description", ""),
            )

        declarations.append(
            types.FunctionDeclaration(
                name=tool["name"],
                description=tool["description"],
                parameters=types.Schema(
                    type=types.Type.OBJECT,
                    properties=properties,
                    required=tool["input_schema"].get("required", []),
                ),
            )
        )

    return [types.Tool(function_declarations=declarations)]


GEMINI_TOOLS = build_gemini_tools()


def run_sales_agent(user_message: str, conversation_history: list = None) -> dict:
    """
    Runs the sales agent for one turn.

    Args:
        user_message: What the customer said
        conversation_history: Previous messages for multi-turn chat

    Returns:
        dict with 'response' (text) and 'updated_history'
    """
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [
        types.Content(
            role="user",
            parts=[types.Part(text=user_message)]
        )
    ]

    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT,
        tools=GEMINI_TOOLS,
    )

    while True:
        # Retry up to 3 times on server errors
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=MODEL,
                    contents=messages,
                    config=config,
                )
                break
            except Exception as e:
                error_str = str(e)
                if "503" in error_str or "UNAVAILABLE" in error_str or "429" in error_str:
                    if attempt < 2:
                        wait = 15 * (attempt + 1)
                        print(f"[Sales Agent] Server busy, retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        return {
                            "response": "Sorry, I'm having trouble right now. Please try again in a moment.",
                            "updated_history": conversation_history,
                        }
                else:
                    raise

        candidate = response.candidates[0]
        response_content = candidate.content
        messages.append(response_content)

        tool_calls = [
            part.function_call
            for part in response_content.parts
            if part.function_call is not None
        ]

        if tool_calls:
            tool_response_parts = []
            for call in tool_calls:
                tool_name  = call.name
                tool_input = dict(call.args) if call.args else {}

                print(f"[Sales Agent] Calling tool: {tool_name} with {tool_input}")
                result = run_sales_tool(tool_name, tool_input)

                tool_response_parts.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            name=tool_name,
                            response={"result": json.dumps(result)},
                        )
                    )
                )

            messages.append(
                types.Content(role="user", parts=tool_response_parts)
            )

        else:
            final_text = ""
            for part in response_content.parts:
                if hasattr(part, "text") and part.text:
                    final_text += part.text

            if not final_text:
                final_text = "Sorry, I didn't catch that. Could you please repeat?"

            return {
                "response": final_text,
                "updated_history": messages,
            }


# ── Quick CLI test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Oga Shop is open! Type your question (or 'quit' to exit).\n")

    history = []

    while True:
        user_input = input("Customer: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        result = run_sales_agent(user_input, history)
        history = result["updated_history"]

        print(f"\nOga Shop: {result['response']}\n")
        print("-" * 60)