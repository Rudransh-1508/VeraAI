#!/usr/bin/env python3
"""
Generate submission.jsonl with 30 test messages.
This will be submitted along with bot.py and README.md.
"""

import asyncio
import json
from datetime import datetime, timezone

from context_store import ContextStore
from conversation import ConversationStore
from suppression import SuppressionStore
from composer import ThreePassComposer
from llm_client import LLMClient
from models import ContextPush


async def generate_message(composer, trigger_id, merchant_id):
    """Generate a single message for submission."""
    now_iso = datetime.now(timezone.utc).isoformat()
    
    try:
        action = await composer.compose_proactive(trigger_id, now_iso)
        
        if action:
            return {
                "merchant_id": merchant_id,
                "trigger_id": trigger_id,
                "body": action.body,
                "cta": action.cta,
                "template_name": action.template_name,
                "rationale": action.rationale
            }
        else:
            return None
            
    except Exception as e:
        print(f"Error generating message for {trigger_id}: {e}")
        return None


async def main():
    """Generate 30 test messages for submission."""
    print("🚀 Generating submission.jsonl")
    print("=" * 60)
    
    # Initialize components with validation enabled but reduced retries
    ctx = ContextStore()
    convs = ConversationStore()
    suppression = SuppressionStore()
    llm = LLMClient()
    composer = ThreePassComposer(
        llm, ctx, convs, suppression,
        enable_validation=True,
        max_retries=1  # Reduced from 2 to save API quota
    )
    
    # Load dataset
    print("📂 Loading dataset...")
    with open("../magicpin-ai-challenge/dataset/merchants_seed.json") as f:
        merchants_data = json.load(f)
        merchants = merchants_data.get("merchants", [])
    
    with open("../magicpin-ai-challenge/dataset/triggers_seed.json") as f:
        triggers_data = json.load(f)
        triggers = triggers_data.get("triggers", [])
    
    with open("../magicpin-ai-challenge/dataset/customers_seed.json") as f:
        customers_data = json.load(f)
        customers = customers_data.get("customers", [])
    
    # Load categories
    categories = {}
    for cat_name in ["dentists", "salons", "gyms", "restaurants", "pharmacies"]:
        with open(f"../magicpin-ai-challenge/dataset/categories/{cat_name}.json") as f:
            cat_data = json.load(f)
            categories[cat_data["slug"]] = cat_data
    
    # Push contexts
    print("📤 Pushing contexts...")
    now_iso = datetime.now(timezone.utc).isoformat()
    
    for cat_slug, cat_data in categories.items():
        ctx.push(ContextPush(
            scope="category",
            context_id=cat_slug,
            version=1,
            payload=cat_data,
            delivered_at=now_iso
        ))
    
    for m in merchants:
        ctx.push(ContextPush(
            scope="merchant",
            context_id=m["merchant_id"],
            version=1,
            payload=m,
            delivered_at=now_iso
        ))
    
    for c in customers:
        ctx.push(ContextPush(
            scope="customer",
            context_id=c["customer_id"],
            version=1,
            payload=c,
            delivered_at=now_iso
        ))
    
    for t in triggers:
        # Normalize trigger_id field
        if "id" in t and "trigger_id" not in t:
            t["trigger_id"] = t["id"]
        ctx.push(ContextPush(
            scope="trigger",
            context_id=t["trigger_id"],
            version=1,
            payload=t,
            delivered_at=now_iso
        ))
    
    print(f"✅ Loaded {len(merchants)} merchants, {len(triggers)} triggers, {len(customers)} customers")
    
    # Select 30 diverse triggers (6 per category)
    selected_triggers = []
    
    # Group triggers by category
    triggers_by_category = {}
    for t in triggers:
        merchant_id = t.get("merchant_id")
        if merchant_id:
            merchant = ctx.get("merchant", merchant_id)
            if merchant:
                cat_slug = merchant.get("category_slug")
                if cat_slug not in triggers_by_category:
                    triggers_by_category[cat_slug] = []
                triggers_by_category[cat_slug].append(t)
    
    # Select 6 triggers per category (or all if less than 6)
    for cat_slug, cat_triggers in triggers_by_category.items():
        selected = cat_triggers[:6]  # Take first 6
        selected_triggers.extend(selected)
    
    print(f"\n📝 Generating {len(selected_triggers)} messages...")
    print("=" * 60)
    
    results = []
    
    for i, trigger in enumerate(selected_triggers, 1):
        trigger_id = trigger.get("trigger_id") or trigger.get("id")
        merchant_id = trigger.get("merchant_id")
        
        print(f"\n[{i}/{len(selected_triggers)}] {trigger_id}")
        
        result = await generate_message(composer, trigger_id, merchant_id)
        
        if result:
            results.append(result)
            print(f"✅ Generated: {result['body'][:60]}...")
        else:
            print(f"⚠️ Skipped (no action)")
        
        # Small delay to avoid rate limiting
        await asyncio.sleep(1)
    
    # Write to submission.jsonl
    output_file = "submission.jsonl"
    with open(output_file, "w") as f:
        for result in results:
            # Write only the required fields
            submission_entry = {
                "merchant_id": result["merchant_id"],
                "trigger_id": result["trigger_id"],
                "body": result["body"]
            }
            f.write(json.dumps(submission_entry, ensure_ascii=False) + "\n")
    
    print("\n" + "=" * 60)
    print(f"✅ Generated {len(results)} messages")
    print(f"📄 Saved to: {output_file}")
    print("=" * 60)
    
    # Summary by category
    category_counts = {}
    for result in results:
        merchant_id = result["merchant_id"]
        merchant = ctx.get("merchant", merchant_id)
        if merchant:
            cat_slug = merchant.get("category_slug", "unknown")
            category_counts[cat_slug] = category_counts.get(cat_slug, 0) + 1
    
    print("\n📊 Messages by Category:")
    for cat_slug, count in sorted(category_counts.items()):
        print(f"  {cat_slug}: {count} messages")
    
    print(f"\n🎯 Total: {len(results)} messages")
    print(f"📁 File: {output_file}")
    print("\n✅ Ready for submission!")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
