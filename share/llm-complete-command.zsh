# Bind Alt-\ to LLM command completion
bindkey '\e\\' __llm_complete_command

__llm_complete_command() {
  local old_cmd=$BUFFER
  local cursor_pos=$CURSOR
  echo # Start the program on a blank line
  if [[ -n ${old_cmd//[[:space:]]/} ]]; then
    print -sr -- "$old_cmd"
  fi
  local result=$(llm complete_command "$old_cmd")
  if [ $? -eq 0 ] && [ ! -z "$result" ]; then
    BUFFER=$result
  else
    BUFFER=$old_cmd
  fi
  zle reset-prompt
}

zle -N __llm_complete_command
