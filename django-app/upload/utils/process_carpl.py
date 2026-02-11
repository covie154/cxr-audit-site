"""
ProcessCarpl wrapper for Django.
This module wraps the original class_process_carpl.py from scripts_lunit_review.
"""

import os
import sys
import json
import pandas as pd
import numpy as np
from pathlib import Path

# Add the scripts_lunit_review directory to path for importing original modules
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'scripts_lunit_review'
sys.path.insert(0, str(SCRIPTS_DIR))

# Import the original modules
from open_protected_xlsx import open_protected_xlsx as original_open_protected_xlsx
from cxr_audit.grade_batch_async import BatchCXRProcessor

# Load JSON configurations from scripts_lunit_review
def load_json_configs():
    """Load the required JSON configuration files."""
    config_dir = SCRIPTS_DIR
    
    with open(config_dir / "padchest_op.json", "r") as f:
        padchest = json.load(f)
    
    with open(config_dir / "padchest_tubes_lines.json", "r") as f:
        tubes_lines = json.load(f)
    
    with open(config_dir / "diagnoses.json", "r") as f:
        diagnoses = json.load(f)
    
    return padchest, tubes_lines, diagnoses


# Default thresholds
THRESHOLDS_DEFAULT = {
    'default': {
        'Atelectasis': 10,
        'Calcification': 10,
        'Cardiomegaly': 10,
        'Consolidation': 10,
        'Fibrosis': 10,
        'Mediastinal Widening': 10,
        'Nodule': 10,
        'Pleural Effusion': 10,
        'Pneumoperitoneum': 10,
        'Pneumothorax': 10,
        'Tuberculosis': 999
    }
}

# Global processor instance (lazy initialization)
_batch_processor = None


def get_batch_processor():
    """Get or create the BatchCXRProcessor singleton."""
    global _batch_processor
    
    if _batch_processor is None:
        padchest, tubes_lines, diagnoses = load_json_configs()
        
        # TODO: Make Ollama server URL configurable via Django settings
        _batch_processor = BatchCXRProcessor(
            findings_dict=padchest,
            tubes_lines_dict=tubes_lines,
            diagnoses_dict=diagnoses,
            model_name="qwen3:32b-q4_K_M",
            base_url="http://192.168.1.204:11434/v1",  # Ollama endpoint
            api_key="dummy",
            max_workers=8,
            rate_limit_delay=0
        )
    
    return _batch_processor


def convert_to_minutes(td):
    """Convert timedelta to human-readable minutes/seconds format."""
    if pd.isnull(td):
        return np.nan
    time_mins = td.total_seconds() / 60
    time_secs = td.total_seconds() % 60
    return f"{int(time_mins)}m {int(time_secs)}s"


class ProcessCarpl:
    """
    ProcessCarpl class for Django - processes CARPL and GE/RIS files.
    This is a Django-compatible version of the original class_process_carpl.py.
    """
    
    def __init__(self, path_carpl_reports, path_ge_reports, processor=None, 
                 supplemental_steps=True, priority_threshold=None, 
                 passwd="GE_2024_P@55", progress_callback=None):
        """
        Initialize the ProcessCarpl instance.
        
        Args:
            path_carpl_reports: Single path or list of paths to CARPL CSV files
            path_ge_reports: Single path or list of paths to GE/RIS Excel files
            processor: BatchCXRProcessor instance (optional, will use default if None)
            supplemental_steps: Whether to run detailed LLM extraction
            priority_threshold: Site-specific thresholds dict
            passwd: Password for protected Excel files
            progress_callback: Callback function for progress updates
        """
        self.path_carpl_reports = path_carpl_reports if isinstance(path_carpl_reports, list) else [path_carpl_reports]
        self.path_ge_reports = path_ge_reports if isinstance(path_ge_reports, list) else [path_ge_reports]
        self.passwd = passwd
        self.processor = processor or get_batch_processor()
        self.priority_threshold = priority_threshold or THRESHOLDS_DEFAULT
        self.supplemental_steps = supplemental_steps
        self.progress_callback = progress_callback
        
        if progress_callback and hasattr(self.processor, 'set_progress_callback'):
            self.processor.set_progress_callback(progress_callback)
    
    def load_reports(self):
        """Load and merge CARPL and GE reports."""
        # Load CARPL files
        carpl_dataframes = []
        for carpl_file in self.path_carpl_reports:
            print(f"Loading CARPL file: {carpl_file}")
            if carpl_file.endswith('.csv'):
                df_carpl = pd.read_csv(carpl_file)
            else:
                df_carpl = pd.read_excel(carpl_file)
            carpl_dataframes.append(df_carpl)
            print(f"  -> Loaded {len(df_carpl)} records")
        
        df_lunit = pd.concat(carpl_dataframes, ignore_index=True)
        print(f"Combined CARPL files: {len(df_lunit)} total records")
        
        # Load GE reports
        ge_dataframes = []
        for ge_file in self.path_ge_reports:
            print(f"Loading GE file: {ge_file}")
            if ge_file.endswith('.csv'):
                df_ge = pd.read_csv(ge_file)
            elif ge_file.endswith(('.xlsx', '.xls')):
                try:
                    df_ge = original_open_protected_xlsx(ge_file, self.passwd)
                except Exception as e:
                    try:
                        print(f"Trying without password: {e}")
                        df_ge = pd.read_excel(ge_file)
                    except Exception as e2:
                        print(f"Error loading {ge_file}: {e2}")
                        continue
            else:
                raise ValueError(f"Unsupported file format: {ge_file}")
            
            if 'PROCEDURE_DATE' in df_ge.columns:
                df_ge = df_ge.rename(columns={'PROCEDURE_DATE': 'PROCEDURE_END_DATE'})
            
            ge_dataframes.append(df_ge)
            print(f"  -> Loaded {len(df_ge)} records")
        
        df_reports = pd.concat(ge_dataframes, ignore_index=True)
        print(f"Combined GE files: {len(df_reports)} total records")
        
        # Remove duplicates
        duplicates_count = df_reports['ACCESSION_NO'].duplicated().sum()
        if duplicates_count > 0:
            print(f"  -> Removing {duplicates_count} duplicate ACCESSION_NO entries")
            df_reports = df_reports[~df_reports['ACCESSION_NO'].duplicated()]
        
        # Convert dates
        df_reports['AI_FLAG_RECEIVED_DATE'] = pd.to_datetime(df_reports['AI_FLAG_RECEIVED_DATE'], errors='coerce')
        df_reports['PROCEDURE_START_DATE'] = pd.to_datetime(df_reports['PROCEDURE_START_DATE'], errors='coerce')
        df_reports['PROCEDURE_END_DATE'] = pd.to_datetime(df_reports['PROCEDURE_END_DATE'], errors='coerce')
        
        # Clean lunit data
        df_lunit = df_lunit.replace("-", np.nan)
        
        # Ensure matching types for merge
        df_reports['ACCESSION_NO'] = pd.to_numeric(df_reports['ACCESSION_NO'], errors='coerce').astype('Int64')
        df_lunit['Accession Number'] = pd.to_numeric(df_lunit['Accession Number'], errors='coerce').astype('Int64')
        
        # Merge
        df_merged = pd.merge(df_reports, df_lunit, left_on="ACCESSION_NO", right_on="Accession Number", how="inner")
        df_merged = df_merged.drop_duplicates(subset='ACCESSION_NO', keep='first')
        
        print(f"Merged data has {len(df_merged)} records")
        
        # Drop unnecessary columns
        columns_to_drop = ['MEDICAL_LOCATION_CODE', 'PROCEDURE_NAME']
        df_merged = df_merged.drop(columns=columns_to_drop, errors='ignore')
        
        return df_merged
    
    def transform_workplace(self, workplace):
        """Transform workplace code to site abbreviation."""
        mapping = {
            'GLCR01': 'GEY', 'KALCR01': 'KAL', 'SEMCR01': 'SEM',
            'TPYCR01': 'TPY', 'KHACR01': 'KHA', 'WDLCR01': 'WDL',
            'HOUCR01': 'HOU', 'AMKCR01': 'AMK', 'YISCR01': 'YIS',
            'SERCR01': 'SER'
        }
        return mapping.get(workplace, 'OTH')
    
    def fill_threshold_dict(self, threshold_dict_site):
        """Fill missing thresholds with defaults."""
        for finding, default_threshold in self.priority_threshold['default'].items():
            if finding not in threshold_dict_site:
                threshold_dict_site[finding] = default_threshold
        return threshold_dict_site
    
    def process_stats_row(self, row, priority_threshold_dict):
        """Process a single row for binary prediction."""
        site = self.transform_workplace(row['WORKPLACE'])
        if site == 'OTH' or site not in priority_threshold_dict:
            threshold_dict_site = self.fill_threshold_dict(priority_threshold_dict['default'].copy())
        else:
            threshold_dict_site = self.fill_threshold_dict(priority_threshold_dict[site].copy())
        
        temp_scores = 0
        for finding, threshold in threshold_dict_site.items():
            if finding in row and pd.notna(row[finding]):
                temp_scores += 1 if row[finding] > threshold else 0
        
        return 1 if temp_scores > 0 else 0
    
    def process_stats_accuracy(self, df_merged, supplemental_steps=False):
        """Compute accuracy statistics."""
        df_merged['Overall_binary'] = df_merged.apply(
            lambda row: self.process_stats_row(row, self.priority_threshold), axis=1
        )
        
        if supplemental_steps:
            steps = ['llm', 'lunit']
        else:
            steps = ['llm']
        
        # Process through LLM
        processed_reports = self.processor.process_full_pipeline(
            df_merged, report_column='TEXT_REPORT', steps=steps
        )
        processed_reports['llm_grade_binary'] = processed_reports['llm_grade'].apply(
            lambda x: 1 if x > 1 else 0
        )
        
        # Merge results
        if supplemental_steps:
            columns_to_merge = ['ACCESSION_NO', 'llm_grade_binary', 'llm_grade',
                              'atelectasis_llm', 'calcification_llm', 'cardiomegaly_llm',
                              'consolidation_llm', 'fibrosis_llm', 'mediastinal_widening_llm',
                              'nodule_llm', 'pleural_effusion_llm', 'pneumoperitoneum_llm',
                              'pneumothorax_llm', 'tb']
        else:
            columns_to_merge = ['ACCESSION_NO', 'llm_grade_binary', 'llm_grade']
        
        # Only merge columns that exist
        columns_to_merge = [col for col in columns_to_merge if col in processed_reports.columns]
        df_merged = pd.merge(df_merged, processed_reports[columns_to_merge], on='ACCESSION_NO', how='left')
        
        return df_merged
    
    def txt_initial_metrics(self, df_merged):
        """Generate initial metrics text report."""
        first_date = df_merged['PROCEDURE_START_DATE'].min()
        last_date = df_merged['PROCEDURE_START_DATE'].max()
        
        first_date_formatted = first_date.strftime("%d-%b-%Y") if pd.notna(first_date) else "N/A"
        last_date_formatted = last_date.strftime("%d-%b-%Y") if pd.notna(last_date) else "N/A"
        
        non_chest_count = len(df_merged[df_merged.get('PROCEDURE_CODE', 0) != 556])
        
        return f'''# REVIEW FOR PERIOD: {first_date_formatted} to {last_date_formatted}
Number of studies inferenced: {len(df_merged)}

# BASIC DESCRIPTORS
Number of inappropriate studies inferenced: {non_chest_count}
'''
    
    def txt_stats_accuracy(self, df_merged, gt_column='llm_grade_binary', pred_column='Overall_binary'):
        """Generate accuracy statistics text report."""
        from sklearn.metrics import confusion_matrix, accuracy_score, cohen_kappa_score
        
        output_lines = []
        output_lines.append('=== LLM vs LUNIT ANALYSIS ===')
        
        if gt_column in df_merged.columns and pred_column in df_merged.columns:
            # Filter out null values
            valid_mask = df_merged[gt_column].notna() & df_merged[pred_column].notna()
            gt = df_merged.loc[valid_mask, gt_column]
            pred = df_merged.loc[valid_mask, pred_column]
            
            if len(gt) > 0:
                accuracy = accuracy_score(gt, pred)
                kappa = cohen_kappa_score(gt, pred)
                tn, fp, fn, tp = confusion_matrix(gt, pred).ravel()
                
                sensitivity = tp / (tp + fn) if (tp + fn) > 0 else 0
                specificity = tn / (tn + fp) if (tn + fp) > 0 else 0
                ppv = tp / (tp + fp) if (tp + fp) > 0 else 0
                npv = tn / (tn + fn) if (tn + fn) > 0 else 0
                
                output_lines.append(f'Accuracy: {accuracy:.3f} ({accuracy*100:.1f}%)')
                output_lines.append(f'Cohen\'s Kappa: {kappa:.3f}')
                output_lines.append(f'Sensitivity: {sensitivity:.3f}')
                output_lines.append(f'Specificity: {specificity:.3f}')
                output_lines.append(f'PPV: {ppv:.3f}')
                output_lines.append(f'NPV: {npv:.3f}')
                output_lines.append(f'TP: {tp}, TN: {tn}, FP: {fp}, FN: {fn}')
        
        return '\n'.join(output_lines)
    
    def process_stats_time(self, df_merged):
        """Process time statistics."""
        def time_clinical_decision(row):
            if row.get('AI_PRIORITY') == "5 AI_ROUTINE":
                return row['AI_FLAG_RECEIVED_DATE'] - row['PROCEDURE_END_DATE']
            else:
                return row.get('REPORT_TURN_AROUND_TIME', pd.NaT)
        
        def time_end_to_end(row):
            if row.get('AI_PRIORITY') != "4 URGENT":
                return row['AI_FLAG_RECEIVED_DATE'] - row['PROCEDURE_END_DATE']
            else:
                return pd.Timedelta(0)
        
        df_merged['Time_to_Clinical_Decision'] = df_merged.apply(time_clinical_decision, axis=1)
        df_merged['Time_End_to_End'] = df_merged.apply(time_end_to_end, axis=1)
        
        return df_merged
    
    def txt_stats_time(self, df_merged):
        """Generate time statistics text report."""
        output_lines = ['=== TIME ANALYSIS SUMMARY ===']
        
        if 'Time_to_Clinical_Decision' in df_merged.columns:
            tcd = df_merged['Time_to_Clinical_Decision'].dropna()
            if len(tcd) > 0:
                output_lines.append('Time to Clinical Decision:')
                output_lines.append(f'- Mean: {convert_to_minutes(tcd.mean())}')
                output_lines.append(f'- Median: {convert_to_minutes(tcd.median())}')
        
        if 'Time_End_to_End' in df_merged.columns:
            tee = df_merged[df_merged['Time_End_to_End'] != pd.Timedelta(0)]['Time_End_to_End'].dropna()
            if len(tee) > 0:
                output_lines.append('End to End Server Time:')
                output_lines.append(f'- Mean: {convert_to_minutes(tee.mean())}')
                output_lines.append(f'- Median: {convert_to_minutes(tee.median())}')
        
        return '\n'.join(output_lines)
    
    def highest_probability(self, row):
        """Find the highest probability finding."""
        findings_columns = ["Atelectasis", "Calcification", "Cardiomegaly",
                          "Consolidation", "Fibrosis", "Mediastinal Widening",
                          "Nodule", "Pleural Effusion", "Pneumoperitoneum",
                          "Pneumothorax", "Tuberculosis"]
        
        probabilities = []
        for col in findings_columns:
            if col in row and pd.notna(row[col]):
                probabilities.append((col, row[col]))
        
        if probabilities:
            max_finding = max(probabilities, key=lambda x: x[1])
            return max_finding[0]
        return None
    
    def rearrange_columns(self, df):
        """Rearrange and rename columns for output."""
        df = df.rename(columns={
            'ground truth': 'gt_manual',
            'llm_grade_binary': 'gt_llm',
            'Overall_binary': 'lunit_binarised',
            'Time_to_Clinical_Decision': 'Time to clinical_decision(mins)'
        })
        
        columns_to_drop_final = ['PROCEDURE_CODE', 'Age', 'Gender', 'Accession Number']
        df = df.drop(columns=columns_to_drop_final, errors='ignore')
        
        return df
    
    def identify_false_negatives(self, df_merged):
        """Identify false negative cases."""
        if 'llm_grade_binary' not in df_merged.columns or 'Overall_binary' not in df_merged.columns:
            return pd.DataFrame(), {"count": 0, "percentage": 0, "total_cases": 0, "description": "Missing columns"}
        
        false_negatives = df_merged[
            (df_merged['llm_grade_binary'] == 0) & 
            (df_merged['Overall_binary'] == 1)
        ]
        
        fn_columns = ['ACCESSION_NO', 'PATIENT_AGE', 'MEDICAL_LOCATION_NAME',
                     'PROCEDURE_START_DATE', 'TEXT_REPORT', 'llm_grade_binary', 'Overall_binary']
        
        available_columns = [col for col in fn_columns if col in df_merged.columns]
        false_negative_df = false_negatives[available_columns].copy()
        
        if not false_negative_df.empty:
            false_negative_df['highest_probability'] = false_negative_df.apply(
                lambda row: self.highest_probability(row), axis=1
            )
        
        total_cases = len(df_merged)
        fn_count = len(false_negative_df)
        fn_percentage = (fn_count / total_cases * 100) if total_cases > 0 else 0
        
        false_negative_summary = {
            "count": fn_count,
            "total_cases": total_cases,
            "percentage": fn_percentage,
            "description": "Cases where LLM predicted negative (0) but Lunit predicted positive (1)"
        }
        
        return false_negative_df, false_negative_summary
    
    def run_all(self):
        """Run the complete processing pipeline."""
        df_merged = self.load_reports()
        
        df_merged = self.process_stats_accuracy(df_merged, supplemental_steps=self.supplemental_steps)
        
        df_merged = self.process_stats_time(df_merged)
        
        false_negative_df, false_negative_summary = self.identify_false_negatives(df_merged)
        
        df_merged = self.rearrange_columns(df_merged)
        
        return df_merged, false_negative_df, false_negative_summary
