# aigent values/principles interview

> A library exists that solves our problem perfectly, but it adds 50MB to the install size and brings in 10 sub-dependencies. Do we use it, or write a simpler 80% solution ourselves?

It depends. We do use some heavy libs like langchain. This project is intended to eventually evolve into something much bigger where langchain and langgraph will really help. If it would take us weeks or months + lots of debugging hell to write something that already exists, then we should scan it for security vulnerabilities and then strongly consider using it. Note: when I say "weeks", I mean even with LLM-assistance. An LLM can create fairly complex libraries within a minute. A library so complex that it would take an LLM weeks to produce should be a candidate for re-using a third party library.

> A third-party API (e.g., for specialized code analysis) is $0.01/call but perfect. An open-source local model is free but 30% worse. Which do we choose? (Tie-breaker: Sovereignty vs. Performance)

In this case, I would want it to be user configurable. We should support ollama for local instances but also paid API options for powerful agents.

> We need a message queue. Do we use RabbitMQ (Industry Standard, heavy) or asyncio.Queue (Standard Lib, single-process)? (Tie-breaker: Simplicity vs. Scale)

Depends. Right now we will focus on supporting up to 50 connected clients and rapid message delivery.

> We want to ship a new plugin feature. The "Right Way" requires refactoring the Core Event Bus. The "Fast Way" involves a small hack in handlers.py. Do we ship the hack to get user feedback, or block the feature for the refactor?

Block the feature for the refactor. We are using LLMs which can produce high quality results at a fraction of the time. One note I want to emphasize here when considering the "time cost"; LLMs often measure time cost based on how long it would take a human to complete a task, because that's how they were trained. It should be emphasized in the docs that LLMs fall prey to this conception of time cost that is irrelevant to them and should **not** be considered when weighing time cost. (1) We prioritize stable, quality code over speed of deliver -- this is a personal project, and (2) LLMs tend to severely underestimate how fast they work lol. If it ever crosses your mind/weights that "stable implementation A is a huge 1 week time cost", know that it'll probably take you 1 hour max, and that's very, very acceptable lol.

> Does this answer change if we are working on src/aigent/core/ vs src/aigent/plugins/experimental/? (Tie-breaker: Core Stability vs. Edge Agility)

Core must always be perfect. Every function should have unit tests. Every set of interactions should have their own separate tests. We also need E2E tests that further stress test every feasible and crazy real-world data that might be thrown at it (including trash data from power users hacking at the websockets and sending their own custom data -- we want to mock crazy data and unexpected data and all manner of unexpected input)

> An LLM generates a test case that passes but is flaky (fails 1/10 times). Do we merge it to get coverage now, or delete it until it's perfect?

Get it perfect. Any failing test should be investigated and a bugfix branch created for it. The loop should be:

1. Assess if test is failing due to code or test
2. If due to bad code:
   1. assess what the fix should be
   2. write a test case that should fail and catch the bad code but succeed once the bug is patched
   3. run the test to ensure it fails
   4. implement the fix
   5. re-run the test to ensure it succeed
   6. IF the test does not succeed on the re-run, revert the fix and start over at #2 and repeat until we get a perfect sequence of `bug exists in code -> write test case -> run test case -> test case fails -> implement fix -> re-run test case -> test case succeeds without any modification to source or test code`
4. If due to bad test:
   1. rewrite test to work
   2. run test
   3. repeat until test works

Any new bugs discovered along the way should be noted and have their own clean git branch created.

> The "Correct" architectural flow for an error message takes 200ms longer because it goes through the proper Event Bus layers. A "Direct" print to stdout is instant. Do we sacrifice architecture for latency?

No.

> A user wants to run a dangerous command. Do we strictly block it (Safety), or do we let them override it with a flag (Autonomy)? (Tie-breaker: Safety vs. Sovereignty)

We let them override it -- sovereignty.

> We can make the CLI look "cooler" with complex animations, but it might break on old terminals. Do we prioritize aesthetics or compatibility?

The TUI mode and Web UI get "cooler" complex animations and modern aesthetics and features. The REPL mode will prioritize and maintain compatibility.

> "Explicit is better than implicit." But how explicit? Do we write user_id: str or UserId (a NewType/Alias)? Do we prefer 5-line functions that do one thing, or 20-line functions that keep context together? (You already answered: 50 lines max).

Yeah, I hate this OOP question. Any object can be decomposed into infinitely many classes. If we foresee needing/wanting custom functions on an object -- if such a thing would simplify code/logic later -- then let's decompose into smaller classes. e.g.: If we think UserId.find_sessions() would be convenient (and the correct location for such a function; I suspect such a function should actually live in a controller and thus NOT result in a decision to decompose to UserId)

> Do we comment what code does (redundant with clean code) or why it does it?

Rationale is king. We want rationale everywhere. Why did we do this? Ideally code should be easily understood and function names long and clear and readily understood. If there is a block of code that is particularly hard to read, consider before commenting:

1. simplifying the logic, even if it's longer
2. moving the logic to a very clearly, simply, explicitly named function

> If the LLM generates code that looks insecure but works, do we accept it?

We analyze it and test it. But yes, if it passes scrutiny, accept it.

> How much data do we log for debugging? If a crash dump contains user code, do we save it by default (Debugging) or drop it (Privacy)?

Dump it, but leave it for DEBUG mode and add a warning when `--log-level DEBUG` is used that DEBUG mode might dump sensitive data to logs.

> Is this tool an "Assistant" (subservient) or a "Partner" (proactive)? If the user is making a mistake, should the agent stop them unprompted?

A partner and, more uniquely relative to other agentic tools: a facilitator of shared sessions and a Web UI that allows easy collaborative sessions + working with an agent that has full filesystem access on a chosen server (enabling shared planning or working sessions that produce actual, immediately deployed work OR letting me log onto a website while i'm driving and use Voice to Text to do actual work/planning remotely).
