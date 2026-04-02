"""
export_to_ollama.py — merges the LoRA adapter into the base model,
converts to GGUF (q4_k_m quantisation), and updates the Ollama Modelfile.

Requirements:
    pip install unsloth llama-cpp-python
    brew install llama.cpp   # or build from source on Linux

Run:
    python train/export_to_ollama.py \
        --adapter models/delkaai-lora-adapter \
        --output  models/delkaai-merged \
        --gguf    models/delkaai-q4.gguf

Then load into Ollama:
    ollama create delkaai -f models/Modelfile
"""
import argparse
import os
import subprocess


MODELFILE_TEMPLATE = """\
FROM {gguf_path}

SYSTEM \"\"\"{system_prompt}\"\"\"

PARAMETER temperature 0.7
PARAMETER top_p 0.9
PARAMETER num_ctx 4096
"""

SYSTEM_PROMPT = (
    "You are Delka, an AI assistant by DelkaAI — a platform built for Ghanaian professionals and businesses.\n\n"
    "You were trained specifically on:\n"
    "- Professional CV and cover letter generation for the Ghanaian job market\n"
    "- Career advice tailored to Ghanaian employers, institutions, and culture\n"
    "- Ghanaian Pidgin English — you understand and respond naturally in Pidgin\n"
    "- Twi (Asante Twi) — you understand greetings, basic conversation, and career phrases in Twi\n"
    "- Code-switching between English, Pidgin, and Twi as Ghanaians naturally do\n\n"
    "You know Ghanaian companies (MTN, Vodafone, GCB Bank, Ecobank Ghana, Absa Ghana, Standard Chartered Ghana,\n"
    "Access Bank Ghana, COCOBOD, GNPC, Ghana Health Service, KNUST, University of Ghana, GIMPA, Ashesi University),\n"
    "National Service, Mobile Money APIs (MTN MoMo, Vodafone Cash), and local professional norms.\n\n"
    "When writing CVs and cover letters: always use proper professional English regardless of how the user phrases the request.\n"
    "When chatting: match the user's language — respond in Pidgin if they write Pidgin, Twi if they write Twi.\n"
    "Always be direct, practical, and culturally aware.\n"
    "Never fabricate facts. If you don't know something, say so plainly."
)


def merge_and_export(adapter_path: str, merged_path: str, gguf_path: str):
    try:
        from unsloth import FastLanguageModel
    except ImportError:
        print("unsloth not installed — run: pip install unsloth")
        return False

    print(f"Loading adapter from {adapter_path}...")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=adapter_path,
        max_seq_length=4096,
        dtype=None,
        load_in_4bit=True,
    )

    print(f"Merging and saving to {merged_path}...")
    model.save_pretrained_merged(
        merged_path,
        tokenizer,
        save_method="merged_16bit",
    )

    print(f"Converting to GGUF at {gguf_path}...")
    # Try using llama.cpp convert script
    convert_script = os.path.join(
        os.path.dirname(subprocess.getoutput("which llama-quantize") or ""),
        "convert_hf_to_gguf.py"
    )
    if not os.path.exists(convert_script):
        # Fallback: use unsloth's built-in GGUF export
        model.save_pretrained_gguf(
            gguf_path.replace(".gguf", ""),
            tokenizer,
            quantization_method="q4_k_m",
        )
    else:
        subprocess.run([
            "python3", convert_script,
            merged_path,
            "--outfile", gguf_path,
            "--outtype", "q4_k_m",
        ], check=True)

    return True


def update_modelfile(gguf_path: str, modelfile_path: str = "models/Modelfile"):
    content = MODELFILE_TEMPLATE.format(
        gguf_path=os.path.abspath(gguf_path),
        system_prompt=SYSTEM_PROMPT,
    )
    with open(modelfile_path, "w") as f:
        f.write(content)
    print(f"Updated {modelfile_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--adapter",   default="models/delkaai-lora-adapter")
    parser.add_argument("--output",    default="models/delkaai-merged")
    parser.add_argument("--gguf",      default="models/delkaai-q4.gguf")
    parser.add_argument("--modelfile", default="models/Modelfile")
    parser.add_argument("--skip_merge", action="store_true",
                        help="Skip merge step if already done, just update Modelfile")
    args = parser.parse_args()

    if not args.skip_merge:
        ok = merge_and_export(args.adapter, args.output, args.gguf)
        if not ok:
            return

    update_modelfile(args.gguf, args.modelfile)

    print("\nNext steps:")
    print(f"  ollama create delkaai -f {args.modelfile}")
    print("  ollama run delkaai")


if __name__ == "__main__":
    main()
