"""
Service for processing file uploads from WhatsApp.
"""
import os
import tempfile
import requests
import logging
from datetime import datetime, timedelta

from app.utils.file_parsers import parse_csv, parse_excel
from app.whatsapp.twilio_client import send_whatsapp_message

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class FileProcessor:
    def __init__(self, calendar_service=None):
        """
        Initialize the file processor.
        
        Args:
            calendar_service: Calendar service for creating events
        """
        self.calendar_service = calendar_service
        
    def process_file_from_url(self, file_url, content_type, sender_id):
        """
        Process a file from a URL (from Twilio media).
        
        Args:
            file_url (str): URL to the file
            content_type (str): Content type of the file
            sender_id (str): Sender's phone number
            
        Returns:
            dict: Processing results
        """
        logger.info(f"Processing file from URL: {file_url}")
        
        try:
            # First, send an acknowledgment message
            send_whatsapp_message(sender_id, "I've received your file. Processing it now...")
            
            # Download the file
            from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN
            response = requests.get(file_url, auth=(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN), timeout=30)
            if response.status_code != 200:
                error_msg = f"Failed to download file: HTTP {response.status_code}"
                logger.error(error_msg)
                send_whatsapp_message(sender_id, f"❌ {error_msg}")
                return {"successful": 0, "failed": 0, "error": error_msg}
            
            # Create a temporary file
            with tempfile.NamedTemporaryFile(delete=False) as temp_file:
                temp_file.write(response.content)
                temp_path = temp_file.name
            
            try:
                # Process based on file type
                if content_type == 'text/csv':
                    tenders = parse_csv(temp_path)
                elif any(x in content_type for x in ['spreadsheet', 'excel', 'xls']):
                    tenders = parse_excel(temp_path)
                else:
                    error_msg = f"Unsupported file type: {content_type}"
                    logger.error(error_msg)
                    send_whatsapp_message(sender_id, f"❌ {error_msg}. Please send a CSV or Excel file.")
                    return {"successful": 0, "failed": 0, "error": error_msg}
                
                # Process the tenders
                if self.calendar_service:
                    results = self._create_calendar_events(tenders, sender_id)
                else:
                    # For demo/testing, just log the tenders
                    logger.info(f"Parsed tenders: {tenders}")
                    message = f"✅ Successfully parsed {len(tenders)} tenders from your file.\n\n"
                    message += "Note: Calendar integration is not configured, so no events were created.\n\n"
                    message += "Sample tenders:\n"
                    
                    for i, tender in enumerate(tenders[:3], 1):
                        message += f"{i}. {tender['tender_name']} - {tender['bidding_date']}\n"
                    
                    if len(tenders) > 3:
                        message += f"...and {len(tenders) - 3} more"
                        
                    send_whatsapp_message(sender_id, message)
                    
                    results = {"successful": len(tenders), "failed": 0}
            
            finally:
                # Clean up the temp file
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {temp_path}: {e}")
            
            return results
            
        except Exception as e:
            error_msg = f"Error processing file: {str(e)}"
            logger.error(error_msg)
            send_whatsapp_message(sender_id, f"❌ {error_msg}")
            return {"successful": 0, "failed": 0, "error": str(e)}
    
    def _create_calendar_events(self, tenders, sender_id):
        """
        Create calendar events for tenders.
        
        Args:
            tenders (list): List of tender dictionaries
            sender_id (str): Sender's phone number
            
        Returns:
            dict: Results with counts of successful and failed events
        """
        if not self.calendar_service:
            return {"successful": 0, "failed": 0, "error": "Calendar service not configured"}
            
        successful = []
        failed = []
        
        for tender in tenders:
            try:
                # Parse bidding date
                try:
                    from app.utils.file_parsers import parse_date
                    bidding_date = parse_date(tender['bidding_date'])
                except ValueError:
                    failed.append({
                        'tender': tender['tender_name'],
                        'reason': f"Invalid date format: {tender['bidding_date']}"
                    })
                    continue
                
                # Calculate reminder date (3 days before)
                reminder_date = bidding_date - timedelta(days=3)
                
                # Create calendar event with default times for tender reminders
                summary = f"Tender: {tender['tender_name']}"
                start_time = bidding_date.replace(hour=0, minute=0, second=0, microsecond=0)
                end_time = bidding_date.replace(hour=23, minute=59, second=0, microsecond=0)
                event_id = self.calendar_service.create_event(
                    summary,
                    start_time,
                    end_time
                )
                
                if event_id:
                    successful.append({
                        'tender': tender['tender_name'],
                        'date': bidding_date.strftime('%Y-%m-%d')
                    })
                else:
                    failed.append({
                        'tender': tender['tender_name'],
                        'reason': 'Failed to create calendar event'
                    })
                
            except Exception as e:
                logger.error(f"Error creating event for tender {tender['tender_name']}: {str(e)}")
                failed.append({
                    'tender': tender['tender_name'],
                    'reason': str(e)
                })
        
        # Send results to user
        self._send_processing_results(successful, failed, sender_id)
        
        return {
            'successful': len(successful),
            'failed': len(failed)
        }
    
    def _send_processing_results(self, successful, failed, sender_id):
        """
        Send processing results to the user.
        
        Args:
            successful (list): List of successfully processed tenders
            failed (list): List of failed tenders
            sender_id (str): Sender's phone number
        """
        message = f"✅ Processed your tender file.\n\n"
        
        if successful:
            message += f"Successfully created {len(successful)} reminder(s):\n"
            # Show up to 5 examples
            for i, item in enumerate(successful[:5], 1):
                message += f"{i}. {item['tender']} (Due: {item['date']})\n"
            
            if len(successful) > 5:
                message += f"...and {len(successful) - 5} more\n"
        
        if failed:
            message += f"\n❌ Failed to process {len(failed)} item(s):\n"
            # Show up to 3 examples
            for i, item in enumerate(failed[:3], 1):
                message += f"{i}. {item['tender']}: {item['reason']}\n"
            
            if len(failed) > 3:
                message += f"...and {len(failed) - 3} more\n"
                
        # Send the message
        send_whatsapp_message(sender_id, message)