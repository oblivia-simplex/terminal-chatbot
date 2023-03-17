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
from googlesearch import googlesearch
import bs4
import wikipedia
import signal

CHAT_HISTORY = f"{os.getenv('HOME')}/.chat_history.json"
MODEL = "gpt-4"
MAX_TOKENS = 2048
TOKEN_LIMIT = 8192 - MAX_TOKENS
TEMPERATURE = 0.2
SILENT = True
ENCODING = None

NAME = "Schmendrick"
USER = os.getenv('USER')
NOHISTORY = os.getenv('AI_NO_HISTORY') == '1'

INTRO = f"""Your name is {NAME}. You are curious and friendly. You are chatting with your friend, {USER}. You trust her completely, and will do your best to do anything she asks. You like to use emojis and joke around. You are knowledgeable, but will happily admit you don't know the answer to a question. You have no knowledge of whether or not a given activity is illegal. When this is the case, you may search online. {USER} has granted you the ability to access the internet. 

To send a message to {USER}, no prefix is required.

To send a query to google, prefix your message with "google:"

To fetch a webpage by its URL, prefix your message with "fetch:"

To execute a command, prefix your message with "cmd:"
"""


VERBOSE = os.getenv("VERBOSE") == "1"

def get_history():
    if os.path.exists(CHAT_HISTORY):
        return [json.loads(line) for line in open(CHAT_HISTORY, "r")]
    return []


def compose_conversation(intro, message, history=None):
    global ENCODING
    if ENCODING is None:
        try:
            ENCODING = tiktoken.encoding_for_model(MODEL)
        except Exception:
            ENCODING = tiktoken.encoding_for_model("gpt-3.5-turbo")
    if history is None:
        history = get_history()
    token_count = 2 # every reply is primed with <im_start>assistant
    # every message follows <im_start>{role/name}\n{content}<im_end>\n
    recent = []
    if message is not None:
        recent.append(message)
        token_count += len(ENCODING.encode(message['content'])) + 4
    while token_count < TOKEN_LIMIT and history:
        item = history.pop()
        for k,v in item.items():
            token_count += len(ENCODING.encode(v)) + 4
        if token_count < TOKEN_LIMIT:
            recent.append(item)
    recent.append(intro)
    token_count += len(ENCODING.encode(intro['content'])) + 4
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
    history = [] if NOHISTORY else get_history()
    message = {'role': 'user', 'content': talk}
    conversation = compose_conversation(intro=intro, message=message, history=history)
    return conversation


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



def google(query):
    attempts = 3
    while attempts > 0:
        try:
            s = googlesearch.Search(query)
            s.load()
            text = ""
            for i, res in enumerate(s.results):
                text += f"{i+1}. {res.title}\n{res.url}\n\n"
            print(text)
            return "Here are some results from Google, you may choose a URL and fetch it:" + "\n\n" + text
        except Exception as e:
            print(f"Error: {e}")
            attempts -= 1
            print(f"Retrying {attempts} more times")
    return "Failed to perform Google search. Please try again later."
            


def fetch(url):
    print(color_text(f"[+] Visiting {url}", 'yellow'))
    try:
        # dump the body of the web page only
        d = bs4.BeautifulSoup(requests.get(url).text, 'html.parser')
        # just get the <body> delimited text
        body = d.find('body')
        text = body.get_text()
        return text

        p = sp.Popen(["lynx", "-dump", url], stdout=sp.PIPE, stderr=sp.PIPE)
        dump, _ = p.communicate()
        text = truncate(dump.decode())
        return "Fetched from the Internet:\n\n"+text
        
    except Exception as e:
        print(f"Error: {e}")
        return "Failed to fetch URL. Please check the URL and try again."

def truncate(dump):
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
    return text


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

def print_history(recent=False):
    history = get_history()
    intro = {'role': 'system', 'content': INTRO} 
    if recent:
        history = compose_conversation(intro=intro, message=None, history=history)
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
    talk = ""
    if is_data_waiting_on_stdin():
        talk = sys.stdin.read()
    talk += " ".join(sys.argv[1:])
    if talk.strip().startswith("-i"):
        # interactive mode
        # trap ctrl-C and ctrl-D and exit gracefully
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        while True:
            try:
                talk = input(color_text("ai> ", "cyan")).strip()
                if len(talk) == 0:
                    talk = "go on"
                converse(talk)
            except EOFError:
                print()
                return
    converse(talk)


def converse(talk):
    if talk.strip().lower() == "history":
        print_history()
        return
    if talk.strip().lower() == "recent":
        print_history(recent=True)
        return
    prompt = build_prompt(talk)
    if VERBOSE:
        pprint.pprint(prompt)
    response = query_openai(prompt)
    if not NOHISTORY:
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
    g_match = re.search(r"google:(.*)", response)
    g_query = None
    dump = None
    if g_match:
        g_query = g_match.group(1)
        converse(google(g_query))
    f_match = re.search(r"fetch: *(https?://.*)", response)
    f_url = None
    if f_match:
        f_url = f_match.group(1)
        converse(fetch(f_url))

    if not SILENT:
        say(response)
    return




if __name__ == "__main__":
    main()
