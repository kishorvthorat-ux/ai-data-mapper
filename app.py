import os
import hmac
import json
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai

from mapper import generate_ai_mappings
from registry import apply_mappings

# 1. Page Configuration
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
# AUTHENTICATED USER SESSION
# -------------------------------------------------------------

# 3. Default Schemas & Data (Fallbacks)
DEFAULT_SOURCE_SCHEMA = {"fields": [{"name": "cust_fname", "type": "string"}, {"name": "cust_lname", "type": "string"}, {"name": "status_code", "type": "string"}, {"name": "dept_id", "type": "string"}]}
DEFAULT_TARGET_SCHEMA = {"fields": [{"name": "full_name", "type": "string", "mandatory": True}, {"name": "account_status", "type": "string", "mandatory": True}, {"name": "currency", "type": "string", "mandatory": True}, {"name": "country_origin", "type": "string", "mandatory": False}]}
DEFAULT_SOURCE_DATA = pd.DataFrame({"cust_fname": ["John", "Jane"], "cust_lname": ["Doe", "Smith"], "status_code": ["1", "0"], "dept_id": ["D101", "D102"]})

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

def load_dataframe(file) -> pd.DataFrame:
    if file.name.endswith('.csv'):
        return pd.read_csv(file)
    elif file.name.endswith(('.xls', '.xlsx')):
        return pd.read_excel(file)
    return pd.DataFrame()

# 5. Sidebar Controls
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
    
    source_data_file = st.file_uploader("Source Data (CSV/Excel)", type=["csv", "xlsx", "xls"])
    source_schema_file = st.file_uploader("Source Schema (JSON)", type=["json"])
    target_schema_file = st.file_uploader("Target Schema (JSON)", type=["json"])
    target_data_file = st.file_uploader("Target Data Sample [Optional]", type=["csv", "xlsx", "xls"])
    
    if st.button("Load Uploaded Files", use_container_width=True):
        try:
            if source_data_file: st.session_state.source_data = load_dataframe(source_data_file)
            if target_data_file: st.session_state.target_data_sample = load_dataframe(target_data_file)
            if source_schema_file: st.session_state.source_schema = json.load(source_schema_file)
            if target_schema_file: st.session_state.target_schema = json.load(target_schema_file)
            
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
            with st.spinner("Gemini is analyzing semantics..."):
                client = genai.Client(api_key=api_key)
                ai_results = generate_ai_mappings(
                    client, 
                    st.session_state.source_schema, 
                    st.session_state.target_schema
                )
                st.session_state.mappings = ai_results
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

# 7. Metrics & Source/Target Analysis
if st.session_state.mappings:
    target_meta = {f["name"]: f for f in st.session_state.target_schema.get("fields", [])}
    total_fields = len(st.session_state.mappings)
    
    # Identify Unmatched Target Fields
    unmatched_target_mappings = [m for m in st.session_state.mappings if m["transformation_type"] == "unmapped"]
    unresolved_mandatory = sum(1 for m in unmatched_target_mappings if target_meta.get(m["target_field"], {}).get("mandatory", False))
    low_confidence = sum(1 for m in st.session_state.mappings if m.get("confidence_score", 1.0) < 0.85 and m["transformation_type"] != "unmapped")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Target Fields", total_fields)
    col2.metric("Mapped / Approved", total_fields - len(unmatched_target_mappings))
    col3.metric("Review Needed", low_confidence, delta_color="off")
    col4.metric("Unmatched (Mandatory)", unresolved_mandatory, delta_color="inverse")
    st.divider()

    # Determine source column pool
    if st.session_state.source_data is not None and not st.session_state.source_data.empty:
        all_sources = st.session_state.source_data.columns.tolist()
    else:
        all_sources = [f["name"] for f in st.session_state.source_schema.get("fields", [])]

    # Track which source columns are currently mapped
    mapped_sources = set()
    for m in st.session_state.mappings:
        if m["transformation_type"] in ["direct", "enum_map"]:
            mapped_sources.add(m["parameters"].get("source_col"))
        elif m["transformation_type"] == "concat":
            mapped_sources.update(m["parameters"].get("source_cols", []))
            
    unused_sources = [s for s in all_sources if s not in mapped_sources]

    # 8. TABS: Tab 1 (Quick Unmatched Resolver), Tab 2 (All Mappings), Tab 3 (New Custom Field)
    tab_unmatched, tab_all, tab_custom = st.tabs([
        f"⚡ Unmatched Target Resolver ({len(unmatched_target_mappings)})",
        "📋 All Active Mappings",
        "➕ Add Custom Target Field"
    ])

    # -------------------------------------------------------------
    # TAB 1: QUICK UNMATCHED RESOLVER (STATIC VALUE & SOURCE BINDING)
    # -------------------------------------------------------------
    with tab_unmatched:
        st.subheader("⚡ Quick Resolution for Unmatched Target Fields")
        st.markdown("Resolve target fields that the AI left unmapped by assigning **static/default values** or linking them directly to available source columns.")
        
        if unused_sources:
            st.info(f"💡 **Unused Source Columns Available:** `{', '.join(unused_sources)}`")

        if not unmatched_target_mappings:
            st.success("🎉 All target fields have an assigned mapping or static value!")
        else:
            for idx, mapping in enumerate(st.session_state.mappings):
                if mapping["transformation_type"] != "unmapped":
                    continue
                
                target_name = mapping["target_field"]
                meta = target_meta.get(target_name, {})
                is_mandatory = meta.get("mandatory", False)
                
                with st.container(border=True):
                    c_title, c_badge = st.columns([3, 1])
                    with c_title:
                        st.markdown(f"#### Target: `{target_name}`")
                    with c_badge:
                        if is_mandatory:
                            st.markdown(":red[**MANDATORY FIELD**]")
                        else:
                            st.markdown(":gray[Optional Field]")

                    st.caption(f"**AI Note:** {mapping.get('logic_description', 'No direct semantic match found in source.')}")
                    
                    # Quick Choice: Static Value vs Map to Source Column
                    resolve_mode = st.radio(
                        f"How would you like to populate '{target_name}'?",
                        ["Set Static / Constant Default Value", "Map to Source Column", "Enum / Value Translation", "Combine (Concat) Columns"],
                        key=f"unmatched_mode_{idx}",
                        horizontal=True
                    )
                    
                    c_input, c_action = st.columns([3, 1])
                    
                    # Option 1: Static Value
                    if resolve_mode == "Set Static / Constant Default Value":
                        with c_input:
                            static_val = st.text_input(
                                f"Enter Static Value for '{target_name}':",
                                placeholder="e.g. USD, 0, NA, Active, Internal",
                                key=f"quick_static_{idx}"
                            )
                        with c_action:
                            st.write("") # vertical spacing
                            st.write("")
                            if st.button("Apply Static Value", key=f"btn_apply_static_{idx}", type="primary"):
                                if not static_val:
                                    st.warning("Please type a static value first.")
                                else:
                                    mapping["transformation_type"] = "static_default"
                                    mapping["parameters"] = {"value": static_val}
                                    mapping["logic_description"] = f"User assigned static value: '{static_val}'"
                                    mapping["confidence_score"] = 1.0
                                    st.success(f"Applied static value '{static_val}' to '{target_name}'!")
                                    st.rerun()

                    # Option 2: Map to Source Column
                    elif resolve_mode == "Map to Source Column":
                        with c_input:
                            col_to_map = st.selectbox(
                                "Select Source Column to link:",
                                options=all_sources,
                                key=f"quick_src_col_{idx}"
                            )
                            # Show preview sample of what this column holds
                            if st.session_state.source_data is not None and col_to_map in st.session_state.source_data.columns:
                                sample_vals = st.session_state.source_data[col_to_map].dropna().head(3).tolist()
                                st.caption(f"Sample data in `{col_to_map}`: {sample_vals}")
                                
                        with c_action:
                            st.write("")
                            st.write("")
                            if st.button("Apply Direct Map", key=f"btn_apply_src_{idx}", type="primary"):
                                mapping["transformation_type"] = "direct"
                                mapping["parameters"] = {"source_col": col_to_map}
                                mapping["logic_description"] = f"User mapped directly to '{col_to_map}'"
                                mapping["confidence_score"] = 1.0
                                st.success(f"Mapped `{target_name}` to `{col_to_map}`!")
                                st.rerun()

                    # Option 3: Enum Map
                    elif resolve_mode == "Enum / Value Translation":
                        with c_input:
                            enum_src = st.selectbox("Source Column:", all_sources, key=f"quick_enum_src_{idx}")
                            enum_json = st.text_area("Translation Map (JSON):", value='{"OldVal": "NewVal"}', key=f"quick_enum_map_{idx}", height=80)
                        with c_action:
                            st.write("")
                            st.write("")
                            if st.button("Apply Enum Map", key=f"btn_apply_enum_{idx}", type="primary"):
                                try:
                                    mapping["transformation_type"] = "enum_map"
                                    mapping["parameters"] = {"source_col": enum_src, "mapping": json.loads(enum_json)}
                                    mapping["confidence_score"] = 1.0
                                    st.success(f"Configured translation for `{target_name}`!")
                                    st.rerun()
                                except json.JSONDecodeError:
                                    st.error("Invalid JSON format.")

                    # Option 4: Concat
                    elif resolve_mode == "Combine (Concat) Columns":
                        with c_input:
                            concat_cols = st.multiselect("Select Columns to combine (in order):", all_sources, key=f"quick_concat_cols_{idx}")
                            delim = st.text_input("Delimiter:", value=" ", key=f"quick_delim_{idx}")
                        with c_action:
                            st.write("")
                            st.write("")
                            if st.button("Apply Concat", key=f"btn_apply_concat_{idx}", type="primary"):
                                if not concat_cols:
                                    st.warning("Select at least one column.")
                                else:
                                    mapping["transformation_type"] = "concat"
                                    mapping["parameters"] = {"source_cols": concat_cols, "delimiter": delim}
                                    mapping["confidence_score"] = 1.0
                                    st.success(f"Configured concat for `{target_name}`!")
                                    st.rerun()

    # -------------------------------------------------------------
    # TAB 2: ALL ACTIVE MAPPINGS (IN-PLACE EDITOR)
    # -------------------------------------------------------------
    with tab_all:
        st.subheader("📋 Comprehensive Rules Editor")
        transform_types = ["direct", "enum_map", "concat", "static_default", "unmapped"]

        for idx, mapping in enumerate(st.session_state.mappings):
            target_name = mapping["target_field"]
            meta = target_meta.get(target_name, {})
            is_mandatory = meta.get("mandatory", False)
            confidence = mapping.get("confidence_score", 1.0)
            
            status_badges = []
            if is_mandatory: status_badges.append(":red[**MANDATORY**]")
            if confidence < 0.85 and mapping["transformation_type"] != "unmapped":
                status_badges.append(f":orange[**Low Conf ({int(confidence*100)}%)**]")
            elif mapping["transformation_type"] == "unmapped":
                status_badges.append(":gray[**Unmapped**]")
            else:
                status_badges.append(f":green[**Conf: {int(confidence*100)}%**]")

            expander_title = f"{'⚠️ ' if (is_mandatory and mapping['transformation_type'] == 'unmapped') else '✅ '} Target: **{target_name}** | {' | '.join(status_badges)}"
            
            with st.expander(expander_title, expanded=False):
                st.caption(f"**AI Reasoning:** {mapping.get('logic_description', 'No AI notes available.')}")
                
                c1, c2 = st.columns([1, 2])
                with c1:
                    selected_type = st.selectbox(
                        "Transformation Type", options=transform_types,
                        index=transform_types.index(mapping["transformation_type"]), key=f"all_type_{idx}"
                    )
                    mapping["transformation_type"] = selected_type

                with c2:
                    if selected_type == "direct":
                        curr = mapping["parameters"].get("source_col", all_sources[0] if all_sources else "")
                        idx_val = all_sources.index(curr) if curr in all_sources else 0
                        mapping["parameters"] = {"source_col": st.selectbox("Source Column", all_sources, index=idx_val, key=f"all_col_{idx}")}
                        
                    elif selected_type == "static_default":
                        mapping["parameters"] = {"value": st.text_input("Static Default Value", value=str(mapping["parameters"].get("value", "")), key=f"all_static_{idx}")}
                        
                    elif selected_type == "concat":
                        curr_cols = mapping["parameters"].get("source_cols", [])
                        cols = st.multiselect("Source Columns", all_sources, default=[c for c in curr_cols if c in all_sources], key=f"all_concat_{idx}")
                        delim = st.text_input("Delimiter", value=mapping["parameters"].get("delimiter", " "), key=f"all_delim_{idx}")
                        mapping["parameters"] = {"source_cols": cols, "delimiter": delim}
                        
                    elif selected_type == "enum_map":
                        curr = mapping["parameters"].get("source_col", all_sources[0] if all_sources else "")
                        idx_val = all_sources.index(curr) if curr in all_sources else 0
                        source_col = st.selectbox("Source Column to Map", all_sources, index=idx_val, key=f"all_enum_col_{idx}")
                        enum_str = st.text_area("JSON Dictionary", value=json.dumps(mapping["parameters"].get("mapping", {}), indent=2), key=f"all_enum_map_{idx}", height=100)
                        try:
                            mapping["parameters"] = {"source_col": source_col, "mapping": json.loads(enum_str)}
                        except json.JSONDecodeError:
                            st.error("Invalid JSON format.")
                            
                    elif selected_type == "unmapped":
                        mapping["parameters"] = {}

    # -------------------------------------------------------------
    # TAB 3: ADD CUSTOM TARGET FIELD (ON THE FLY)
    # -------------------------------------------------------------
    with tab_custom:
        st.subheader("➕ Add Custom Target Field")
        st.markdown("Need a field in the target dataset that was not defined in the initial target schema? Add it here with a static constant or source calculation.")
        
        with st.form("add_custom_field_form"):
            c_name, c_type = st.columns(2)
            with c_name:
                custom_target_name = st.text_input("New Target Column Name:", placeholder="e.g. batch_id, country_code, tenant")
            with c_type:
                custom_type = st.selectbox("Transformation Type:", ["static_default", "direct", "concat", "enum_map"])
                
            custom_static_val = st.text_input("Static Value (if using static_default):", placeholder="e.g., 2026_BATCH_01")
            custom_src_col = st.selectbox("Source Column (if using direct or enum_map):", all_sources)
            custom_concat_cols = st.multiselect("Source Columns (if using concat):", all_sources)
            custom_delim = st.text_input("Delimiter (if using concat):", value=" ")
            
            submit_custom = st.form_submit_button("➕ Add Field to Pipeline", use_container_width=True)
            
            if submit_custom:
                if not custom_target_name:
                    st.error("Please specify a Target Column Name.")
                else:
                    # Construct parameters
                    params = {}
                    if custom_type == "static_default":
                        params = {"value": custom_static_val}
                    elif custom_type == "direct":
                        params = {"source_col": custom_src_col}
                    elif custom_type == "concat":
                        params = {"source_cols": custom_concat_cols, "delimiter": custom_delim}
                    elif custom_type == "enum_map":
                        params = {"source_col": custom_src_col, "mapping": {}}
                        
                    new_entry = {
                        "target_field": custom_target_name,
                        "transformation_type": custom_type,
                        "parameters": params,
                        "logic_description": "User created custom target field",
                        "confidence_score": 1.0
                    }
                    st.session_state.mappings.append(new_entry)
                    st.success(f"Custom column '{custom_target_name}' added!")
                    st.rerun()

    st.divider()

    # 9. Live Preview & Download
    st.subheader("👀 Live Execution Preview")
    
    st.markdown("**Source Data Preview:**")
    st.dataframe(st.session_state.source_data.head(10), use_container_width=True)
    
    col_left, col_right = st.columns(2)
    with col_left:
        st.markdown("**Transformed Output (Live Result):**")
        try:
            df_preview = apply_mappings(st.session_state.source_data, st.session_state.mappings)
            st.dataframe(df_preview.head(10), use_container_width=True)
        except Exception as e:
            st.error(f"Execution Error: {e}")
            
    with col_right:
        st.markdown("**Target Data Sample (Expected Output):**")
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
