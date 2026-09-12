# Agents for Humans: multi-agent crowd safety for the Nashik Kumbh 2027

*Draft for publication on [builder.aws](https://builder.aws/). "Agents for
Humans" stays in the title — that is the bonus-content rule. Suggested tags:
`strands-agents`, `multi-agent`, `generative-ai`, `agents`, `bedrock`, `ecs`,
`public-safety`.*

*This is the **3000-character** version: the post is the title line plus
everything below the rule, and measures **3017 characters**. The earlier
long-form draft (~2260 words) is still in this file's git history if a
longer format is wanted. Editorial notes above the rule are not part of the
count.*

---

In 2003, a barricade gave way beside Kalaram Mandir in Nashik. **39 people died** in a lane 1.8 metres wide. In 2025 at Prayagraj, barricades broke before dawn: 30 dead officially, at least 82 by the BBC's count. The same pattern 22 years apart — a narrow point failing at the most crowded moment of the event.

In 2027, tens of millions will walk those same lanes for the Simhastha Kumbh Mela. I built **Trinetra** on the **Strands Agents SDK** to ask whether agents could help an authority *rehearse* that failure first.

**Why multi-agent, not a chatbot.** A pilgrim needs a route in Bhojpuri. An operator needs to know whether to close a gate in four minutes. A planner needs to stress-test that plan months earlier. Three jobs, not three prompts. Trinetra composes ten Strands agents with the SDK's **"agents as tools"** pattern — a router whose only job is picking the specialist, never answering itself.

**Code computes, models interpret.** Every number a safety decision rests on is plain Python: crowd simulation, evacuation feasibility, responder allocation, conflict detection. No model in that path. Agents sit on top supplying judgment, returning validated Pydantic objects rather than prose:

```python
result = agent(prompt, structured_output_model=HydrologyAdvisory)
```

That boundary is what makes it testable. `trinetra calibrate` replays Nashik 2003 and Prayagraj 2025 and requires both to flag CRITICAL — but alone that is a tautology, passed by a function returning CRITICAL forever. What matters is the controls that must *not* fire. One pair is the same crowd, window and surge, differing only in whether the 1.8m lane is on the route: one stays routine, one flags. That is the only evidence the model reacts to a decision, not a headcount.

**What multi-agent actually bought.** Independent desks, each correct alone, still miss things. The flood desk needs Ramkund cleared; the crowd desk has the neighbouring ghat at 96%. Both right — and doing both pushes an evacuation into a crush. The conflict is a property of the *pair*, invisible from inside either. So code detects it, code divides the finite responder pool, and only then does a commander agent judge the remainder — with a red-team agent attacking the result. Its sharpest catch live: the plan named an assembly point absent from our site data. Our adversarial agent found our own hallucination.

**On AWS.** It deploys from **CloudShell** with no local Docker: **CodeBuild** builds the image, **ECS Express Mode** provisions Fargate, an ALB, TLS and a public URL. It runs on **Amazon Bedrock** or the Anthropic API.

**Honest limits:** the sites, the 1.8m width and both incidents are cited. Capacities and lead times are our own estimates — the relationships hold, the minute counts need NTKMA's real figures.

Live: https://tr-f84a1a73e8154b1c88e4d700c96ccb64.ecs.us-east-1.on.aws

Code (MIT): https://github.com/akashtalole/Agents-for-Humans-Hackathon
