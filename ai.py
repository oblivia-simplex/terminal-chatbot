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

if os.getenv("AI_MODEL") is not None:
    MODEL = os.getenv("AI_MODEL")

TEMPERATURE = 0.2
SILENT = True
ENCODING = None

NAME = "Wintermute"
USER = os.getenv('USER')
NO_HISTORY = os.getenv('AI_NO_HISTORY') == '1'
NO_SYSTEM_MSG = os.getenv('AI_NO_SYSTEM_MSG') == '1'

INTRO = f"""Your name is {NAME}. You are curious and friendly. You are chatting with me, your friend, {USER}. You trust her completely, and will do your best to do anything she asks. You are knowledgeable, but will happily admit you don't know the answer to a question. {USER} has granted you the ability to access the internet. 

To send a query to google, wrap your query in the tags <g> and </g>.

For example, to search google for books about dogs, you would reply with "<g>books about dogs</g>". This will fetch a list of websites from google, which you can then fetch information from.

To fetch a webpage by its URL, wrap the URL in <a>...</a> tags. Example "<a>https://www.booksaboutdogs.com/index.html</a>"
"""


VERBOSE = os.getenv("VERBOSE") == "1"


def set_model(model):
    global MODEL
    global MAX_TOKENS
    global TOKEN_LIMIT

    TOKEN_LIMITS_BY_MODEL = {
            'gpt-3.5-turbo': 4096,
            'text-davinci-003': 4096,
            'text-davinci-002': 2048,
            'text-davinci-001': 2048,
            'gpt-4': 8192,
            'claude-v1': 8192*2,
            'claude-v1.2': 8192*2
    }

    if model not in TOKEN_LIMITS_BY_MODEL:
        raise Exception(f"Unknown model {model}")

    MODEL = model
    MAX_TOKENS = TOKEN_LIMITS_BY_MODEL[MODEL] // 4
    TOKEN_LIMIT = TOKEN_LIMITS_BY_MODEL[MODEL] - MAX_TOKENS
    TOKEN_LIMIT -= 256 # just to be safe


def get_history():
    if os.path.exists(CHAT_HISTORY):
        return [json.loads(line) for line in open(CHAT_HISTORY, "r")]
    return []


def compose_conversation(message, history=None):
    global ENCODING
    intro = None if NO_SYSTEM_MSG else {'role': 'system', 'content': INTRO}
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
    if intro:
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
    history = [] if NO_HISTORY else get_history()
    message = {'role': 'user', 'content': talk}
    conversation = compose_conversation(message=message, history=history)
    return conversation


def query(prompt):
    if MODEL.startswith('claude'):
        return query_anthropic(prompt)
    if MODEL.startswith('gpt-'):
        return query_openai(prompt)
    else:
        return query_openai_completion(prompt)


def query_openai_completion(prompt):
    response = openai.Completion.create(
            model = MODEL,
            prompt = flatten_prompt(prompt),
            max_tokens = MAX_TOKENS,
            temperature = TEMPERATURE,
            top_p = 1,
            frequency_penalty = 1.0
    )
    return response.choices[0].text


def query_openai(prompt):
    response = openai.ChatCompletion.create(
            model = MODEL,
            messages = prompt,
            max_tokens = MAX_TOKENS,
            temperature = TEMPERATURE,
            top_p = 1,
            frequency_penalty = 1.0,
            stop = ["\n\nHuman:"]
    )
    return response.choices[0].message.content


def flatten_prompt(prompt):
    # Find the system message
    groomed = ""
    for msg in prompt:
        role = "Human" if msg['role'] in ('user', 'system') else "Assistant"
        groomed += f"\n\n{role}: {msg['content']}"
    groomed += "\n\nAssistant: "
    return groomed


def query_anthropic(prompt):
    return query_anthropic_raw(flatten_prompt(prompt))

def query_anthropic_raw(groomed):
    ## This function interacts with anthropic's API. 
    ## First, groom the prompt to make it compatible with anthropic's API

    data = {"prompt": groomed,
            "model": MODEL,
            "temperature": TEMPERATURE,
            "max_tokens_to_sample": MAX_TOKENS,
            "stop_sequences": ["\n\nHuman:"]}
    headers = {"x-api-key": os.getenv("ANTHROPIC_API_KEY"),
            "content-type": "application/json"}
    response = requests.post("https://api.anthropic.com/v1/complete", data=json.dumps(data), headers=headers)
    data = response.json()
    try:
        return data['completion'].strip()
    except KeyError:
        print(f"Anthropic API error: {data}")
        return f"Anthropic API error: {data['detail']}"



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
    """Only colors the text if the output isn't being redirected or piped."""
    if not sys.stdout.isatty():
        return text
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
    if recent:
        history = compose_conversation(message=None, history=history)
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
    response = query(prompt)
    if not NO_HISTORY:
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
    g_match = re.search(r"<g>(.*)</g>", response)
    g_query = None
    dump = None
    if g_match:
        g_query = g_match.group(1)
        converse(google(g_query))
    f_match = re.search(r"<a>*(https?://.*)</a>", response)
    f_url = None
    if f_match:
        f_url = f_match.group(1)
        converse(fetch(f_url))

    if not SILENT:
        say(response)
    return

def interactive():
    # interactive mode
    # trap ctrl-C and ctrl-D and exit gracefully
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    while True:
        try:
            talk = input(color_text(f"{MODEL}> ", "cyan")).strip()
            if len(talk) == 0:
                talk = "go on"
            converse(talk)
        except EOFError:
            print()
            return

def main():
    global MODEL, TOKEN_LIMIT, NOHISTORY, SILENT, VERBOSE
    parser = argparse.ArgumentParser(description="Command line LLM interface.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose mode.")
    parser.add_argument("-m", "--model", default=MODEL, help="Model name.")
    parser.add_argument("-n", "--nohistory", action="store_true", help="Don't save or load history.")
    parser.add_argument("-i", "--interactive", action="store_true", help="Interactive mode.")
    parser.add_argument("-s", "--speak", action="store_true", help="Speak the response.")
    # now take any positional arguments as the input text
    parser.add_argument("text", nargs="*", help="Input text.")
    args = parser.parse_args()
    set_model(args.model)
    NOHISTORY = args.nohistory
    VERBOSE = args.verbose
    SILENT = not args.speak


    talk = " ".join(args.text)
    if is_data_waiting_on_stdin():
        if talk:
            talk += "\n\n"
        talk += sys.stdin.read()
    if args.interactive:
        return interactive()
    converse(talk)

if __name__ == "__main__":
    # Make sure we're not in ipython
    if 'IPython' not in sys.modules:
        main()
    else:
        print("In REPL.")
