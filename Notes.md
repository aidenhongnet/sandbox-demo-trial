Test bed should actually be an incredibly well-documented product with synthetic malformed docs

- thus we have labels for corrections that need to be identified (also good because we'll design around good docs rather than over or under shooting)

- The malformed documentation can also be synthesized more organically by reverting the current good documentation back to a bad documentation state. 

What is the exact problem statement and solution we are looking for?

- The docs are inaccurate? Documentation coverage isn't wide enough? Documentation isn't clear enough for users?

What are some possible solutions?

1. For maximum coverage: Agent blindly takes every single interaction it can find in the product, then reconciled to docs. Useful for answering the question: Where does documentation have gaps around the real product? 

2. For precision: Follow the idiomatic flow and see where it deviates from the documentation. Useful for answering the question: Where does documentation deviate from the real product? 

- Classify documentation as GUI or non-GUI. Non-GUI can be resolved with code analysis. 

  

Rough Draft by James: Have a cheaper model assess the documentation and plan out a comprehensive search suite.  

  

Necessary components right now for sure:

Sandboxing, permission management, agent follows flow from instructions, state / flow / prompt caching and encoding, agent starting from state and achieving goal, agent surfacing obvious docs error

Opus vs. Fable experiment right now : just point at code-repo and identify docs errors, might end up being significantly cheaper than human QA anyways

Code analysis for every single different GUI branch. 

Pass driver the docs directly and let it do anything  

How would Haiku decompose the documentation into driver instructions?

Possibly work on marketing materials as well

Difficulties:
	- Version management
	- Highly branched pages
	- Side effects on filesystem
	- Integrations with any other products


two trials:
	- Original James thought of
	- DAST + docs search + verify 

Tagging 