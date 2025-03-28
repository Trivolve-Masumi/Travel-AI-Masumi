from typing import Dict, Any, List, Optional
import json
import os
import logging
from datetime import datetime

class TravelAgent:
    """
    A simplified travel agent that focuses on direct API interactions
    and leaves natural language understanding to the CrewAI agent
    """
    
    def __init__(self, tools):
        """Initialize the travel agent with the necessary tools"""
        # Extract tools
        self.airport_tool = next((t for t in tools if t.name == "Airport Code Lookup Tool"), None)
        self.date_tool = next((t for t in tools if t.name == "Date Helper Tool"), None)
        self.search_tool = next((t for t in tools if t.name == "Amadeus Flight Search Tool"), None)
        self.price_tool = next((t for t in tools if t.name == "Amadeus Flight Price Tool"), None)
        self.booking_tool = next((t for t in tools if t.name == "Amadeus Flight Booking Tool"), None)
        
        # State management
        self.flight_offers = []
        self.selected_flight_offer = None
        
        # Store raw API responses
        self.raw_responses = {
            "search": None,
            "price": None,
            "booking": None
        }
        
        # Setup logging
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up basic logging"""
        self.logger = logging.getLogger('travel_agent')
        
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        if not self.logger.handlers:
            file_handler = logging.FileHandler(f"logs/travel_agent_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
            console_handler = logging.StreamHandler()
            
            formatter = logging.Formatter('%(asctime)s | %(levelname)s | %(message)s')
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            self.logger.addHandler(file_handler)
            self.logger.addHandler(console_handler)
            self.logger.setLevel(logging.INFO)
    
    def search_flights(self, origin, destination, departure_date, return_date=None, adults=1, travel_class=None):
        """Search for flights using the Amadeus Flight Search Tool"""
        # Direct API call without complex preprocessing
        self.logger.info(f"Searching flights: {origin} to {destination} on {departure_date}")
        
        # Validate API credentials exist
        if not os.getenv("AMADEUS_API_KEY") or not os.getenv("AMADEUS_API_SECRET"):
            error_msg = "Amadeus API credentials are missing. Cannot search for flights."
            self.logger.error(error_msg)
            return error_msg
        
        try:
            # Execute search directly
            search_result = self.search_tool.run(
                origin=origin,
                destination=destination,
                departure_date=departure_date,
                return_date=return_date,
                adults=adults,
                travel_class=travel_class,
                non_stop=False,
                max_results=10
            )
            
            # Store flight offers for later selection
            if hasattr(self.search_tool, '_last_response') and self.search_tool._last_response:
                self.raw_responses["search"] = self.search_tool._last_response
                self.flight_offers = self.search_tool._last_response.get('data', [])
                self.logger.info(f"Retrieved {len(self.flight_offers)} flight offers")
            
            # Use price verification for more accurate pricing
            if self.price_tool and self.flight_offers:
                try:
                    price_result = self.price_tool.run(
                        origin=origin,
                        destination=destination,
                        departure_date=departure_date,
                        return_date=return_date,
                        adults=adults
                    )
                    
                    if hasattr(self.price_tool, '_last_response'):
                        self.raw_responses["price"] = self.price_tool._last_response
                    
                    # Return price verification results if available
                    if price_result and "## Verified Flight Prices" in price_result:
                        return price_result
                except Exception as e:
                    self.logger.warning(f"Price verification failed: {str(e)}")
            
            return search_result
                
        except Exception as e:
            error_msg = f"Error searching flights: {str(e)}"
            self.logger.error(error_msg)
            return error_msg
    
    def select_flight(self, option_number):
        """Select a flight option by number"""
        try:
            option_number = int(option_number)
            
            if not self.flight_offers:
                return "No flight options available. Please search for flights first."
                
            if option_number <= 0 or option_number > len(self.flight_offers):
                return f"Invalid option. Please select a number between 1 and {len(self.flight_offers)}."
            
            # Store the selected flight offer
            self.selected_flight_offer = self.flight_offers[option_number - 1]
            self.logger.info(f"Selected flight option {option_number}")
            
            # Get basic flight info for confirmation
            price = self.selected_flight_offer.get('price', {}).get('grandTotal', 'Unknown')
            currency = self.selected_flight_offer.get('price', {}).get('currency', '')
            
            return f"You've selected flight option {option_number} for {price} {currency}. Please provide passenger information to complete the booking."
            
        except ValueError:
            return "Please enter a valid number to select a flight option."
        except Exception as e:
            error_msg = f"Error selecting flight: {str(e)}"
            self.logger.error(error_msg)
            return error_msg
    
    def book_flight(self, traveler_info):
        """Book the selected flight with traveler information"""
        if not self.selected_flight_offer:
            return "No flight has been selected. Please select a flight option first."
        
        self.logger.info(f"Booking flight with offer ID: {self.selected_flight_offer.get('id')}")
        
        try:
            # Just pass the provided traveler info directly to the booking tool
            booking_result = self.booking_tool.run(
                flight_offer=self.selected_flight_offer,
                traveler_info=traveler_info
            )
            
            # Store the booking response
            if hasattr(self.booking_tool, 'last_booking'):
                self.raw_responses["booking"] = self.booking_tool.last_booking
            
            return booking_result
            
        except Exception as e:
            error_msg = f"Error booking flight: {str(e)}"
            self.logger.error(error_msg)
            return error_msg
    
    def get_booking_details(self):
        """Get the details of the latest booking"""
        if not self.raw_responses["booking"]:
            return "No booking information available."
        
        try:
            booking_data = self.raw_responses["booking"]
            
            # Extract basic booking information
            if "data" in booking_data:
                data = booking_data["data"]
                booking_id = data.get("id", "Unknown")
                
                result = f"Booking Reference: {booking_id}\n\n"
                
                # Extract PNR information
                if "associatedRecords" in data and data["associatedRecords"]:
                    record = data["associatedRecords"][0]
                    pnr = record.get("reference", "Unknown")
                    result += f"PNR: {pnr}\n"
                
                # Extract price information
                if "flightOffers" in data and data["flightOffers"]:
                    flight = data["flightOffers"][0]
                    if "price" in flight:
                        price = flight["price"]
                        currency = price.get("currency", "")
                        total = price.get("grandTotal", "Unknown")
                        result += f"Total Price: {total} {currency}\n"
                
                return result
            
            return "No detailed booking information available."
            
        except Exception as e:
            error_msg = f"Error retrieving booking details: {str(e)}"
            self.logger.error(error_msg)
            return error_msg
    
    def generate_flight_pdf(self):
        """Generate a PDF for the current booking"""
        if not self.selected_flight_offer or not self.raw_responses["booking"]:
            self.logger.warning("Cannot generate PDF: No booking or flight selection found")
            return "No booking information available. Please make a booking first."
        
        try:
            # Import the new PDF generator
            from pdf_generator import generate_flight_pdf
            
            # Extract booking details
            booking_data = self.raw_responses["booking"]
            if "data" in booking_data:
                booking_data = booking_data["data"]
            
            # Extract booking reference
            booking_id = booking_data.get("id", f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            # Extract PNR
            pnr = "UNKNOWN"
            if "associatedRecords" in booking_data and booking_data["associatedRecords"]:
                pnr = booking_data["associatedRecords"][0].get("reference", "UNKNOWN")
            
            # Extract traveler information
            traveler_info = {}
            if "travelers" in booking_data and booking_data["travelers"]:
                traveler = booking_data["travelers"][0]
                
                # Extract name
                if "name" in traveler:
                    traveler_info["first_name"] = traveler["name"].get("firstName", "")
                    traveler_info["last_name"] = traveler["name"].get("lastName", "")
                
                # Extract other info
                traveler_info["date_of_birth"] = traveler.get("dateOfBirth", "")
                traveler_info["gender"] = traveler.get("gender", "")
                
                # Extract contact info
                if "contact" in traveler:
                    traveler_info["email"] = traveler["contact"].get("emailAddress", "")
                    
                    if "phones" in traveler["contact"] and traveler["contact"]["phones"]:
                        phone = traveler["contact"]["phones"][0]
                        traveler_info["phone"] = phone.get("number", "")
                        if "countryCallingCode" in phone:
                            traveler_info["phone"] = f"+{phone['countryCallingCode']} {traveler_info['phone']}"
            
            # Generate PDF
            pdf_path = generate_flight_pdf(
                flight_option=self.selected_flight_offer,
                traveler_info=traveler_info,
                booking_reference=booking_id,
                pnr=pnr
            )
            
            if pdf_path:
                self.logger.info(f"Generated booking PDF: {pdf_path}")
                return f"Your booking confirmation PDF has been generated and saved to: {pdf_path}"
            else:
                self.logger.warning("Could not generate PDF")
                return "Could not generate booking PDF. Please make sure ReportLab is installed."
                
        except Exception as e:
            self.logger.error(f"Error generating PDF: {str(e)}")
            import traceback
            self.logger.error(traceback.format_exc())
            return f"Error generating PDF: {str(e)}"
            
    def test_connection(self):
        """Test the connection to Amadeus API"""
        if not self.search_tool or not hasattr(self.search_tool, '_get_access_token'):
            return "API tools not properly configured"
        
        try:
            # Get an access token
            token = self.search_tool._get_access_token()
            
            if token:
                return "Amadeus API connection successful. Ready to search flights."
            else:
                return "Failed to authenticate with Amadeus API."
                
        except Exception as e:
            return f"API connection error: {str(e)}"