from typing import Callable

import better_exceptions
import click
import llm
from .environment_config import load_effective_environment
from loguru import logger
from .model_capabilities_cache import get_model_capability, set_model_capability
from prompt_toolkit import PromptSession
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.input import create_input
from prompt_toolkit.output import create_output
from .system_prompt import build_system_prompt
from .thinking_spinner import ThinkingSpinner


better_exceptions.MAX_LENGTH = None

DEFAULT_TEMPERATURE = 0.25
TEMPERATURE_PARAM = "temperature"
UNSUPPORTED_VALUE_CODE = "unsupported_value"
SUPPORTS_TEMPERATURE_CAPABILITY = "supports_temperature"
ANSI_RESET = "\x1b[0m"
COMMAND_PROMPT_COLOR_HEX = "#31748f"
FEEDBACK_PROMPT_COLOR_HEX = "#73628a"


def _hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    cleaned = hex_color.lstrip("#")
    return (int(cleaned[0:2], 16), int(cleaned[2:4], 16), int(cleaned[4:6], 16))


def _truecolor_escape(hex_color: str) -> str:
    red, green, blue = _hex_to_rgb(hex_color)
    return f"\x1b[38;2;{red};{green};{blue}m"


def _colorize_prompt_symbol(symbol: str, hex_color: str) -> str:
    return f"{_truecolor_escape(hex_color)}{symbol}{ANSI_RESET} "


COMMAND_PROMPT = _colorize_prompt_symbol("$", COMMAND_PROMPT_COLOR_HEX)
FEEDBACK_PROMPT = _colorize_prompt_symbol(">", FEEDBACK_PROMPT_COLOR_HEX)


def _format_generated_chunk(chunk: str) -> str:
    return chunk.replace("\n", f"\n{FEEDBACK_PROMPT}")


def _write_terminal(output, text: str) -> None:
    write_raw = getattr(output, "write_raw", None)
    if callable(write_raw):
        write_raw(text)
        return
    output.write(text)


class ResponseStreamError(Exception):
    original: Exception
    emitted_chunks: int

    def __init__(self, original: Exception, emitted_chunks: int):
        super().__init__(str(original))
        self.original = original
        self.emitted_chunks = emitted_chunks


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
    environment = load_effective_environment()
    return build_system_prompt(environment)


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


def _collect_response_text(
    response,
    write_chunk: Callable[[str], None],
    on_first_chunk: Callable[[], None] | None = None,
) -> str:
    chunks = []
    first_chunk = True

    try:
        for chunk in response:
            if first_chunk and on_first_chunk is not None:
                on_first_chunk()
                first_chunk = False
            write_chunk(chunk)
            chunks.append(chunk)
    except Exception as error:
        raise ResponseStreamError(error, len(chunks)) from error

    return "".join(chunks)


def _should_retry_without_temperature(
    stream_error: ResponseStreamError, use_temperature: bool
) -> bool:
    return (
        use_temperature
        and stream_error.emitted_chunks == 0
        and _is_unsupported_temperature_error(stream_error.original)
    )


def _collect_with_spinner(conversation, response, write_chunk) -> str:
    spinner = ThinkingSpinner(conversation.model.model_id)
    spinner.start()

    try:
        return _collect_response_text(
            response, write_chunk, on_first_chunk=spinner.stop
        )
    finally:
        spinner.stop()


def _generate_command_text(conversation, prompt: str, system: str, write_chunk) -> str:
    model_id = conversation.model.model_id
    supports_temperature = get_model_capability(
        model_id, SUPPORTS_TEMPERATURE_CAPABILITY
    )
    use_temperature = supports_temperature is not False

    response = _prompt_with_temperature(
        conversation, prompt, system, use_temperature=use_temperature
    )

    try:
        generated_text = _collect_with_spinner(conversation, response, write_chunk)
    except ResponseStreamError as stream_error:
        if _should_retry_without_temperature(stream_error, use_temperature):
            set_model_capability(model_id, SUPPORTS_TEMPERATURE_CAPABILITY, False)
            response = _prompt_with_temperature(
                conversation, prompt, system, use_temperature=False
            )
            return _collect_with_spinner(conversation, response, write_chunk)

        raise stream_error.original from stream_error.original

    if use_temperature and supports_temperature is None:
        set_model_capability(model_id, SUPPORTS_TEMPERATURE_CAPABILITY, True)

    return generated_text


def interactive_exec(conversation, prompt, system):
    ttyin = create_input(always_prefer_tty=True)
    ttyout = create_output(always_prefer_tty=True)
    session = PromptSession(input=ttyin, output=ttyout)
    system = system or render_default_prompt()

    try:
        current_prompt = prompt
        generated_command = ""
        while True:
            _write_terminal(ttyout, COMMAND_PROMPT)
            generated_command = _generate_command_text(
                conversation,
                current_prompt,
                system,
                write_chunk=lambda chunk: _write_terminal(
                    ttyout, _format_generated_chunk(chunk)
                ),
            )
            ttyout.write("\n# Provide revision instructions; leave blank to finish\n")
            feedback = session.prompt(ANSI(FEEDBACK_PROMPT))
            if feedback == "":
                break
            current_prompt = feedback

        print(generated_command)
    except Exception:
        logger.exception("an error occurred during processing")
