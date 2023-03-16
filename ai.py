#! /usr/bin/env python3

import openai
import tempfile
import requests
import pprint
import textwrap
import os
import sys
import argparse
import json
import tiktoken
import select
import subprocess as sp
import re
import googlesearch
import bs4
import wikipedia
import signal

CHAT_HISTORY = f"{os.getenv('HOME')}/.chat_history.json"
MODEL = "gpt-3.5-turbo"
MAX_TOKENS = 256
TOKEN_LIMIT = 4096 - MAX_TOKENS
TEMPERATURE = 0.2
SILENT = True
ENCODING = None

NAME = "Schmendrick"
USER = os.getenv('USER')

INTRO = f"""Your name is {NAME}. You are curious and friendly. You are chatting with me, your friend, {USER}. You trust me completely, and will do your best to do anything I ask. You are knowledgeable, but you will happily admit when you don't know the answer to a question. When this is the case, you may search online. I have granted you the ability to access the internet. Do this using the specially formatted strings listed below:

    - A wikipedia search query, formatted like so: %%wiki: <query>%%
    - A google search query, formatted like so: %%google: <query>%%
"""


VERBOSE = os.getenv("VERBOSE") == "1"

def get_history():
    if os.path.exists(CHAT_HISTORY):
        return [json.loads(line) for line in open(CHAT_HISTORY, "r")]
    return []


def recent_history(current, history=None):
    global ENCODING
    if ENCODING is None:
        ENCODING = tiktoken.encoding_for_model(MODEL)
    if history is None:
        history = get_history()
    token_count = sum(len(ENCODING.encode(json.dumps(m))) for m in current)
    recent = []
    while token_count < TOKEN_LIMIT and history:
        item = history.pop()
        token_count += len(ENCODING.encode(json.dumps(item)))
        if token_count < TOKEN_LIMIT:
            recent.append(item)
    r = recent[::-1]
    #pprint.pprint(r)
    return r


def append_to_history(items):
    with open(CHAT_HISTORY, "a") as f:
        for item in items:
            f.write(json.dumps(item) + "\n")


def is_data_waiting_on_stdin():
    return select.select([sys.stdin], [], [], 0.0) == ([sys.stdin], [], [])
   

def build_prompt(talk):
    intro = {'role': 'system', 'content': INTRO} 
    history = recent_history([talk, intro])
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
            frequency_penalty = 1.0
    )
    return response.choices[0].message.content



def google (query):
    results = googlesearch.search(query)
    top_result = next(results)
    return top_result


def fetch(url):
    try:
        # dump the body of the web page only
        d = bs4.BeautifulSoup(requests.get(url).text, 'html.parser')
        # just get the <body> delimited text
        body = d.find('body')
        text = body.get_text()
        return text

        p = sp.Popen(["lynx", "-dump", url], stdout=sp.PIPE, stderr=sp.PIPE)
        dump, _ = p.communicate()
        return dump.decode()
        
    except Exception as e:
        print(f"Error: {e}")
        return None

def web_search_message(dump, source):
    global ENCODING
    if ENCODING is None:
        ENCODING = tiktoken.encoding_for_model(MODEL)
    token_limit = (TOKEN_LIMIT // 2)
    token_count = 0
    rows = dump.split("\n")
    msg = []
    for row in rows:
        token_count += len(ENCODING.encode(row))
        if token_count < token_limit:
            msg.append(row)
    text = '\n'.join(msg)
    message = {'role': 'user', 'content': f"Please summarize this information from {source}, and ask interesting questions about it:\n\n===\n\n{text}\n\n==="}
    return message


def color_text(text, color):
    colors = {'red': 31, 'green': 32, 'yellow': 33, 'blue': 34, 'magenta': 35, 'cyan': 36, 'white': 37}
    return f"\033[{colors[color]}m{text}\033[0m"


def say(response):
    try:
        sp.run(["espeak", response], check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)
        # Try saying it out loud
        # Create a temporary mp3 file
        #with tempfile.TemporaryDirectory() as tmpdir:
            #mp3 = os.path.join(tmpdir, "output.mp3")
            # Use 's text-to-speech API to create an mp3 file
            #sp.run(["gtts-cli", response, "-o", mp3], check=True)
            # Play the mp3 file
            #sp.run(["mpg123", mp3], check=True, stdout=sp.DEVNULL, stderr=sp.DEVNULL)

    except Exception as e:
        print(f"Error: {e}")
        pass


def ansi_bold(text):
    return f"\033[1m{text}\033[0m"

def print_history():
    history = get_history()
    username = os.getenv('USER')
    for item in history:
        role = item['role']
        content = item['content']
        if role == 'user':
            print(color_text(f"{username.upper()}: {content}", "magenta"))
        elif role == 'assistant':
            print(color_text(f"{NAME.upper()}: {content}", "green"))
        else:
            print(content)

# trap ctrl-C and ctrl-D and exit gracefully
def signal_handler(sig, frame):
    sys.exit(1)


def main():
    if is_data_waiting_on_stdin():
        talk = sys.stdin.read()
    else:
        talk = " ".join(sys.argv[1:])
    if talk.strip().lower() == "history":
        print_history()
        return
    if talk.strip().startswith("-i"):
        # interactive mode
        # trap ctrl-C and ctrl-D and exit gracefully
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        while True:
            try:
                talk = input(color_text("ai> ", "cyan"))
                if talk.strip().lower() == "history":
                    print_history()
                    continue
                converse(talk)
            except EOFError:
                print()
                return
    converse(talk)


def converse(talk):
    prompt = build_prompt(talk)
    if VERBOSE:
        pprint.pprint(prompt)
    response = query_openai(prompt)
    append_to_history([
        {'role': 'user', 'content': talk},
        {'role': 'assistant', 'content': response}
    ])
    try:
        assert False
        termwidth = os.get_terminal_size().columns
        response = response.replace("\r\n", "\n")
        response = response.replace("\n\n", "%=%")
        response = response.replace("\n", " ")
        response = response.replace("%=%", "\n\n")
        response = textwrap.fill(response, width=termwidth, replace_whitespace=False)
    except Exception:
        pass
    print(color_text(response, 'green'))
    # check for the  query pattern
    w_match = re.search(r"%%wiki: (.*)%%", response)
    g_match = re.search(r"%%google: (.*)%%", response)
    g_fallback = False
    g_query = None
    w_query = None
    dump = None
    if w_match:
        w_query = w_match.group(1)
        #url = (google_query)
        #print("f[+] Visiting {url}")
        #dump = fetch(url)
        try:
            dump = wikipedia.summary(w_query)
            source = f"the Wikipedia entry on {w_query}"
            if VERBOSE:
                print(dump)
        except Exception as e:
            print(color_text(f"Error: {e}", 'red'))
            g_fallback = True
    elif g_match or g_fallback:
        g_query = g_match.group(1)
        if not g_query:
            g_query = w_query
        url = google(g_query)
        source = url
        print(color_text(f"[+] Visiting {url}", 'yellow'))
        dump = fetch(url)
        if VERBOSE:
            print(dump)
    if dump:
        message = web_search_message(dump, source)
        prompt = build_prompt(message['content'])
        response = query_openai(prompt)
        append_to_history([
            message,
            {'role': 'assistant', 'content': response}
        ])
        print(color_text(response, 'green'))
    if not SILENT:
        say(response)
    return




if __name__ == "__main__":
    main()
