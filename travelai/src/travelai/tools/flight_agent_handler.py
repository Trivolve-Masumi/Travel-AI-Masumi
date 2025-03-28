from typing import Dict, Any
from crewai import Agent
import logging
import os
from .travel_agent import TravelAgent

class FlightAgentHandler:
    """
    Minimalist handler that connects the CrewAI agent with the TravelAgent
    """
    
    def __init__(self, agent: Agent):
        # Initialize the agent and travel agent
        self.agent = agent
        self.travel_agent = TravelAgent(agent.tools)
        
        # Simple conversation state
        self.conversation_state = {
            "searched": False,
            "selected_flight": False,
            "booked": False
        }
        
        # Setup logging
        self.logger = logging.getLogger('flight_agent_handler')
        if not self.logger.handlers:
            handler = logging.StreamHandler()
            handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
            self.logger.addHandler(handler)
            self.logger.setLevel(logging.INFO)
    
    def handle_user_input(self, user_input: str) -> str:
        """
        Simple handler that relies on the agent's intelligence to interpret user input
        and just manages the current state of the conversation
        """
        user_input = user_input.strip()
        
        # Direct command handling
        if user_input.lower() in ["debug", "test connection", "check api"]:
            return self.travel_agent.test_connection()
        
        # Check API credentials first
        if not os.getenv("AMADEUS_API_KEY") or not os.getenv("AMADEUS_API_SECRET"):
            return "Error: Amadeus API credentials are missing. The system cannot function without API access."
        
        try:
            # 1. Handle flight search (initial state)
            if not self.conversation_state["searched"]:
                # Check if this message contains everything needed for a flight search
                # For simplicity, just look for key terms
                if self._looks_like_search_request(user_input):
                    # Let the agent extract search parameters directly
                    search_result = self._handle_search_request(user_input)
                    
                    if "Available Flight Options" in search_result or "Verified Flight Prices" in search_result:
                        self.conversation_state["searched"] = True
                    
                    return search_result
                else:
                    # Ask for travel details
                    return "Please provide your travel details including departure city, destination, and travel date."
            
            # 2. Handle flight selection
            elif self.conversation_state["searched"] and not self.conversation_state["selected_flight"]:
                if self._looks_like_selection_request(user_input):
                    # Extract option number and select flight
                    option_number = self._extract_option_number(user_input)
                    if option_number:
                        selection_result = self.travel_agent.select_flight(option_number)
                        
                        if "You've selected flight option" in selection_result:
                            self.conversation_state["selected_flight"] = True
                        
                        return selection_result
                    else:
                        return "Please specify which flight option you'd like to select (e.g., 'option 1')."
                else:
                    return "Please select one of the flight options by number."
            
            # 3. Handle booking
            elif self.conversation_state["selected_flight"] and not self.conversation_state["booked"]:
                if self._looks_like_traveler_info(user_input):
                    # Parse traveler information directly from input
                    booking_result = self._handle_booking_request(user_input)
                    
                    if "Booking Confirmation" in booking_result:
                        self.conversation_state["booked"] = True
                        
                        # AUTOMATICALLY GENERATE PDF AFTER BOOKING
                        try:
                            pdf_result = self.generate_pdf()
                            return f"{booking_result}\n\n{pdf_result}"
                        except Exception as e:
                            self.logger.error(f"Failed to generate PDF automatically: {str(e)}")
                            return booking_result
                    
                    return booking_result
                else:
                    return "Please provide traveler information: full name, date of birth (YYYY-MM-DD), email, phone, and gender."
            
            # 4. Post-booking state
            elif self.conversation_state["booked"]:
                # Just handle a few common post-booking queries
                lower_input = user_input.lower()
                
                if "pnr" in lower_input or "reference" in lower_input or "details" in lower_input or "confirmation" in lower_input:
                    return self.travel_agent.get_booking_details()
                elif "pdf" in lower_input or "document" in lower_input or "ticket" in lower_input or "receipt" in lower_input:
                    # Generate PDF on demand if not already generated
                    return self.generate_pdf()
                else:
                    return "Your booking is confirmed. Is there anything else you would like to know about your booking?"
            
            # Fallback
            return "I'm not sure how to help with that. Please provide more details about your travel plans."
            
        except Exception as e:
            self.logger.error(f"Error handling user input: {str(e)}")
            return f"An error occurred: {str(e)}"
    
    def generate_pdf(self):
        """Generate a PDF e-ticket based on the latest booking"""
        try:
            if not self.travel_agent.selected_flight_offer or not self.travel_agent.raw_responses["booking"]:
                self.logger.warning("Cannot generate PDF: No booking or flight selection found")
                return "No booking information available. Please make a booking first."
                
            # Get booking details from travel agent
            booking_data = self.travel_agent.raw_responses["booking"]
            
            # Check if a PDF was already generated during booking
            if "_pdf_path" in booking_data:
                return f"Your e-ticket PDF is available at: {booking_data['_pdf_path']}"
                
            # Get booking reference from booking data
            booking_id = "UNKNOWN"
            if "data" in booking_data and "id" in booking_data["data"]:
                booking_id = booking_data["data"]["id"]
                
            # Look for PDF with booking ID in filename
            for directory in ["booking_pdfs", "."]:
                if os.path.exists(directory):
                    for filename in os.listdir(directory):
                        if booking_id in filename and filename.endswith(".pdf"):
                            pdf_path = os.path.join(directory, filename)
                            return f"Your e-ticket PDF has been found at: {pdf_path}"
            
            # If no PDF found, try to generate one using the booking tool
            if hasattr(self.travel_agent, 'booking_tool') and hasattr(self.travel_agent.booking_tool, 'generate_booking_pdf'):
                pdf_path = self.travel_agent.booking_tool.generate_booking_pdf(booking_data)
                if pdf_path:
                    return f"Your e-ticket PDF has been generated and saved to: {pdf_path}"
                
            return "Could not generate or find the e-ticket PDF. Please check your booking details."
        
        except Exception as e:
            self.logger.error(f"Error generating PDF: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return f"Error generating PDF: {str(e)}"
    
    def _looks_like_search_request(self, text: str) -> bool:
        """Very simple check if this appears to be a flight search request"""
        lower = text.lower()
        
        # Check for common patterns in a flight search
        has_from_to = "from" in lower and "to" in lower
        has_flight_terms = any(term in lower for term in ["flight", "travel", "trip", "book"])
        has_date_terms = any(term in lower for term in ["on", "date", "depart", "leave", "return"])
        
        # Either has from/to or mentions flights and dates
        return has_from_to or (has_flight_terms and has_date_terms)
    
    def _handle_search_request(self, text: str) -> str:
        """Extract parameters from text and search flights"""
        # Extract origin and destination
        origin = None
        destination = None
        
        lower = text.lower()
        if "from" in lower and "to" in lower:
            try:
                from_idx = lower.index("from") + 5
                to_idx = lower.index("to", from_idx)
                
                origin = text[from_idx:to_idx].strip()
                destination = text[to_idx + 3:].split()[0].strip()
            except:
                pass
        
        # If extraction failed, we need to ask for more information
        if not origin or not destination:
            return "I need both origin and destination to search for flights. Please provide details like 'flights from NYC to LAX'."
        
        # Look for date information in the text
        departure_date = None
        return_date = None
        
        # Use the DateHelperTool to parse dates if mentioned
        if hasattr(self, 'travel_agent') and hasattr(self.travel_agent, 'date_tool') and self.travel_agent.date_tool:
            date_terms = ["today", "tomorrow", "next", "on", "depart"]
            for term in date_terms:
                if term in lower:
                    # Find the part of text that might contain a date
                    date_part = None
                    if term == "on":
                        # Look for text after "on"
                        try:
                            on_idx = lower.index(term) + 3  # Length of "on" + space
                            date_part = text[on_idx:on_idx + 20]  # Take enough text to capture a date
                        except:
                            pass
                            
                    if date_part:
                        try:
                            date_result = self.travel_agent.date_tool.run(date_text=date_part)
                            # Extract YYYY-MM-DD format from the result
                            import re
                            date_match = re.search(r'\d{4}-\d{2}-\d{2}', date_result)
                            if date_match:
                                departure_date = date_match.group(0)
                        except:
                            pass
        
        # If we still don't have a date, ask for it
        if not departure_date:
            return "Please provide a specific departure date for your flight search."
        
        # Now we have enough information to search
        return self.travel_agent.search_flights(
            origin=origin,
            destination=destination,
            departure_date=departure_date,
            return_date=return_date,
            adults=1  # Default to 1 adult unless specified
        )
    
    def _looks_like_selection_request(self, text: str) -> bool:
        """Check if this appears to be a flight selection request"""
        lower = text.lower()
        
        # Check for selection indicators
        has_selection_term = any(term in lower for term in ["select", "choose", "book", "option", "flight"])
        has_number = any(char.isdigit() for char in text)
        
        # Either explicitly selects or just has a number
        return has_selection_term or has_number
    
    def _extract_option_number(self, text: str) -> str:
        """Extract flight option number from text"""
        # First check for numbers after keywords
        import re
        for keyword in ["option", "flight", "number", "select", "choose", "book"]:
            pattern = f"{keyword}\\s*([0-9]+)"
            match = re.search(pattern, text.lower())
            if match:
                return match.group(1)
        
        # Then check if input is just a number
        if text.strip().isdigit():
            return text.strip()
        
        # Last resort - find any number in the text
        numbers = re.findall(r'\d+', text)
        if numbers:
            return numbers[0]
        
        return None
    
    def _looks_like_traveler_info(self, text: str) -> bool:
        """Check if this appears to contain traveler information"""
        lower = text.lower()
        
        # Check for common traveler info indicators
        has_email = "@" in lower and "." in lower.split("@")[1]
        has_name = len(text.split()) >= 2  # At least first and last name
        
        # Check for gender indicators
        has_gender = any(term in lower for term in ["male", "female", "gender"])
        
        # Check for date of birth indicators
        has_dob = (
            "-" in text or "/" in text or
            any(term in lower for term in ["birth", "dob", "born"])
        )
        
        # Text has multiple indicators of traveler info
        return (has_email and has_name) or (has_name and (has_gender or has_dob))
    
    def _handle_booking_request(self, text: str) -> str:
        """Process traveler info and book the flight"""
        # Parse basic traveler information
        # In a real implementation, the agent would understand this better
        
        # Split by commas if present, otherwise by newlines
        if "," in text:
            parts = [p.strip() for p in text.split(",")]
        else:
            parts = [p.strip() for p in text.splitlines() if p.strip()]
        
        # Build traveler info dictionary
        traveler_info = {}
        
        # Name (assume first part is the name)
        if parts:
            name_parts = parts[0].split()
            if len(name_parts) >= 2:
                traveler_info["first_name"] = name_parts[0]
                traveler_info["last_name"] = " ".join(name_parts[1:])
        
        # Email (look for @ sign)
        for part in parts:
            if "@" in part and "." in part.split("@")[1]:
                traveler_info["email"] = part.strip()
                break
        
        # Date of birth (assume YYYY-MM-DD format)
        import re
        for part in parts:
            dob_match = re.search(r'\d{4}-\d{2}-\d{2}', part)
            if dob_match:
                traveler_info["date_of_birth"] = dob_match.group(0)
                break
        
        # Phone (look for digits)
        for part in parts:
            if any(c.isdigit() for c in part):
                # Clean up phone format
                phone = "".join(c for c in part if c.isdigit() or c in "+-() ")
                if phone:
                    traveler_info["phone"] = phone
                    break
        
        # Gender
        for part in parts:
            lower_part = part.lower()
            if "male" in lower_part:
                traveler_info["gender"] = "MALE"
                break
            elif "female" in lower_part:
                traveler_info["gender"] = "FEMALE"
                break
        
        # Check if all required fields are present
        required_fields = ["first_name", "last_name", "email", "phone", "date_of_birth", "gender"]
        missing_fields = [field for field in required_fields if field not in traveler_info]
        
        if missing_fields:
            return f"Missing required traveler information: {', '.join(missing_fields)}. Please provide complete details."
        
        # Book the flight with the provided information
        return self.travel_agent.book_flight(traveler_info)