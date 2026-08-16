import json
from typing import List, Dict
from google import genai
from google.genai import types
from schemas import MappingResult

def generate_ai_mappings(client: genai.Client, source_schema: dict, target_schema: dict) -> List[Dict]:
    prompt = f"""
    You are an expert data migration and ETL engineer. 
    Analyze the source schema and target schema below and generate robust transformation mapping rules.

    Source Schema:
    {json.dumps(source_schema, indent=2)}

    Target Schema:
    {json.dumps(target_schema, indent=2)}

    For each target field, determine the best transformation type ('direct', 'enum_map', 'concat', 'static_default', 'calculated', 'regex', or 'unmapped') and provide its parameters inside 'parameters_json'.
    """

    response = client.models.generate_content(
        model='gemini-2.5-flash',
        contents=prompt,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=MappingResult,
            temperature=0.1
        ),
    )

    try:
        data = json.loads(response.text)
        parsed_mappings = []
        raw_mappings = data.get("mappings", data) if isinstance(data, dict) else data
        
        for m in raw_mappings:
            params_str = m.get("parameters_json", "{}")
            if isinstance(params_str, str):
                try:
                    params = json.loads(params_str)
                except json.JSONDecodeError:
                    params = {}
            else:
                params = params_str if isinstance(params_str, dict) else {}

            parsed_mappings.append({
                "target_field": m.get("target_field"),
                "transformation_type": m.get("transformation_type", "unmapped"),
                "parameters": params,
                "logic_description": m.get("logic_description", ""),
                "confidence_score": m.get("confidence_score", 1.0)
            })
        return parsed_mappings
    except Exception as e:
        print(f"Error parsing Gemini response: {e}")
        return []
