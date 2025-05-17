# Tender File Parser Utility – Code Explanation

## Example Workflow: Submitting a Correct File

Below is a sample workflow and example of a correctly formatted tender file for successful parsing:

### 1. Prepare Your File
- Use one of the supported formats: **CSV**, **Excel (.xlsx, .xls)**, or **Word (.docx)**.
- Ensure your file contains the following columns (case-insensitive):
  - `tender_name`
  - `email`
  - `bidding_date`

### 2. Example of a Correct CSV/Excel File

| tender_name | email               | bidding_date |
|-------------|---------------------|--------------|
| Project A   | projecta@email.com  | 25/12/2025   |
| Project B   | projectb@email.com  | 30/12/2025   |

**CSV Example:**
```csv
tender_name,email,bidding_date
Project A,projecta@email.com,25/12/2025
Project B,projectb@email.com,30/12/2025
```

**Excel Example:**
- The first row should be the header: `tender_name`, `email`, `bidding_date`.
- Each subsequent row should contain valid data as above.

**Word Table Example:**
| tender_name | email               | bidding_date |
|-------------|---------------------|--------------|
| Project A   | projecta@email.com  | 25/12/2025   |
| Project B   | projectb@email.com  | 30/12/2025   |

### 3. Run the Parser
Run the following command in your terminal:
```sh
python tender_file_parser.py Tender/tender_testing_file/csv/correct_example.csv
```

### 4. Expected Output
```
ℹ️ Parsed 2 tenders:
{'tender_name': 'Project A', 'email': 'projecta@email.com', 'bidding_date': '25/12/2025'}
{'tender_name': 'Project B', 'email': 'projectb@email.com', 'bidding_date': '30/12/2025'}
```

---

## Purpose

The script extracts and validates tender information for use in a WhatsApp AI assistant or similar workflow. It ensures that only well-formed, non-duplicate, and future-dated tenders are processed, and provides clear feedback for any issues found in the input files.

---

## Main Features

- **Supports CSV, Excel (.xlsx, .xls), and Word (.docx) files**
- **Validates required columns:** `tender_name`, `email`, `bidding_date`
- **Checks for:**
  - Empty files
  - Invalid email and date formats
  - Duplicate tenders (by name+email)
  - Empty/whitespace fields
  - Bidding dates in the past
  - Extra columns (ignored)
  - Unsupported file types
  - File not found
  - General/corrupted file errors
- **User-friendly error/warning/info messages** with icons

---

## Code Structure

### 1. Imports and Setup
- Uses `pandas` for CSV/Excel, `python-docx` for Word, and standard libraries for regex, date, and system operations.
- Defines required columns and a regex for email validation.

### 2. Message Formatting Functions
- `format_error(msg)`: Returns a red cross (❌) error message.
- `format_warning(msg)`: Returns a warning (⚠️) message.
- `format_info(msg)`: Returns an info (ℹ️) message.

### 3. Validation Functions
- `validate_columns(df)`: Ensures all required columns are present.
- `validate_email(email)`: Checks email format.
- `validate_date(date_str)`: Accepts `DD/MM/YYYY` or `YYYY-MM-DD`.

### 4. File Parsing Functions
- **parse_csv(file_path)**: Reads and validates CSV files row by row.
- **parse_excel(file_path)**: Reads and validates Excel files (same logic as CSV).
- **parse_docx(file_path)**: Reads and validates tables in Word files, handling table/row structure.

Each parser:
- Skips rows with errors, printing formatted warnings.
- Collects valid tenders.
- Prints a summary of skipped/parsed rows.
- Raises a formatted error if no valid tenders are found.

### 5. File Type Dispatcher
- `parse_tender_file(file_path)`: Calls the appropriate parser based on file extension. Raises a formatted error for unsupported types.

### 6. Main Script Logic
- Checks for command-line argument (file path).
- Checks if file exists.
- Calls the parser and prints results.
- Catches all exceptions, prints a formatted error, and (optionally) a troubleshooting hint. Tracebacks are suppressed for user-friendliness.

---

## Error/Warning Message Examples
- ❌ Missing required columns: bidding_date. Please ensure your file includes all required columns: tender_name, email, and bidding_date.
- ⚠️ Row 2 skipped: Invalid email address 'not-an-email'
- ⚠️ Row 3 in table 1 skipped: Bidding date '01/01/2020' is in the past
- ℹ️ Summary: 2 row(s) skipped, 1 row(s) parsed successfully.

---

## Customization
- You can adapt the required columns, validation logic, or message formats as needed for your workflow.
- The script is modular and can be imported as a library or used standalone.

---

## Dependencies
- `pandas` (for CSV/Excel)
- `python-docx` (for Word files, optional)

---

## Author & Contact
For questions or improvements, contact the project maintainer.
