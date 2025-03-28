import os
import json
import logging
from typing import Dict, Any, List, Optional, Union
from pydantic import BaseModel, Field, PrivateAttr
from crewai.tools import BaseTool
from datetime import datetime
import uuid
import re
import random
import string

# This model defines the structure for traveler information
class TravelerInfo(BaseModel):
    """Information about a traveler."""
    first_name: str = Field(..., description="Traveler's first name")
    last_name: str = Field(..., description="Traveler's last name")
    email: str = Field(..., description="Traveler's email address")
    phone: Union[str, int] = Field(..., description="Traveler's phone number")
    date_of_birth: str = Field(..., description="Traveler's date of birth in YYYY-MM-DD format")
    gender: str = Field("MALE", description="Traveler's gender: MALE or FEMALE")
    
class FlightBookingInput(BaseModel):
    """Input schema for AmadeusBookingTool."""
    flight_offer: Dict[str, Any] = Field(..., description="Flight offer data to be booked")
    traveler_info: Dict[str, Any] = Field(..., description="Information about the traveler making the booking")
    
class AmadeusFlightBookingTool(BaseTool):
    name: str = "Amadeus Flight Booking Tool"
    description: str = "Book a flight using locally generated booking data"
    args_schema: type[BaseModel] = FlightBookingInput
    
    # Use PrivateAttr for internal state
    _logger = PrivateAttr(default=None)
    _last_booking = PrivateAttr(default=None)
    _last_search_response = PrivateAttr(default=None)
    
    def __init__(self, **data):
        super().__init__(**data)
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up logging for the tool"""
        self._logger = logging.getLogger('amadeus_booking')
        
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        if not self._logger.handlers:
            log_file = f"logs/amadeus_booking_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file)
            console_handler = logging.StreamHandler()
            
            formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            self._logger.addHandler(file_handler)
            self._logger.addHandler(console_handler)
            self._logger.setLevel(logging.INFO)
    
    @property
    def last_booking(self):
        """Property getter for last_booking"""
        return self._last_booking
    
    def _run(
        self,
        flight_offer: Dict[str, Any],
        traveler_info: Dict[str, Any]
    ) -> str:
        """Book a flight using locally generated data - no API calls."""
        self._logger.info("\n===== BOOKING FLIGHT =====")
        
        # Reset last booking
        self._last_booking = None
        
        self._logger.info("Flight booking requested")
        
        # Validate flight offer has essential data
        if not isinstance(flight_offer, dict):
            error_msg = f"Invalid flight offer format: {type(flight_offer)}"
            self._logger.error(error_msg)
            return error_msg
        
        # Process traveler info to ensure it has all required fields
        required_fields = ["first_name", "last_name", "email", "phone", "date_of_birth", "gender"]
        missing_fields = [field for field in required_fields if field not in traveler_info]
        
        if missing_fields:
            error_msg = f"Missing traveler information: {', '.join(missing_fields)}"
            self._logger.error(error_msg)
            return error_msg
        
        # Ensure phone is a string
        if "phone" in traveler_info and not isinstance(traveler_info["phone"], str):
            traveler_info["phone"] = str(traveler_info["phone"])
            self._logger.info("Converted phone number to string format")
        
        try:
            # Create a booking ID with timestamp for uniqueness
            booking_id = f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            
            # Generate a realistic PNR (6 uppercase letters)
            pnr = ''.join(random.choices(string.ascii_uppercase, k=6))
            
            # Generate eticket number based on carrier
            carrier_code = self._extract_carrier_code(flight_offer)
            eticket_number = self._generate_eticket_number(carrier_code)
            
            # Create a booking timestamp
            booking_timestamp = datetime.now().isoformat()
            
            # Create the mock booking structure (similar to API response)
            mock_booking = {
                "data": {
                    "type": "flight-order",
                    "id": booking_id,
                    "queuingOfficeId": "AMADEUS",
                    "associatedRecords": [
                        {
                            "reference": pnr,
                            "creationDateTime": booking_timestamp,
                            "originSystemCode": "AMADEUS",
                            "flightOfferId": flight_offer.get("id", "1")
                        }
                    ],
                    "travelers": [
                        {
                            "id": "1",
                            "dateOfBirth": traveler_info.get("date_of_birth", ""),
                            "name": {
                                "firstName": traveler_info.get("first_name", ""),
                                "lastName": traveler_info.get("last_name", "")
                            },
                            "gender": traveler_info.get("gender", ""),
                            "contact": {
                                "emailAddress": traveler_info.get("email", ""),
                                "phones": [
                                    {
                                        "deviceType": "MOBILE",
                                        "countryCallingCode": "1",
                                        "number": traveler_info.get("phone", "")
                                    }
                                ]
                            },
                            "documents": [
                                {
                                    "documentType": "TICKET",
                                    "number": eticket_number,
                                    "validityCountry": "US"
                                }
                            ]
                        }
                    ],
                    "flightOffers": [flight_offer],
                    "ticketingAgreement": {
                        "option": "DELAY_TO_CANCEL",
                        "delay": "6D"
                    }
                }
            }
            
            # Store the mock booking
            self._last_booking = mock_booking
            
            # Save the mock booking to a file
            self._save_booking_data(mock_booking)
            
            # Generate e-ticket PDF
            pdf_path = self.generate_booking_pdf(mock_booking)
            if pdf_path:
                self._logger.info(f"Generated e-ticket PDF: {pdf_path}")
                mock_booking["_pdf_path"] = pdf_path
            
            # Format and return the booking results
            return self._format_booking_results(mock_booking["data"])
                
        except Exception as e:
            error_msg = f"Error creating booking: {str(e)}"
            self._logger.error(error_msg)
            return error_msg
    
    def _extract_carrier_code(self, flight_offer: Dict[str, Any]) -> str:
        """Extract the primary carrier code from a flight offer"""
        # First, try to get the carrier directly from the flight offer
        if "carrier" in flight_offer:
            carrier = flight_offer["carrier"]
            if isinstance(carrier, str):
                # Handle full airline names by mapping to codes
                airline_mapping = {
                    "ALASKA AIRLINES": "AS",
                    "AMERICAN AIRLINES": "AA", 
                    "DELTA AIR LINES": "DL",
                    "UNITED AIRLINES": "UA",
                    "SOUTHWEST AIRLINES": "WN",
                    "JETBLUE AIRWAYS": "B6",
                    "FRONTIER AIRLINES": "F9",
                    "SPIRIT AIRLINES": "NK",
                    "LUFTHANSA": "LH",
                    "BRITISH AIRWAYS": "BA",
                    "AIR FRANCE": "AF",
                    "KLM": "KL"
                }
                
                # Check exact matches first
                if carrier.upper() in airline_mapping:
                    return airline_mapping[carrier.upper()]
                
                # Check for partial matches
                for name, code in airline_mapping.items():
                    if name in carrier.upper() or carrier.upper() in name:
                        return code
                
                # Check if the carrier is already a 2-letter code
                if len(carrier) == 2 and carrier.isalpha():
                    return carrier.upper()
                    
                # If it starts with a 2-letter code (like "AS435")
                if len(carrier) > 2 and carrier[:2].isalpha() and carrier[2:].isdigit():
                    return carrier[:2].upper()
        
        # Check itineraries/segments
        try:
            if "itineraries" in flight_offer and flight_offer["itineraries"]:
                for itinerary in flight_offer["itineraries"]:
                    if "segments" in itinerary and itinerary["segments"]:
                        for segment in itinerary["segments"]:
                            if "carrierCode" in segment:
                                return segment["carrierCode"]
        except:
            pass
        
        # Check validatingAirlineCodes
        if "validatingAirlineCodes" in flight_offer and flight_offer["validatingAirlineCodes"]:
            if isinstance(flight_offer["validatingAirlineCodes"], list) and flight_offer["validatingAirlineCodes"]:
                return flight_offer["validatingAirlineCodes"][0]
                
        # Default to Alaska Airlines as fallback
        return "AS"
    
    def _generate_eticket_number(self, airline_code: str) -> str:
        """Generate a realistic-looking e-ticket number (13 digits, starting with airline code)"""
        # Airline prefix - usually 3 digits based on airline code
        airline_prefix = {
            "AS": "027",
            "AA": "001",
            "DL": "006",
            "UA": "016",
            "WN": "526",
            "B6": "279",
            "LH": "220",
            "BA": "125"
        }.get(airline_code, "000")
        
        # Add 10 random digits after the airline prefix
        random_part = ''.join(random.choices(string.digits, k=10))
        return f"{airline_prefix}{random_part}"
    
    def _save_booking_data(self, booking_data: Dict[str, Any]) -> None:
        """Save the mock booking data to a JSON file"""
        if not os.path.exists("bookings"):
            os.makedirs("bookings")
            
        booking_id = booking_data["data"]["id"]
        booking_file = os.path.join("bookings", f"{booking_id}.json")
        
        with open(booking_file, "w") as f:
            json.dump(booking_data, f, indent=2)
            
        self._logger.info(f"Saved booking data to {booking_file}")
    
    def _format_booking_results(self, booking_data: Dict[str, Any]) -> str:
        """Format the booking results for better readability."""
        if not booking_data:
            return "No booking information available."
        
        # Format the basic information
        formatted_result = f"## Flight Booking Confirmation\n\n"
        
        # Add booking reference
        booking_id = booking_data.get("id", "N/A")
        formatted_result += f"**Booking Reference**: {booking_id}\n\n"
        
        # Add associated records (PNR)
        if "associatedRecords" in booking_data:
            formatted_result += "**Booking References**:\n"
            for record in booking_data["associatedRecords"]:
                formatted_result += f"- **PNR**: {record.get('reference', 'N/A')}\n"
                formatted_result += f"  Created: {record.get('creationDateTime', 'N/A')}\n"
                formatted_result += f"  System: {record.get('originSystemCode', 'N/A')}\n"
            formatted_result += "\n"
        
        # Add traveler information
        if "travelers" in booking_data:
            formatted_result += "**Passenger Information**:\n"
            for traveler in booking_data["travelers"]:
                traveler_id = traveler.get("id", "N/A")
                name = traveler.get("name", {})
                first_name = name.get("firstName", "N/A")
                last_name = name.get("lastName", "N/A")
                formatted_result += f"- Passenger {traveler_id}: {first_name} {last_name}\n"
                if "dateOfBirth" in traveler:
                    formatted_result += f"  Date of Birth: {traveler.get('dateOfBirth', 'N/A')}\n"
                if "gender" in traveler:
                    formatted_result += f"  Gender: {traveler.get('gender', 'N/A')}\n"
            formatted_result += "\n"
        
        # Add flight information
        if "flightOffers" in booking_data and booking_data["flightOffers"]:
            flight_offer = booking_data["flightOffers"][0]
            formatted_result += "**Flight Details**:\n"
            
            # Add price information
            if "price" in flight_offer:
                price = flight_offer["price"]
                
                # Handle different price formats
                if isinstance(price, dict):
                    currency = price.get("currency", "USD")
                    total = price.get("grandTotal", price.get("total", "N/A"))
                elif isinstance(price, str):
                    # Try to parse string as number
                    try:
                        total = price
                        currency = "USD"  # Default currency
                    except:
                        total = "N/A"
                        currency = ""
                else:
                    total = "N/A"
                    currency = ""
                    
                formatted_result += f"**Total Price**: {total} {currency}\n\n"
            
            # Add itinerary information
            if "itineraries" in flight_offer:
                for i, itinerary in enumerate(flight_offer["itineraries"], 1):
                    # Trip type indicator
                    trip_type = "Outbound" if i == 1 else "Return"
                    if len(flight_offer["itineraries"]) == 1:
                        trip_type = "Flight"
                    
                    formatted_result += f"**{trip_type} Journey**:\n"
                    
                    if "segments" in itinerary:
                        for j, segment in enumerate(itinerary["segments"], 1):
                            carrier_code = segment.get("carrierCode", "")
                            flight_number = segment.get("number", "")
                            
                            # Get departure info
                            departure = segment.get("departure", {})
                            dep_airport = departure.get("iataCode", "")
                            dep_terminal = departure.get("terminal", "")
                            dep_time = departure.get("at", "")
                            if dep_time:
                                try:
                                    dep_time = datetime.fromisoformat(dep_time.replace("Z", "+00:00"))
                                    dep_time = dep_time.strftime("%a, %b %d, %H:%M")
                                except:
                                    pass
                            
                            # Get arrival info
                            arrival = segment.get("arrival", {})
                            arr_airport = arrival.get("iataCode", "")
                            arr_terminal = arrival.get("terminal", "")
                            arr_time = arrival.get("at", "")
                            if arr_time:
                                try:
                                    arr_time = datetime.fromisoformat(arr_time.replace("Z", "+00:00"))
                                    arr_time = arr_time.strftime("%a, %b %d, %H:%M")
                                except:
                                    pass
                            
                            # Format segment info
                            formatted_result += f"- Flight: {carrier_code}{flight_number}\n"
                            formatted_result += f"  From: {dep_airport}"
                            if dep_terminal:
                                formatted_result += f" Terminal {dep_terminal}"
                            formatted_result += f" at {dep_time}\n"
                            
                            formatted_result += f"  To: {arr_airport}"
                            if arr_terminal:
                                formatted_result += f" Terminal {arr_terminal}"
                            formatted_result += f" at {arr_time}\n"
                            
                            if "duration" in segment:
                                duration = segment["duration"].replace("PT", "").replace("H", "h ").replace("M", "m")
                                formatted_result += f"  Duration: {duration}\n"
                                
                            # Add aircraft type if available
                            if "aircraft" in segment and "code" in segment["aircraft"]:
                                formatted_result += f"  Aircraft: {segment['aircraft']['code']}\n"
                                
                            formatted_result += "\n"
        
        # Add information about e-ticket PDF
        pdf_path = self._find_booking_pdf(booking_id)
        if pdf_path:
            formatted_result += f"**E-Ticket**: Your e-ticket has been generated and saved to: {pdf_path}\n\n"
        
        formatted_result += "**Important**: Please arrive at the airport at least 2 hours before your flight.\n"
        formatted_result += "Thank you for booking with us!\n"
        
        return formatted_result
    
    def _find_booking_pdf(self, booking_id: str) -> Optional[str]:
        """Find the PDF file for a booking if it exists"""
        if not os.path.exists("booking_pdfs"):
            return None
            
        # Look for PDF files that match this booking ID
        for filename in os.listdir("booking_pdfs"):
            if filename.startswith(f"eticket_") and booking_id in filename and filename.endswith(".pdf"):
                return os.path.join("booking_pdfs", filename)
                
        return None
    
    def generate_booking_pdf(self, booking_data: Dict[str, Any]) -> Optional[str]:
        """
        Generate a realistic-looking e-ticket PDF for the booking
        """
        try:
            # Import reportlab
            from reportlab.lib.pagesizes import letter
            from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib import colors
            from reportlab.lib.units import inch
            from reportlab.lib.enums import TA_CENTER
        except ImportError:
            self._logger.warning("ReportLab not available. Cannot generate e-ticket PDF.")
            return None
        
        try:
            # Extract necessary data
            if "data" in booking_data:
                data = booking_data["data"]
            else:
                data = booking_data  # Handle case where data is already unwrapped
                
            booking_id = data.get("id", f"ORDER_{datetime.now().strftime('%Y%m%d%H%M%S')}")
            
            # Get PNR
            pnr = "UNKNWN"
            if "associatedRecords" in data and data["associatedRecords"]:
                pnr = data["associatedRecords"][0].get("reference", "UNKNWN")
            
            # Get traveler details
            traveler_name = "Guest Traveler"
            traveler_email = ""
            if "travelers" in data and data["travelers"]:
                traveler = data["travelers"][0]
                if "name" in traveler:
                    first = traveler["name"].get("firstName", "")
                    last = traveler["name"].get("lastName", "")
                    if first or last:
                        traveler_name = f"{first} {last}".strip()
                traveler_email = traveler.get("contact", {}).get("emailAddress", "")
            
            # Generate ticket number if not already in the data
            ticket_number = None
            for traveler in data.get("travelers", []):
                for doc in traveler.get("documents", []):
                    if doc.get("documentType") == "TICKET":
                        ticket_number = doc.get("number")
                        break
                if ticket_number:
                    break
                    
            if not ticket_number:
                ticket_number = f"0{random.randint(10000000000, 99999999999)}"
                
            # Get flight offer data
            flight_offer = None
            if "flightOffers" in data and data["flightOffers"]:
                flight_offer = data["flightOffers"][0]
                
            if not flight_offer:
                self._logger.warning("No flight offer data found for PDF generation")
                return None
                
            # Get primary carrier code
            carrier_code = self._extract_carrier_code(flight_offer)
            
            # Airline info mapping
            airline_info = {
                "AS": {"name": "Alaska Airlines", "phone": "1-800-252-7522"},
                "AA": {"name": "American Airlines", "phone": "1-800-433-7300"},
                "DL": {"name": "Delta Air Lines", "phone": "1-800-221-1212"},
                "UA": {"name": "United Airlines", "phone": "1-800-864-8331"},
                "WN": {"name": "Southwest Airlines", "phone": "1-800-435-9792"},
                "B6": {"name": "JetBlue Airways", "phone": "1-800-538-2583"},
                "LH": {"name": "Lufthansa", "phone": "1-800-645-3880"},
                "BA": {"name": "British Airways", "phone": "1-800-247-9297"},
            }
            
            # Look up carrier info, or use generic placeholder if we can't find it
            if carrier_code in airline_info:
                carrier_name = airline_info[carrier_code]["name"]
                carrier_phone = airline_info[carrier_code]["phone"]
            else:
                # Use whatever information we have from the flight offer directly
                if "carrier" in flight_offer and isinstance(flight_offer["carrier"], str):
                    carrier_name = flight_offer["carrier"]  # Use exact carrier name from user input
                else:
                    carrier_name = f"{carrier_code} Airlines"  # Generic name based on code
                
                carrier_phone = "Please check airline website for contact information"
            
            # Ensure booking_pdfs directory exists
            if not os.path.exists("booking_pdfs"):
                os.makedirs("booking_pdfs")
                
            # Create PDF filename
            pdf_file_path = os.path.join("booking_pdfs", f"eticket_{pnr}_{booking_id}.pdf")
            
            # Create PDF document
            doc = SimpleDocTemplate(
                pdf_file_path,
                pagesize=letter,
                rightMargin=72,
                leftMargin=72,
                topMargin=72,
                bottomMargin=72,
                title=f"E-Ticket Receipt - {pnr}"
            )
            
            # Define styles
            styles = getSampleStyleSheet()
            title_style = ParagraphStyle(
                'Title',
                parent=styles['Heading1'],
                fontSize=16,
                alignment=TA_CENTER,
                spaceAfter=12
            )
            subtitle_style = ParagraphStyle(
                'Subtitle',
                parent=styles['Heading2'],
                fontSize=14,
                alignment=TA_CENTER,
                spaceAfter=10
            )
            header_style = ParagraphStyle(
                'Header',
                parent=styles['Heading3'],
                fontSize=12,
                spaceAfter=6
            )
            normal_style = styles['Normal']
            
            # Create elements for the PDF
            elements = []
            
            # Add title
            elements.append(Paragraph(f"{carrier_name} E-Ticket Receipt", title_style))
            elements.append(Spacer(1, 10))
            
            # Add booking reference section
            elements.append(Paragraph("Booking Information", header_style))
            
            booking_info_data = [
                ["Booking Reference (PNR):", pnr],
                ["E-Ticket Number:", ticket_number],
                ["Booking Date:", datetime.now().strftime("%d %b %Y")],
                ["Passenger Name:", traveler_name]
            ]
            
            booking_info_table = Table(booking_info_data, colWidths=[150, 300])
            booking_info_table.setStyle(TableStyle([
                ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, -1), 10),
                ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ]))
            elements.append(booking_info_table)
            elements.append(Spacer(1, 20))
            
            # Add flight information section
            elements.append(Paragraph("Flight Information", header_style))
            
            # Process each itinerary (outbound, return, etc.)
            if "itineraries" in flight_offer:
                for i, itinerary in enumerate(flight_offer.get("itineraries", [])):
                    trip_type = "Outbound" if i == 0 else "Return"
                    if len(flight_offer.get("itineraries", [])) == 1:
                        trip_type = "Flight"
                    
                    elements.append(Paragraph(f"{trip_type} Journey", subtitle_style))
                    
                    # Process each flight segment
                    for j, segment in enumerate(itinerary.get("segments", [])):
                        # Get segment details
                        carrier_code = segment.get("carrierCode", "")
                        flight_number = segment.get("number", "")
                        
                        airline_name = airline_info.get(carrier_code, {}).get("name", f"{carrier_code} Airlines")
                        
                        # Departure and arrival info
                        departure = segment.get("departure", {})
                        dep_airport = departure.get("iataCode", "")
                        dep_terminal = departure.get("terminal", "")
                        dep_time = departure.get("at", "")
                        if dep_time:
                            try:
                                dep_time = datetime.fromisoformat(dep_time.replace("Z", "+00:00"))
                                dep_time_str = dep_time.strftime("%d %b %Y, %H:%M")
                            except:
                                dep_time_str = dep_time
                        else:
                            dep_time_str = "N/A"
                            
                        arrival = segment.get("arrival", {})
                        arr_airport = arrival.get("iataCode", "")
                        arr_terminal = arrival.get("terminal", "")
                        arr_time = arrival.get("at", "")
                        if arr_time:
                            try:
                                arr_time = datetime.fromisoformat(arr_time.replace("Z", "+00:00"))
                                arr_time_str = arr_time.strftime("%d %b %Y, %H:%M")
                            except:
                                arr_time_str = arr_time
                        else:
                            arr_time_str = "N/A"
                        
                        # Create flight data table
                        flight_data = [
                            ["Flight:", f"{airline_name} {carrier_code}{flight_number}"],
                            ["From:", f"{dep_airport} {f'Terminal {dep_terminal}' if dep_terminal else ''}"],
                            ["Departure:", dep_time_str],
                            ["To:", f"{arr_airport} {f'Terminal {arr_terminal}' if arr_terminal else ''}"],
                            ["Arrival:", arr_time_str]
                        ]
                        
                        # Add aircraft type if available
                        if "aircraft" in segment and "code" in segment["aircraft"]:
                            aircraft_code = segment["aircraft"]["code"]
                            flight_data.append(["Aircraft:", aircraft_code])
                        
                        # Add cabin class
                        cabin = "Economy"
                        if "travelerPricings" in flight_offer:
                            for traveler_pricing in flight_offer["travelerPricings"]:
                                for fare_detail in traveler_pricing.get("fareDetailsBySegment", []):
                                    if "cabin" in fare_detail:
                                        cabin = fare_detail["cabin"].capitalize()
                                        break
                        
                        flight_data.append(["Cabin:", cabin])
                        
                        # Add baggage allowance
                        baggage_qty = 0
                        if "travelerPricings" in flight_offer:
                            for traveler_pricing in flight_offer["travelerPricings"]:
                                for fare_detail in traveler_pricing.get("fareDetailsBySegment", []):
                                    if "includedCheckedBags" in fare_detail:
                                        bags = fare_detail["includedCheckedBags"]
                                        if "quantity" in bags:
                                            baggage_qty = bags["quantity"]
                                            break
                        
                        flight_data.append(["Checked Baggage:", f"{baggage_qty} bag(s)"])
                        
                        # Create and add the flight table
                        flight_table = Table(flight_data, colWidths=[100, 350])
                        flight_table.setStyle(TableStyle([
                            ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                            ('FONTSIZE', (0, 0), (-1, -1), 10),
                            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                            ('BACKGROUND', (0, 0), (-1, 0), colors.lightgrey),
                        ]))
                        elements.append(flight_table)
                        elements.append(Spacer(1, 15))
            
            # Add price information
            if "price" in flight_offer:
                elements.append(Paragraph("Fare Information", header_style))
                
                price = flight_offer["price"]
                
                if isinstance(price, dict):
                    currency = price.get("currency", "")
                    
                    price_data = []
                    
                    if "base" in price:
                        price_data.append(["Base Fare:", f"{price['base']} {currency}"])
                    
                    if "total" in price:
                        price_data.append(["Total:", f"{price['total']} {currency}"])
                    elif "grandTotal" in price:
                        price_data.append(["Total:", f"{price['grandTotal']} {currency}"])
                else:
                    # Handle case where price is a string or number
                    price_data = [
                        ["Total:", str(price)]
                    ]
                
                price_table = Table(price_data, colWidths=[150, 300])
                price_table.setStyle(TableStyle([
                    ('FONTNAME', (0, 0), (0, -1), 'Helvetica-Bold'),
                    ('FONTSIZE', (0, 0), (-1, -1), 10),
                    ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
                    ('LINEBELOW', (0, -1), (-1, -1), 1, colors.black),
                ]))
                elements.append(price_table)
                elements.append(Spacer(1, 20))
            
            # Add important information
            elements.append(Paragraph("Important Information", header_style))
            elements.append(Paragraph("• Please arrive at the airport at least 2 hours before your flight departure time.", normal_style))
            elements.append(Paragraph("• Please check the latest travel requirements and restrictions.", normal_style))
            elements.append(Paragraph("• This electronic ticket is valid for the flights, date, and passenger listed only.", normal_style))
            elements.append(Paragraph(f"• In case of any issues, please contact {carrier_name} at {carrier_phone}.", normal_style))
            elements.append(Spacer(1, 25))
            
            # Add footer
            elements.append(Paragraph("This e-ticket was issued automatically.", normal_style))
            elements.append(Paragraph(f"Generated on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", normal_style))
            
            # Build the PDF
            doc.build(elements)
            
            return pdf_file_path
                
        except Exception as e:
            self._logger.error(f"Error generating e-ticket PDF: {str(e)}")
            import traceback
            self._logger.error(traceback.format_exc())
            return None
    
    def set_last_search_response(self, response):
        """Store the last search response for finding original flight offers"""
        self._last_search_response = response
        self._logger.info("Stored search response for future bookings")