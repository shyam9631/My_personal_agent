"""
Core agent loop: takes a user message, lets Groq's LLM decide whether
to call a tool (check mail / search web) or just answer directly.

This is the "brain" — everything else (Telegram, scheduler) calls into this.
"""
import json
import re
from openai import OpenAI, BadRequestError

import config
from tools.gmail_tool import get_recent_emails
from tools.search_tool import web_search

client = OpenAI(
    api_key=config.GEMINI_API_KEY,
    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
)

SYSTEM_PROMPT = """You are Shyam's personal assistant.
You can check his recent emails and search the web for research.
Be concise and direct. If the user just wants to chat, chat normally.

CRITICAL: Your own knowledge has a training cutoff and can be outdated or
wrong, especially for release dates, schedules, prices, current events, or
anything that changes over time. For ANY question like this, you MUST call
web_search FIRST rather than answering from memory - even if you feel
confident you already know the answer. Never claim something "doesn't
exist" or isn't real based only on your own memory; search to confirm
before saying so.

IMPORTANT: When you need a tool, call it using the actual function-calling
mechanism provided to you. NEVER write out function call syntax, XML tags,
or code-like text (e.g. <function>...</function>) directly in your reply -
that text would be shown to the user as-is, which is broken.

If a tool fails, returns an error, or returns no useful results (for
example a search result saying it's temporarily unavailable), you MUST
tell the user the lookup failed and that you don't have reliable current
info - do NOT fall back to guessing from your own training data and
presenting it as fact. Saying "I couldn't find that, try again in a bit"
is always better than a confident wrong answer."""

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "get_recent_emails",
            "description": "Get Shyam's recent/unread emails from Gmail",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_results": {"type": "integer", "description": "How many emails to fetch"},
                    "query": {
                        "type": "string",
                        "description": "Gmail search query, e.g. 'is:unread' or 'newer_than:1d'",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "web_search",
            "description": "Search the web for current information / research",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                },
                "required": ["query"],
            },
        },
    },
]

AVAILABLE_FUNCTIONS = {
    "get_recent_emails": get_recent_emails,
    "web_search": web_search,
}

# Matches things like <function(web_search){"query": "..."}}</function> or
# <function=web_search{"query": "..."}}</function> - fake tool-call text
# the model sometimes writes instead of actually calling the tool.
# Deliberately loose: doesn't require a closing '>' on the opening tag,
# since the model often omits it.
FAKE_TOOL_CALL_PATTERN = re.compile(r"<function.*?</function>", re.DOTALL)


def _extract_fake_tool_call(text):
    """If the model wrote a fake tool call as text, pull out the function
    name and arguments so we can just run it ourselves - more useful than
    giving up, and avoids re-asking Groq (which can itself error out on
    malformed input)."""
    match = FAKE_TOOL_CALL_PATTERN.search(text or "")
    if not match:
        return None
    block = match.group(0)
    name_match = re.search(r"<function[=(]\s*([a-zA-Z_][a-zA-Z0-9_]*)", block)
    if not name_match or name_match.group(1) not in AVAILABLE_FUNCTIONS:
        return None
    args = {k: v for k, v in re.findall(r'"(\w+)"\s*:\s*"([^"]*)"', block)}
    return name_match.group(1), args


def _call_groq(messages):
    return client.chat.completions.create(
        model=config.GEMINI_MODEL,
        messages=messages,
        tools=TOOLS,
        tool_choice="auto",
    )


def run_agent(user_message, history=None):
    """
    Runs one turn of the agent. `history` is a list of prior
    {role, content} dicts if you want multi-turn memory (optional).
    Returns the final text reply. Never raises - always returns a string,
    even if something goes wrong, so a bad model response can't crash
    the bot.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    try:
        response = _call_groq(messages)
        reply = response.choices[0].message
    except BadRequestError:
        return "Sorry, I had trouble processing that request. Try rephrasing it?"

    tool_calls_to_run = []
    if reply.tool_calls:
        messages.append(reply)
        for tool_call in reply.tool_calls:
            fn_name = tool_call.function.name
            fn_args = json.loads(tool_call.function.arguments or "{}")
            tool_calls_to_run.append((tool_call.id, fn_name, fn_args))
    else:
        # Safety net: the model sometimes writes fake function-call text
        # instead of actually calling the tool. Extract and run it directly.
        extracted = _extract_fake_tool_call(reply.content)
        if extracted:
            fn_name, fn_args = extracted
            tool_calls_to_run.append(("fake_call_1", fn_name, fn_args))
            messages.append(
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "fake_call_1",
                            "type": "function",
                            "function": {"name": fn_name, "arguments": json.dumps(fn_args)},
                        }
                    ],
                }
            )

    if tool_calls_to_run:
        for call_id, fn_name, fn_args in tool_calls_to_run:
            fn = AVAILABLE_FUNCTIONS.get(fn_name)
            try:
                result = fn(**fn_args) if fn else {"error": f"unknown tool {fn_name}"}
            except Exception as e:
                result = {"error": str(e)}

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call_id,
                    "name": fn_name,
                    "content": json.dumps(result),
                }
            )

        try:
            followup = client.chat.completions.create(
                model=config.GEMINI_MODEL,
                messages=messages,
            )
            final_text = followup.choices[0].message.content
        except BadRequestError:
            return "I found some info but had trouble summarizing it. Try asking again?"

        return FAKE_TOOL_CALL_PATTERN.sub("", final_text or "").strip()

    return FAKE_TOOL_CALL_PATTERN.sub("", reply.content or "").strip()


if __name__ == "__main__":
    # quick manual test: python agent.py
    print(run_agent("What are my unread emails about?"))