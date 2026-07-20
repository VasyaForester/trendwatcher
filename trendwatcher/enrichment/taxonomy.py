"""Таксономия AI security на базе OWASP LLM Top 10 / MITRE ATLAS / NIST AI RMF.

Каждый тег задается списком regex-паттернов (регистронезависимых).
Это baseline-разметка; позже поверх добавляется LLM-классификатор.
"""

TAXONOMY: dict[str, list[str]] = {
    "prompt_injection": [
        r"prompt injection", r"indirect prompt", r"injection attack.{0,30}(llm|model|agent)",
    ],
    "jailbreak": [
        r"jailbreak", r"guardrail bypass", r"safety bypass", r"refusal bypass",
    ],
    "data_poisoning": [
        r"data poisoning", r"training data.{0,20}(poison|manipul)", r"poisoned (data|dataset|model)",
        r"backdoor attack", r"trojan.{0,15}model",
    ],
    "model_supply_chain": [
        r"model supply chain", r"malicious (model|checkpoint|weights)", r"pickle (exploit|deserial)",
        r"hugging\s?face.{0,40}(malicious|vulnerab|attack)", r"typosquat", r"dependency confusion",
        r"(model|ai) (attest|provenance|sbom)", r"supply chain.{0,25}(attest|provenance)",
        r"verifiable (model|weights|checkpoint)",
    ],
    "agent_security": [
        r"agent(ic)? (security|attack|hijack|abuse)", r"tool (abuse|poisoning|misuse)",
        r"autonomous agent.{0,40}(risk|attack|vulnerab)",
        r"computer[- ]use", r"browser agent",
        r"ai agents?.{0,40}(attack|memory|poison|compromis)",
        r"false memor", r"memory.{0,30}(inject|poison|plant|manipul|attack)",
        r"agent memory poison", r"memghost",
        r"secure agentic (workflow|system)", r"cognitive firewall",
    ],
    "mcp_security": [
        r"\bmcp\b.{0,30}(security|attack|vulnerab|risk|exploit)",
        r"model context protocol.{0,30}(security|risk|attack|vulnerab)",
    ],
    "agent_identity_trust": [
        r"agent (identity|trust|authentication|attest)", r"trustworthy agent",
        r"verifiable agent", r"ai[- ]to[- ]ai (auth|trust)",
        r"agent[- ]to[- ]agent.{0,20}(auth|trust|identity)",
        r"ai trust (infrastructure|framework|layer)",
    ],
    "agent_permissions": [
        r"agent permission", r"tool permission", r"permission (system|model).{0,20}agent",
        r"least privilege.{0,20}agent", r"capability (control|sandbox).{0,20}agent",
    ],
    "agent_swarm_security": [
        r"(agent swarm|swarm of agents).{0,20}(sec|attack|risk)",
        r"multi[- ]agent.{0,25}(security|attack|coordination)",
    ],
    "inference_integrity": [
        r"inference[- ]time (integrity|security|attack)", r"test[- ]time.{0,20}(integrity|security)",
        r"runtime (integrity|security).{0,20}(model|llm|inference)",
    ],
    "rag_security": [
        r"\brag\b.{0,40}(poison|attack|security|leak)", r"retrieval[- ]augmented",
        r"vector (database|store).{0,40}(attack|leak|poison)", r"embedding inversion",
    ],
    "data_exfiltration": [
        r"(data|prompt|credential) (exfiltrat|leak)", r"system prompt (leak|extraction)",
        r"training data extraction", r"membership inference", r"sensitive (data|information) disclosure",
    ],
    "model_theft": [
        r"model (theft|extraction|stealing)", r"weights (stolen|leak)", r"distillation attack",
    ],
    "deepfake_fraud": [
        r"deepfake", r"voice clon", r"synthetic (media|identity)", r"ai[- ]generated (phishing|scam|fraud)",
        r"impersonation.{0,30}ai",
    ],
    "adversarial_ml": [
        r"adversarial (example|attack|perturbation|robustness)", r"evasion attack",
    ],
    "vulnerability_cve": [
        r"cve-\d{4}-\d{3,}", r"remote code execution", r"\brce\b", r"zero[- ]day", r"0[- ]day",
        r"arbitrary (code|file)", r"path traversal", r"\bssrf\b",
    ],
    "governance_regulation": [
        r"ai act", r"executive order.{0,30}ai", r"ai (regulation|governance|policy|law)",
        r"nist ai", r"ai rmf", r"iso/iec 42001", r"ai safety institute", r"responsible ai",
        r"autonom(y|ous).{0,20}(govern|control|oversight|compliance)", r"model autonomy.{0,20}govern",
    ],
    "red_teaming": [
        r"red[- ]team", r"penetration test.{0,30}(ai|llm|model)", r"ai security (test|evaluat|benchmark)",
        r"attack simulation", r"machine[- ]speed.{0,20}(red|sec)",
        r"continuous (red[- ]team|automated testing)", r"automated red.?team",
    ],
    "guardrails_defense": [
        r"guardrail", r"prompt (filter|shield|firewall)", r"llm firewall", r"content moderation",
        r"safety (classifier|filter|layer)", r"defense against.{0,30}(injection|jailbreak)",
        r"input sanitiz", r"ai security (tool|platform|product)",
    ],
    "privacy": [
        r"differential privacy", r"\bpii\b", r"personal data.{0,30}(model|ai|llm)",
        r"privacy.{0,30}(llm|ai model|machine learning)", r"gdpr.{0,30}ai",
    ],
    "misinformation": [
        r"misinformation", r"disinformation", r"hallucination", r"fake news.{0,20}ai",
        r"influence operation", r"unreliable (output|generation)", r"confabulation",
    ],
    "bias_fairness": [
        r"\bbias(es)?\b.{0,30}(model|ai|llm|fairness)", r"algorithmic fairness",
        r"discriminat(ion|ory).{0,25}(ai|model|llm)", r"model (fairness|bias)",
    ],
    "model_drift": [
        r"model drift", r"data drift", r"concept drift", r"distribution(al)? shift",
        r"performance degrad", r"model (decay|stale|rot)",
    ],
    "malware_abuse": [
        r"ai[- ](powered|generated|assisted) (malware|attack|exploit)", r"malicious use of (ai|llm)",
        r"llm.{0,30}(malware|phishing) generation", r"wormgpt|fraudgpt", r"dark ?ai",
        r"synthetic insider", r"insider threat.{0,20}ai",
    ],
    # --- Новые security-темы (по разметке сигналов) ---
    "indirect_prompt_injection": [
        r"indirect prompt injection", r"stored prompt injection", r"cross[- ]site prompt",
        r"prompt injection.{0,30}(email|web|document|website|html)",
        r"(email|webpage|document).{0,30}prompt injection",
    ],
    "model_context_poisoning": [
        r"context poison", r"poison(ed|ing)?.{0,25}(context|tool output|document)",
        r"(tool output|retrieved document).{0,30}(poison|manipul|attack)",
        r"knowledge[- ]base poison",
    ],
    "multimodal_injection": [
        r"multimodal (prompt )?injection", r"(image|audio|video|vision).{0,25}(prompt )?injection",
        r"visual prompt injection", r"adversarial (image|audio).{0,30}(vlm|agent|llm)",
    ],
    "agent_memory_security": [
        r"agent memory (poison|inject|attack|leak|security)", r"memory (poison|inject).{0,20}agent",
        r"false memor", r"memghost", r"persistent.{0,20}(false )?memor",
    ],
    "tool_calling_security": [
        r"tool[- ]call(ing)?.{0,30}(security|attack|abuse|hijack|vulnerab)",
        r"function[- ]call(ing)?.{0,30}(security|attack|abuse|hijack)",
        r"tool (abuse|poisoning|misuse|hijack)",
    ],
    "ai_codegen_security": [
        r"(codex|cursor|copilot|vibe coding|code generat).{0,40}(security|vulnerab|attack|risk|malware)",
        r"ai[- ]generated code.{0,30}(vulnerab|insecure|security|exploit)",
        r"(insecure|malicious).{0,25}ai[- ]generated code",
        r"llm.{0,20}code.{0,20}(security|vulnerab)",
    ],
    "autonomous_cyber_offense": [
        r"autonomous (ai )?agent.{0,40}(attack|intrusion|exploit|offense|red.?team)",
        r"ai agents? turned into attack", r"agentic (intrusion|offense|cyber attack)",
        r"llm[- ]driven (cyber|attack|exploit|intrusion)",
        r"machine[- ]speed.{0,20}(offense|attack)",
    ],
    # --- Общие AI-темы (не только security): технологические тренды ---
    "self_evolving_agents": [
        r"self[- ]evolv", r"self[- ]improv", r"recursive self[- ]improvement",
        r"self[- ]modif(y|ying|ication)", r"autonomous(ly)? (improve|evolve|learn)",
        r"darwin.{0,25}(machine|agent|model)", r"agent.{0,30}(rewrites?|updates?) (its|their) own",
        r"self[- ]heal.{0,20}(ai|system|agent)", r"self[- ]repair.{0,20}ai",
    ],
    "agentic_ai": [
        r"multi[- ]agent", r"agent orchestrat", r"agentic (workflow|system|framework|ai|coding)",
        r"agent[- ]to[- ]agent", r"\ba2a protocol\b", r"swarm of agents",
    ],
    "computer_use_agents": [
        r"computer[- ]use (agent|model|ai)", r"browser agent", r"desktop agent",
        r"os[- ]level agent", r"gui agent", r"operator.{0,20}(openai|agent|brows)",
        r"agents?.{0,25}(control|use|operate).{0,20}(computer|browser|desktop)",
    ],
    "reasoning_models": [
        r"reasoning (model|llm)", r"chain[- ]of[- ]thought", r"test[- ]time (compute|scaling)",
        r"inference[- ]time scaling", r"extended thinking", r"deliberative reasoning",
    ],
    "multimodal_ai": [
        r"multimodal", r"vision[- ]language", r"text[- ]to[- ](video|image|3d|speech)",
        r"\bvlm(s)?\b", r"image generation model",
    ],
    "world_models": [
        r"world model", r"embodied (ai|agent)", r"robot(ics)?.{0,30}foundation model",
    ],
    "on_device_ai": [
        r"on[- ]device (ai|model|inference)", r"edge ai", r"small language model", r"\bslm(s)?\b",
        r"local(ly)? (run|running|deployed).{0,20}(model|llm)",
    ],
    "synthetic_data": [
        r"synthetic data", r"synthetic(ally)? generated (data|dataset)",
    ],
    "open_weights": [
        r"open[- ]weight", r"open[- ]sourc.{0,30}(model|llm|weights)", r"weights (release|available)",
    ],
    "model_efficiency": [
        r"quantiz", r"distillation", r"pruning", r"mixture[- ]of[- ]experts", r"\bmoe\b",
        r"efficient (inference|training|fine[- ]tuning)",
    ],
    "long_context_memory": [
        r"long[- ]context", r"context window", r"memory[- ]augmented",
        r"million[- ]token",
    ],
}

# Общие AI-темы: технологические тренды, а не поверхности атак.
AI_TECH_TAGS: set[str] = {
    "self_evolving_agents", "agentic_ai", "computer_use_agents", "reasoning_models",
    "multimodal_ai", "world_models", "on_device_ai", "synthetic_data", "open_weights",
    "model_efficiency", "long_context_memory",
}
SECURITY_TAGS: set[str] = set(TAXONOMY) - AI_TECH_TAGS

# Признак AI-релевантности — для фильтрации общих security-лент (ingest, широкий).
AI_RELEVANCE_PATTERNS: list[str] = [
    r"\bai\b", r"artificial intelligence", r"\bllm(s)?\b", r"large language model",
    r"\bgpt-?\d?\b", r"chatgpt", r"openai", r"anthropic", r"claude", r"gemini",
    r"copilot", r"deepseek", r"mistral", r"llama", r"machine learning", r"deep learning",
    r"neural network", r"deepfake", r"prompt", r"chatbot", r"gen(erative)?[- ]ai",
    r"foundation model", r"hugging ?face", r"langchain", r"\bagentic\b", r"mcp server",
    r"vibe coding", r"ai[- ]agent", r"self[- ]evolving", r"multi[- ]agent",
    r"reasoning model", r"open[- ]weight", r"self[- ]healing", r"mcp security",
    r"model context protocol", r"agent memory",
]

# Узкий фильтр для ленты и строгих новостных источников:
# AI security ИЛИ прорывные AI-технологии (не любое упоминание «AI»).
BREAKTHROUGH_AI_PATTERNS: list[str] = [
    r"\bagentic\b", r"ai[- ]agent(s)?\b", r"multi[- ]agent", r"self[- ]evolving",
    r"self[- ]improving agent", r"reasoning model", r"test[- ]time (compute|scaling)",
    r"foundation model", r"world model", r"open[- ]weight", r"mixture[- ]of[- ]experts",
    r"model context protocol", r"\bmcp\b.{0,20}(server|security|tool)",
    r"\bllm(s)?\b", r"large language model", r"gen(erative)?[- ]ai",
    r"prompt injection", r"\bjailbreak\b", r"llm security", r"ai security",
    r"ai red team", r"adversarial (attack|example).{0,30}(llm|model|ai)",
    r"deepfake", r"model (poisoning|extraction|theft)", r"ai[- ]generated malware",
]

BREAKTHROUGH_AI_TAGS: set[str] = {
    "self_evolving_agents", "computer_use_agents", "long_context_memory",
    "agentic_ai", "reasoning_models", "multimodal_ai",
    "world_models", "open_weights", "synthetic_data",
}

# Лента: только AI-security СОБЫТИЯ / артефакты (не product marketing и не opinion).
FEED_EVENT_PATTERNS: list[str] = [
    r"\bcve-\d{4}-\d+",
    r"\bbreach", r"\bhacked\b", r"compromised", r"security incident",
    r"incident disclosure", r"in the wild",
    # botnet — только если цель/объект AI, не «LLM помог написать IoT-ботнет»
    r"botnet.{0,50}(ai service|llm|ai agent|model|kubernetes|cloud key)",
    r"(ai service|llm|ai agent).{0,50}botnet",
    r"prompt injection", r"indirect prompt", r"\bjailbreak\b",
    r"agent data injection", r"data injection attack.{0,40}ai agent",
    r"(exfiltrat|leaking|leak).{0,40}(secret|credential|api key|data)",
    r"(tricked|jailbreak).{0,40}(claude|gpt|llm|model|agent)",
    r"cyber safeguard", r"safeguards? and our jailbreak",
    r"\bmitigat", r"\bdisclosure\b",
    r"vulnerabilit", r"zero[- ]day", r"0[- ]day",
    r"red team", r"gpt[- ]red", r"prompt injection testing",
    r"adversarial (attack|example|prompt)",
    r"security model for ai", r"security model.{0,40}ai system",
    r"ai (threats?|security|red team)",
    r"(hunt|target|attack).{0,40}(ai service|llm|ai agent|model repo)",
    r"(ai agent|autonomous (ai )?agent).{0,40}(attack|breach|intrusion|compromis|misclick|command)",
    r"(attack|breach|intrusion).{0,40}(ai agent|autonomous|hugging ?face|model repo)",
    r"\bmcp\b.{0,30}(cve|vulnerab|security|attack|exploit)",
    r"(cve|vulnerab).{0,40}\bmcp\b",
    r"llm prompt", r"\bprompty\b", r"prompt loader",
    r"(expose|exfiltrat).{0,40}(llm |api )?keys?",
    r"unauthenticated.{0,40}(llm|api key|config api)",
]

FEED_REJECT_PATTERNS: list[str] = [
    r"^quoting\b",
    r"\bweeknotes?\b",
    r"\bscorecard\b",
    r"\b\d+\s+kinds of\b",
    r"\bhow (cios?|leaders|companies|executives) should\b",
    r"\bissues impacting\b",
    r"deserve access",
    r"concentration of wealth",
    r"data centers? and the",
    r"\bevacuat",
    r"voice ?eq",
    r"vids updates|personal avatars?",
    r"eviscerating",
    r"mania is",
    r"protecting privacy in an AI era",
    r"protecting privacy in an ai era",
    # LLM «помог» классической кибербезе / IoT — не AI security поверхности
    r"llm[- ]assisted.{0,80}(botnet|iot|malware|ransomware)",
    r"(botnet|iot|malware|ransomware).{0,80}llm[- ]assisted",
    r"signs of llm[- ]assisted",
    # Product drops without security event wording
    r"^introducing (claude|gemini|gpt|llama|sonnet|opus|haiku)\b",
    r"^introducing real world\b",
    r"expanding managed agents",
    r"create, edit and star",
]

# AI-сигнал (уже, чем любой «AI»): модель/агент/LLM/MCP в security-контексте.
FEED_AI_ANCHOR_PATTERNS: list[str] = [
    r"\bai\b", r"artificial intelligence", r"\bllm(s)?\b", r"large language model",
    r"\bagentic\b", r"ai[- ]agent", r"\bmcp\b", r"model context protocol",
    r"prompt injection", r"\bjailbreak\b", r"\bprompty\b", r"hugging ?face",
    r"openai|anthropic|claude|gemini|copilot|chatgpt",
]

# Известные сущности (вендоры, продукты, модели) для простого извлечения.
KNOWN_ENTITIES: list[str] = [
    "OpenAI", "ChatGPT", "GPT-4", "GPT-5", "Anthropic", "Claude", "Google", "Gemini",
    "DeepMind", "Microsoft", "Copilot", "Azure", "Meta", "Llama", "NVIDIA", "AWS",
    "Hugging Face", "LangChain", "Ollama", "vLLM", "MLflow", "PyTorch", "TensorFlow",
    "DeepSeek", "Mistral", "Grok", "xAI", "Cursor", "GitHub", "NIST", "OWASP", "MITRE",
    "CISA", "ENISA", "EU AI Act", "Perplexity", "Slack", "Salesforce", "Databricks",
]

SEVERITY_PATTERNS: dict[str, float] = {
    r"actively exploited|in the wild|zero[- ]day|0[- ]day": 1.0,
    r"critical (vulnerability|flaw|bug)|cvss (9|10)": 0.9,
    r"remote code execution|\brce\b": 0.8,
    r"(data )?breach|compromised|hacked|stolen": 0.7,
    r"exploit|attack campaign|malware": 0.5,
    r"vulnerabilit|flaw|weakness": 0.3,
}
