# Terminal Chatbot

A rudimentary terminal interface for OpenAI's ChatGPT and Anthropic's Claude. Accepts input
either through command line arguments (as `' '.join(sys.argv[1:])`) or `stdin`, if on the
receiving end of a pipe. 

To open an interactive session, run with `ai -i`.

To set the model, use the environment variable `AI_MODEL`. The following models are known to work:

- `gpt-3.5-turbo` and `gpt-4`, using OpenAI's `ChatCompletion` API
- `text-davinci-003` using OpenAI's `Completion` API
- `claude-v1` using Anthropic's Claude API.

Chat history will be written to `~/.chat_history.json` and a sliding context window will be read
from that file to maintain conversational continuity. To ignore this history (to neither read 
from nor write to it), set the environment variable `AI_NO_HISTORY=1`.
