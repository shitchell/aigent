import asyncio
from typing import List, AsyncGenerator, Any, Optional
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage, AIMessage, ToolMessage
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnableConfig
from langchain.agents import AgentExecutor
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Handle potential import location changes or missing function in older versions
try:
    from langchain.agents import create_tool_calling_agent
except ImportError:
    try:
        # Try importing from specific module if main package doesn't expose it
        from langchain.agents.tool_calling_agent.base import create_tool_calling_agent
    except ImportError:
         # If truly missing, we might be on a very old version (pre-0.1.15)
         # But we specified >=0.3.0 in pyproject.toml now.
         # Re-raise with clear message
         raise ImportError("Could not import 'create_tool_calling_agent'. Please ensure langchain>=0.2.0 is installed.")

from aigent.core.schemas import UserProfile, AgentEvent, EventType, ModelProvider, PermissionSchema, PermissionPolicy
from aigent.core.memory import MemoryLoader
from aigent.plugins.loader import PluginLoader
from aigent.core.tools import fs_read, fs_write, fs_patch, bash_execute
from aigent.core.permissions import Authorizer
from aigent.core.profiles import ProfileManager

class AgentEngine:
    def __init__(self, profile: UserProfile, yolo: bool = False):
        self.profile = profile
        self.yolo = yolo
        self.memory_loader = MemoryLoader()
        self.plugin_loader = PluginLoader()
        self.tools: List[Any] = []
        self.llm: BaseChatModel = None # type: ignore
        self.history: List[BaseMessage] = []
        
        # Event Queue for streaming events out (populated during stream)
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self.authorizer: Authorizer = None # type: ignore

    async def _emit_event(self, event: AgentEvent):
        await self._event_queue.put(event)

    async def initialize(self) -> None:
        """
        Async initialization: loads tools, reads memory files, sets up LLM.
        """
        # Initialize Authorizer
        
        schema = None
        
        # 1. YOLO Mode Override (Highest Priority)
        if self.yolo:
            schema = PermissionSchema(name="yolo", default_policy=PermissionPolicy.ALLOW)
        else:
            # 2. Load from Profile Config
            pm = ProfileManager()
            schema_name = self.profile.permission_schema
            found_schema = pm.get_permission_schema(schema_name)
            
            if found_schema:
                schema = found_schema
            else:
                # 3. Fallback/Default Safe Schema
                schema = PermissionSchema(name="fallback_safe", default_policy=PermissionPolicy.ASK)
                schema.tools = {
                    "fs_read": PermissionPolicy.ALLOW,
                    "bash_execute": PermissionPolicy.ASK,
                    "fs_write": PermissionPolicy.ASK,
                    "fs_patch": PermissionPolicy.ASK
                }
        
        self.authorizer = Authorizer(schema, self._emit_event)

        # 1. Load Base Context (System Prompt)
        import datetime
        import platform
        import os
        from aigent.core.prompts import PRESETS
        
        base_template = PRESETS.get(self.profile.base_prompt, PRESETS["standard"])
        
        # Variable Expansion
        variables = {
            "date": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
            "platform": platform.system(),
            "cwd": os.getcwd(),
            "user": self.profile.name
        }
        
        try:
            system_context = base_template.format(**variables)
        except Exception:
            # Fallback if formatting fails (e.g. user provided broken template)
            system_context = base_template

        # Load Static Context from Files (Standard locations)
        # This appends to the base prompt
        file_context = await self.memory_loader.load_context()
        if file_context:
             system_context += "\n" + file_context
        
        # Profile-specific files (Absolute paths resolved by ProfileManager)
        if self.profile.system_prompt_files:
            # We pass Path(".") as base because paths are already absolute
            extra_context = await self.memory_loader.load_from_paths(self.profile.system_prompt_files, Path("."))
            system_context += "\n" + extra_context

        if self.profile.context_files:
            extra_context = await self.memory_loader.load_from_paths(self.profile.context_files, Path("."))
            system_context += "\n" + extra_context

        # Profile-specific inline prompt
        if self.profile.system_prompt:
            system_context += f"\n--- Profile Instructions ---\n{self.profile.system_prompt}\n"

        # 2. Load Tools (Plugins + Core)
        plugin_tools = self.plugin_loader.load_plugins(self.profile.allowed_tools)
        core_tools = [fs_read, fs_write, fs_patch, bash_execute]
        
        raw_tools = []
        if "*" in self.profile.allowed_tools:
             raw_tools = plugin_tools + core_tools
        else:
             raw_tools = plugin_tools + core_tools

        # WRAP TOOLS WITH AUTHORIZATION
        self.tools = [self._wrap_tool(t) for t in raw_tools]

        # 3. Setup LLM
        if self.profile.model_provider == ModelProvider.OPENAI:
            self.llm = ChatOpenAI(
                model=self.profile.model_name,
                temperature=self.profile.temperature
            )
        elif self.profile.model_provider == ModelProvider.ANTHROPIC:
            self.llm = ChatAnthropic(
                model=self.profile.model_name,
                temperature=self.profile.temperature
            )
        elif self.profile.model_provider == ModelProvider.GOOGLE:
            self.llm = ChatGoogleGenerativeAI(
                model=self.profile.model_name,
                temperature=self.profile.temperature,
                convert_system_message_to_human=True # Sometimes needed for older Gemini models, safe to keep
            )
        elif self.profile.model_provider == ModelProvider.GROK:
            # Grok uses the OpenAI SDK format
            import os
            api_key = os.getenv("XAI_API_KEY")
            if not api_key:
                raise ValueError("XAI_API_KEY not found in environment")
                
            self.llm = ChatOpenAI(
                model=self.profile.model_name,
                base_url="https://api.x.ai/v1",
                api_key=api_key,
                temperature=self.profile.temperature
            )
        else:
            raise ValueError(f"Unsupported provider: {self.profile.model_provider}")

        # Bind tools
        if self.tools:
            self.llm = self.llm.bind_tools(self.tools)

        # Initialize History with System Prompt
        self.history = [SystemMessage(content=system_context)]

    def _wrap_tool(self, tool: Any) -> Any:
        """
        Wraps a tool's _arun method to check permissions first.
        """
        # We need to modify the instance method
        # This is a bit hacky but standard for dynamic interception
        original_arun = tool._arun
        
        async def wrapped_arun(*args, config: Optional[RunnableConfig] = None, **kwargs):
            # Construct args dict for check
            input_args = {}
            if args:
                if isinstance(args[0], dict):
                    input_args = args[0]
                elif isinstance(args[0], str):
                    input_args = {"input": args[0]}
            if kwargs:
                input_args.update(kwargs)

            allowed = await self.authorizer.check(tool.name, input_args)
            if not allowed:
                return "Error: Tool execution denied by user."
            
            # Pass config explicitly if provided
            return await original_arun(*args, config=config, **kwargs)
        
        tool._arun = wrapped_arun
        return tool

    async def _run_agent_executor(self, user_input: str, user_name: Optional[str] = None) -> None:
        """
        Helper to run the agent and push events to the queue.
        
        Args:
            user_input: The text input from the user.
            user_name: Optional name of the user for history tracking.
        """
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        try:
            # Construct agent
            prompt = ChatPromptTemplate.from_messages([
                ("system", "{system_message}"),
                MessagesPlaceholder(variable_name="chat_history"),
                # We don't standardly inject user name into prompt unless we change the prompt structure.
                # But LangChain HumanMessage name is enough for history tracking.
                ("human", "{input}"),
                MessagesPlaceholder(variable_name="agent_scratchpad"),
            ])

            agent = create_tool_calling_agent(self.llm, self.tools, prompt)
            agent_executor = AgentExecutor(agent=agent, tools=self.tools, verbose=False)

            system_msg_content = self.history[0].content if self.history else ""
            
            # History Slicing (Compactification)
            # Get all messages between System (0) and Latest User (last)
            intermediate_history = self.history[1:-1]
            
            # Slice to keep only the last N messages
            max_msgs = getattr(self.profile, "max_messages", 50)
            chat_history_safe = intermediate_history[-max_msgs:] if max_msgs > 0 else intermediate_history

            final_text = ""
            tool_buffer = {}

            async for event in agent_executor.astream_events(
                {
                    "system_message": system_msg_content,
                    "chat_history": chat_history_safe,
                    "input": user_input
                },
                version="v2"
            ):
                kind = event["event"]
                
                if kind == "on_chat_model_stream":
                    content = event["data"]["chunk"].content
                    if content:
                        final_text += content
                        await self._emit_event(AgentEvent(type=EventType.TOKEN, content=content))
                
                elif kind == "on_tool_start":
                    await self._emit_event(AgentEvent(
                        type=EventType.TOOL_START, 
                        content=f"Calling tool: {event['name']}",
                        metadata={"input": event["data"].get("input")}
                    ))
                    run_id = event["run_id"]
                    tool_buffer[run_id] = {
                        "name": event["name"],
                        "args": event["data"].get("input"),
                        "id": run_id,
                        "output": None
                    }
                    
                elif kind == "on_tool_end":
                     await self._emit_event(AgentEvent(
                        type=EventType.TOOL_END, 
                        content=str(event["data"].get("output")),
                        metadata={"name": event["name"]}
                    ))
                     run_id = event["run_id"]
                     if run_id in tool_buffer:
                         tool_buffer[run_id]["output"] = str(event["data"].get("output"))

            # Update History
            if tool_buffer:
                tool_calls = []
                for run_id, data in tool_buffer.items():
                    tool_calls.append({
                        "name": data["name"],
                        "args": data["args"],
                        "id": data["id"]
                    })
                
                ai_msg_tools = AIMessage(content="", tool_calls=tool_calls)
                self.history.append(ai_msg_tools)
                
                for run_id, data in tool_buffer.items():
                    if data["output"] is not None:
                        tool_msg = ToolMessage(
                            content=data["output"],
                            tool_call_id=data["id"]
                        )
                        self.history.append(tool_msg)

            if final_text:
                self.history.append(AIMessage(content=final_text))
            
            await self._emit_event(AgentEvent(type=EventType.FINISH))
            
        except Exception as e:
            await self._emit_event(AgentEvent(type=EventType.ERROR, content=str(e)))

    async def stream(self, user_input: str, user_name: Optional[str] = None) -> AsyncGenerator[AgentEvent, None]:
        """
        The main loop. Streams events from the queue as they happen.
        
        Args:
            user_input: The text input from the user.
            user_name: Optional name of the user for history tracking.
            
        Yields:
            AgentEvent: Events generated during execution.
        """
        if not self.llm:
            await self.initialize()

        # Add user message to history
        # Attach the name if provided
        self.history.append(HumanMessage(content=user_input, name=user_name))

        # Start execution in background
        task = asyncio.create_task(self._run_agent_executor(user_input, user_name))
        
        # Consume queue
        while not task.done() or not self._event_queue.empty():
            try:
                event = await asyncio.wait_for(self._event_queue.get(), timeout=0.1)
                yield event
            except asyncio.TimeoutError:
                continue
        
        # Check for task crash
        if task.done() and task.exception():
            yield AgentEvent(type=EventType.ERROR, content=f"Engine Crash: {task.exception()}")



