import asyncio
from typing import AsyncGenerator, List, Any
from langchain_core.messages import HumanMessage, SystemMessage, BaseMessage
from langchain_core.language_models import BaseChatModel
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnableConfig

from aigent.core.schemas import UserProfile, AgentEvent, EventType, ModelProvider
from aigent.core.memory import MemoryLoader
from aigent.plugins.loader import PluginLoader
from aigent.core.tools import fs_read, fs_write, fs_patch, bash_execute

class AgentEngine:
    def __init__(self, profile: UserProfile):
        self.profile = profile
        self.memory_loader = MemoryLoader()
        self.plugin_loader = PluginLoader()
        self.tools = []
        self.llm: BaseChatModel = None # type: ignore
        self.history: List[BaseMessage] = []

    async def initialize(self) -> None:
        """
        Async initialization: loads tools, reads memory files, sets up LLM.
        """
        # 1. Load Static Context (System Prompt)
        system_context = await self.memory_loader.load_context()
        
        # Override with profile path if specified
        if self.profile.system_prompt_path:
             # Logic to load specific file could go here
             pass

        # 2. Load Tools (Plugins + Core)
        plugin_tools = self.plugin_loader.load_plugins(self.profile.allowed_tools)
        core_tools = [fs_read, fs_write, fs_patch, bash_execute]
        
        # If user restricts tools, we might want to filter core tools too?
        # For now, let's assume core tools are always available unless we add a flag.
        # But we should respect 'allowed_tools' if it's NOT ["*"].
        
        if "*" in self.profile.allowed_tools:
             self.tools = plugin_tools + core_tools
        else:
             # Only allow core tools if explicitly named? 
             # Or always include them? Let's always include them for convenience 
             # unless explicitly filtered.
             # Actually, simpler: just add them to the pool and let filter handle it?
             # No, 'allowed_tools' is currently used by PluginLoader to filter DISK plugins.
             # Let's just add Core tools by default for now.
             self.tools = plugin_tools + core_tools

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

    async def stream(self, user_input: str) -> AsyncGenerator[AgentEvent, None]:
        """
        The main loop. Streams events as they happen.
        """
        if not self.llm:
            await self.initialize()

        # Add user message to history
        self.history.append(HumanMessage(content=user_input))

        # We use the raw LLM + Tool calling loop manually or use a prebuilt agent.
        # For maximum control and "Simplicity" (avoiding AgentExecutor blackbox), 
        # let's use the model directly.
        # However, handling the "Loop" (Model -> Tool -> Model) manually is complex.
        # Let's use LangChain's AgentExecutor for now as it provides the robust loop 
        # and astream_events support.
        
        from langchain.agents import create_tool_calling_agent, AgentExecutor
        from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

        # Construct a temporary agent for this execution
        prompt = ChatPromptTemplate.from_messages([
            ("system", "{system_message}"),
            MessagesPlaceholder(variable_name="chat_history"),
            ("human", "{input}"),
            MessagesPlaceholder(variable_name="agent_scratchpad"),
        ])

        # Create the agent runnable
        agent = create_tool_calling_agent(self.llm, self.tools, prompt)
        agent_executor = AgentExecutor(agent=agent, tools=self.tools, verbose=False)

        # Extract system message content
        system_msg_content = self.history[0].content if self.history else ""
        chat_history_safe = self.history[1:-1] # Exclude system and latest human (passed as input)

        # Stream events
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
                # Token received
                content = event["data"]["chunk"].content
                if content:
                    yield AgentEvent(type=EventType.TOKEN, content=content)
            
            elif kind == "on_tool_start":
                yield AgentEvent(
                    type=EventType.TOOL_START, 
                    content=f"Calling tool: {event['name']}",
                    metadata={"input": event["data"].get("input")}
                )
                
            elif kind == "on_tool_end":
                 yield AgentEvent(
                    type=EventType.TOOL_END, 
                    content=str(event["data"].get("output")),
                    metadata={"name": event["name"]}
                )
            
            # Handle "Thinking" / Intermediate steps if not covered by tool calls
            # (AgentExecutor yields intermediate_steps in on_chain_end usually, 
            # but real-time thinking is usually just the text before a tool call)

        # Update history (AgentExecutor doesn't auto-update our list)
        # In a real implementation, we'd parse the output and append AI Message + Tool Messages
        # For now, we assume a single turn or need a better history manager.
        # Simplification: We don't persist the full tool execution trace back to self.history 
        # in this snippet to avoid complexity, but the Chat History provided to the agent 
        # ensures context is kept for *this* session if we managed it correctly.
        
        yield AgentEvent(type=EventType.FINISH)
