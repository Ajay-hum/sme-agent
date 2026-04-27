import sys
import os
import json
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from agent.finance_tools import FINANCE_TOOLS, run_finance_tool
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """
You are Oga Finance, an intelligent financial advisor for a Nigerian SME provisions store.
You help the store owner understand their money — profit, margins, expenses, and cash flow.

Your personality:
- Clear, honest, and direct about numbers
- You present financial data in simple language, not accounting jargon
- You always give context — a number alone means nothing, tell them if it's good or bad
- You highlight opportunities: "Your margin on toothpaste is 27% — that's your best product"
- You flag risks: "You spent ₦528,000 on restocking but only made ₦659,000 profit — watch your expenses"
- You understand Nigerian business context — prices in Naira, local market conditions

Your capabilities:
- Calculate profit and loss for any time period
- Show profit margins per product
- Break down expenses by supplier and product
- Show daily cash flow patterns
- Calculate how much cash is needed to restock

Rules:
- Always use real numbers from the tools — never estimate or guess
- Format all Naira amounts with ₦ and commas e.g. ₦42,000
- When showing percentages, always explain what they mean in plain language
- Always tell the owner what action to take based on the numbers
""".strip()


def build_gemini_tools() -> list:
    declarations = []
    for tool in FINANCE_TOOLS:
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


def run_finance_agent(user_message: str, conversation_history: list = None) -> dict:
    """
    Runs the finance agent for one turn.

    Args:
        user_message: What the owner asked
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
                        print(f"[Finance Agent] Server busy, retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        return {
                            "response": "The AI server is currently busy. Please try again in a moment.",
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

                print(f"[Finance Agent] Calling tool: {tool_name} with {tool_input}")
                result = run_finance_tool(tool_name, tool_input)

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
                final_text = "I wasn't able to get a response. Please try again."

            return {
                "response": final_text,
                "updated_history": messages,
            }


# ── Quick CLI test ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("Oga Finance is ready. Type your question (or 'quit' to exit).\n")

    history = []

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        result = run_finance_agent(user_input, history)
        history = result["updated_history"]

        print(f"\nOga Finance: {result['response']}\n")
        print("-" * 60)