from typing import Protocol, Dict, List, Type, Any
from dataclasses import dataclass
import json

@dataclass
class CommandContext:
    websocket: Any
    # Return True to stop the CLI loop (exit)
    should_exit: bool = False

class SlashCommand(Protocol):
    name: str
    description: str
    
    async def execute(self, context: CommandContext) -> None:
        ...

# Registry to hold instantiated commands
REGISTRY: Dict[str, SlashCommand] = {}

class BaseCommand:
    """
    Base class for all slash commands.
    Automatically registers subclasses with a 'name' attribute to the REGISTRY.
    """
    name: str
    description: str

    async def execute(self, context: CommandContext) -> None:
        raise NotImplementedError("Commands must implement execute()")

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        # Register the command if it has a concrete name
        if hasattr(cls, "name") and cls.name:
            REGISTRY[cls.name] = cls()

class ClearCommand(BaseCommand):
    name = "/clear"
    description = "Clear the terminal screen"

    async def execute(self, context: CommandContext) -> None:
        import os
        os.system('clear' if os.name == 'posix' else 'cls')

class ResetCommand(BaseCommand):
    name = "/reset"
    description = "Reset the agent's memory (keep system prompt)"
    
    async def execute(self, context: CommandContext) -> None:
        # Send command to server
        msg = {"type": "command", "content": "/reset"}
        await context.websocket.send(json.dumps(msg))

class ExitCommand(BaseCommand):
    name = "/exit"
    description = "Exit the application"
    
    async def execute(self, context: CommandContext) -> None:
        context.should_exit = True

class QuitCommand(BaseCommand):
    name = "/quit"
    description = "Exit the application"
    
    async def execute(self, context: CommandContext) -> None:
        context.should_exit = True

class HelpCommand(BaseCommand):
    name = "/help"
    description = "Show available commands"

    async def execute(self, context: CommandContext) -> None:
        print("Available Commands:")
        for cmd in REGISTRY.values():
            print(f"  {cmd.name}: {cmd.description}")

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
