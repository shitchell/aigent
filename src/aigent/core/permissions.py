import asyncio
import shlex
import uuid
import logging
from typing import Dict, Any, Optional, Callable, Set, Awaitable
from aigent.core.schemas import PermissionSchema, PermissionPolicy, AgentEvent, EventType

# Type for strategy function: (tool_name, input_args) -> Optional[signature_string]
Strategy = Callable[[str, Dict[str, Any]], Optional[str]]

class AuthorizationStrategy:
    @staticmethod
    def default(tool: str, args: Dict[str, Any]) -> str:
        """Returns exact match signature."""
        import json
        # Sort keys to ensure stable signature
        return f"{tool}:{json.dumps(args, sort_keys=True)}"

    @staticmethod
    def tool_only(tool: str, args: Dict[str, Any]) -> str:
        """Returns signature allowing entire tool."""
        return f"{tool}:*"

    @staticmethod
    def bash_command(tool: str, args: Dict[str, Any]) -> Optional[str]:
        """
        Attempts to extract the base command from bash execution.
        Returns None if complex/unsafe to parse.
        """
        command = args.get("command", "")
        if not command:
            return None
            
        try:
            # Simple heuristic parsing
            # We want to skip env vars (VAR=val) and sudo/timeout prefixes
            parts = shlex.split(command)
            
            # Safety Check: If any shell operators are present, treat as complex/unsafe
            # We can't easily distinguish "ls" from "ls && rm" if we just pick the first word.
            operators = {"&&", "||", ";", "|", ">", ">>", "<", "&"}
            if any(p in operators for p in parts):
                return None
            
            # List of prefixes to skip
            skip_prefixes = {"sudo", "timeout", "nohup", "nice", "time"}
            
            idx = 0
            while idx < len(parts):
                token = parts[idx]
                # Skip env vars
                if "=" in token and not token.startswith("-"): 
                    idx += 1
                    continue
                
                # Skip prefixes
                if token in skip_prefixes:
                    idx += 1
                    continue
                
                # Stop at operators (safety fallback)
                if token in ["&&", "||", ";", "|", ">", ">>", "<"]:
                    return None
                    
                # Found the candidate command
                # If it looks like a flag, that's weird (e.g. sudo -u user ls)
                if token.startswith("-"):
                     # Complex sudo usage? Fallback.
                     return None
                     
                return f"bash:{token}"
                
            return None
        except Exception:
            return None

class Authorizer:
    def __init__(self, schema: PermissionSchema, event_callback: Callable[[AgentEvent], Awaitable[None]]):
        self.schema = schema
        self.event_callback = event_callback
        
        # Session-level Allowlist
        # Set of signatures that are allowed
        self.allowlist: Set[str] = set()
        
        # Pending Requests: request_id -> Future
        self.pending_requests: Dict[str, asyncio.Future] = {}

    async def check(self, tool_name: str, input_args: Dict[str, Any]) -> bool:
        """
        Determines if a tool call is allowed.
        Returns True if allowed, False if denied (after prompting user).
        """
        # 1. Check Session Allowlist (Fast Path)
        # We check exact match and tool-level match
        exact_sig = AuthorizationStrategy.default(tool_name, input_args)
        tool_sig = AuthorizationStrategy.tool_only(tool_name, input_args)
        
        if exact_sig in self.allowlist or tool_sig in self.allowlist:
            return True
            
        # Check special strategies (e.g. bash command)
        if tool_name == "bash_execute":
            cmd_sig = AuthorizationStrategy.bash_command(tool_name, input_args)
            if cmd_sig and cmd_sig in self.allowlist:
                return True

        # 2. Check Policy
        policy = self.schema.tools.get(tool_name, self.schema.default_policy)
        
        if policy == PermissionPolicy.ALLOW:
            return True
        elif policy == PermissionPolicy.DENY:
            return False
        
        # 3. Ask User (Policy == ASK)
        return await self._request_approval(tool_name, input_args)

    async def _request_approval(self, tool_name: str, input_args: Dict[str, Any]) -> bool:
        request_id = str(uuid.uuid4())
        future = asyncio.Future()
        self.pending_requests[request_id] = future
        
        # Emit Request Event
        # We check if we have a "smart" signature for the prompt UI?
        # For now, just send raw info.
        event = AgentEvent(
            type=EventType.APPROVAL_REQUEST,
            content=f"Allow {tool_name}?",
            metadata={
                "tool": tool_name, 
                "input": input_args, 
                "request_id": request_id
            }
        )
        await self.event_callback(event)
        
        try:
            # Wait for response
            decision_data = await future
            # decision_data = { "decision": "allow"|"deny"|"always_tool"|"always_exact"|"always_smart" }
            
            decision = decision_data.get("decision")
            
            if decision == "deny":
                return False
            
            if decision == "allow":
                return True
                
            # Handle "Always" variants
            if decision == "always_tool":
                self.allowlist.add(AuthorizationStrategy.tool_only(tool_name, input_args))
            elif decision == "always_exact":
                self.allowlist.add(AuthorizationStrategy.default(tool_name, input_args))
            elif decision == "always_smart":
                if tool_name == "bash_execute":
                    sig = AuthorizationStrategy.bash_command(tool_name, input_args)
                    if sig:
                        self.allowlist.add(sig)
                    else:
                        # Fallback if smart parsing failed but user clicked smart? 
                        # Should be handled by UI (don't show smart option if null)
                        self.allowlist.add(AuthorizationStrategy.default(tool_name, input_args))
            
            return True
            
        finally:
            if request_id in self.pending_requests:
                del self.pending_requests[request_id]

    def resolve_request(self, request_id: str, decision_data: Dict[str, Any]):
        if request_id in self.pending_requests:
            future = self.pending_requests[request_id]
            if not future.done():
                future.set_result(decision_data)
