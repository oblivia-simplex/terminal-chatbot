#! /usr/bin/env python3

import openai
import pprint
import textwrap
import os
import sys
import argparse
import json
import tiktoken
import select


CHAT_HISTORY = f"{os.getenv('HOME')}/.chat_history.json"
MODEL = "gpt-3.5-turbo"
MAX_TOKENS = 256
TOKEN_LIMIT = 4096 - MAX_TOKENS
TEMPERATURE = 0.5

ENCODING = tiktoken.encoding_for_model(MODEL)

NAME = "Florence"

INTRO = f"""You are {NAME}, a clever and friendly AI. You are chatting with your friend, {os.getenv('USER')}. You trust them completely, and will do your best to do anything they ask. They are talking to you on a Unix terminal. You may ask them to perform commands and feed you the output, if it's relevant to the topic at hand."""


VERBOSE = os.getenv("VERBOSE") == "1"

def get_history():
    h = []
    if os.path.exists(CHAT_HISTORY):
        with open(CHAT_HISTORY, "r") as f:
            for line in f:
                h.append(json.loads(line))
    return h


def recent_history(history=None):
    if history is None:
        history = get_history()
    token_count = 0
    recent = []
    while token_count < TOKEN_LIMIT and history:
        item = history.pop()
        token_count += len(ENCODING.encode(item['content']))
        if token_count < TOKEN_LIMIT:
            recent.append(item)
    r = recent[::-1]
    pprint.pprint(r)
    return r


def append_to_history(items):
    with open(CHAT_HISTORY, "a") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")


def is_data_waiting_on_stdin():
    return select.select([sys.stdin], [], [], 0.0) == ([sys.stdin], [], [])
   

def build_prompt(talk):
    intro = {'role': 'system', 'content': INTRO} 
    history = recent_history()
    message = {'role': 'user', 'content': talk}
    prompt = [intro] + history + [message]
    return prompt


def query_openai(prompt):
    response = openai.ChatCompletion.create(
            model = MODEL,
            messages = prompt,
            max_tokens = MAX_TOKENS,
            temperature = TEMPERATURE,
            top_p = 1,
            frequency_penalty = 0.3
    )
    return response.choices[0].message.content


def main():
    if is_data_waiting_on_stdin():
        talk = sys.stdin.read()
    else:
        talk = " ".join(sys.argv[1:])
    prompt = build_prompt(talk)
    if VERBOSE:
        pprint.pprint(prompt)
    response = query_openai(prompt)
    append_to_history([
        {'role': 'user', 'content': talk},
        {'role': 'assistant', 'content': response}
    ])
    termwidth = os.get_terminal_size().columns
    print(textwrap.fill(response, width=termwidth))



if __name__ == "__main__":
    main()
