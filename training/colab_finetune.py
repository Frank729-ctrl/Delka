# DelkaAI — LoRA Fine-Tuning Script
# Run this on Google Colab with a T4 GPU runtime.
#
# Before running:
#   1. Export training data:
#      curl "http://localhost:8000/v1/admin/training/export?min_rating=4&format=jsonl" \
#           -H "X-DelkaAI-Master-Key: YOUR_KEY" --output delkaai_training_data.jsonl
#   2. Upload delkaai_training_data.jsonl to Colab (Files panel → Upload)
#   3. Runtime → Change runtime type → T4 GPU
#   4. Run cells top to bottom

# ─── Cell 1 — Install dependencies ───────────────────────────────────────────

# !pip install unsloth
# !pip install transformers datasets trl peft bitsandbytes

# ─── Cell 2 — Load base model (QLoRA 4-bit) ──────────────────────────────────

from unsloth import FastLanguageModel
import torch

model, tokenizer = FastLanguageModel.from_pretrained(
    model_name="unsloth/llama-3.1-8b-bnb-4bit",
    max_seq_length=4096,
    dtype=None,
    load_in_4bit=True,    # QLoRA — fits in 8 GB VRAM
)

print("✅ Base model loaded")

# ─── Cell 3 — Add LoRA adapters ───────────────────────────────────────────────

model = FastLanguageModel.get_peft_model(
    model,
    r=16,
    target_modules=[
        "q_proj", "k_proj", "v_proj", "o_proj",
        "gate_proj", "up_proj", "down_proj",
    ],
    lora_alpha=16,
    lora_dropout=0,
    bias="none",
    use_gradient_checkpointing="unsloth",
    random_state=42,
)

print("✅ LoRA adapters added")
print(f"Trainable parameters: {sum(p.numel() for p in model.parameters() if p.requires_grad):,}")

# ─── Cell 4 — Load training data ──────────────────────────────────────────────

from datasets import load_dataset

dataset = load_dataset(
    "json",
    data_files="/content/delkaai_training_data.jsonl",
    split="train",
)


def format_training_example(example):
    """Format each example as a chat-style instruction string."""
    return {
        "text": f"<s>[INST] {example['prompt']} [/INST] {example['completion']} </s>"
    }


dataset = dataset.map(format_training_example)
print(f"✅ Dataset loaded: {len(dataset)} examples")

# ─── Cell 5 — Train ───────────────────────────────────────────────────────────

from trl import SFTTrainer
from transformers import TrainingArguments

trainer = SFTTrainer(
    model=model,
    tokenizer=tokenizer,
    train_dataset=dataset,
    dataset_text_field="text",
    max_seq_length=4096,
    dataset_num_proc=2,
    packing=False,
    args=TrainingArguments(
        per_device_train_batch_size=2,
        gradient_accumulation_steps=4,
        warmup_steps=5,
        num_train_epochs=3,
        learning_rate=2e-4,
        fp16=not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_bf16_supported(),
        logging_steps=10,
        output_dir="outputs",
        optim="adamw_8bit",
        weight_decay=0.01,
        lr_scheduler_type="linear",
        seed=42,
        report_to="none",
    ),
)

print("🚀 Starting training...")
trainer_stats = trainer.train()
print(f"✅ Training complete in {trainer_stats.metrics['train_runtime']:.0f}s")

# ─── Cell 6 — Quick test ──────────────────────────────────────────────────────

FastLanguageModel.for_inference(model)

test_prompt = (
    "Generate a professional CV summary for:\n"
    "Name: Kofi Mensah\n"
    "Role: Software Engineer\n"
    "Experience: 3 years at MTN Ghana building mobile payment systems"
)

inputs = tokenizer(
    f"<s>[INST] {test_prompt} [/INST]",
    return_tensors="pt",
).to("cuda")

outputs = model.generate(**inputs, max_new_tokens=200, temperature=0.7)
print("\n📄 Test output:")
print(tokenizer.decode(outputs[0], skip_special_tokens=True))

# ─── Cell 7 — Save & download ─────────────────────────────────────────────────

model.save_pretrained("delkaai-lora-adapter")
tokenizer.save_pretrained("delkaai-lora-adapter")
print("✅ Adapter saved")

import shutil
shutil.make_archive("delkaai-lora-adapter", "zip", "delkaai-lora-adapter")
print("✅ delkaai-lora-adapter.zip ready — download from Files panel")

# ─── After downloading: deploy to your server ────────────────────────────────
#
# 1. Upload and unzip on server:
#      scp delkaai-lora-adapter.zip user@server:/opt/delkaai/
#      cd /opt/delkaai && unzip delkaai-lora-adapter.zip
#
# 2. Create Ollama Modelfile:
#      cat > Modelfile << 'EOF'
#      FROM llama3.1:8b
#      ADAPTER ./delkaai-lora-adapter
#      SYSTEM """You are DelkaAI, a professional AI assistant trained specifically
#      on high-quality document generation and conversation for Ghanaian professionals
#      and businesses. You understand Ghanaian context, local employers, institutions,
#      and cultural nuances."""
#      EOF
#
# 3. Register model with Ollama:
#      ollama create delkaai-cv-v1 -f Modelfile
#      ollama run delkaai-cv-v1 "Test prompt"
#
# 4. Enable A/B test in .env:
#      AB_TEST_ENABLED=true
#      AB_TEST_MODEL_B_MODEL=delkaai-cv-v1
#
# 5. After 200+ rated samples per group, check winner:
#      curl http://localhost:8000/v1/admin/ab-results?task=cv \
#           -H "X-DelkaAI-Master-Key: YOUR_KEY"
#
# 6. If model_b wins, promote:
#      CV_PRIMARY_PROVIDER=ollama
#      CV_PRIMARY_MODEL=delkaai-cv-v1
#      AB_TEST_ENABLED=false
