import os
import hmac
import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai

from mapper import generate_ai_mappings
from registry import apply_mappings

# 1. Page Configuration (Must be the first Streamlit command)
st.set_page_config(
    page_title="AI Data Mapping & HITL Governance",
    page_icon="🔒",
    layout="wide"
)

load_dotenv()

# 2. Password Protection Gate
def check_password() -> bool:
    expected_password = st.secrets.get("APP_PASSWORD", os.getenv("APP_PASSWORD", "admin123"))

    def login_form():
        col1, col2, col3 = st.columns([1, 1.2, 1])
        with col2:
            st.markdown("### 🔒 Protected Application")
            st.info("Please enter the password to access the AI Data Mapping Tool.")
            
            with st.form("login_form"):
                password = st.text_input("Password", type="password")
                submit = st.form_submit_button("Log In", use_container_width=True)
                
                if submit:
                    if hmac.compare_digest(password, expected_password):
                        st.session_state["authenticated"] = True
                        st.rerun()
                    else:
                        st.error("❌ Incorrect password. Please try again.")

    if not st.session_state.get("authenticated", False):
        login_form()
        return False
    return True

if not check_password():
    st.stop()


# -------------------------------------------------------------
# EVERYTHING BELOW ONLY RUNS FOR AUTHENTICATED USERS
# -------------------------------------------------------------

# 3. Mock Default Schemas & Data (Fallbacks)
DEFAULT_SOURCE_SCHEMA = {"fields": [{"name": "cust_fname", "type": "string"}, {"name": "cust_lname", "type": "string"}, {"name": "status_code", "type": "string"}]}
DEFAULT_TARGET_SCHEMA = {"fields": [{"name": "full_name", "type": "string", "mandatory": True}, {"name": "account_status", "type": "string", "mandatory": True}]}
DEFAULT_SOURCE_DATA = pd.DataFrame({"cust_fname": ["John", "Jane"], "cust_lname": ["Doe", "Smith"], "status_code": ["1", "0"]})

# 4. Initialize Session State
if "mappings" not in st.session_state:
    st.session_state.mappings = []
if "source_data" not in st.session_state:
    st.session_state.source_data = DEFAULT_SOURCE_DATA
if "target_data_sample" not in st.session_state:
    st.session_state.target_data_sample = None
if "source_schema" not in st.session_state:
    st.session_state.source_schema = DEFAULT_SOURCE_SCHEMA
if "target_schema" not in st.session_state:
    st.session_state.target_schema = DEFAULT_TARGET_SCHEMA

# Helper to load data files (CSV or Excel)
def load_dataframe(file) -> pd.DataFrame:
    if file.name.endswith('.csv'):
        return pd.read_csv(file)
    elif file.name.endswith(('.xls', '.xlsx')):
        return pd.read_excel(file)
    return pd.DataFrame()

# 5. Sidebar Controls, Authentication & Uploaders
with st.sidebar:
    st.title("⚙️ Configuration")
    
    if st.button("🚪 Log Out", use_container_width=True):
        st.session_state["authenticated"] = False
        st.rerun()

    st.divider()
    default_key = st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY", ""))
    api_key = st.text_input("Gemini API Key", value=default_key, type="password")
    
    st.divider()
    st.subheader("📁 1. Upload Files")
    st.caption("Upload schemas (JSON) and sample data (CSV/Excel).")
    
    # Updated to support CSV and Excel
    source_data_file = st.file_uploader("Source Data (CSV/Excel)", type=["csv", "xlsx", "xls"])
    source_schema_file = st.file_uploader("Source Schema (JSON)", type=["json"])
    
    target_schema_file = st.file_uploader("Target Schema (JSON)", type=["json"])
    target_data_file = st.file_uploader("Target Data Sample [Optional] (CSV/Excel)", type=["csv", "xlsx", "xls"], help="Upload a sample of the expected output to compare visually.")
    
    if st.button("Load Uploaded Files", use_container_width=True):
        try:
            if source_data_file:
                st.session_state.source_data = load_dataframe(source_data_file)
            if target_data_file:
                st.session_state.target_data_sample = load_dataframe(target_data_file)
                
            if source_schema_file:
                st.session_state.source_schema = json.load(source_schema_file)
            if target_schema_file:
                st.session_state.target_schema = json.load(target_schema_file)
            
            st.session_state.mappings = [] 
            st.success("Files successfully loaded into memory!")
        except Exception as e:
            st.error(f"Error parsing files: {e}")

    st.divider()
    st.subheader("🤖 2. Run Automation")
    
    if st.button("🚀 Run Gemini Auto-Mapping", type="primary", use_container_width=True):
        if not api_key:
            st.error("Please provide a Gemini API key.")
        else:
            with st.spinner("Gemini is analyzing semantics and proposing mappings..."):
                client = genai.Client(api_key=api_key)
                ai_results = generate_ai_mappings(
                    client, 
                    st.session_state.source_schema, 
                    st.session_state.target_schema
                )
                st.session_state.mappings = [m.model_dump() for m in ai_results]
                st.success("Mapping suggestions generated!")
                st.rerun()

# 6. Main Dashboard Header
st.title("🔄 AI Data Mapping & Business Review")

with st.expander("🔍 View Active Schemas in Memory", expanded=False):
    c_left, c_right = st.columns(2)
    with c_left:
        st.markdown("**Source Schema:**")
        st.json(st.session_state.source_schema)
    with c_right:
        st.markdown("**Target Schema:**")
        st.json(st.session_state.target_schema)

# 7. Overview Metrics
if st.session_state.mappings:
    target_meta = {f["name"]: f for f in st.session_state.target_schema.get("fields", [])}
    total_fields = len(st.session_state.mappings)
    
    unresolved_mandatory = sum(1 for m in st.session_state.mappings 
                             if target_meta.get(m["target_field"], {}).get("mandatory", False) 
                             and m["transformation_type"] == "unmapped")
    low_confidence = sum(1 for m in st.session_state.mappings 
                       if m.get("confidence_score", 1.0) < 0.85 
                       and m["transformation_type"] != "unmapped")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Target Fields", total_fields)
    col2.metric("Auto-Approved", total_fields - unresolved_mandatory - low_confidence)
    col3.metric("Review Needed", low_confidence, delta_color="off")
    col4.metric("Action Required", unresolved_mandatory, delta_color="inverse")

    st.divider()

    # 8. Interactive Human-in-the-Loop Mapping Editor
    st.subheader("🛠️ Target Field Review & Rules Editor")
    
    source_col_options = [f["name"] for f in st.session_state.source_schema.get("fields", [])]
    transform_types = ["direct", "enum_map", "concat", "static_default", "unmapped"]

    for idx, mapping in enumerate(st.session_state.mappings):
        target_name = mapping["target_field"]
        meta = target_meta.get(target_name, {})
        is_mandatory = meta.get("mandatory", False)
        confidence = mapping.get("confidence_score", 1.0)
        
        status_badges = []
        if is_mandatory:
            status_badges.append(":red[**MANDATORY**]")
        if confidence < 0.85 and mapping["transformation_type"] != "unmapped":
            status_badges.append(f":orange[**Low Confidence ({int(confidence*100)}%)**]")
        elif mapping["transformation_type"] == "unmapped":
            status_badges.append(":gray[**Unmapped**]")
        else:
            status_badges.append(f":green[**Confidence: {int(confidence*100)}%**]")

        expander_title = f"{'⚠️ ' if (is_mandatory and mapping['transformation_type'] == 'unmapped') else '✅ '} Target: **{target_name}** | {' | '.join(status_badges)}"
        
        with st.expander(expander_title, expanded=(is_mandatory and mapping['transformation_type'] == "unmapped")):
            st.caption(f"**AI Reasoning:** {mapping.get('logic_description', 'No AI notes available.')}")
            
            c1, c2 = st.columns([1, 2])
            
            with c1:
                selected_type = st.selectbox(
                    "Transformation Type",
                    options=transform_types,
                    index=transform_types.index(mapping["transformation_type"]),
                    key=f"type_{idx}"
                )
                mapping["transformation_type"] = selected_type

            with c2:
                if selected_type == "direct":
                    current_col = mapping["parameters"].get("source_col", source_col_options[0] if source_col_options else "")
                    default_idx = source_col_options.index(current_col) if current_col in source_col_options else 0
                    source_col = st.selectbox("Source Column", options=source_col_options, index=default_idx, key=f"col_{idx}")
                    mapping["parameters"] = {"source_col": source_col}
                    
                elif selected_type == "static_default":
                    val = st.text_input("Static Default Value", value=str(mapping["parameters"].get("value", "")), key=f"static_{idx}")
                    mapping["parameters"] = {"value": val}
                    
                elif selected_type == "concat":
                    curr_cols = mapping["parameters"].get("source_cols", [])
                    cols = st.multiselect("Source Columns", options=source_col_options, default=[c for c in curr_cols if c in source_col_options], key=f"concat_{idx}")
                    delim = st.text_input("Delimiter", value=mapping["parameters"].get("delimiter", " "), key=f"delim_{idx}")
                    mapping["parameters"] = {"source_cols": cols, "delimiter": delim}
                    
                elif selected_type == "enum_map":
                    curr_col = mapping["parameters"].get("source_col", source_col_options[0] if source_col_options else "")
                    default_idx = source_col_options.index(curr_col) if current_col in source_col_options else 0
                    source_col = st.selectbox("Source Column to Map", options=source_col_options, index=default_idx, key=f"enum_col_{idx}")
                    
                    enum_dict = mapping["parameters"].get("mapping", {})
                    enum_str = st.text_area("JSON Mapping Dictionary", value=json.dumps(enum_dict, indent=2), key=f"enum_map_{idx}", height=100)
                    try:
                        parsed_map = json.loads(enum_str)
                        mapping["parameters"] = {"source_col": source_col, "mapping": parsed_map}
                    except json.JSONDecodeError:
                        st.error("Invalid JSON format for enum mapping.")
                        
                elif selected_type == "unmapped":
                    mapping["parameters"] = {}
                    if is_mandatory:
                        st.warning("⚠️ Mandatory field. Please select a transformation or set a static default.")

    st.divider()

    # 9. Live Preview & Download
    st.subheader("👀 Live Execution Preview")
    
    st.markdown("**Source Data Preview:**")
    st.dataframe(st.session_state.source_data.head(10), use_container_width=True)
    
    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("**Transformed Output (Live):**")
        try:
            df_preview = apply_mappings(st.session_state.source_data, st.session_state.mappings)
            st.dataframe(df_preview.head(10), use_container_width=True)
        except Exception as e:
            st.error(f"Execution Error: {e}")
            
    with col_right:
        st.markdown("**Target Data Sample (Expected):**")
        if st.session_state.target_data_sample is not None:
            st.dataframe(st.session_state.target_data_sample.head(10), use_container_width=True)
        else:
            st.info("No target data sample uploaded. Upload in sidebar to compare side-by-side.")

    st.download_button(
        label="💾 Download Approved Mapping Rules (JSON)",
        data=json.dumps(st.session_state.mappings, indent=2),
        file_name="final_mapping_rules.json",
        mime="application/json",
        type="primary"
    )

else:
    st.info("👈 Upload your files in the sidebar and click **Run Gemini Auto-Mapping** to begin.")
