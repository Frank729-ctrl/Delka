"""
prepare_data.py — converts all DelkaAI parquet training datasets into a
single unified JSONL file in the Unsloth/HuggingFace chat format.

Output format per line:
    {"messages": [
        {"role": "system", "content": "..."},
        {"role": "user",   "content": "..."},
        {"role": "assistant", "content": "..."}
    ]}

Run:
    python train/prepare_data.py --out train/delka_train.jsonl
"""
import argparse
import json
import os
import random
import re
import sys

import pyarrow.parquet as pq
import pandas as pd

# ── Delka system prompt (injected into every example) ─────────────────────────
DELKA_SYSTEM = (
    "You are Delka, an AI assistant by DelkaAI — built for Ghanaian professionals and businesses. "
    "You are honest, warm, clear, and culturally aware. "
    "You understand Ghanaian Pidgin English and Twi. "
    "You know Ghanaian companies, Mobile Money (MTN MoMo, Vodafone Cash), National Service, "
    "and the local professional context. "
    "When writing CVs and cover letters use proper professional English. "
    "In casual chat match the user's language. "
    "Never fabricate facts. If you don't know something, say so."
)

PARQUET_DIR = os.path.join(os.path.dirname(__file__), "..")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _clean(text: str) -> str:
    if not isinstance(text, str):
        return ""
    return text.strip()


def _sharegpt_to_messages(convs: list, system_override: str = "") -> list[dict] | None:
    """Convert ShareGPT [{"from": "human"/"gpt"/"system", "value": ...}] format."""
    if not convs or not isinstance(convs, list):
        return None
    messages = []
    sys_added = False
    for turn in convs:
        role_raw = turn.get("from", "")
        value = _clean(turn.get("value", ""))
        if not value:
            continue
        if role_raw == "system":
            messages.append({"role": "system", "content": value})
            sys_added = True
        elif role_raw in ("human", "user"):
            if not sys_added:
                messages.append({"role": "system", "content": system_override or DELKA_SYSTEM})
                sys_added = True
            messages.append({"role": "user", "content": value})
        elif role_raw in ("gpt", "assistant", "bot"):
            messages.append({"role": "assistant", "content": value})
    # Must have at least one user + assistant pair
    roles = {m["role"] for m in messages}
    if "user" not in roles or "assistant" not in roles:
        return None
    return messages


def _rlhf_chosen_to_messages(chosen: str) -> list[dict] | None:
    """Parse Anthropic RLHF Human:/Assistant: dialogue format."""
    if not isinstance(chosen, str):
        return None
    # Support both short (H:/A:) and full (Human:/Assistant:) tags
    turns = re.split(r"\n\n(Human:|Assistant:|H:|A:)\s*", "\n\n" + chosen.strip())
    messages = [{"role": "system", "content": DELKA_SYSTEM}]
    i = 1
    while i < len(turns) - 1:
        tag = turns[i].strip()
        content = _clean(turns[i + 1]) if i + 1 < len(turns) else ""
        if not content:
            i += 2
            continue
        if tag in ("H:", "Human:"):
            messages.append({"role": "user", "content": content})
        elif tag in ("A:", "Assistant:"):
            messages.append({"role": "assistant", "content": content})
        i += 2
    roles = {m["role"] for m in messages}
    if "user" not in roles or "assistant" not in roles:
        return None
    return messages


def _openai_messages_to_messages(raw: list) -> list[dict] | None:
    """Convert [{"role": ..., "content": ...}] format (UltraFeedback, CAI messages)."""
    if not isinstance(raw, list) or len(raw) < 2:
        return None
    messages = [{"role": "system", "content": DELKA_SYSTEM}]
    for m in raw:
        role = m.get("role", "")
        content = _clean(m.get("content", ""))
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    roles = {m["role"] for m in messages}
    if "user" not in roles or "assistant" not in roles:
        return None
    return messages


def _instruction_pair(prompt: str, completion: str) -> list[dict] | None:
    p, c = _clean(prompt), _clean(completion)
    if not p or not c:
        return None
    return [
        {"role": "system", "content": DELKA_SYSTEM},
        {"role": "user", "content": p},
        {"role": "assistant", "content": c},
    ]


def _ultrachat_to_messages(data) -> list[dict] | None:
    """UltraChat 'data' field is a list of [question, answer, question, answer...]"""
    if not isinstance(data, list) or len(data) < 2:
        return None
    messages = [{"role": "system", "content": DELKA_SYSTEM}]
    for i, text in enumerate(data):
        text = _clean(str(text))
        if not text:
            continue
        messages.append({"role": "user" if i % 2 == 0 else "assistant", "content": text})
    roles = {m["role"] for m in messages}
    if "user" not in roles or "assistant" not in roles:
        return None
    return messages


def _claude_reasoning_to_messages(messages_raw) -> list[dict] | None:
    """claude_reasoning has [{"role": ..., "content": ..., "thinking": ...}]"""
    if not isinstance(messages_raw, list):
        return None
    out = [{"role": "system", "content": DELKA_SYSTEM}]
    for m in messages_raw:
        role = m.get("role", "")
        content = _clean(m.get("content", ""))
        if role in ("user", "assistant") and content:
            out.append({"role": role, "content": content})
    roles = {m["role"] for m in out}
    if "user" not in roles or "assistant" not in roles:
        return None
    return out


# ── Dataset loaders ───────────────────────────────────────────────────────────

def load_anthropic_rlhf(path: str, limit: int) -> list:
    t = pq.read_table(path, columns=["chosen"])
    rows = t.column("chosen").to_pylist()
    random.shuffle(rows)
    out = []
    for r in rows[:limit * 2]:
        msgs = _rlhf_chosen_to_messages(r)
        if msgs:
            out.append({"messages": msgs})
        if len(out) >= limit:
            break
    return out


def load_cai(path: str, limit: int) -> list:
    # CAI harmless uses a 'messages' column with [{"role":..., "content":...}] format
    schema = pq.read_schema(path).names
    col = "messages" if "messages" in schema else "chosen"
    t = pq.read_table(path, columns=[col])
    rows = t.column(col).to_pylist()
    out = []
    for row in rows[:limit * 2]:
        if isinstance(row, list):
            msgs = _openai_messages_to_messages(row)
        else:
            msgs = _rlhf_chosen_to_messages(str(row))
        if msgs:
            out.append({"messages": msgs})
        if len(out) >= limit:
            break
    return out


def load_claude_reasoning(path: str, limit: int) -> list:
    t = pq.read_table(path, columns=["messages"])
    rows = t.column("messages").to_pylist()
    out = []
    for r in rows[:limit * 2]:
        msgs = _claude_reasoning_to_messages(r)
        if msgs:
            out.append({"messages": msgs})
        if len(out) >= limit:
            break
    return out


def load_codealpaca(path: str, limit: int) -> list:
    t = pq.read_table(path, columns=["prompt", "completion"])
    df = t.to_pandas().sample(frac=1).reset_index(drop=True)
    out = []
    for _, row in df.iterrows():
        msgs = _instruction_pair(row["prompt"], row["completion"])
        if msgs:
            out.append({"messages": msgs})
        if len(out) >= limit:
            break
    return out


def load_sharegpt(path: str, col: str, limit: int, system_override: str = "") -> list:
    t = pq.read_table(path, columns=[col])
    rows = t.column(col).to_pylist()
    random.shuffle(rows)
    out = []
    for r in rows[:limit * 3]:
        if isinstance(r, str):
            try:
                r = json.loads(r)
            except Exception:
                continue
        msgs = _sharegpt_to_messages(r, system_override)
        if msgs:
            out.append({"messages": msgs})
        if len(out) >= limit:
            break
    return out


def load_ultrachat(paths: list[str], limit: int) -> list:
    out = []
    for path in paths:
        if not os.path.exists(path):
            continue
        t = pq.read_table(path, columns=["data"] if "data" in pq.read_schema(path).names else ["conversations"])
        col = "data" if "data" in t.column_names else "conversations"
        rows = t.column(col).to_pylist()
        random.shuffle(rows)
        for r in rows:
            if col == "data":
                msgs = _ultrachat_to_messages(r)
            else:
                msgs = _sharegpt_to_messages(r)
            if msgs:
                out.append({"messages": msgs})
            if len(out) >= limit:
                return out
    return out


def load_ultrafeedback(path: str, limit: int) -> list:
    # UltraFeedback chosen is [{"role": ..., "content": ...}] (OpenAI format)
    t = pq.read_table(path, columns=["chosen"])
    rows = t.column("chosen").to_pylist()
    out = []
    for chosen in rows[:limit * 2]:
        if isinstance(chosen, list):
            # Try OpenAI format first, then ShareGPT
            msgs = _openai_messages_to_messages(chosen) or _sharegpt_to_messages(chosen)
        else:
            continue
        if msgs:
            out.append({"messages": msgs})
        if len(out) >= limit:
            break
    return out


# ── Main ──────────────────────────────────────────────────────────────────────

DATASET_CONFIG = [
    # (loader_fn, args, limit, description)
    ("anthropic_rlhf",  ["anthropic_rlhf_0.parquet"],        5_000,  "Anthropic RLHF"),
    ("cai",             ["cai_harmless_train.parquet"],       3_000,  "Constitutional AI"),
    ("claude_reasoning",["claude_reasoning_0.parquet"],         799,  "Claude Reasoning (all)"),
    ("codealpaca",      ["codealpaca_0.parquet"],             5_000,  "CodeAlpaca"),
    ("sharegpt_convs",  ["openhermes_0.parquet", "conversations", 10_000], 10_000, "OpenHermes"),
    ("sharegpt_convs",  ["slimorca_0.parquet",   "conversations",  8_000],  8_000, "SlimOrca-0"),
    ("sharegpt_convs",  ["slimorca_1.parquet",   "conversations",  8_000],  8_000, "SlimOrca-1"),
    ("sharegpt_convs",  ["wizardlm_0.parquet",   "conversations",  5_000],  5_000, "WizardLM"),
    ("ultrachat",       None,                               10_000, "UltraChat"),
    ("ultrafeedback",   ["ultrafeedback_0.parquet"],          5_000,  "UltraFeedback"),
]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default="train/delka_train.jsonl")
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()

    random.seed(args.seed)
    os.chdir(PARQUET_DIR)

    all_examples: list[dict] = []

    for entry in DATASET_CONFIG:
        loader_name, loader_args, limit, desc = entry
        print(f"Loading {desc}...", end=" ", flush=True)

        try:
            if loader_name == "anthropic_rlhf":
                examples = load_anthropic_rlhf(loader_args[0], limit)
            elif loader_name == "cai":
                examples = load_cai(loader_args[0], limit)
            elif loader_name == "claude_reasoning":
                examples = load_claude_reasoning(loader_args[0], limit)
            elif loader_name == "codealpaca":
                examples = load_codealpaca(loader_args[0], limit)
            elif loader_name == "sharegpt_convs":
                path, col, _ = loader_args
                examples = load_sharegpt(path, col, limit)
            elif loader_name == "ultrachat":
                paths = [f"ultrachat_{i}.parquet" for i in range(10)]
                examples = load_ultrachat(paths, limit)
            elif loader_name == "ultrafeedback":
                examples = load_ultrafeedback(loader_args[0], limit)
            else:
                examples = []

            print(f"{len(examples):,} examples")
            all_examples.extend(examples)
        except Exception as e:
            print(f"ERROR: {e}")

    # Shuffle and deduplicate (rough check on first user message)
    random.shuffle(all_examples)
    seen = set()
    deduped = []
    for ex in all_examples:
        user_msgs = [m["content"][:80] for m in ex["messages"] if m["role"] == "user"]
        key = "||".join(user_msgs)
        if key not in seen:
            seen.add(key)
            deduped.append(ex)

    print(f"\nTotal: {len(all_examples):,} → after dedup: {len(deduped):,}")

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for ex in deduped:
            f.write(json.dumps(ex, ensure_ascii=False) + "\n")

    print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()
