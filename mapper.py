import json
import time
from google import genai
from google.genai import types
from schemas import MappingResult
from typing import List, Dict

def generate_ai_mappings(client: genai.Client, source_schema: dict, target_schema: dict) -> List[Dict]:
    """Calls Google Gemini to generate the initial mapping DSL with automatic retries."""
    
    prompt = f"""
    You are an expert data engineer. Map the Source Schema to the Target Schema.
    Return a configuration using only the allowed transformation types (direct, enum_map, concat, static_default).
    If a field has no logical match, set type to 'unmapped'.
    
    Source Schema: {json.dumps(source_schema)}
    Target Schema: {json.dumps(target_schema)}
    """
    
    print("🤖 Gemini AI is analyzing schemas...")
    
    max_retries = 3
    retry_delay = 3  # seconds to wait before retrying
    
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model='gemini-3.5-flash-lite',
                contents=prompt,
                config=types.GenerateContentConfig(
                    response_mime_type="application/json",
                    response_schema=MappingResult,
                    temperature=0.0,
                    system_instruction="You are a precise data migration mapping engine."
                )
            )
            break  # If successful, exit the retry loop
            
        except Exception as e:
            error_msg = str(e)
            # Catch 503 Overloaded Errors
            if "503" in error_msg or "UNAVAILABLE" in error_msg:
                if attempt < max_retries - 1:
                    print(f"⚠️ Gemini API overloaded (503). Retrying in {retry_delay} seconds... (Attempt {attempt + 1} of {max_retries})")
                    time.sleep(retry_delay)
                    continue
            
            # If it's a different error (like Auth) or we run out of retries, crash gracefully
            raise Exception(f"Gemini API failed after {attempt + 1} attempts. Original Error: {error_msg}")

    
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
            
        del m_dict["parameters_json"]
        final_mappings.append(m_dict)
        
    return final_mappings
