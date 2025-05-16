# app/services/tender_service.py

import os
import pandas as pd
from datetime import datetime, timedelta
from .calendar_service import CalendarService
from ..whatsapp.twilio_client import send_whatsapp_message

class TenderService:
    def __init__(self):
        self.calendar_service = CalendarService()
    
    def process_tender_file(self, file_path):
        """
        Process a tender file (CSV or Excel) and extract tender information.
        
        Args:
            file_path: Path to the uploaded file
            
        Returns:
            List of dictionaries containing tender information
        """
        file_ext = os.path.splitext(file_path)[1].lower()
        
        try:
            if file_ext == '.csv':
                df = pd.read_csv(file_path)
            elif file_ext in ['.xls', '.xlsx']:
                df = pd.read_excel(file_path)
            else:
                raise ValueError(f"Unsupported file type: {file_ext}")
            
            # Validate and standardize column names
            required_cols = ['tender_name', 'email', 'bidding_date']
            df.columns = [col.lower().strip().replace(' ', '_') for col in df.columns]
            
            if not all(col in df.columns for col in required_cols):
                raise ValueError(f"Missing required columns. Required: {', '.join(required_cols)}")
            
            # Convert DataFrame to list of dictionaries
            tenders = df[required_cols].to_dict('records')
            return tenders
            
        except Exception as e:
            raise Exception(f"Error processing file: {str(e)}")
    
    def process_tenders(self, tenders, sender_id):
        """Process a list of tenders and set calendar reminders"""
        successful = []
        failed = []
        
        for tender in tenders:
            try:
                # Validate tender data
                if not self._validate_tender(tender):
                    failed.append({
                        'tender': tender['tender_name'],
                        'reason': 'Invalid data format'
                    })
                    continue
                
                # Parse bidding date
                bidding_date = self._parse_date(tender['bidding_date'])
                if not bidding_date:
                    failed.append({
                        'tender': tender['tender_name'],
                        'reason': 'Invalid date format'
                    })
                    continue
                
                # Calculate reminder date (e.g., 3 days before)
                reminder_date = bidding_date - timedelta(days=3)
                
                # Create calendar event
                event_details = {
                    'summary': f"Tender Bidding: {tender['tender_name']}",
                    'description': f"Bidding deadline for {tender['tender_name']}. Contact: {tender['email']}",
                    'start': bidding_date.isoformat(),
                    'end': (bidding_date + timedelta(hours=1)).isoformat(),
                    'reminders': {
                        'useDefault': False,
                        'overrides': [
                            {'method': 'email', 'minutes': 24 * 60},  # 1 day before
                            {'method': 'popup', 'minutes': 3 * 24 * 60}  # 3 days before
                        ]
                    }
                }
                
                event_id = self.calendar_service.create_event(event_details)
                
                if event_id:
                    successful.append({
                        'tender': tender['tender_name'],
                        'date': bidding_date.strftime('%Y-%m-%d')
                    })
                else:
                    failed.append({
                        'tender': tender['tender_name'],
                        'reason': 'Calendar API error'
                    })
                
            except Exception as e:
                failed.append({
                    'tender': tender['tender_name'],
                    'reason': str(e)
                })
        
        # Send results back to the user
        self._send_processing_results(successful, failed, sender_id)
        
        return {
            'successful': len(successful),
            'failed': len(failed)
        }
    
    def _validate_tender(self, tender):
        """Validate tender data format"""
        required_fields = ['tender_name', 'email', 'bidding_date']
        return all(field in tender and tender[field] for field in required_fields)
    
    def _parse_date(self, date_string):
        """Parse date string into datetime object"""
        date_formats = [
            '%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', 
            '%d-%m-%Y', '%m-%d-%Y'
        ]
        
        for fmt in date_formats:
            try:
                return datetime.strptime(date_string, fmt)
            except ValueError:
                continue
        
        return None
    
    def _send_processing_results(self, successful, failed, sender_id):
        """Send processing results back to the user via WhatsApp"""
        message = f"✅ Processed your tender file.\n\n"
        
        if successful:
            message += f"Successfully created {len(successful)} reminder(s):\n"
            for i, item in enumerate(successful[:5], 1):  # Show up to 5 examples
                message += f"{i}. {item['tender']} (Due: {item['date']})\n"
            
            if len(successful) > 5:
                message += f"...and {len(successful) - 5} more\n"
        
        if failed:
            
            message += f"\n❌ Failed to process {len(failed)} item(s):\n"
            for i, item in enumerate(failed[:3], 1):  # Show up to 3 examples
                message += f"{i}. {item['tender']}: {item['reason']}\n"
            
            if len(failed) > 3:
                message += f"...and {len(failed) - 3} more\n"
        
        send_whatsapp_message(sender_id, message)