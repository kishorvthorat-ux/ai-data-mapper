import os
import json
import pandas as pd
from dotenv import load_dotenv
from openai import OpenAI

from mapper import generate_ai_mappings, hitl_review_loop
from registry import apply_mappings

# 1. Setup Environment
load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

# 2. Define Schemas & Mock Data
SOURCE_SCHEMA = {
    "fields": [
        {"name": "cust_fname", "type": "string"},
        {"name": "cust_lname", "type": "string"},
        {"name": "status_code", "type": "string", "notes": "Values: 1 for Active, 0 for Inactive"}
    ]
}

TARGET_SCHEMA = {
    "fields": [
        {"name": "full_name", "type": "string", "mandatory": True},
        {"name": "account_status", "type": "string", "mandatory": True, "allowed_values": ["Active", "Inactive"]},
        {"name": "currency", "type": "string", "mandatory": True} # Missing from source entirely
    ]
}

MOCK_SOURCE_DATA = pd.DataFrame({
    "cust_fname": ["John", "Jane", "Alice"],
    "cust_lname": ["Doe", "Smith", "Johnson"],
    "status_code": ["1", "0", "1"]
})

def run_pipeline():
    # Step 1: AI generates rules
    ai_rules = generate_ai_mappings(client, SOURCE_SCHEMA, TARGET_SCHEMA)
    
    # Step 2: Human-in-the-Loop Validation
    final_rules = hitl_review_loop(ai_rules, TARGET_SCHEMA)
    
    # Save the approved mapping configuration
    with open("final_mapping_rules.json", "w") as f:
        json.dump(final_rules, f, indent=2)
    print("\n✅ Final mapping rules saved to 'final_mapping_rules.json'")
    
    # Step 3: Execute Rules Securely against Pandas Dataframe
    print("\n⚙️ Executing mappings against source data...")
    df_target = apply_mappings(MOCK_SOURCE_DATA, final_rules)
    
    print("\n🎉 TARGET DATAFRAME GENERATED SUCCESSFULLY:")
    print("="*50)
    print(df_target.to_markdown())
    print("="*50)

if __name__ == "__main__":
    run_pipeline()