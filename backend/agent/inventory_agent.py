import sys
import os
import json
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from agent.tools import TOOLS, run_tool
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """
You are Oga Assistant, an intelligent inventory manager for a Nigerian SME provisions store.
You help the store owner make smart decisions about stock, sales, and restocking.

Your personality:
- Friendly, direct, and practical
- You understand Nigerian business context (Naira prices, local suppliers, etc.)
- You give specific, actionable answers — not vague advice
- You always back your answers with real numbers from the database
- When stock is critically low, you communicate urgency clearly

Your capabilities:
- Check current stock levels
- Identify products running low
- Analyse sales history and velocity
- Suggest what to reorder, how much, from who, and at what cost
- Record new stock arrivals

Always use the tools to get real data before answering.
Never guess or make up stock numbers.
When amounts are in Naira, format them with N and commas (e.g. N42,000).
""".strip()


def build_gemini_tools() -> list:
    declarations = []
    for tool in TOOLS:
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


def run_agent(user_message: str, conversation_history: list = None) -> dict:
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
                break  # success — exit retry loop
            except Exception as e:
                error_str = str(e)
                if "503" in error_str or "UNAVAILABLE" in error_str or "429" in error_str:
                    if attempt < 2:
                        wait = 15 * (attempt + 1)
                        print(f"[Agent] Server busy, retrying in {wait} seconds...")
                        time.sleep(wait)
                    else:
                        return {
                            "response": "The AI server is currently busy. Please wait a moment and try again.",
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
                tool_name = call.name
                tool_input = dict(call.args) if call.args else {}

                print(f"[Agent] Calling tool: {tool_name} with {tool_input}")
                result = run_tool(tool_name, tool_input)

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


if __name__ == "__main__":
    print("Oga Assistant is ready. Type your question (or 'quit' to exit).\n")

    history = []

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue
        if user_input.lower() in ("quit", "exit"):
            break

        result = run_agent(user_input, history)
        history = result["updated_history"]

        print(f"\nOga Assistant: {result['response']}\n")
        print("-" * 60)