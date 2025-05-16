"""
Calendar service for managing events using Google Calendar API.
"""
import datetime
import pytz
from googleapiclient.errors import HttpError

from app.utils.auth import get_calendar_service
from app.utils.helpers import (
    format_datetime, 
    format_date, 
    format_time,
    create_time_slot_range,
    get_weekday_name,
    get_current_time
)
from app.config import TIME_ZONE

class CalendarService:
    def __init__(self):
        """Initialize the calendar service with Google Calendar API."""
        self.service = get_calendar_service()
        self.timezone = pytz.timezone(TIME_ZONE)
        if not self.service:
            print("Failed to initialize Calendar service")
    
    def create_event(self, summary, start_time, end_time, description=None, 
                 location=None, attendees=None, send_notifications=True):
        """
        Create a calendar event.
        
        Args:
            summary: Event title
            start_time: Start time (datetime object or ISO format string)
            end_time: End time (datetime object or ISO format string)
            description: Event description (optional)
            location: Event location (optional)
            attendees: List of attendee email addresses (optional)
            send_notifications: Whether to send notifications to attendees
            
        Returns:
            Dict containing success status and event details if successful
        """
        if not self.service:
            return {"success": False, "error": "Calendar service not initialized"}
        
        print(f"Creating event with timezone={TIME_ZONE}")
        
        print(f"Start time type: {type(start_time)}")
        
        # Convert datetime objects if needed
        if isinstance(start_time, datetime.datetime):
            print(f"Start datetime: {start_time}")
            print(f"Start datetime tzinfo: {start_time.tzinfo}")
            # Debug timezone information
            print(f"Start time before conversion: {start_time.strftime('%Y-%m-%d %H:%M %Z')}")
            start_dt = start_time
        else:
            # Try to parse the string
            try:
                start_dt = datetime.datetime.fromisoformat(start_time.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return {"success": False, "error": "Invalid start time format"}
        
        if isinstance(end_time, datetime.datetime):
            # Debug timezone information
            print(f"End time before conversion: {end_time.strftime('%Y-%m-%d %H:%M %Z')}")
            end_dt = end_time
        else:
            # Try to parse the string
            try:
                end_dt = datetime.datetime.fromisoformat(end_time.replace('Z', '+00:00'))
            except (ValueError, AttributeError):
                return {"success": False, "error": "Invalid end time format"}
        
        # Ensure end time is after start time
        if end_dt <= start_dt:
            # If end time is on or before start time, assume it's the next day
            if isinstance(end_dt, datetime.datetime):
                # Add one day to end_time if it's earlier than start_time
                end_dt = end_dt + datetime.timedelta(days=1)
                print(f"End time adjusted to next day: {end_dt.strftime('%Y-%m-%d %H:%M %Z')}")
            else:
                return {"success": False, "error": "End time must be after start time"}
        
        # Convert back to ISO format
        start_time_iso = start_dt.isoformat()
        end_time_iso = end_dt.isoformat()
        
        # Prepare event data with explicit timezone
        event = {
            'summary': summary,
            'start': {
                'dateTime': start_time_iso,
                'timeZone': TIME_ZONE,
            },
            'end': {
                'dateTime': end_time_iso,
                'timeZone': TIME_ZONE,
            }
        }
        
        if description:
            event['description'] = description
            
        if location:
            event['location'] = location
            
        if attendees:
            if isinstance(attendees, str):
                attendees = [attendees]
            event['attendees'] = [{'email': email} for email in attendees]
            
        # Add Google Meet conferencing
        event['conferenceData'] = {
            'createRequest': {
                'requestId': f"meet-{int(datetime.datetime.now().timestamp())}",
                'conferenceSolutionKey': {
                    'type': 'hangoutsMeet'
                }
            }
        }
                
        try:
            event = self.service.events().insert(
                calendarId='primary',
                body=event,
                sendUpdates='none',
                conferenceDataVersion=1  # This enables Meet link generation
            ).execute()
            
            # Extract the Google Meet link
            meet_link = None
            if 'conferenceData' in event and 'entryPoints' in event['conferenceData']:
                for entry_point in event['conferenceData']['entryPoints']:
                    if entry_point.get('entryPointType') == 'video':
                        meet_link = entry_point.get('uri')
                        break
            
            return {
                "success": True,
                "event_id": event.get('id'),
                "html_link": event.get('htmlLink'),
                "meet_link": meet_link
            }
            
        except HttpError as error:
            return {"success": False, "error": f"Calendar API error: {error}"}
        except Exception as e:
            return {"success": False, "error": f"Error creating event: {e}"}
    
    def get_events(self, start_date=None, end_date=None, max_results=10):
        """
        Get calendar events for a specific date range.
        
        Args:
            start_date: Start date (datetime.date object), defaults to today
            end_date: End date (datetime.date object), defaults to today
            max_results: Maximum number of events to return
            
        Returns:
            List of event dictionaries
        """
        if not self.service:
            print("Calendar service not initialized")
            return []
            
        try:
            # Use today's date if none provided
            if not start_date:
                start_date = datetime.datetime.now(self.timezone).date()
            if not end_date:
                end_date = start_date
            
            # Convert dates to timezone-aware datetime objects
            start_dt = datetime.datetime.combine(start_date, datetime.time.min)
            start_dt = self.timezone.localize(start_dt)
            
            end_dt = datetime.datetime.combine(end_date, datetime.time.max)
            end_dt = self.timezone.localize(end_dt)
            
            # Call the Calendar API
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=start_dt.isoformat(),
                timeMax=end_dt.isoformat(),
                maxResults=max_results,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            # Process events
            processed_events = []
            for event in events:
                start = event['start'].get('dateTime')
                if start:
                    # It's a timed event
                    start = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                    start = start.astimezone(self.timezone)
                else:
                    # It's an all-day event
                    start = datetime.datetime.strptime(event['start'].get('date'), '%Y-%m-%d')
                
                end = event['end'].get('dateTime')
                if end:
                    end = datetime.datetime.fromisoformat(end.replace('Z', '+00:00'))
                    end = end.astimezone(self.timezone)
                else:
                    end = datetime.datetime.strptime(event['end'].get('date'), '%Y-%m-%d')
                
                processed_events.append({
                    'summary': event.get('summary', 'Untitled Event'),
                    'start': start,
                    'end': end,
                    'location': event.get('location', ''),
                    'description': event.get('description', '')
                })
            
            return processed_events
            
        except Exception as e:
            print(f"Error getting calendar events: {e}")
            return []
    
    def get_free_slots(self, date, start_time=None, end_time=None, duration_minutes=30):
        """
        Find free time slots on a specific date.
        
        Args:
            date: The date to check (date object or ISO format string)
            start_time: Start of working hours (time object or string, default: 9:00)
            end_time: End of working hours (time object or string, default: 17:00)
            duration_minutes: Duration of each slot in minutes
            
        Returns:
            List of available time slots as (start, end) datetime tuples
        """
        if not self.service:
            return []
        
        # Set default times if not provided
        if not start_time:
            start_time = datetime.time(9, 0)  # 9:00 AM
        elif isinstance(start_time, str):
            # Parse time string (format: HH:MM)
            hour, minute = map(int, start_time.split(':'))
            start_time = datetime.time(hour, minute)
            
        if not end_time:
            end_time = datetime.time(17, 0)  # 5:00 PM
        elif isinstance(end_time, str):
            # Parse time string (format: HH:MM)
            hour, minute = map(int, end_time.split(':'))
            end_time = datetime.time(hour, minute)
        
        # Convert date string to date object if needed
        if isinstance(date, str):
            date = datetime.datetime.strptime(date, "%Y-%m-%d").date()
        
        # Create datetime objects for start and end of the day
        day_start = datetime.datetime.combine(date, start_time)
        day_start = self.timezone.localize(day_start)
        
        day_end = datetime.datetime.combine(date, end_time)
        day_end = self.timezone.localize(day_end)
        
        # Get all slots for the day
        all_slots = create_time_slot_range(day_start, day_end, duration_minutes)
        
        # Get events for the day
        events = self.get_events(
            start_date=day_start,
            end_date=day_end
        )
        
        # Mark busy slots
        busy_slots = []
        for event in events:
            event_start = event['start']
            event_end = event['end']
            
            # Convert to datetime objects if they are strings
            if isinstance(event_start, str):
                event_start = datetime.datetime.fromisoformat(event_start.replace('Z', '+00:00'))
                event_start = event_start.astimezone(self.timezone)
                
            if isinstance(event_end, str):
                event_end = datetime.datetime.fromisoformat(event_end.replace('Z', '+00:00'))
                event_end = event_end.astimezone(self.timezone)
            
            # Add to busy slots
            busy_slots.append((event_start, event_end))
        
        # Find free slots
        free_slots = []
        for slot_start, slot_end in all_slots:
            is_free = True
            
            for busy_start, busy_end in busy_slots:
                # Check if slot overlaps with any busy period
                if (slot_start < busy_end and slot_end > busy_start):
                    is_free = False
                    break
            
            if is_free:
                free_slots.append((slot_start, slot_end))
        
        return free_slots
    
    def format_free_slots(self, free_slots):
        """
        Format free slots for display.
        
        Args:
            free_slots: List of (start, end) datetime tuples
            
        Returns:
            List of formatted time slot strings
        """
        formatted_slots = []
        
        for start, end in free_slots:
            start_time = format_time(start)
            end_time = format_time(end)
            formatted_slots.append(f"{start_time} - {end_time}")
        
        return formatted_slots
    
    def get_next_event(self):
        """
        Get the next upcoming event.
        
        Returns:
            Dict containing the next event details or None if no upcoming events
        """
        if not self.service:
            return None
            
        now = get_current_time().isoformat()
        
        try:
            events_result = self.service.events().list(
                calendarId='primary',
                timeMin=now,
                maxResults=1,
                singleEvents=True,
                orderBy='startTime'
            ).execute()
            
            events = events_result.get('items', [])
            
            if not events:
                return None
            
                
            event = events[0]
            start = event['start'].get('dateTime', event['start'].get('date'))
            
            # Convert to datetime object if it's a string
            if isinstance(start, str):
                if 'T' in start:  # It's a datetime
                    start_dt = datetime.datetime.fromisoformat(start.replace('Z', '+00:00'))
                else:  # It's a date
                    start_dt = datetime.datetime.strptime(start, "%Y-%m-%d")
                    
                start_dt = start_dt.astimezone(self.timezone)
            else:
                start_dt = start
                
            # Format date and time
            event_date = format_date(start_dt)
            event_time = format_time(start_dt)
            weekday = get_weekday_name(start_dt)
            
            return {
                'id': event['id'],
                'summary': event.get('summary', 'No Title'),
                'date': event_date,
                'time': event_time,
                'weekday': weekday,
                'location': event.get('location', ''),
                'description': event.get('description', ''),
                'link': event.get('htmlLink', '')
            }
            
        except HttpError as error:
            print(f"Calendar API error: {error}")
            return None
        except Exception as e:
            print(f"Error getting next event: {e}")
            return None