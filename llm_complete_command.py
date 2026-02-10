import os
import platform
import shlex
import string
import subprocess
import textwrap

import click
import llm
from loguru import logger
from model_capabilities_cache import get_model_capability, set_model_capability
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

DEFAULT_TEMPERATURE = 0.25
TEMPERATURE_PARAM = "temperature"
UNSUPPORTED_VALUE_CODE = "unsupported_value"
SUPPORTS_TEMPERATURE_CAPABILITY = "supports_temperature"


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
        result = subprocess.run(["which", "zsh"], capture_output=True, text=True)
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


def _is_unsupported_temperature_error(error: Exception) -> bool:
    return (
        getattr(error, "param", None) == TEMPERATURE_PARAM
        and getattr(error, "code", None) == UNSUPPORTED_VALUE_CODE
    )


def _prompt_with_temperature(
    conversation, prompt: str, system: str, use_temperature: bool
):
    prompt_kwargs: dict[str, object] = {"system": system}
    if use_temperature:
        prompt_kwargs[TEMPERATURE_PARAM] = DEFAULT_TEMPERATURE
    return conversation.prompt(prompt, **prompt_kwargs)


def _generate_command_text(conversation, prompt: str, system: str, write_chunk) -> str:
    model_id = conversation.model.model_id
    supports_temperature = get_model_capability(
        model_id, SUPPORTS_TEMPERATURE_CAPABILITY
    )
    should_try_temperature = supports_temperature is not False

    response = _prompt_with_temperature(
        conversation, prompt, system, use_temperature=should_try_temperature
    )
    chunks = []

    try:
        for chunk in response:
            write_chunk(chunk)
            chunks.append(chunk)
    except Exception as error:
        if (
            should_try_temperature
            and not chunks
            and _is_unsupported_temperature_error(error)
        ):
            set_model_capability(model_id, SUPPORTS_TEMPERATURE_CAPABILITY, False)
            response = _prompt_with_temperature(
                conversation, prompt, system, use_temperature=False
            )
            for chunk in response:
                write_chunk(chunk)
                chunks.append(chunk)
        else:
            raise
    else:
        if should_try_temperature and supports_temperature is None:
            set_model_capability(model_id, SUPPORTS_TEMPERATURE_CAPABILITY, True)

    return "".join(chunks)


def interactive_exec(conversation, prompt, system):
    ttyin = create_input(always_prefer_tty=True)
    ttyout = create_output(always_prefer_tty=True)
    session = PromptSession(input=ttyin, output=ttyout)
    system = system or render_default_prompt()

    # Add the original input to zsh history and print the generated command
    # (useful when we want to make changes))
    add_to_zsh_history(prompt)

    try:
        current_prompt = prompt
        generated_command = ""
        while True:
            with Progress(transient=True) as progress:
                _task = progress.add_task("Working", total=None)
                ttyout.write("$ ")
                generated_command = _generate_command_text(
                    conversation,
                    current_prompt,
                    system,
                    write_chunk=lambda chunk: ttyout.write(chunk.replace("\n", "\n> ")),
                )
            ttyout.write("\n# Provide revision instructions; leave blank to finish\n")
            feedback = session.prompt("> ")
            if feedback == "":
                break
            current_prompt = feedback

        print(generated_command)
    except Exception:
        logger.exception("an error occured during processing")
