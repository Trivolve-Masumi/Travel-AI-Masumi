import re
import calendar
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, Tuple, Union
from pydantic import BaseModel, Field
from crewai.tools import BaseTool

class DateParseInput(BaseModel):
    """Input schema for DateHelperTool."""
    date_text: str = Field(..., description="The date text to parse (e.g., 'May 1st', 'next Friday', '5/1')")

class DateHelperTool(BaseTool):
    name: str = "Date Helper Tool"
    description: str = "Parse various date formats and return standardized dates based on current date context"
    args_schema: type[BaseModel] = DateParseInput
    
    def _run(self, date_text: str) -> str:
        """Parse date text and return it in standardized format."""
        current_date = datetime.now()
        current_year = current_date.year
        
        try:
            # Clean the input
            date_text = date_text.strip().lower()
            
            # Case 1: Handle "today", "tomorrow", "next week", etc.
            if date_text in ["today", "now"]:
                result_date = current_date
            elif date_text == "tomorrow":
                result_date = current_date + timedelta(days=1)
            elif date_text == "day after tomorrow":
                result_date = current_date + timedelta(days=2)
            elif date_text == "next week":
                result_date = current_date + timedelta(days=7)
            elif date_text == "next month":
                # Add 30 days as an approximation for "next month"
                result_date = current_date + timedelta(days=30)
                
            # Case 2: Handle "next Monday", "this Friday", etc.
            elif "next" in date_text or "this" in date_text:
                weekday_pattern = r'(next|this)\s+(monday|tuesday|wednesday|thursday|friday|saturday|sunday)'
                match = re.search(weekday_pattern, date_text)
                if match:
                    prefix, weekday = match.groups()
                    weekday_num = {"monday": 0, "tuesday": 1, "wednesday": 2, 
                                  "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}[weekday]
                    
                    days_ahead = weekday_num - current_date.weekday()
                    if days_ahead <= 0 or prefix == "next":  # If the weekday has passed this week or explicitly "next"
                        days_ahead += 7
                        
                    result_date = current_date + timedelta(days=days_ahead)
                else:
                    return f"Could not understand '{date_text}'. Please provide a date in YYYY-MM-DD format or a clear description."
                
            # Case 3: Handle "May 1st", "Jan 15", etc.
            elif any(month in date_text for month in ["jan", "feb", "mar", "apr", "may", "jun", 
                                                    "jul", "aug", "sep", "oct", "nov", "dec"]):
                # Match patterns like "May 1st", "January 15", etc.
                month_pattern = r'(jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|aug(?:ust)?|sep(?:tember)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)\s+(\d+)(?:st|nd|rd|th)?'
                match = re.search(month_pattern, date_text)
                
                if match:
                    month_name, day = match.groups()
                    # Map month name to number
                    month_map = {"jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
                                "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12}
                    month_num = month_map[month_name[:3]]
                    
                    # Extract year if present, otherwise use current year 
                    # (or next year if the date has already passed this year)
                    year_match = re.search(r'\b(20\d{2})\b', date_text)
                    if year_match:
                        year = int(year_match.group(1))
                    else:
                        # If month/day has already passed this year, use next year
                        if (month_num < current_date.month or 
                            (month_num == current_date.month and int(day) < current_date.day)):
                            year = current_year + 1
                        else:
                            year = current_year
                            
                    # Create date object
                    try:
                        result_date = datetime(year, month_num, int(day))
                    except ValueError:
                        return f"Invalid date: {month_name} {day}, {year}. Please check if this date exists."
                else:
                    return f"Could not understand '{date_text}'. Please provide a date in YYYY-MM-DD format or a clear description."
                    
            # Case 4: Handle MM/DD or MM-DD
            elif re.match(r'^\d{1,2}[/-]\d{1,2}$', date_text):
                separator = '/' if '/' in date_text else '-'
                month, day = map(int, date_text.split(separator))
                
                # Validate month and day
                if month < 1 or month > 12:
                    return f"Invalid month ({month}). Month must be between 1 and 12."
                
                _, last_day = calendar.monthrange(current_year, month)
                if day < 1 or day > last_day:
                    return f"Invalid day ({day}) for month {month}. Day must be between 1 and {last_day}."
                
                # If month/day has already passed this year, use next year
                if (month < current_date.month or 
                    (month == current_date.month and day < current_date.day)):
                    year = current_year + 1
                else:
                    year = current_year
                    
                result_date = datetime(year, month, day)
                
            # Case 5: Handle YYYY/MM/DD or YYYY-MM-DD
            elif re.match(r'^\d{4}[/-]\d{1,2}[/-]\d{1,2}$', date_text):
                if '-' in date_text:
                    year, month, day = map(int, date_text.split('-'))
                else:
                    year, month, day = map(int, date_text.split('/'))
                
                # Validate month and day
                if month < 1 or month > 12:
                    return f"Invalid month ({month}). Month must be between 1 and 12."
                
                _, last_day = calendar.monthrange(year, month)
                if day < 1 or day > last_day:
                    return f"Invalid day ({day}) for month {month}/{year}. Day must be between 1 and {last_day}."
                    
                result_date = datetime(year, month, day)
                
            # Could not parse the date
            else:
                return (f"Could not understand '{date_text}'. "
                        f"Please provide a date in YYYY-MM-DD format or a clear description like 'May 1st' or 'next Friday'.")
            
            # Format the result
            formatted_date = result_date.strftime('%Y-%m-%d')
            
            # Add additional context
            days_from_now = (result_date.date() - current_date.date()).days
            
            if days_from_now < 0:
                return f"Warning: The date {formatted_date} is in the past ({abs(days_from_now)} days ago)."
            elif days_from_now == 0:
                return f"Date parsed as today: {formatted_date}"
            elif days_from_now == 1:
                return f"Date parsed as tomorrow: {formatted_date}"
            elif days_from_now < 7:
                return f"Date parsed as {result_date.strftime('%A')}: {formatted_date} ({days_from_now} days from now)"
            elif days_from_now < 30:
                return f"Date parsed as {formatted_date} ({days_from_now} days / {days_from_now // 7} weeks from now)"
            elif days_from_now < 365:
                return f"Date parsed as {formatted_date} (about {days_from_now // 30} months from now)"
            else:
                return f"Date parsed as {formatted_date} (about {days_from_now // 365} years from now)"
                
        except Exception as e:
            return f"Error parsing date: {str(e)}. Please provide a date in YYYY-MM-DD format or a clear description."