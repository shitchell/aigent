from typing import Protocol, Dict, List, Type
from dataclasses import dataclass
from rich.console import Console
from rich.markup import escape
from aigent.core.engine import AgentEngine

@dataclass
class CommandContext:
    console: Console
    engine: AgentEngine
    # Return True to stop the CLI loop (exit)
    should_exit: bool = False

class SlashCommand(Protocol):
    name: str
    description: str
    
    async def execute(self, context: CommandContext) -> None:
        ...

class ClearCommand:
    name = "/clear"
    description = "Clear the terminal screen"
    
    async def execute(self, context: CommandContext) -> None:
        context.console.clear()

class ResetCommand:
    name = "/reset"
    description = "Reset the agent's memory (keep system prompt)"
    
    async def execute(self, context: CommandContext) -> None:
        if context.engine.history:
            # Keep system prompt at index 0
            context.engine.history = [context.engine.history[0]]
        context.console.print("[green]History cleared.[/green]")

class ExitCommand:
    name = "/exit"
    description = "Exit the application"
    
    async def execute(self, context: CommandContext) -> None:
        context.should_exit = True

class QuitCommand:
    name = "/quit"
    description = "Exit the application"
    
    async def execute(self, context: CommandContext) -> None:
        context.should_exit = True

class HelpCommand:
    name = "/help"
    description = "Show available commands"
    
    async def execute(self, context: CommandContext) -> None:
        context.console.print("[bold]Available Commands:[/bold]")
        for cmd in REGISTRY.values():
            context.console.print(f"  [yellow]{cmd.name}[/yellow]: {cmd.description}")

# Central Registry
_COMMANDS: List[Type[SlashCommand]] = [
    ClearCommand,
    ResetCommand,
    ExitCommand,
    QuitCommand,
    HelpCommand
]

REGISTRY: Dict[str, SlashCommand] = {cls.name: cls() for cls in _COMMANDS}

def get_command_names() -> List[str]:
    return list(REGISTRY.keys())

async def handle_command(input_text: str, context: CommandContext) -> bool:
    """
    Parses and executes a command if present.
    Returns True if a command was executed, False otherwise.
    """
    cmd_name = input_text.strip().split()[0].lower()
    if cmd_name in REGISTRY:
        await REGISTRY[cmd_name].execute(context)
        return True
    return False
