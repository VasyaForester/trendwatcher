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
    ],
    "agent_security": [
        r"agent(ic)? (security|attack|hijack|abuse)", r"tool (abuse|poisoning|misuse)",
        r"mcp (server|tool|protocol)", r"autonomous agent.{0,40}(risk|attack|vulnerab)",
        r"computer[- ]use", r"browser agent",
        r"ai agents?.{0,40}(attack|memory|poison|compromis)",
        r"false memor", r"memory.{0,30}(inject|poison|plant|manipul|attack)",
        r"agent memory", r"memghost",
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
    ],
    "red_teaming": [
        r"red[- ]team", r"penetration test.{0,30}(ai|llm|model)", r"ai security (test|evaluat|benchmark)",
        r"attack simulation",
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
    ],
    # --- Общие AI-темы (не только security): технологические тренды ---
    "self_evolving_agents": [
        r"self[- ]evolv", r"self[- ]improv", r"recursive self[- ]improvement",
        r"self[- ]modif(y|ying|ication)", r"autonomous(ly)? (improve|evolve|learn)",
        r"darwin.{0,25}(machine|agent|model)", r"agent.{0,30}(rewrites?|updates?) (its|their) own",
    ],
    "agentic_ai": [
        r"multi[- ]agent", r"agent orchestrat", r"agentic (workflow|system|framework|ai|coding)",
        r"agent[- ]to[- ]agent", r"\ba2a protocol\b", r"swarm of agents", r"computer[- ]use agent",
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
    "self_evolving_agents", "agentic_ai", "reasoning_models", "multimodal_ai",
    "world_models", "on_device_ai", "synthetic_data", "open_weights",
    "model_efficiency", "long_context_memory",
}
SECURITY_TAGS: set[str] = set(TAXONOMY) - AI_TECH_TAGS

# Признак AI-релевантности — для фильтрации общих security-лент.
AI_RELEVANCE_PATTERNS: list[str] = [
    r"\bai\b", r"artificial intelligence", r"\bllm(s)?\b", r"large language model",
    r"\bgpt-?\d?\b", r"chatgpt", r"openai", r"anthropic", r"claude", r"gemini",
    r"copilot", r"deepseek", r"mistral", r"llama", r"machine learning", r"deep learning",
    r"neural network", r"deepfake", r"prompt", r"chatbot", r"gen(erative)?[- ]ai",
    r"foundation model", r"hugging ?face", r"langchain", r"\bagentic\b", r"mcp server",
    r"vibe coding", r"ai[- ]agent", r"self[- ]evolving", r"multi[- ]agent",
    r"reasoning model", r"open[- ]weight",
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
