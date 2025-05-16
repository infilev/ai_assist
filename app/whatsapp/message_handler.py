"""
Handler for WhatsApp messages with intent-based processing.
"""
import datetime
import traceback
import pytz
import os
import tempfile
import requests
from app.config import TIME_ZONE

from app.nlp.intent_recognizer import (
    IntentRecognizer,
    INTENT_PROCESS_TENDERS,
    INTENT_SCHEDULE_MEETING,
    INTENT_CHECK_CALENDAR,
    INTENT_SEND_EMAIL,
    INTENT_FIND_CONTACT,
    INTENT_UNKNOWN
)
from app.nlp.entity_extractor import EntityExtractor
from app.services.email_service import EmailService
from app.services.calendar_service import CalendarService
from app.services.contacts_service import ContactsService
from app.services.contacts_db_service import ContactsDBService
from app.services.tender_service import TenderService
from app.utils.helpers import format_date, format_time, get_current_time, is_valid_email
from ..services.file_processor import FileProcessor
from .twilio_client import send_whatsapp_message

class MessageHandler:
    def __init__(self, whatsapp_client):
        """
        Initialize the message handler.
        
        Args:
            whatsapp_client: WhatsApp client instance for sending responses
        """
        self.whatsapp_client = whatsapp_client
        self.intent_recognizer = IntentRecognizer()
        self.entity_extractor = EntityExtractor()
        self.email_service = EmailService()
        self.calendar_service = CalendarService()
        self.contacts_service = ContactsService()
        self.contacts_db_service = ContactsDBService()
        self.tender_service = TenderService()
        self.file_processor = FileProcessor(calendar_service=self.calendar_service)
        
        # User state for multi-step conversations
        self.user_state = {}
    
    def __call__(self, from_number, message_text, media_url=None, media_type=None):
        """
        Handle incoming WhatsApp messages.
        """
        try:
            # Check for ongoing conversations first
            if from_number in self.user_state:
                print(f"Continuing conversation for {from_number} with state: {self.user_state[from_number]}")
                conversation_state = self.user_state[from_number]

                # Handle file uploads for 'process tenders' workflow
                if conversation_state.get("type") == "tender" and media_url and media_type:
                    if any(x in media_type.lower() for x in ['csv', 'spreadsheet', 'excel', 'xls']):
                        # Process the file
                        self.file_processor.process_file_from_url(media_url, media_type, from_number)
                        # Clear the state
                        del self.user_state[from_number]
                        return
                    else:
                        self._send_response(from_number, 
                            "❌ Please send a CSV or Excel file. Other file types are not supported."
                        )
                        return

                # Continue other conversation flows
                conversation_handled = self._continue_conversation(from_number, message_text)
                if conversation_handled:
                    return

            # Process new messages
            print(f"Processing new message from {from_number}: {message_text}")
            
            # Extract entities before intent recognition for better context
            entities = self.entity_extractor.extract_entities(message_text)
            print(f"Extracted entities: {entities}")
            
            # Recognize intent
            intent_data = self.intent_recognizer.recognize_intent(message_text)
            intent = intent_data.get("intent", INTENT_UNKNOWN)
            confidence = intent_data.get("confidence", 0)
            print(f"Recognized intent: {intent} with confidence: {confidence}")
            
            # Handle different intents
            if intent == INTENT_PROCESS_TENDERS:
                print("Invoking _handle_process_tenders")
                self.user_state[from_number] = {"type": "tender", "step": "awaiting_file"}
                self._send_response(from_number, 
                    "Please upload a CSV or Excel file containing tender information with the following columns:\n"
                    "- tender_name\n"
                    "- email\n"
                    "- bidding_date"
                )
                return
                
            elif intent == INTENT_SCHEDULE_MEETING:
                print("Invoking _handle_schedule_meeting")
                self._handle_schedule_meeting(from_number, message_text, entities)
                
            elif intent == INTENT_CHECK_CALENDAR:
                print("Invoking _handle_check_calendar")
                self._handle_check_calendar(from_number, message_text, entities)
                
            elif intent == INTENT_FIND_CONTACT:
                print("Invoking _handle_find_contact")
                self._handle_find_contact(from_number, message_text, entities)
                
            elif intent == INTENT_SEND_EMAIL:
                print("Invoking _handle_send_email")
                self._handle_send_email(from_number, message_text, entities)
                
            else:
                # Default response for unknown intents
                print("Unknown intent. Sending default response.")
                send_whatsapp_message(from_number, 
                    "I can help you with:\n"
                    "- Processing tender files and setting reminders\n"
                    "- Scheduling meetings\n"
                    "- Checking your calendar\n"
                    "- Finding contacts\n"
                    "- Sending emails\n\n"
                    "How can I assist you today?"
                )
            
        except Exception as e:
            print(f"Error processing message: {e}")
            traceback.print_exc()
            send_whatsapp_message(from_number, f"Sorry, an error occurred: {str(e)}")
    
    def handle_message(self, from_number, message_text, media_url=None, media_type=None):
        """
        Process incoming WhatsApp messages.
        
        Args:
            from_number: Sender's phone number
            message_text: Message content
            media_url: URL to attached media (optional)
            media_type: Content type of attached media (optional)
        """
        try:
            # Handle file attachments for tender processing
            if (media_url and media_type):
                print(f"Received media: {media_type} from {media_url}")
                
                if from_number in self.user_state and self.user_state[from_number].get("type") == "tender":
                    if any(x in media_type.lower() for x in ['csv', 'spreadsheet', 'excel', 'xls']):
                        # Process the file
                        self.file_processor.process_file_from_url(media_url, media_type, from_number)
                        # Clear the state
                        del self.user_state[from_number]
                        return
                    else:
                        self._send_response(from_number, 
                            "❌ Please send a CSV or Excel file. Other file types are not supported."
                        )
                        return
                else:
                    self._send_response(from_number,
                        "I received your file, but I'm not sure what to do with it. "
                        "If you want to set up tender reminders, please say 'process tenders' first."
                    )
                    return

            print(f"Received message from {from_number}: {message_text}")
            
            # For debugging, print current user state
            if from_number in self.user_state:
                print(f"Current user state: {self.user_state[from_number]}")
            else:
                print("No existing conversation state")
            
            # Check for sync command
            if message_text.lower() == "sync contacts":
                success = self.contacts_db_service.sync_contacts(self.contacts_service)
                if isinstance(success, dict) and success.get("success"):
                    if success.get("complete"):
                        self._send_response(from_number, "✅ Contacts synchronized successfully!")
                    else:
                        self._send_response(from_number, 
                            f"Partially synchronized {success.get('contacts_synced')} contacts. "
                            f"Run 'sync contacts' again after 1-2 minutes to continue."
                        )
                else:
                    self._send_response(from_number, 
                        "❌ Failed to synchronize contacts. Please try again later."
                    )
                return
                
            # Always prioritize ongoing conversations
            if from_number in self.user_state:
                conversation_handled = self._continue_conversation(from_number, message_text)
                if conversation_handled:
                    print("Handled as part of ongoing conversation")
                    return  # Exit early if conversation was handled
            
            # Process new intent if not in a conversation
            intent_data = self.intent_recognizer.recognize_intent(message_text)
            intent = intent_data["intent"]
            confidence = intent_data.get("confidence", 0)
            
            print(f"Detected intent: {intent} with confidence: {confidence}")
            
            # Extract entities
            entities = self.entity_extractor.extract_entities(message_text, intent)
            print(f"Extracted entities: {entities}")
            
            # Process based on intent
            if intent == IntentRecognizer.INTENT_SEND_EMAIL:
                self._handle_send_email(from_number, message_text, entities)
                    
            elif intent == IntentRecognizer.INTENT_SCHEDULE_MEETING:
                self._handle_schedule_meeting(from_number, message_text, entities)
                    
            elif intent == IntentRecognizer.INTENT_CHECK_CALENDAR:
                self._handle_check_calendar(from_number, message_text, entities)
                    
            elif intent == IntentRecognizer.INTENT_FIND_CONTACT:
                self._handle_find_contact(from_number, message_text, entities)
                    
            elif intent == IntentRecognizer.INTENT_CHECK_FREE_SLOTS:
                self._handle_check_free_slots(from_number, message_text, entities)

            elif intent == IntentRecognizer.INTENT_PROCESS_TENDERS:
                self._handle_process_tenders(from_number, message_text, media_url, media_type)
                    
            else:
                # Unknown intent
                self._send_response(from_number, 
                    "I'm not sure what you're asking for. I can help you with:\n"
                    "- Sending emails\n"
                    "- Scheduling meetings\n"
                    "- Checking your calendar\n"
                    "- Finding contacts\n"
                    "- Setting tender reminders from CSV/Excel\n"
                    "- Checking your availability\n\n"
                    "Please try phrasing your request differently."
                )
        
        except Exception as e:
            # Log the error and send an apologetic message
            print(f"Error handling message: {e}")
            traceback.print_exc()
            self._send_response(
                from_number,
                "I'm sorry, I encountered an error while processing your request. "
                "Please try again or rephrase your request."
            )
    
    def _continue_conversation(self, from_number, message_text):
        """
        Continue an ongoing conversation.
        
        Args:
            from_number: Sender's phone number
            message_text: Message content
            
        Returns:
            True if conversation was continued, False otherwise
        """
        state = self.user_state[from_number]
        conversation_type = state.get("type")
        step = state.get("step")
        
        # Different conversation flows
        if conversation_type == "email":
            if step == "recipient":
                # User provided recipient
                if message_text.lower() == "cancel":
                    self._send_response(from_number, "Email canceled.")
                    del self.user_state[from_number]
                    return True
                
                state["recipient"] = message_text
                self._send_response(from_number, 
                    "What's the subject of the email? (or type 'cancel' to abort)"
                )
                state["step"] = "subject"
                return True
                
            elif step == "subject":
                # User provided subject
                if message_text.lower() == "cancel":
                    self._send_response(from_number, "Email canceled.")
                    del self.user_state[from_number]
                    return True
                
                state["subject"] = message_text
                self._send_response(from_number, 
                    "What's the content of the email? (or type 'cancel' to abort)"
                )
                state["step"] = "body"
                return True
                
            elif step == "body":
                # User provided body
                if message_text.lower() == "cancel":
                    self._send_response(from_number, "Email canceled.")
                    del self.user_state[from_number]
                    return True
                
                state["body"] = message_text
                
                # Ask for confirmation
                self._send_response(from_number, 
                    f"I'll send an email with:\n"
                    f"To: {state['recipient']}\n"
                    f"Subject: {state['subject']}\n"
                    f"Body: {state['body']}\n\n"
                    f"Send it? (yes/no)"
                )
                state["step"] = "confirm"
                return True
                
            elif step == "confirm":
                # User confirmed
                if message_text.lower() in ["yes", "y", "sure", "ok", "send"]:
                    # Try to find contact if recipient is not an email
                    recipient = state["recipient"]
                    if "@" not in recipient:
                        # Try Google Contacts first
                        contact = None
                        try:
                            contact = self.contacts_service.get_contact_by_name(recipient)
                        except Exception as e:
                            print(f"Error finding contact via Google: {e}")
                        
                        # If not found in Google, try local DB
                        if not contact or not contact.get("email"):
                            try:
                                contact = self.contacts_db_service.get_contact_by_name(recipient)
                            except Exception as e:
                                print(f"Error finding contact in local DB: {e}")
                        
                        if contact and contact.get("email"):
                            recipient = contact["email"]
                        else:
                            self._send_response(from_number, 
                                f"I couldn't find an email for '{recipient}'. "
                                f"Please provide a valid email address or contact name."
                            )
                            state["step"] = "recipient"
                            return True
                    
                    # Send the email
                    result = self.email_service.send_email(
                        to=recipient,
                        subject=state["subject"],
                        body=state["body"]
                    )
                    
                    if result["success"]:
                        self._send_response(from_number, 
                            "Email sent successfully!"
                        )
                    else:
                        self._send_response(from_number, 
                            f"Failed to send email: {result.get('error', 'Unknown error')}"
                        )
                    
                    # Clear state
                    del self.user_state[from_number]
                    
                else:
                    self._send_response(from_number, "Email canceled.")
                    del self.user_state[from_number]
                
                return True
        
        elif conversation_type == "meeting":
            if step == "person":
                # User provided person
                if message_text.lower() == "cancel":
                    self._send_response(from_number, "Meeting scheduling canceled.")
                    del self.user_state[from_number]
                    return True
                
                # Check if it's an email
                if '@' in message_text or '.' in message_text:
                    is_valid, error_msg, suggestion = is_valid_email(message_text)
                    
                    if not is_valid:
                        response = f"The email '{message_text}' appears to be invalid. {error_msg}"
                        if suggestion:
                            response += f"\n\nDid you mean '{suggestion}'? Please confirm or provide a correct email."
                            # Save the suggestion for later use
                            state["suggested_email"] = suggestion
                            state["step"] = "confirm_email"
                        else:
                            response += "\n\nPlease provide a valid email address."
                        
                        self._send_response(from_number, response)
                        return True
                
                state["person"] = message_text
                
                # If we already have a date, ask for time
                if "date" in state:
                    self._send_response(from_number, 
                        f"What time on {format_date(state['date'])}? (or type 'cancel' to abort)"
                    )
                    state["step"] = "time"
                else:
                    self._send_response(from_number, 
                        "What date? (or type 'cancel' to abort)"
                    )
                    state["step"] = "date"
                
                return True
                
            elif step == "confirm_email":
                
                # Allow cancellation
                if message_text.lower() == "cancel":
                    self._send_response(from_number, "Meeting scheduling canceled.")
                    del self.user_state[from_number]
                    return True
                
                # User confirmed the suggested email
                elif message_text.lower() in ["yes", "y", "correct", "confirm", "right"]:
                    state["person"] = state["suggested_email"]
                    del state["suggested_email"]
                    
                    # Continue with date
                    self._send_response(from_number, 
                        "What date? (or type 'cancel' to abort)"
                    )
                    state["step"] = "date"
                    return True
                    
                # User provided a different email
                elif '@' in message_text:
                    is_valid, error_msg, suggestion = is_valid_email(message_text)
                    
                    if not is_valid:
                        response = f"The email '{message_text}' still appears to be invalid. {error_msg}"
                        if suggestion:
                            response += f"\n\nDid you mean '{suggestion}'?"
                            state["suggested_email"] = suggestion
                        else:
                            response += "\n\nPlease provide a valid email address."
                        
                        self._send_response(from_number, response)
                        return True
                        
                    # Email is valid
                    state["person"] = message_text
                    del state["suggested_email"]
                    
                    # Continue with date
                    self._send_response(from_number, 
                        "What date? (or type 'cancel' to abort)"
                    )
                    state["step"] = "date"
                    return True
                    
                else:
                    # User rejected suggestion but didn't provide a new email
                    self._send_response(from_number, 
                        "Please provide a valid email address or type 'cancel' to abort."
                    )
                    return True
                    
            elif step == "date":
                # User provided date
                if message_text.lower() == "cancel":
                    self._send_response(from_number, "Meeting scheduling canceled.")
                    del self.user_state[from_number]
                    return True
                
                # Extract date
                entities = self.entity_extractor.extract_entities(message_text)
                date = entities.get("date")
                
                if not date:
                    self._send_response(from_number, 
                        "I couldn't understand that date. Please provide a specific date "
                        "like 'tomorrow', 'next Friday', or 'May 15th'."
                    )
                    return True
                
                # Check if date is in the past
                current_date = get_current_time().date()
                print(f"Comparing dates - Input date: {date} (type: {type(date)}), Current date: {current_date}")
                if date < current_date:
                    # Format dates for display
                    formatted_input_date = f"{date.day:02d}/{date.month:02d}/{date.year}"
                    formatted_current_date = f"{current_date.day:02d}/{current_date.month:02d}/{current_date.year}"
                    self._send_response(from_number, 
                        f"The date {formatted_input_date} has already passed. Today is {formatted_current_date}. "
                        f"Please provide a future date."
                    )
                    return True
                
                state["date"] = date
                
                # If we already have a time, check availability
                if "time" in state:
                    return self._check_meeting_availability(from_number, state)
                else:
                    self._send_response(from_number, 
                        f"What time on {format_date(date)}? (or type 'cancel' to abort)"
                    )
                    state["step"] = "time"
                
                return True
                
            elif step == "time":
                # User provided time
                if message_text.lower() == "cancel":
                    self._send_response(from_number, "Meeting scheduling canceled.")
                    del self.user_state[from_number]
                    return True
                
                # Extract time
                entities = self.entity_extractor.extract_entities(message_text)
                time = entities.get("time")
                
                if not time:
                    self._send_response(from_number, 
                        "I couldn't understand that time. Please provide a specific time "
                        "like '3pm', '15:30', or 'at 2 o'clock'."
                    )
                    return True
                
                # Ensure time is a datetime.time object
                if isinstance(time, str):
                    try:
                        # Try to parse the time string
                        time_obj = datetime.datetime.strptime(time, "%H:%M").time()
                        time = time_obj
                    except ValueError:
                        self._send_response(from_number, 
                            "I couldn't process that time format. Please use HH:MM format (e.g. 13:00)."
                        )
                        return True
                
                state["time"] = time
                print(f"Set time in state: {time} (type: {type(time)})")
                
                # Check availability
                return self._check_meeting_availability(from_number, state)
                
            elif step == "confirm":
                # User confirmed or selected a slot
                if message_text.lower() in ["yes", "y", "sure", "ok", "book", "1"]:
                    # Book the meeting
                    return self._book_meeting(from_number, state)
                elif message_text.lower() in ["no", "n", "nope", "cancel"]:
                    self._send_response(from_number, "Meeting scheduling canceled.")
                    del self.user_state[from_number]
                    return True
                elif message_text.isdigit():
                    # User selected an alternative slot
                    slot_index = int(message_text) - 1
                    if 0 <= slot_index < len(state.get("alternative_slots", [])):
                        slot = state["alternative_slots"][slot_index]
                        
                        # Update state with selected slot
                        state["date"] = slot[0].date()
                        state["time"] = slot[0].time()
                        state["end_time"] = slot[1].time()
                        
                        # Book the meeting
                        return self._book_meeting(from_number, state)
                    else:
                        self._send_response(from_number, 
                            "Invalid selection. Please choose a number from the list "
                            "or type 'cancel' to abort."
                        )
                        return True
                else:
                    self._send_response(from_number, 
                        "I didn't understand your response. Please answer with 'yes', 'no', "
                        "or the number of an alternative slot."
                    )
                    return True
        
        # No ongoing conversation or unhandled state
        return False
    
    def _check_meeting_availability(self, from_number, state):
        """
        Check availability for a meeting and ask for confirmation.
        
        Args:
            from_number: Sender's phone number
            state: Current conversation state
            
        Returns:
            True to indicate the conversation was handled
        """
        print(f"TIME_ZONE from config: {TIME_ZONE}")
        date = state["date"]
        time = state["time"]
        print(f"Raw time from state: {time}")
        
        # Create datetime objects
        try:
            # Get current time in the configured timezone
            current_dt = get_current_time()
            
            # Create a timezone-aware datetime for the requested meeting time
            start_dt = datetime.datetime.combine(date, time)
            # Make it timezone-aware
            start_dt = pytz.timezone(TIME_ZONE).localize(start_dt)
            
            # Check if datetime is in the past
            if start_dt < current_dt:
                time_str = time.strftime("%H:%M") if hasattr(time, 'strftime') else str(time)
                self._send_response(from_number, 
                    f"The time {time_str} on {format_date(date)} has already passed. "
                    f"Current time is {current_dt.strftime('%H:%M')}. "
                    f"Please provide a future time."
                )
                state["step"] = "time"
                return True
            
            # Set default duration if not specified
            duration = state.get("duration", 30)  # Default 30 minutes
            end_dt = start_dt + datetime.timedelta(minutes=duration)
            
            # Assign end time to state
            state["end_time"] = end_dt.time()
            
            # Check calendar for conflicts - simplified approach
            try:
                # Convert to ISO format for the API
                time_min = start_dt.isoformat()
                time_max = end_dt.isoformat()
                
                events_result = self.calendar_service.service.events().list(
                    calendarId='primary',
                    timeMin=time_min,
                    timeMax=time_max,
                    maxResults=10,
                    singleEvents=True,
                    orderBy='startTime'
                ).execute()
                
                events = events_result.get('items', [])
                
            except Exception as e:
                print(f"Calendar API error checking conflicts: {e}")
                events = []  # Assume no conflicts on error
            
            if events:
                # There's a conflict
                try:
                    free_slots = self.calendar_service.get_free_slots(
                        date=date,
                        start_time=datetime.time(8, 0),  # 8 AM
                        end_time=datetime.time(18, 0),   # 6 PM
                        duration_minutes=duration
                    )
                except Exception as e:
                    print(f"Error getting free slots: {e}")
                    free_slots = []
                
                if not free_slots:
                    self._send_response(from_number, 
                        f"I'm sorry, you don't have any free {duration}-minute slots "
                        f"on {format_date(date)}. Would you like to try another date?"
                    )
                    state["step"] = "date"
                    return True
                
                # Find and suggest alternative slots
                formatted_slots = []
                state["alternative_slots"] = []
                
                # Limit to 5 suggestions
                for i, (slot_start, slot_end) in enumerate(free_slots[:5]):
                    formatted_slots.append(f"{i+1}. {format_time(slot_start)} - {format_time(slot_end)}")
                    state["alternative_slots"].append((slot_start, slot_end))
                
                self._send_response(from_number, 
                    f"You already have a meeting at {format_time(time)} on {format_date(date)}. "
                    f"Here are some free {duration}-minute slots:\n\n" +
                    "\n".join(formatted_slots) +
                    "\n\nPlease choose a slot by number, or type 'cancel' to abort."
                )
                state["step"] = "confirm"
                
            else:
                # Slot is available, ask for confirmation
                person = state.get("person", "the person")
                
                # Try to find contact if it's a name
                contact_info = ""
                if "@" not in person:
                    # Try Google Contacts first
                    contact = None
                    try:
                        contact = self.contacts_service.get_contact_by_name(person)
                    except Exception as e:
                        print(f"Error finding contact via Google: {e}")
                    
                    # If not found in Google, try local DB
                    if not contact or not contact.get("email"):
                        try:
                            contact = self.contacts_db_service.get_contact_by_name(person)
                        except Exception as e:
                            print(f"Error finding contact in local DB: {e}")
                    
                    if contact and contact.get("email"):
                        contact_info = f" ({contact['email']})"
                
                self._send_response(from_number, 
                    f"I'll schedule a {duration}-minute meeting with {person}{contact_info} "
                    f"on {format_date(date)} at {format_time(time)}. "
                    f"Is that correct? (yes/no)"
                )
                state["step"] = "confirm"
            
            return True
            
        except Exception as e:
            print(f"Error checking meeting availability: {e}")
            traceback.print_exc()  # Add stack trace for debugging
            self._send_response(from_number, 
                "I couldn't process the meeting time. Please try again with a different format."
            )
            del self.user_state[from_number]
            return True
    
    def _book_meeting(self, from_number, state):
        """
        Book a meeting after confirmation.
        
        Args:
            from_number: Sender's phone number
            state: Current conversation state
            
        Returns:
            True to indicate the conversation was handled
        """
        try:
            person = state["person"]
            date = state["date"]
            time = state["time"]
            end_time = state["end_time"]
            
            # Create timezone-aware datetime objects
            timezone_obj = pytz.timezone(TIME_ZONE)
            
            # Create naive datetime first
            start_naive = datetime.datetime.combine(date, time)
            end_naive = datetime.datetime.combine(date, end_time)
            
            # Make them timezone-aware properly
            start_dt = timezone_obj.localize(start_naive)
            end_dt = timezone_obj.localize(end_naive)
            
            # Try to find contact if it's a name
            attendees = []
            if "@" not in person:
                # Try Google Contacts first
                contact = None
                try:
                    contact = self.contacts_service.get_contact_by_name(person)
                except Exception as e:
                    print(f"Error finding contact via Google: {e}")
                
                # If not found in Google, try local DB
                if not contact or not contact.get("email"):
                    try:
                        contact = self.contacts_db_service.get_contact_by_name(person)
                    except Exception as e:
                        print(f"Error finding contact in local DB: {e}")
                
                if contact and contact.get("email"):
                    person = contact["name"]
                    attendees.append(contact["email"])
            else:
                # It's an email address
                attendees.append(person)
                
            # Validate email address for attendees
            valid_attendees = []
            for attendee_email in attendees:
                is_valid, error_msg, suggestion = is_valid_email(attendee_email)
                if not is_valid:
                    self._send_response(from_number,
                        f"Cannot schedule meeting: Invalid email '{attendee_email}'. {error_msg}"
                    )
                    if suggestion:
                        self._send_response(from_number,
                            f"Did you mean '{suggestion}'? Please try again with the correct email."
                        )
                    del self.user_state[from_number]
                    return True
                valid_attendees.append(attendee_email)
                
            # Create event
            result = self.calendar_service.create_event(
                summary=f"Meeting with {person}",
                start_time=start_dt,
                end_time=end_dt,
                description=state.get("description", ""),
                location=state.get("location", ""),
                attendees=attendees,
                send_notifications=True
            )
            
            if result["success"]:
                # Get the Meet link from the result
                meet_link = result.get("meet_link")
                
                response = f"✅ Meeting scheduled successfully!\n\n" \
                          f"Meeting with {person}\n" \
                          f"Date: {format_date(date)}\n" \
                          f"Time: {format_time(time)} - {format_time(end_time)}"
                
                # Add calendar link if available
                if result.get('html_link'):
                    response += f"\nCalendar link: {result.get('html_link')}"
                
                # Add Meet link to the message if available
                if meet_link:
                    response += f"\nGoogle Meet link: {meet_link}"
                
                self._send_response(from_number, response)
                
                # Send email with meeting details to attendees
                if attendees and meet_link:
                    self._send_meeting_email(attendees, person, date, time, end_time, meet_link, state.get("description", ""))
            else:
                self._send_response(from_number, 
                    f"Failed to schedule meeting: {result.get('error', 'Unknown error')}"
                )
            
            # Clear state
            del self.user_state[from_number]
            return True
            
        except Exception as e:
            print(f"Error booking meeting: {e}")
            self._send_response(from_number, 
                "I encountered an error while scheduling the meeting. Please try again."
            )
            del self.user_state[from_number]
            return True
        
    
    def _handle_send_email(self, from_number, message_text, entities):
        """
        Handle email sending intent.
        
        Args:
            from_number: Sender's phone number
            message_text: Message content
            entities: Extracted entities
        """
        # Check if we have all required entities
        person = entities.get("person", [])
        email = entities.get("email", [])
        subject = entities.get("subject")
        body = entities.get("body")
        
        # If we have enough information, send the email directly
        if (person or email) and subject and body:
            recipient = email[0] if email else None
            
            if not recipient and person:
                # Try Google Contacts first
                contact = None
                try:
                    contact = self.contacts_service.get_contact_by_name(person[0])
                except Exception as e:
                    print(f"Error finding contact via Google: {e}")
                
                # If not found in Google, try local DB
                if not contact or not contact.get("email"):
                    try:
                        contact = self.contacts_db_service.get_contact_by_name(person[0])
                    except Exception as e:
                        print(f"Error finding contact in local DB: {e}")
                
                if contact and contact.get("email"):
                    recipient = contact["email"]
            
            if recipient:
                result = self.email_service.send_email(
                    to=recipient,
                    subject=subject,
                    body=body
                )
                
                if result["success"]:
                    self._send_response(from_number, 
                        f"Email sent successfully to {recipient}!"
                    )
                else:
                    self._send_response(from_number, 
                        f"Failed to send email: {result.get('error', 'Unknown error')}"
                    )
                
                return
        
        # Start conversation to gather missing information
        recipient = None
        if email:
            recipient = email[0]
        elif person:
            # Try Google Contacts first
            contact = None
            try:
                contact = self.contacts_service.get_contact_by_name(person[0])
            except Exception as e:
                print(f"Error finding contact via Google: {e}")
            
            # If not found in Google, try local DB
            if not contact or not contact.get("email"):
                try:
                    contact = self.contacts_db_service.get_contact_by_name(person[0])
                except Exception as e:
                    print(f"Error finding contact in local DB: {e}")
            
            if contact and contact.get("email"):
                recipient = contact["email"]
            else:
                recipient = person[0]
        
        # Initialize state
        state = {
            "type": "email",
            "step": "recipient" if not recipient else "subject",
        }
        
        if recipient:
            state["recipient"] = recipient
        if subject:
            state["subject"] = subject
        if body:
            state["body"] = body
        
        self.user_state[from_number] = state
        
        # Ask for missing information
        if not recipient:
            self._send_response(from_number, 
                "Who would you like to send an email to? (email address)"
            )
        elif not subject:
            self._send_response(from_number, 
                f"What's the subject of the email to {recipient}?"
            )
        elif not body:
            self._send_response(from_number, 
                f"What's the content of the email to {recipient}?"
            )
    
    def _handle_schedule_meeting(self, from_number, message_text, entities):
        """
        Handle meeting scheduling intent.
        
        Args:
            from_number: Sender's phone number
            message_text: Message content
            entities: Extracted entities
        """
        # Extract entities
        person = entities.get("person", [])
        date = entities.get("date")
        time = entities.get("time")
        duration = entities.get("duration")
        location = entities.get("location")
        subject = entities.get("subject")
        
        # Initialize state
        state = {
            "type": "meeting",
            "step": "person",
        }
        
        if person:
            state["person"] = person[0]
            state["step"] = "date" if not date else "time"
        
        if date:
            state["date"] = date
        
        if time:
            state["time"] = time
        
        if duration:
            state["duration"] = duration
        
        if location:
            state["location"] = location
        
        if subject:
            state["description"] = subject
        
        # Save state
        self.user_state[from_number] = state
        
        # Ask for missing information
        if not person:
            self._send_response(from_number, 
                "Who would you like to schedule a meeting with? (email address)"
            )
        elif not date:
            self._send_response(from_number, 
                f"When would you like to schedule the meeting with {person[0]}? (date)"
            )
        elif not time:
            self._send_response(from_number, 
                f"What time on {format_date(date)} would you like to schedule the meeting?"
            )
        else:
            # We have enough information to check availability
            self._check_meeting_availability(from_number, state)
    
    def _handle_check_calendar(self, from_number, message_text, entities=None):
        """
        Handle calendar checking intent
        """
        try:
            # Get current date if no date is specified
            now = datetime.datetime.now(pytz.timezone(TIME_ZONE))
            query_date = now.date()
            
            if entities and "date" in entities:
                query_date = entities["date"]

            # Get events from calendar
            events = self.calendar_service.get_events(
                start_date=query_date,
                end_date=query_date + datetime.timedelta(days=1)
            )
            
            if not events:
                send_whatsapp_message(from_number, 
                    f"You have no events scheduled for {format_date(query_date)}."
                )
                return

            # Format response
            response = f"📅 Here are your events for {format_date(query_date)}:\n\n"
            for idx, event in enumerate(events, 1):
                start_time = format_time(event['start'].time()) if isinstance(event['start'], datetime.datetime) else "All day"
                end_time = format_time(event['end'].time()) if isinstance(event['end'], datetime.datetime) else ""
                time_str = f"{start_time} - {end_time}" if end_time else start_time
                
                response += f"{idx}. {time_str}\n"
                response += f"   {event['summary']}\n"
                if event.get('location'):
                    response += f"   📍 {event['location']}\n"
                response += "\n"

            send_whatsapp_message(from_number, response.strip())

        except Exception as e:
            print(f"Error checking calendar: {e}")
            traceback.print_exc()
            send_whatsapp_message(from_number, 
                "Sorry, I couldn't retrieve your calendar events. Please try again later."
            )
    
    def _handle_find_contact(self, from_number, message_text, entities):
        """
        Handle contact finding intent with stricter matching.
        
        Args:
            from_number: Sender's phone number
            message_text: Message content
            entities: Extracted entities
        """
        # Extract person name
        person = entities.get("person", [])
        
        if not person:
            # Extract from message using more general approach
            words = message_text.split()
            for i, word in enumerate(words):
                if word.lower() in ["for", "about", "contact", "email", "address", "phone"]:
                    if i + 1 < len(words):
                        person = [" ".join(words[i+1:])]
                        break
        
        if not person:
            self._send_response(from_number, 
                "Who would you like to find contact information for?"
            )
            return
        
        # Search for contact
        contacts = []
        try:
            contacts = self.contacts_service.search_contacts(person[0])
        except Exception as e:
            print(f"Error searching contacts: {e}")
        
        if contacts:
            if len(contacts) == 1:
                # Get full details
                contact_details = None
                try:
                    contact_details = self.contacts_service.get_contact_details(contacts[0]["resource_name"])
                except Exception as e:
                    print(f"Error getting contact details: {e}")
                    contact_details = contacts[0]  # Use basic info if detailed fetch fails
                
                if contact_details:
                    # Format details
                    details_text = f"📇 Contact information for {contact_details['name']}:\n\n"
                    
                    # Add email(s)
                    if contact_details.get('all_emails'):
                        details_text += "📧 Email addresses:\n"
                        for i, email in enumerate(contact_details['all_emails']):
                            details_text += f"   {i+1}. {email}\n"
                    elif contact_details.get('email'):
                        details_text += f"📧 Email: {contact_details['email']}\n"
                    
                    # Add phone(s)
                    if contact_details.get('all_phones'):
                        details_text += "📱 Phone numbers:\n"
                        for i, phone in enumerate(contact_details['all_phones']):
                            details_text += f"   {i+1}. {phone}\n"
                    elif contact_details.get('phone'):
                        details_text += f"📱 Phone: {contact_details['phone']}\n"
                    
                    # Add other details
                    details_text += f"🏢 Organization: {contact_details['organization']}\n" if contact_details.get('organization') else ""
                    details_text += f"📍 Address: {contact_details['address']}" if contact_details.get('address') else ""
                    
                    self._send_response(from_number, details_text)
                else:
                    # Format basic info safely
                    contact_info = f"Found contact: {contacts[0]['name']}"
                    if contacts[0].get('email'):
                        contact_info += f" ({contacts[0]['email']})"
                    if contacts[0].get('phone'):
                        contact_info += f" - {contacts[0]['phone']}"
                    contact_info += f" - {contacts[0]['address']}"

                    self._send_response(from_number, contact_info)
            else:
                # Multiple contacts found
                contacts_text = f"Found {len(contacts)} contacts for '{person[0]}':\n\n"
                
                for i, contact in enumerate(contacts):
                    contacts_text += f"{i+1}. {contact['name']}"
                    if contact.get('email'):
                        contacts_text += f" ({contact['email']})"
                    if contact.get('phone'):
                        contacts_text += f" - {contact['phone']}"
                    contacts_text += "\n"
                
                self._send_response(from_number, contacts_text)
        else:
            self._send_response(from_number, 
                f"No contacts found for '{person[0]}'."
            )
                        
    def _send_response(self, to_number, message):
        """ Send a response to the user.
        Args:
        to_number: Recipient's phone number
        message: Message content"""
        print(f"Sending response to {to_number}: {message}")
        self.whatsapp_client.send_message(to_number, message)                    
    
    
    def _handle_check_free_slots(self, from_number, message_text, entities):
        """
        Handle checking free time slots intent.
        
        Args:
            from_number: Sender's phone number
            message_text: Message content
            entities: Extracted entities
        """
        # Extract date
        date = entities.get("date")
        
        if not date:
            # Default to today
            date = get_current_time().date()
        
        # Get free slots
        free_slots = self.calendar_service.get_free_slots(
            date=date,
            start_time=datetime.time(9, 0),  # 9 AM
            end_time=datetime.time(17, 0),   # 5 PM
            duration_minutes=30              # 30-minute slots
        )
        
        if free_slots:
            # Format free slots
            formatted_slots = self.calendar_service.format_free_slots(free_slots)
            
            self._send_response(from_number, 
                f"📅 Free 30-minute slots for {format_date(date)}:\n\n" +
                "\n".join([f"🕒 {slot}" for slot in formatted_slots])
            )
        else:
            self._send_response(from_number, 
                f"You don't have any free 30-minute slots on {format_date(date)}."
            )    
            
    def _send_meeting_email(self, attendees, person, date, start_time, end_time, meet_link, description=""):
        """
        Send an email with meeting details to attendees.
        
        Args:
            attendees: List of attendee email addresses
            person: Person's name or email
            date: Meeting date
            start_time: Start time
            end_time: End time
            meet_link: Google Meet link
            description: Meeting description/notes
        """
        try:
            # Format the date and times
            date_str = format_date(date)
            start_str = format_time(start_time)
            end_str = format_time(end_time)
            
            # Create email subject - removed mention of recipient in subject
            subject = f"Meeting Invitation: Meeting on {date_str}"
            
            # Define the organizer (your assistant's identity)
            organizer_name = "Your AI Personal Assistant"
            
            # Create email body in HTML format - removed mentioning the recipient's name
            body = f"""
            <html>
            <body>
                <h2>Meeting Invitation</h2>
                <p>You have been invited to a meeting.</p>
                
                <h3>Meeting Details:</h3>
                <ul>
                    <li><strong>Date:</strong> {date_str}</li>
                    <li><strong>Time:</strong> {start_str} - {end_str}</li>
                    <li><strong>Google Meet:</strong> <a href="{meet_link}">{meet_link}</a></li>
                </ul>
                
                <p>You can join the meeting by clicking the Google Meet link above.</p>
                
                {f'<h3>Notes:</h3><p>{description}</p>' if description else ''}
                
                <p>This invitation was sent by {organizer_name}.</p>
            </body>
            </html>
            """
            
            # Send the email
            result = self.email_service.send_email(
                to=attendees,
                subject=subject,
                body=body
            )
            
            if result["success"]:
                print(f"Meeting invitation email sent to {attendees}")
            else:
                print(f"Failed to send meeting invitation email: {result.get('error', 'Unknown error')}")
            
        except Exception as e:
            print(f"Error sending meeting email: {e}")

    def _handle_process_tenders(self, from_number, message_text, media_url=None, media_type=None):
        """
        Handle tender processing intent.
        
        Args:
            from_number: Sender's phone number
            message_text: Message content
            media_url: URL to attached media (optional)
            media_type: Content type of attached media (optional)
        """
        if media_url and media_type:
            try:
                # Download and process the file
                response = requests.get(media_url)
                if response.status_code == 200:
                    # Create a temporary file with appropriate extension
                    ext = '.csv' if 'csv' in media_type.lower() else '.xlsx'
                    with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as temp_file:
                        temp_file.write(response.content)
                        temp_file.flush()
                        
                        # Process the tender file
                        tenders = self.tender_service.process_tender_file(temp_file.name)
                        results = self.tender_service.process_tenders(tenders, from_number)
                        
                        # Clean up
                        os.unlink(temp_file.name)
                        
                else:
                    send_whatsapp_message(from_number, "Sorry, I couldn't download your file. Please try again.")
            
            except Exception as e:
                send_whatsapp_message(from_number, f"Error processing file: {str(e)}")
        
        else:
            # If no file is attached, ask for one
            send_whatsapp_message(from_number, 
                "Please upload a CSV or Excel file containing tender information with the following columns:\n"
                "- tender_name\n"
                "- email\n"
                "- bidding_date"
            )


