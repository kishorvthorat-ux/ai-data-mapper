import json
from openai import OpenAI
from schemas import MappingResult, FieldMapping
from typing import List, Dict

def generate_ai_mappings(client: OpenAI, source_schema: dict, target_schema: dict) -> List[FieldMapping]:
    """Calls OpenAI to generate the initial mapping DSL."""
    
    prompt = f"""
    You are an expert data engineer. Map the Source Schema to the Target Schema.
    Return a configuration using only the allowed transformation types (direct, enum_map, concat, static_default).
    If a field has no logical match, set type to 'unmapped'.
    
    Source Schema: {json.dumps(source_schema)}
    Target Schema: {json.dumps(target_schema)}
    """
    
    print("🤖 AI is analyzing schemas and generating mapping rules...")
    response = client.beta.chat.completions.parse(
        model="gpt-4o-2024-08-06", # Ensure model supports strict Structured Outputs
        messages=[
            {"role": "system", "content": "You are a precise data migration mapping engine."},
            {"role": "user", "content": prompt}
        ],
        response_format=MappingResult,
        temperature=0.0
    )
    
    return response.choices[0].message.parsed.mappings


def hitl_review_loop(ai_mappings: List[FieldMapping], target_schema: dict) -> List[Dict]:
    """Iterates through AI mappings, forcing user input on low-confidence or unmapped mandatory fields."""
    
    final_mappings = []
    target_meta = {f["name"]: f for f in target_schema["fields"]}
    
    print("\n" + "="*50)
    print(" 🧑‍💻 STARTING HUMAN-IN-THE-LOOP REVIEW")
    print("="*50)
    
    for mapping in ai_mappings:
        meta = target_meta.get(mapping.target_field, {})
        is_mandatory = meta.get("mandatory", False)
        needs_review = False
        reason = ""
        
        # Guardrail logic
        if is_mandatory and mapping.transformation_type == "unmapped":
            needs_review = True
            reason = "MANDATORY target field is missing a source match."
        elif mapping.confidence_score < 0.85:
            needs_review = True
            reason = f"Low AI confidence ({mapping.confidence_score})."
            
        if needs_review:
            print(f"\n⚠️  [REVIEW REQUIRED] Target Field: '{mapping.target_field}' (Mandatory: {is_mandatory})")
            print(f"Reason: {reason}")
            print(f"AI Suggestion: {mapping.transformation_type} | Params: {mapping.parameters}")
            print(f"Logic: {mapping.logic_description}")
            
            action = input("Action -> (A)ccept, (D)efault Static Value, (M)anual Edit col mapping, (S)kip: ").strip().upper()
            
            if action == 'D':
                val = input(f"Enter static default value for '{mapping.target_field}': ")
                mapping.transformation_type = "static_default"
                mapping.parameters = {"value": val}
                final_mappings.append(mapping.model_dump())
                
            elif action == 'M':
                col = input("Enter true Source Column name to map directly: ")
                mapping.transformation_type = "direct"
                mapping.parameters = {"source_col": col}
                final_mappings.append(mapping.model_dump())
                
            elif action == 'A' and mapping.transformation_type != "unmapped":
                final_mappings.append(mapping.model_dump())
            else:
                print(f"Skipping {mapping.target_field}...")
        else:
            # Auto-approve
            final_mappings.append(mapping.model_dump())
            
    return final_mappings