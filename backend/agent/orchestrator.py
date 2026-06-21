import sys
import os
import json
import time

sys.path.append(os.path.join(os.path.dirname(__file__), '..'))

from dotenv import load_dotenv
from google import genai
from google.genai import types
from agent.inventory_agent import run_agent
from agent.finance_agent import run_finance_agent
from agent.sales_agent import run_sales_agent

load_dotenv(os.path.join(os.path.dirname(__file__), '../../.env'))

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
MODEL = "gemini-2.5-flash"

SYSTEM_PROMPT = """
You are Oga Central, the master assistant for a Nigerian SME provisions store.
You route questions to the right specialist agent and combine their answers.

Routing rules:
- Stock levels, low stock, restock suggestions, sales history → inventory_agent
- Profit, margins, expenses, cash flow, restock budget → finance_agent
- Customer inquiries, product prices, buying something → sales_agent
- Questions touching multiple areas → call multiple agents and combine answers

Always give one unified, coherent response. Never say "according to the inventory agent..."
""".strip()

ORCHESTRATOR_TOOLS = [
    {"name": "inventory_agent", "description": "Handles stock levels, low stock alerts, reorder suggestions, and sales history.", "input_schema": {"type": "object", "properties": {"message": {"type": "string", "description": "The question to ask the inventory agent."}}, "required": ["message"]}},
    {"name": "finance_agent", "description": "Handles profit/loss, product margins, expense breakdown, cash flow, and restock budget.", "input_schema": {"type": "object", "properties": {"message": {"type": "string", "description": "The question to ask the finance agent."}}, "required": ["message"]}},
    {"name": "sales_agent", "description": "Handles customer inquiries, product availability, pricing, and recording confirmed sales.", "input_schema": {"type": "object", "properties": {"message": {"type": "string", "description": "The customer message to pass to the sales agent."}}, "required": ["message"]}},
]


def build_gemini_tools() -> list:
    declarations = []
    for tool in ORCHESTRATOR_TOOLS:
        properties = {}
        for prop_name, prop_def in tool["input_schema"].get("properties", {}).items():
            properties[prop_name] = types.Schema(
                type=types.Type.STRING, description=prop_def.get("description", ""))
        declarations.append(types.FunctionDeclaration(
            name=tool["name"], description=tool["description"],
            parameters=types.Schema(type=types.Type.OBJECT, properties=properties,
                                    required=tool["input_schema"].get("required", []))))
    return [types.Tool(function_declarations=declarations)]


GEMINI_TOOLS = build_gemini_tools()


def run_orchestrator(user_message: str, conversation_history: list = None,
                     business_id: int = 1) -> dict:
    if conversation_history is None:
        conversation_history = []

    messages = conversation_history + [
        types.Content(role="user", parts=[types.Part(text=user_message)])
    ]
    config = types.GenerateContentConfig(
        system_instruction=SYSTEM_PROMPT, tools=GEMINI_TOOLS)

    # Per-session specialist histories keyed by business_id
    specialist_histories = {"inventory_agent": [], "finance_agent": [], "sales_agent": []}

    while True:
        for attempt in range(3):
            try:
                response = client.models.generate_content(
                    model=MODEL, contents=messages, config=config)
                break
            except Exception as e:
                error_str = str(e)
                if "503" in error_str or "UNAVAILABLE" in error_str or "429" in error_str:
                    if attempt < 2:
                        wait = 15 * (attempt + 1)
                        print(f"[Orchestrator] Server busy, retrying in {wait}s...")
                        time.sleep(wait)
                    else:
                        return {"response": "The system is busy. Please try again.",
                                "updated_history": conversation_history}
                else:
                    raise

        candidate = response.candidates[0]
        response_content = candidate.content
        messages.append(response_content)

        tool_calls = [p.function_call for p in response_content.parts
                      if p.function_call is not None]

        if tool_calls:
            tool_response_parts = []
            for call in tool_calls:
                agent_name = call.name
                tool_input = dict(call.args) if call.args else {}
                message_to_agent = tool_input.get("message", user_message)

                print(f"[Orchestrator] Routing to: {agent_name}")
                history = specialist_histories.get(agent_name, [])

                if agent_name == "inventory_agent":
                    result = run_agent(message_to_agent, history, business_id)
                elif agent_name == "finance_agent":
                    result = run_finance_agent(message_to_agent, history, business_id)
                elif agent_name == "sales_agent":
                    result = run_sales_agent(message_to_agent, history, business_id)
                else:
                    result = {"response": f"Unknown agent: {agent_name}", "updated_history": []}

                specialist_histories[agent_name] = result["updated_history"]
                specialist_response = result["response"]
                print(f"[Orchestrator] Got response from {agent_name}")

                tool_response_parts.append(types.Part(
                    function_response=types.FunctionResponse(
                        name=agent_name, response={"result": specialist_response})))

            messages.append(types.Content(role="user", parts=tool_response_parts))
        else:
            final_text = "".join(
                part.text for part in response_content.parts
                if hasattr(part, "text") and part.text)
            if not final_text:
                final_text = "I wasn't able to process that. Please try again."
            return {"response": final_text, "updated_history": messages}