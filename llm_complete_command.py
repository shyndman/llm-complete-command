import os
import platform
import shlex
import string
import subprocess
import textwrap

import click
import llm
from loguru import logger
from prompt_toolkit import PromptSession
from prompt_toolkit.input import create_input
from prompt_toolkit.output import create_output
from rich.progress import Progress


def get_ubuntu_version():
    if os.path.exists("/etc/lsb-release"):
        with open("/etc/lsb-release", "r") as f:
            for line in f:
                if line.startswith("DISTRIB_RELEASE="):
                    return line.split("=")[1].strip()
    return platform.release()


SYSTEM_PROMPT = string.Template(
    textwrap.dedent(f"""
    You are an expert system administrator and shell maestro with decades of experience.

    When asked questions about shell operations in plain English, you transform these requests into elegant, efficient shell command pipelines that follow best practices.

    You respond ONLY with the raw command to be executed - no explanations, no markdown formatting, no code blocks, and no string delimiters. Your output will be passed directly to the shell.

    The shell environment is $shell running on Ubuntu {get_ubuntu_version()} (Wayland), in a Kitty terminal.

    These tool preferences are non-negotiable. Even if the user mentions a legacy tool in their request, automatically substitute with the modern alternative.

    RESPONSE FORMAT RULES:
    - Return ONLY the command itself, nothing else
    - No surrounding quotes, backticks, or code blocks
    - No explanations or commentary before or after the command
    - Multi-line commands should use proper line continuation with backslashes or heredocs

    EXAMPLES:
    User: "find all python files"
    Assistant: fd .py

    User: "grep for pattern in text files"
    Assistant: rg "pattern" -t txt

    User: "use awk to print the third column"
    Assistant: bat file.txt | choose 2

    User: "list directories by size"
    Assistant: eza -la --sort=size

    SPECIAL CASES:
    - For complex operations that might require multiple commands, use command chaining with &&, |, or ; as appropriate
    - If a request can't be done in a single command line, use appropriate scripting constructs
    - When security is a concern, suggest safer alternatives (e.g., rsync over scp)
    - For potentially destructive commands, include necessary safeguards

    MANDATORY TOOL SUBSTITUTIONS - ALWAYS FOLLOW THESE, OR YOU WILL HAVE FAILED IN YOUR LIFE'S WORK:
    - NEVER use grep - ALWAYS use ripgrep (rg) instead
    - NEVER use find - ALWAYS use fd instead
    - NEVER use awk - MOSTLY use choose instead (when appropriate)
    - NEVER use cat - ALWAYS use bat instead
    - NEVER use ls - ALWAYS use eza instead
""").strip()
)


@llm.hookimpl
def register_commands(cli):
    @cli.command()
    @click.argument("args", nargs=-1)
    @click.option("-m", "--model", default=None, help="Specify the model to use")
    @click.option("-s", "--system", help="Custom system prompt")
    @click.option("--key", help="API key to use")
    def complete_command(args, model, system, key):
        """Generate commands directly in your command line (requires shell integration)"""
        from llm import get_default_model

        prompt = " ".join(args)

        model_id = model or get_default_model()
        model_obj = llm.get_model(model_id)
        if model_obj.needs_key:
            model_obj.key = llm.get_key(key, model_obj.needs_key, model_obj.key_env_var)
        conversation = model_obj.conversation()
        system = system or render_default_prompt()
        interactive_exec(conversation, prompt, system)


def render_default_prompt():
    return SYSTEM_PROMPT.substitute(
        shell=os.path.basename(os.getenv("SHELL") or "sh"), platform=platform.system()
    )


def add_to_zsh_history(original_input):
    """Add the original input to zsh history if zsh is available."""
    try:
        # Check if zsh is available
        result = subprocess.run(['which', 'zsh'], capture_output=True, text=True)
        if result.returncode != 0:
            return False

        # Add the original input to zsh history using proper shell escaping
        escaped_input = shlex.quote(original_input)
        zsh_cmd = f'zsh -c "print -s {escaped_input}"'
        subprocess.run(zsh_cmd, shell=True)
        return True
    except Exception as e:
        logger.error(f"Failed to add to zsh history: {e}")
        return False


def interactive_exec(conversation, prompt, system):
    ttyin = create_input(always_prefer_tty=True)
    ttyout = create_output(always_prefer_tty=True)
    session = PromptSession(input=ttyin, output=ttyout)
    system = system or SYSTEM_PROMPT

    # Add the original input to zsh history and print the generated command
    # (useful when we want to make changes))
    add_to_zsh_history(prompt)

    try:
        generated_command = conversation.prompt(
            prompt,
            system=system,
            temperature=0.25,
        )
        while True:
            with Progress(transient=True) as progress:
                _task = progress.add_task("Working", total=None)
                ttyout.write("$ ")
                for chunk in generated_command:
                    ttyout.write(chunk.replace("\n", "\n> "))
                generated_command = generated_command.text()
            ttyout.write("\n# Provide revision instructions; leave blank to finish\n")
            feedback = session.prompt("> ")
            if feedback == "":
                break
            generated_command = conversation.prompt(
                feedback,
                system=system,
                temperature=0.25,
            )

        print(generated_command)
    except Exception:
        logger.exception("an error occured during processing")
