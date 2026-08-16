import pandas as pd
import numpy as np
from asteval import Interpreter
from typing import List, Dict

def _find_best_col(df_cols: List[str], target: str) -> str:
    """Intelligently matches target columns to actual dataframe columns while avoiding ID/Name cross-contamination."""
    if not target:
        return df_cols[0] if df_cols else ""
    if target in df_cols:
        return target
    
    target_lower = target.lower()
    
    # 1. Exact case-insensitive match
    for c in df_cols:
        if c.lower() == target_lower:
            return c
            
    # 2. Specific semantic keyword mapping to prevent ID mix-ups
    keyword_map = {
        'fname': ['first', 'fname', 'given', 'name'],
        'lname': ['last', 'lname', 'surname', 'family'],
        'status': ['status', 'state', 'code'],
        'sku': ['sku', 'item', 'product', 'code']
    }
    
    for key, synonyms in keyword_map.items():
        if key in target_lower:
            for c in df_cols:
                c_lower = c.lower()
                if any(syn in c_lower for syn in synonyms) and 'id' not in c_lower and 'sku' not in c_lower:
                    return c

    # 3. Direct substring match
    for c in df_cols:
        c_lower = c.lower()
        if target_lower in c_lower or c_lower in target_lower:
            if ('id' in c_lower or 'sku' in c_lower) and not ('id' in target_lower or 'sku' in target_lower):
                continue
            return c
            
    # 4. Fallback token overlap
    target_tokens = set(target_lower.replace('_', ' ').split()) - {'cust', 'client', 'user', 'src', 'target'}
    best_match = None
    max_overlap = 0
    
    for c in df_cols:
        c_lower = c.lower()
        if ('id' in c_lower or 'sku' in c_lower) and not any(t in target_lower for t in ['id', 'sku', 'cust']):
            continue
        c_tokens = set(c_lower.replace('_', ' ').split())
        overlap = len(target_tokens & c_tokens)
        if overlap > max_overlap:
            max_overlap = overlap
            best_match = c
            
    return best_match if best_match else (df_cols[0] if df_cols else target)

class TransformationRegistry:
    """Hardcoded safe transformations with smart schema-bridging fallbacks."""
    
    @staticmethod
    def direct(df: pd.DataFrame, source_col: str, **kwargs) -> pd.Series:
        matched_col = _find_best_col(df.columns.tolist(), source_col)
        return df[matched_col]

    @staticmethod
    def enum_map(df: pd.DataFrame, source_col: str, mapping: dict, **kwargs) -> pd.Series:
        matched_col = _find_best_col(df.columns.tolist(), source_col)
        s = df[matched_col].astype(str)
        mapped = s.map(mapping)
        return mapped.fillna(s)

    @staticmethod
    def concat(df: pd.DataFrame, source_cols=None, source_columns=None, columns=None, delimiter: str = " ", **kwargs) -> pd.Series:
        cols = source_cols or source_columns or columns or []
        matched_cols = [_find_best_col(df.columns.tolist(), c) for c in cols]
        valid_cols = [c for c in matched_cols if c in df.columns]
        
        if not valid_cols:
            auto_cols = [c for c in df.columns if any(k in c.lower() for k in ['fname', 'lname', 'first', 'last', 'name']) and 'id' not in c.lower()]
            if len(auto_cols) >= 2:
                valid_cols = auto_cols[:2]
            else:
                str_cols = [c for c in df.select_dtypes(include=['object']).columns.tolist() if 'id' not in c.lower()]
                valid_cols = str_cols[:2] if len(str_cols) >= 2 else str_cols
                
        if not valid_cols:
            return pd.Series([""] * len(df), index=df.index)
            
        return df[valid_cols].astype(str).agg(delimiter.join, axis=1)
        
    @staticmethod
    def static_default(df: pd.DataFrame, value: str, **kwargs) -> pd.Series:
        return pd.Series([value] * len(df), index=df.index)

    @staticmethod
    def calculated(df: pd.DataFrame, expression: str, **kwargs) -> pd.Series:
        aeval = Interpreter()
        aeval.symtable['where'] = np.where
        aeval.symtable['ifelse'] = np.where
        
        for col in df.columns:
            aeval.symtable[col] = df[col]
            
        try:
            result = aeval.eval(expression)
            if len(aeval.error) > 0:
                err_msg = aeval.error[0].get_error()
                raise ValueError(f"{err_msg}. (Hint: Ensure text values are wrapped in quotes!)")
            return pd.Series(result, index=df.index)
        except Exception as e:
            raise ValueError(f"Expression Error in '{expression}': {e}")

    @staticmethod
    def regex(df: pd.DataFrame, source_col: str, operation: str = "extract", pattern: str = "", replacement: str = "", **kwargs) -> pd.Series:
        matched_col = _find_best_col(df.columns.tolist(), source_col)
        series = df[matched_col].astype(str)
        
        if operation == "extract":
            if pattern and ('(' not in pattern or ')' not in pattern):
                pattern = f"({pattern})"  # Auto-wrap in capture groups if missing
            return series.str.extract(pattern, expand=False)
        elif operation == "replace":
            return series.str.replace(pattern, replacement, regex=True)
        elif operation == "match":
            return series.str.contains(pattern, regex=True)
        return series


def apply_mappings(df_source: pd.DataFrame, final_mappings: List[Dict]) -> pd.DataFrame:
    df_target = pd.DataFrame()
    
    for rule in final_mappings:
        target = rule["target_field"]
        func_name = rule["transformation_type"]
        params = rule["parameters"]
        
        if func_name == "unmapped":
            continue
            
        if hasattr(TransformationRegistry, func_name):
            func = getattr(TransformationRegistry, func_name)
            df_target[target] = func(df=df_source, **params)
        else:
            raise ValueError(f"CRITICAL: Transformation '{func_name}' is not registered.")
            
    return df_target
