import json
from google import genai
from google.genai import types
from schemas import MappingResult
from typing import List, Dict

def generate_ai_mappings(client: genai.Client, source_schema: dict, target_schema: dict) -> List[Dict]:
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
        model='gemini-1.5-flash', # Try gemini-1.5-flash if 2.0 also throws an error
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MappingResult,
            temperature=0.0,
            system_instruction="You are a precise data migration mapping engine."
        )
    )
    
    raw_mappings = response.parsed.mappings
    final_mappings = []
    
    # Safely convert the JSON string back into the dictionary our app expects
    for mapping in raw_mappings:
        m_dict = mapping.model_dump()
        try:
            m_dict["parameters"] = json.loads(m_dict["parameters_json"])
        except Exception as e:
            print(f"Failed to parse params for {m_dict['target_field']}: {e}")
            m_dict["parameters"] = {}
            
        # Clean up the temporary json string field
        del m_dict["parameters_json"]
        final_mappings.append(m_dict)
        
    return final_mappings
