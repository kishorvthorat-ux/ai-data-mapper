import json
from google import genai
from google.genai import types
from schemas import MappingResult, FieldMapping
from typing import List

def generate_ai_mappings(client: genai.Client, source_schema: dict, target_schema: dict) -> List[FieldMapping]:
    """Calls Google Gemini to generate the initial mapping DSL."""
    
    prompt = f"""
    You are an expert data engineer. Map the Source Schema to the Target Schema.
    Return a configuration using only the allowed transformation types (direct, enum_map, concat, static_default).
    If a field has no logical match, set type to 'unmapped'.
    
    Source Schema: {json.dumps(source_schema)}
    Target Schema: {json.dumps(target_schema)}
    """
    
    print("🤖 Gemini AI is analyzing schemas...")
    
    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MappingResult,
            temperature=0.0,
            system_instruction="You are a precise data migration mapping engine."
        )
    )
    
    # Gemini parses Pydantic outputs directly into the .parsed property
    return response.parsed.mappings
