"""
train_delka.py — fine-tunes llama-3.1-8b with Unsloth using the
prepared JSONL dataset, then saves the updated LoRA adapter.

Requirements:
    pip install unsloth trl transformers datasets accelerate bitsandbytes

Run:
    python train/train_delka.py \
        --data train/delka_train.jsonl \
        --output models/delkaai-lora-adapter \
        --epochs 1 \
        --batch 2 \
        --max_steps 2000

GPU memory required: ~12 GB (4-bit quantised base model + r=16 LoRA).
On Google Colab (T4): set --batch 1 --grad_accum 8.
"""
import argparse
import os


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data",       default="train/delka_train.jsonl")
    parser.add_argument("--output",     default="models/delkaai-lora-adapter")
    parser.add_argument("--base_model", default="unsloth/llama-3.1-8b-bnb-4bit")
    parser.add_argument("--epochs",     type=int,   default=1)
    parser.add_argument("--max_steps",  type=int,   default=2000)
    parser.add_argument("--batch",      type=int,   default=2)
    parser.add_argument("--grad_accum", type=int,   default=4)
    parser.add_argument("--lr",         type=float, default=2e-4)
    parser.add_argument("--max_seq",    type=int,   default=2048)
    parser.add_argument("--lora_r",     type=int,   default=16)
    parser.add_argument("--lora_alpha", type=int,   default=16)
    args = parser.parse_args()

    # ── Lazy imports (requires GPU environment) ───────────────────────────────
    try:
        from unsloth import FastLanguageModel
        from unsloth.chat_templates import get_chat_template
        from datasets import load_dataset
        from trl import SFTTrainer
        from transformers import TrainingArguments
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Install with: pip install unsloth trl transformers datasets accelerate bitsandbytes")
        return

    print(f"Loading base model: {args.base_model}")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=args.base_model,
        max_seq_length=args.max_seq,
        dtype=None,         # auto-detect
        load_in_4bit=True,
    )

    # Apply LoRA
    model = FastLanguageModel.get_peft_model(
        model,
        r=args.lora_r,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj",
                        "gate_proj", "up_proj", "down_proj"],
        lora_alpha=args.lora_alpha,
        lora_dropout=0,
        bias="none",
        use_gradient_checkpointing="unsloth",
        random_state=42,
    )

    # Apply chat template
    tokenizer = get_chat_template(tokenizer, chat_template="llama-3")

    def format_example(examples):
        convos = examples["messages"]
        texts = [
            tokenizer.apply_chat_template(c, tokenize=False, add_generation_prompt=False)
            for c in convos
        ]
        return {"text": texts}

    print(f"Loading dataset: {args.data}")
    dataset = load_dataset("json", data_files=args.data, split="train")
    dataset = dataset.map(format_example, batched=True)

    trainer = SFTTrainer(
        model=model,
        tokenizer=tokenizer,
        train_dataset=dataset,
        dataset_text_field="text",
        max_seq_length=args.max_seq,
        dataset_num_proc=2,
        packing=False,
        args=TrainingArguments(
            per_device_train_batch_size=args.batch,
            gradient_accumulation_steps=args.grad_accum,
            warmup_steps=50,
            max_steps=args.max_steps,
            num_train_epochs=args.epochs,
            learning_rate=args.lr,
            fp16=True,
            logging_steps=25,
            optim="adamw_8bit",
            weight_decay=0.01,
            lr_scheduler_type="cosine",
            seed=42,
            output_dir="train/checkpoints",
            save_steps=500,
            save_total_limit=2,
        ),
    )

    print("Training...")
    trainer.train()

    print(f"Saving adapter to {args.output}")
    model.save_pretrained(args.output)
    tokenizer.save_pretrained(args.output)
    print("Done.")


if __name__ == "__main__":
    main()
