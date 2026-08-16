import os
import hmac
import json
import io
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai

from mapper import generate_ai_mappings
from registry import apply_mappings, _find_best_col

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

DEFAULT_SOURCE_SCHEMA = {"fields": [{"name": "cust_fname", "type": "string"}, {"name": "cust_lname", "type": "string"}, {"name": "status_code", "type": "string"}, {"name": "raw_sku", "type": "string"}]}
DEFAULT_TARGET_SCHEMA = {"fields": [{"name": "full_name", "type": "string", "mandatory": True}, {"name": "account_status", "type": "string", "mandatory": True}, {"name": "clean_sku", "type": "string", "mandatory": False}]}
DEFAULT_SOURCE_DATA = pd.DataFrame({"cust_fname": ["John", "Jane"], "cust_lname": ["Doe", "Smith"], "status_code": ["1", "0"], "raw_sku": ["SKU-9921-US", "SKU-4412-EU"]})

# Initialize Session State
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
if "confirm_auto_map" not in st.session_state:
    st.session_state.confirm_auto_map = False

def load_dataframe(file) -> pd.DataFrame:
    if file.name.endswith('.csv'):
        return pd.read_csv(file)
    elif file.name.endswith(('.xls', '.xlsx')):
        return pd.read_excel(file)
    return pd.DataFrame()

# Sidebar Controls
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
            st.session_state.confirm_auto_map = False
            st.success("Files successfully loaded into memory!")
        except Exception as e:
            st.error(f"Error parsing files: {e}")

    st.divider()
    st.subheader("🤖 2. Run Automation")
    
    if st.button("🚀 Run Gemini Auto-Mapping", type="primary", use_container_width=True):
        if not api_key:
            st.error("Please provide a Gemini API key.")
        else:
            # Check if there are custom columns present
            standard_target_fields = {f["name"] for f in st.session_state.target_schema.get("fields", [])}
            has_custom_cols = any(
                m["target_field"] not in standard_target_fields 
                for m in st.session_state.mappings
            )
            
            # If mappings exist and custom columns are found, prompt the user first
            if st.session_state.mappings and has_custom_cols:
                st.session_state.confirm_auto_map = True
                st.rerun()
            else:
                # First-time run or no custom columns: execute immediately without prompting
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

    # Interactive prompt for custom column preservation
    if st.session_state.confirm_auto_map:
        st.warning("⚠️ Custom columns/adjustments detected!")
        preserve_choice = st.radio(
            "Do you want to preserve your custom columns?",
            ["Preserve custom columns", "Overwrite (Discard custom columns)"],
            key="preserve_custom_radio"
        )
        
        c_btn1, c_btn2 = st.columns(2)
        with c_btn1:
            if st.button("Confirm Run", type="primary", use_container_width=True):
                with st.spinner("Gemini is analyzing semantics..."):
                    client = genai.Client(api_key=api_key)
                    
                    standard_target_fields = {f["name"] for f in st.session_state.target_schema.get("fields", [])}
                    custom_mappings_to_preserve = [
                        m for m in st.session_state.mappings 
                        if m["target_field"] not in standard_target_fields
                    ]
                    
                    ai_results = generate_ai_mappings(
                        client, 
                        st.session_state.source_schema, 
                        st.session_state.target_schema
                    )
                    
                    if "Preserve" in preserve_choice:
                        st.session_state.mappings = ai_results + custom_mappings_to_preserve
                        st.success("Auto-mapping complete & custom columns preserved!")
                    else:
                        st.session_state.mappings = ai_results
                        st.success("Auto-mapping complete & custom columns discarded!")
                        
                    st.session_state.confirm_auto_map = False
                    st.rerun()
        with c_btn2:
            if st.button("Cancel", use_container_width=True):
                st.session_state.confirm_auto_map = False
                st.rerun()

# Main Dashboard Header
st.title("🔄 AI Data Mapping & Business Review")

with st.expander("🔍 View Active Schemas in Memory", expanded=False):
    c_left, c_right = st.columns(2)
    with c_left:
        st.json(st.session_state.source_schema)
    with c_right:
        st.json(st.session_state.target_schema)

if st.session_state.mappings:
    target_meta = {f["name"]: f for f in st.session_state.target_schema.get("fields", [])}
    total_fields = len(st.session_state.mappings)
    
    unmatched_target_mappings = [m for m in st.session_state.mappings if m["transformation_type"] == "unmapped"]
    unresolved_mandatory = sum(1 for m in unmatched_target_mappings if target_meta.get(m["target_field"], {}).get("mandatory", False))
    low_confidence = sum(1 for m in st.session_state.mappings if m.get("confidence_score", 1.0) < 0.85 and m["transformation_type"] != "unmapped")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Total Target Fields", total_fields)
    col2.metric("Mapped / Approved", total_fields - len(unmatched_target_mappings))
    col3.metric("Review Needed", low_confidence, delta_color="off")
    col4.metric("Unmatched (Mandatory)", unresolved_mandatory, delta_color="inverse")
    st.divider()

    if st.session_state.source_data is not None and not st.session_state.source_data.empty:
        all_sources = st.session_state.source_data.columns.tolist()
    else:
        all_sources = [f["name"] for f in st.session_state.source_schema.get("fields", [])]

    # Tabs Layout
    tab_unmatched, tab_all, tab_custom = st.tabs([
        f"⚡ Unmatched Target Resolver ({len(unmatched_target_mappings)})",
        f"📋 All Active Mappings ({len(st.session_state.mappings)})",
        "➕ Add Custom Target Field"
    ])

    # -------------------------------------------------------------
    # TAB 1: UNMATCHED TARGET RESOLVER
    # -------------------------------------------------------------
    with tab_unmatched:
        st.subheader("⚡ Quick Resolution for Unmatched Target Fields")
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
                        st.markdown(":red[**MANDATORY FIELD**]" if is_mandatory else ":gray[Optional Field]")

                    st.caption(f"**AI Note:** {mapping.get('logic_description', 'No direct semantic match found.')}")
                    
                    resolve_mode = st.radio(
                        f"Choose transformation for '{target_name}':",
                        ["Static Default Value", "Direct Map", "If-Else / Calculated Expression", "Regex Pattern (Extract/Replace)", "Enum Map", "Concat"],
                        key=f"unmatched_mode_{idx}",
                        horizontal=True
                    )
                    
                    c_input, c_action = st.columns([3, 1])
                    
                    if resolve_mode == "Static Default Value":
                        with c_input:
                            static_val = st.text_input("Static Value:", key=f"q_static_{idx}")
                        with c_action:
                            st.write("")
                            st.write("")
                            if st.button("Apply Static", key=f"b_static_{idx}", type="primary"):
                                mapping["transformation_type"] = "static_default"
                                mapping["parameters"] = {"value": static_val}
                                st.rerun()

                    elif resolve_mode == "Direct Map":
                        with c_input:
                            col_map = st.selectbox("Source Column:", all_sources, key=f"q_dir_{idx}")
                        with c_action:
                            st.write("")
                            st.write("")
                            if st.button("Apply Direct", key=f"b_dir_{idx}", type="primary"):
                                mapping["transformation_type"] = "direct"
                                mapping["parameters"] = {"source_col": col_map}
                                st.rerun()

                    elif resolve_mode == "If-Else / Calculated Expression":
                        with c_input:
                            st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
                            st.markdown("Use `where(condition, true_val, false_val)` e.g., `where(country_cd == 'USA', 'USD', 'CAD')`")
                            calc_expr = st.text_input("Expression:", key=f"q_calc_{idx}")
                        with c_action:
                            st.write("")
                            st.write("")
                            st.write("")
                            if st.button("Apply Calculated", key=f"b_calc_{idx}", type="primary"):
                                mapping["transformation_type"] = "calculated"
                                mapping["parameters"] = {"expression": calc_expr}
                                st.rerun()

                    elif resolve_mode == "Regex Pattern (Extract/Replace)":
                        with c_input:
                            st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
                            reg_col = st.selectbox("Source Column:", all_sources, key=f"q_reg_col_{idx}")
                            reg_op = st.selectbox("Operation:", ["extract", "replace", "match"], key=f"q_reg_op_{idx}")
                            reg_pat = st.text_input("Regex Pattern:", key=f"q_reg_pat_{idx}")
                            reg_rep = st.text_input("Replacement (if replace):", key=f"q_reg_rep_{idx}")
                        with c_action:
                            st.write("")
                            st.write("")
                            st.write("")
                            if st.button("Apply Regex", key=f"b_reg_{idx}", type="primary"):
                                mapping["transformation_type"] = "regex"
                                mapping["parameters"] = {"source_col": reg_col, "operation": reg_op, "pattern": reg_pat, "replacement": reg_rep}
                                st.rerun()

                    elif resolve_mode == "Enum Map":
                        with c_input:
                            st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
                            enum_src = st.selectbox("Source Column:", all_sources, key=f"q_enum_src_{idx}")
                            enum_json = st.text_area("JSON Map:", value='{"A": "Active", "I": "Inactive"}', key=f"q_enum_json_{idx}", height=60)
                        with c_action:
                            st.write("")
                            st.write("")
                            if st.button("Apply Enum", key=f"b_enum_{idx}", type="primary"):
                                try:
                                    mapping["transformation_type"] = "enum_map"
                                    mapping["parameters"] = {"source_col": enum_src, "mapping": json.loads(enum_json)}
                                    st.rerun()
                                except json.JSONDecodeError:
                                    st.error("Invalid JSON.")

                    elif resolve_mode == "Concat":
                        with c_input:
                            st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
                            ccols = st.multiselect("Columns:", all_sources, key=f"q_ccols_{idx}")
                            cdelim = st.text_input("Delimiter:", value=" ", key=f"q_cdelim_{idx}")
                        with c_action:
                            st.write("")
                            st.write("")
                            if st.button("Apply Concat", key=f"b_ccols_{idx}", type="primary"):
                                mapping["transformation_type"] = "concat"
                                mapping["parameters"] = {"source_cols": ccols, "delimiter": cdelim}
                                st.rerun()

    # -------------------------------------------------------------
    # TAB 2: ALL ACTIVE MAPPINGS (FULL CRUD + EXPLICIT APPLY BUTTONS)
    # -------------------------------------------------------------
    with tab_all:
        st.subheader("📋 Comprehensive Rules Editor")
        st.markdown("Edit target field names, modify parameters, click **Apply Changes** for your updates to take effect, or delete rules.")
        
        transform_types = ["direct", "enum_map", "concat", "static_default", "calculated", "regex", "unmapped"]
        to_delete = []

        for idx, mapping in enumerate(list(st.session_state.mappings)):
            target_name = mapping["target_field"]
            
            with st.expander(f"Target: **{target_name}** | Type: `{mapping['transformation_type']}`", expanded=False):
                c_name, c_del = st.columns([3, 1])
                with c_name:
                    new_target_name = st.text_input("Target Field Name", value=target_name, key=f"edit_target_name_{idx}")
                    mapping["target_field"] = new_target_name
                with c_del:
                    st.write("") 
                    if st.button("🗑️ Delete Rule", key=f"del_rule_{idx}", type="secondary"):
                        to_delete.append(idx)
                        
                st.divider()

                current_params = mapping.get("parameters", {})
                if isinstance(current_params, str):
                    try: current_params = json.loads(current_params)
                    except: current_params = {}

                c1, c2 = st.columns([1, 2])
                with c1:
                    selected_type = st.selectbox("Transformation Type", transform_types, index=transform_types.index(mapping["transformation_type"]) if mapping["transformation_type"] in transform_types else 0, key=f"all_type_{idx}")
                    mapping["transformation_type"] = selected_type

                with c2:
                    if selected_type == "direct":
                        curr_col = current_params.get("source_col", all_sources[0] if all_sources else "")
                        matched_curr = _find_best_col(all_sources, curr_col)
                        idx_val = all_sources.index(matched_curr) if matched_curr in all_sources else 0
                        dir_col = st.selectbox("Source Column", all_sources, index=idx_val, key=f"all_dir_{idx}")
                        
                        if st.button("💾 Apply Direct Changes", key=f"apply_dir_{idx}", type="primary"):
                            mapping["parameters"] = {"source_col": dir_col}
                            st.success("Direct mapping updated!")
                            st.rerun()
                        
                    elif selected_type == "static_default":
                        stat_val = st.text_input("Static Default Value", value=str(current_params.get("value", "")), key=f"all_stat_{idx}")
                        
                        if st.button("💾 Apply Static Changes", key=f"apply_stat_{idx}", type="primary"):
                            mapping["parameters"] = {"value": stat_val}
                            st.success("Static default updated!")
                            st.rerun()
                        
                    elif selected_type == "calculated":
                        current_expr = current_params.get("expression", "")
                        st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
                        expr_val = st.text_input("Expression", value=str(current_expr), key=f"all_calc_{idx}")
                        
                        if st.button("💾 Apply Expression Changes", key=f"apply_calc_{idx}", type="primary"):
                            mapping["parameters"] = {"expression": expr_val}
                            st.success("Expression saved!")
                            st.rerun()
                        
                    elif selected_type == "regex":
                        col_val = current_params.get("source_col", all_sources[0] if all_sources else "")
                        matched_curr = _find_best_col(all_sources, col_val)
                        op_val = current_params.get("operation", "extract")
                        pat_val = current_params.get("pattern", "")
                        rep_val = current_params.get("replacement", "")
                        
                        st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
                        r_col = st.selectbox("Source Col", all_sources, index=all_sources.index(matched_curr) if matched_curr in all_sources else 0, key=f"all_reg_col_{idx}")
                        r_op = st.selectbox("Op", ["extract", "replace", "match"], index=["extract", "replace", "match"].index(op_val) if op_val in ["extract", "replace", "match"] else 0, key=f"all_reg_op_{idx}")
                        r_pat = st.text_input("Pattern", value=pat_val, key=f"all_reg_pat_{idx}")
                        r_rep = st.text_input("Replacement", value=rep_val, key=f"all_reg_rep_{idx}")
                        
                        if st.button("💾 Apply Regex Changes", key=f"apply_reg_{idx}", type="primary"):
                            mapping["parameters"] = {"source_col": r_col, "operation": r_op, "pattern": r_pat, "replacement": r_rep}
                            st.success("Regex mapping updated!")
                            st.rerun()
                        
                    elif selected_type == "enum_map":
                        curr_col = current_params.get("source_col", all_sources[0] if all_sources else "")
                        matched_curr = _find_best_col(all_sources, curr_col)
                        idx_val = all_sources.index(matched_curr) if matched_curr in all_sources else 0
                        st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
                        e_col = st.selectbox("Source Col", all_sources, index=idx_val, key=f"all_enum_col_{idx}")
                        e_map = current_params.get("mapping", {})
                        e_str = st.text_area("JSON Map", value=json.dumps(e_map, indent=2), key=f"all_enum_map_{idx}", height=80)
                        
                        if st.button("💾 Apply Enum Changes", key=f"apply_enum_{idx}", type="primary"):
                            try:
                                parsed_json = json.loads(e_str)
                                mapping["parameters"] = {"source_col": e_col, "mapping": parsed_json}
                                st.success("Enum mapping updated!")
                                st.rerun()
                            except json.JSONDecodeError:
                                st.error("Invalid JSON format.")
                            
                    elif selected_type == "concat":
                        curr_cols = current_params.get("source_cols", current_params.get("source_columns", []))
                        matched_defaults = [_find_best_col(all_sources, c) for c in curr_cols]
                        valid_defaults = [c for c in matched_defaults if c in all_sources]
                        
                        st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
                        c_cols = st.multiselect("Source Columns", all_sources, default=valid_defaults, key=f"all_concat_{idx}")
                        c_delim = st.text_input("Delimiter", value=current_params.get("delimiter", " "), key=f"all_delim_{idx}")
                        
                        if st.button("💾 Apply Concat Changes", key=f"apply_concat_{idx}", type="primary"):
                            mapping["parameters"] = {"source_cols": c_cols, "delimiter": c_delim}
                            st.success("Concatenation rule updated!")
                            st.rerun()
                        
                    elif selected_type == "unmapped":
                        mapping["parameters"] = {}
                        if st.button("💾 Apply Unmapped", key=f"apply_unmap_{idx}", type="primary"):
                            st.success("Set to unmapped.")
                            st.rerun()

        if to_delete:
            for i in sorted(to_delete, reverse=True):
                st.session_state.mappings.pop(i)
            st.success("Mapping rule deleted successfully!")
            st.rerun()

    # -------------------------------------------------------------
    # TAB 3: ADD CUSTOM TARGET FIELD
    # -------------------------------------------------------------
    with tab_custom:
        st.subheader("➕ Add Custom Target Field")
        st.markdown("Add brand-new calculated or static target columns to your pipeline. You can add multiple fields consecutively.")
        
        with st.form("add_custom_field_form", clear_on_submit=True):
            st.info(f"💡 **Available Source Fields:** `{', '.join(all_sources)}`")
            custom_name = st.text_input("New Target Column Name:", key="custom_field_name_input")
            custom_type = st.selectbox("Transformation Type:", ["static_default", "calculated", "regex", "direct", "concat"], key="custom_field_type_input")
            
            c_val = st.text_input("Static Value / Expression / Regex Pattern / Delimiter:", key="custom_field_val_input")
            c_src = st.selectbox("Source Column (if applicable):", all_sources, key="custom_field_src_input")
            c_multisrc = st.multiselect("Source Columns (if concat):", all_sources, key="custom_field_multisrc_input")
            
            submitted = st.form_submit_button("Add Field to Pipeline", use_container_width=True)
            
            if submitted:
                if not custom_name.strip():
                    st.error("Please specify a Target Column Name.")
                else:
                    existing_fields = [m["target_field"] for m in st.session_state.mappings]
                    if custom_name.strip() in existing_fields:
                        st.error(f"Target field '{custom_name.strip()}' already exists! Choose a unique name.")
                    else:
                        params = {}
                        if custom_type == "static_default":
                            params = {"value": c_val}
                        elif custom_type == "calculated":
                            params = {"expression": c_val}
                        elif custom_type == "regex":
                            params = {"source_col": c_src, "operation": "extract", "pattern": c_val}
                        elif custom_type == "direct":
                            params = {"source_col": c_src}
                        elif custom_type == "concat":
                            params = {"source_cols": c_multisrc, "delimiter": c_val or " "}
                            
                        st.session_state.mappings.append({
                            "target_field": custom_name.strip(),
                            "transformation_type": custom_type,
                            "parameters": params,
                            "logic_description": "User created custom field",
                            "confidence_score": 1.0
                        })
                        st.success(f"Added '{custom_name.strip()}' successfully!")
                        st.rerun()

    st.divider()

    # 9. Live Execution Preview & Export Options
    st.subheader("👀 Live Execution Preview & Export Options")
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
            st.info("No target sample uploaded.")

    st.divider()
    st.markdown("### 💾 Export Mapping Rules & Specifications")
    st.caption("Download the finalized mapping configuration for pipeline execution or stakeholder sign-off.")

    export_rows = []
    for mapping in st.session_state.mappings:
        t_field = mapping["target_field"]
        meta = target_meta.get(t_field, {})
        
        export_rows.append({
            "Target Field": t_field,
            "Target Datatype": meta.get("type", "string"),
            "Mandatory": meta.get("mandatory", False),
            "Transformation Type": mapping["transformation_type"],
            "Parameters (JSON/Config)": json.dumps(mapping["parameters"]),
            "Logic Description": mapping.get("logic_description", ""),
            "Confidence Score": mapping.get("confidence_score", 1.0)
        })
    df_export_spec = pd.DataFrame(export_rows)

    col_dl_1, col_dl_2, col_dl_3 = st.columns(3)

    with col_dl_1:
        st.download_button(
            label="💾 Download JSON Contract",
            data=json.dumps(st.session_state.mappings, indent=2),
            file_name="final_mapping_rules.json",
            mime="application/json",
            use_container_width=True
        )

    with col_dl_2:
        csv_data = df_export_spec.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="📊 Download CSV Specification",
            data=csv_data,
            file_name="data_mapping_specification.csv",
            mime="text/csv",
            use_container_width=True
        )

    with col_dl_3:
        excel_buffer = io.BytesIO()
        with pd.ExcelWriter(excel_buffer, engine='openpyxl') as writer:
            df_export_spec.to_excel(writer, index=False, sheet_name='Mapping Specifications')
        excel_data = excel_buffer.getvalue()
        
        st.download_button(
            label="📈 Download Excel Specification",
            data=excel_data,
            file_name="data_mapping_specification.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            type="primary"
        )

else:
    st.info("👈 Upload your files in the sidebar and click **Run Gemini Auto-Mapping** to begin.")
