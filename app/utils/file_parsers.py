"""
Utilities for parsing CSV and Excel files for the tender management system.
"""
import csv
import pandas as pd
from datetime import datetime
import os
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def parse_csv(file_path):
    """
    Parse a CSV file containing tender information.
    
    Args:
        file_path (str): Path to the CSV file
        
    Returns:
        list: List of dictionaries with tender information
        
    Raises:
        ValueError: If the file is invalid or missing required columns
    """
    logger.info(f"Parsing CSV file: {file_path}")
    tenders = []
    
    try:
        # Try different encodings if necessary
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        
        for encoding in encodings:
            try:
                with open(file_path, 'r', encoding=encoding) as csvfile:
                    # Check if file is empty
                    if os.path.getsize(file_path) == 0:
                        raise ValueError("CSV file is empty")
                    
                    # Peek at the first line to get column names
                    first_line = csvfile.readline().strip()
                    csvfile.seek(0)  # Reset file pointer
                    
                    # Try to detect delimiter
                    sniffer = csv.Sniffer()
                    dialect = sniffer.sniff(first_line)
                    delimiter = dialect.delimiter
                    
                    reader = csv.DictReader(csvfile, delimiter=delimiter)
                    
                    # Check for required columns (case-insensitive)
                    fieldnames_lower = [f.lower() for f in reader.fieldnames]
                    required_fields = {
                        'tender_name': ['tender_name', 'tender', 'name', 'project', 'project_name'],
                        'email': ['email', 'email_id', 'contact_email', 'contact'],
                        'bidding_date': ['bidding_date', 'date', 'due_date', 'deadline', 'submission_date']
                    }
                    
                    field_mapping = {}
                    for req_field, alternatives in required_fields.items():
                        found = False
                        for alt in alternatives:
                            if alt.lower() in fieldnames_lower:
                                field_mapping[req_field] = reader.fieldnames[fieldnames_lower.index(alt.lower())]
                                found = True
                                break
                        
                        if not found:
                            raise ValueError(f"Missing required column: {req_field} (or equivalent)")
                    
                    # Process rows
                    for row in reader:
                        # Skip empty rows
                        if not any(row.values()):
                            continue
                            
                        tender = {
                            'tender_name': row[field_mapping['tender_name']].strip(),
                            'email': row[field_mapping['email']].strip(),
                            'bidding_date': row[field_mapping['bidding_date']].strip()
                        }
                        
                        # Validate tender_name is not empty
                        if not tender['tender_name']:
                            continue
                            
                        # Try to validate date format
                        try:
                            _ = parse_date(tender['bidding_date'])
                            tenders.append(tender)
                        except ValueError:
                            logger.warning(f"Invalid date format in row: {tender}")
                
                # If we get here, parsing was successful
                break
                
            except Exception as e:
                # Try the next encoding if this one failed
                if encoding == encodings[-1]:
                    # This was the last encoding, re-raise the exception
                    logger.error(f"Failed to parse CSV with all encodings: {str(e)}")
                    raise
                    
                logger.warning(f"Failed with encoding {encoding}, trying next one")
    
    except Exception as e:
        logger.error(f"Error parsing CSV file: {str(e)}")
        raise ValueError(f"Error parsing CSV file: {str(e)}")
    
    logger.info(f"Successfully parsed {len(tenders)} tenders from CSV")
    return tenders

def parse_excel(file_path):
    """
    Parse an Excel file containing tender information.
    
    Args:
        file_path (str): Path to the Excel file
        
    Returns:
        list: List of dictionaries with tender information
        
    Raises:
        ValueError: If the file is invalid or missing required columns
    """
    logger.info(f"Parsing Excel file: {file_path}")
    try:
        # Try to read the file with pandas
        df = pd.read_excel(file_path, engine='openpyxl')
        
        if df.empty:
            raise ValueError("Excel file is empty or has no data")
            
        # Check for required columns (case-insensitive)
        columns_lower = [col.lower() if isinstance(col, str) else str(col).lower() for col in df.columns]
        required_fields = {
            'tender_name': ['tender_name', 'tender', 'name', 'project', 'project_name'],
            'email': ['email', 'email_id', 'contact_email', 'contact'],
            'bidding_date': ['bidding_date', 'date', 'due_date', 'deadline', 'submission_date']
        }
        
        field_mapping = {}
        for req_field, alternatives in required_fields.items():
            found = False
            for alt in alternatives:
                if alt.lower() in columns_lower:
                    field_mapping[req_field] = df.columns[columns_lower.index(alt.lower())]
                    found = True
                    break
            
            if not found:
                raise ValueError(f"Missing required column: {req_field} (or equivalent)")
        
        # Process rows and convert to list of dictionaries
        tenders = []
        for _, row in df.iterrows():
            # Skip rows where all mapped fields are empty/NaN
            if all(pd.isna(row[field_mapping[field]]) for field in field_mapping):
                continue
                
            tender = {}
            for req_field, excel_field in field_mapping.items():
                value = row[excel_field]
                
                # Convert to string and strip whitespace
                if pd.isna(value):
                    value = ""
                elif isinstance(value, (int, float)):
                    value = str(value)
                else:
                    value = str(value).strip()
                    
                tender[req_field] = value
            
            # Validate tender_name is not empty
            if not tender['tender_name']:
                continue
                
            # Try to validate date format
            try:
                _ = parse_date(tender['bidding_date'])
                tenders.append(tender)
            except ValueError:
                logger.warning(f"Invalid date format in row: {tender}")
    
    except Exception as e:
        logger.error(f"Error parsing Excel file: {str(e)}")
        raise ValueError(f"Error parsing Excel file: {str(e)}")
    
    logger.info(f"Successfully parsed {len(tenders)} tenders from Excel")
    return tenders

def parse_date(date_string):
    """
    Parse date string into datetime object.
    
    Args:
        date_string (str): Date string to parse
        
    Returns:
        datetime: Parsed datetime object
        
    Raises:
        ValueError: If the date string cannot be parsed
    """
    # Remove extra whitespace
    date_string = date_string.strip()
    
    # Try common date formats
    date_formats = [
        '%Y-%m-%d',       # 2023-05-15
        '%d/%m/%Y',       # 15/05/2023
        '%m/%d/%Y',       # 05/15/2023
        '%d-%m-%Y',       # 15-05-2023
        '%m-%d-%Y',       # 05-15-2023
        '%d.%m.%Y',       # 15.05.2023
        '%m.%d.%Y',       # 05.15.2023
        '%d %b %Y',       # 15 May 2023
        '%d %B %Y',       # 15 May 2023
        '%b %d, %Y',      # May 15, 2023
        '%B %d, %Y',      # May 15, 2023
    ]
    
    # If the date is a pandas Timestamp or datetime object
    if isinstance(date_string, (pd.Timestamp, datetime)):
        return date_string
    
    # Try each format
    for fmt in date_formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    # If all formats fail, try pandas to_datetime as a fallback
    try:
        return pd.to_datetime(date_string).to_pydatetime()
    except Exception:
        raise ValueError(f"Could not parse date: {date_string}")