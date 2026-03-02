"""
Script to open a password-protected Excel file, convert to DataFrame.
Ported from scripts_lunit_review for Django app.
"""

import pandas as pd
from msoffcrypto import OfficeFile
import io
import os


def open_protected_xlsx(file_path, password=None, sheet_name=None):
    if password is None:
        password = os.environ.get("XLSX_DECRYPT_PASSWORD", "")
    """
    Open a password-protected Excel file and convert to DataFrame
    
    Parameters:
    file_path (str): Path to the password-protected Excel file
    password (str): Password for the Excel file
    sheet_name (str or int, optional): Name or index of the sheet to read. If None, reads the first sheet
    
    Returns:
    pandas.DataFrame: DataFrame containing the Excel data
    """
    
    try:
        # Check if file exists
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"File not found: {file_path}")
        
        print(f"Opening password-protected file: {file_path}")
        
        decrypted_content = io.BytesIO()
        
        # Open the encrypted file
        with open(file_path, 'rb') as file:
            office_file = OfficeFile(file)
            office_file.load_key(password=password)
            office_file.decrypt(decrypted_content)
        
        # Read the decrypted Excel file into a DataFrame
        print("Converting to DataFrame...")
        if sheet_name is not None:
            df = pd.read_excel(decrypted_content, sheet_name=sheet_name)
        else:
            df = pd.read_excel(decrypted_content)
        
        print(f"Successfully loaded DataFrame with shape: {df.shape}")
        print(f"Columns: {list(df.columns)}")
        
        return df
        
    except Exception as e:
        raise ValueError(f"Error processing file: {str(e)}")
