bind \e\\ __llm_complete_command

function __llm_complete_command -d "Fill in the command using an LLM"
  set __llm_oldcmd (commandline -b)
  set __llm_cursor_pos (commandline -C)
  echo # Start the program on a blank line
  set result (llm complete_command $__llm_oldcmd)
  if test $status -eq 0
    commandline -r $result
    echo # Move down a line to prevent fish from overwriting the program output
  end
  commandline -f repaint
end
