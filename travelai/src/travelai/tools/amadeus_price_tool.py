import os
import json
import requests
import logging
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, PrivateAttr
from crewai.tools import BaseTool
from datetime import datetime

class FlightOfferPriceInput(BaseModel):
    """Input schema for AmadeusPriceTool."""
    origin: str = Field(..., description="The IATA code of the origin airport or city")
    destination: str = Field(..., description="The IATA code of the destination airport or city")
    departure_date: str = Field(..., description="The departure date in YYYY-MM-DD format")
    return_date: Optional[str] = Field(None, description="The return date in YYYY-MM-DD format (for round trip)")
    adults: int = Field(1, description="Number of adult travelers")
    flight_number: Optional[str] = Field(None, description="Flight number if known")
    carrier_code: Optional[str] = Field(None, description="Carrier code if known")
    
class AmadeusFlightPriceTool(BaseTool):
    name: str = "Amadeus Flight Price Tool"
    description: str = "Verify and confirm the final price of flights by searching again with the same parameters"
    args_schema: type[BaseModel] = FlightOfferPriceInput
    
    # Use PrivateAttr for the logger and last_response
    _logger = PrivateAttr(default=None)
    _last_response = PrivateAttr(default=None)
    
    def __init__(self, **data):
        super().__init__(**data)
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up logging for the tool"""
        self._logger = logging.getLogger('amadeus_price_tool')
        
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        if not self._logger.handlers:
            log_file = f"logs/amadeus_price_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file)
            console_handler = logging.StreamHandler()
            
            formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            self._logger.addHandler(file_handler)
            self._logger.addHandler(console_handler)
            self._logger.setLevel(logging.INFO)
    
    def _get_access_token(self) -> str:
        """Get an access token from the Amadeus API."""
        url = "https://test.api.amadeus.com/v1/security/oauth2/token"
        
        api_key = os.getenv("AMADEUS_API_KEY")
        api_secret = os.getenv("AMADEUS_API_SECRET")
        
        if not api_key or not api_secret:
            error_msg = "Missing Amadeus API credentials"
            self._logger.error(error_msg)
            raise ValueError(error_msg)
        
        payload = {
            "grant_type": "client_credentials",
            "client_id": api_key,
            "client_secret": api_secret
        }
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        
        self._logger.info("Getting Amadeus API access token")
        response = requests.post(url, data=payload, headers=headers)
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            
            if not access_token:
                error_msg = "Access token not found in response"
                self._logger.error(error_msg)
                raise ValueError(error_msg)
                
            self._logger.info(f"Got access token: {access_token[:10]}...")
            return access_token
        else:
            error_msg = f"Failed to get access token: HTTP {response.status_code}"
            self._logger.error(f"{error_msg}: {response.text}")
            raise Exception(error_msg)
    
    def _run(
        self,
        origin: str,
        destination: str,
        departure_date: str,
        return_date: Optional[str] = None,
        adults: int = 1,
        flight_number: Optional[str] = None,
        carrier_code: Optional[str] = None
    ) -> str:
        """Verify and confirm the final price by searching with the same parameters."""
        self._logger.info(f"Verifying prices for flights: {origin} to {destination} on {departure_date}")
        
        # Reset last response
        self._last_response = None
        
        # Verify API credentials exist
        if not os.getenv("AMADEUS_API_KEY") or not os.getenv("AMADEUS_API_SECRET"):
            error_msg = "No Amadeus API credentials found. Cannot verify flight prices."
            self._logger.error(error_msg)
            return error_msg
        
        # Get access token
        try:
            access_token = self._get_access_token()
        except Exception as e:
            self._logger.error(f"Authentication error: {str(e)}")
            return f"Error connecting to Amadeus API: {str(e)}"
            
        # Build query parameters for the search API
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": adults,
            "max": 5  # Limit results for efficiency
        }
        
        # Add optional parameters if provided
        if return_date:
            params["returnDate"] = return_date
        
        self._logger.info(f"Request parameters: {json.dumps(params, indent=2)}")
        
        # API endpoint
        base_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        try:
            self._logger.info(f"Sending request to {base_url}")
            start_time = datetime.now()
            
            # Execute API call
            response = requests.get(base_url, params=params, headers=headers)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            self._logger.info(f"API response received in {duration:.2f} seconds")
            self._logger.info(f"Response status code: {response.status_code}")
            
            # Save the raw response
            self._save_api_response(response, origin, destination)
            
            # Process the response
            if response.status_code == 200:
                try:
                    # Parse JSON response
                    flight_data = response.json()
                    
                    # Store the raw flight data
                    self._last_response = flight_data
                    
                    # Check if any flights were found
                    flight_count = len(flight_data.get('data', []))
                    self._logger.info(f"Found {flight_count} flights")
                    
                    if flight_count == 0:
                        return f"No flights found for {origin} to {destination} on {departure_date}. Please try different dates or airports."
                    
                    # If specific flight number is provided, filter results
                    if flight_number and carrier_code:
                        self._logger.info(f"Filtering for specific flight: {carrier_code}{flight_number}")
                        matching_flights = []
                        for offer in flight_data.get("data", []):
                            for itinerary in offer.get("itineraries", []):
                                for segment in itinerary.get("segments", []):
                                    if (segment.get("carrierCode") == carrier_code and 
                                        segment.get("number") == flight_number):
                                        matching_flights.append(offer)
                                        break
                        
                        if matching_flights:
                            self._logger.info(f"Found {len(matching_flights)} matching the specified flight")
                            # Replace the data with filtered results
                            flight_data["data"] = matching_flights
                        else:
                            self._logger.warning(f"No matches found for flight {carrier_code}{flight_number}")
                            return f"Could not find prices for flight {carrier_code}{flight_number}. Please verify the flight details."
                    
                    # Format the price verification results
                    return self._format_price_verification_results(flight_data)
                    
                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON response: {str(e)}"
                    self._logger.error(error_msg)
                    return f"Error processing API response: {error_msg}"
                    
                except Exception as e:
                    error_msg = f"Error processing API response: {str(e)}"
                    self._logger.error(error_msg)
                    return f"Error processing flight data: {error_msg}"
            
            else:
                # Handle error response
                try:
                    error_data = response.json()
                    error_details = error_data.get('errors', [{}])[0]
                    error_msg = f"API Error: {error_details.get('detail', 'Unknown error')}"
                    error_code = error_details.get('code', 'unknown')
                    
                    self._logger.error(f"API error {error_code}: {error_msg}")
                    return f"Price verification error: {error_msg} (Code: {error_code})"
                except:
                    error_msg = f"API error {response.status_code}: {response.text[:500]}"
                    self._logger.error(error_msg)
                    return f"Price verification failed: HTTP {response.status_code}"
                    
        except requests.exceptions.ConnectionError as e:
            error_msg = f"Connection error: {str(e)}"
            self._logger.error(error_msg)
            return f"Connection error: Could not connect to Amadeus API"
        except requests.exceptions.Timeout as e:
            error_msg = f"Timeout error: {str(e)}"
            self._logger.error(error_msg)
            return f"Request timeout: The API request took too long to complete"
        except Exception as e:
            error_msg = f"Unexpected error: {str(e)}"
            self._logger.error(error_msg)
            return f"An unexpected error occurred: {str(e)}"
    
    def _save_api_response(self, response, origin, destination):
        """Save API response for debugging and auditing"""
        # Create directory for saving responses if it doesn't exist
        if not os.path.exists('api_responses'):
            os.makedirs('api_responses')
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        response_file = f"api_responses/price_{origin}_{destination}_{timestamp}.txt"
        
        # Save raw response to file
        with open(response_file, 'w') as f:
            f.write(f"URL: {response.url}\n")
            f.write(f"Status: {response.status_code}\n")
            f.write(f"Headers: {dict(response.headers)}\n\n")
            f.write("Body:\n")
            f.write(response.text)
        
        self._logger.info(f"Raw API response saved to {response_file}")
        
        # Save structured JSON if available
        try:
            if response.status_code == 200:
                json_data = response.json()
                json_file = f"api_responses/price_{origin}_{destination}_{timestamp}.json"
                with open(json_file, 'w') as f:
                    json.dump(json_data, f, indent=2)
                self._logger.info(f"Structured API response saved to {json_file}")
        except:
            self._logger.warning("Could not save structured JSON response")

    def _format_price_verification_results(self, flight_data: Dict[str, Any]) -> str:
        """Format the price verification results for better readability."""
        # Get dictionaries for lookups
        dictionaries = flight_data.get("dictionaries", {})
        carriers = dictionaries.get("carriers", {})
        aircraft = dictionaries.get("aircraft", {})
        
        results = []
        results.append("## Verified Flight Prices\n")
        
        # Process each flight offer
        for i, offer in enumerate(flight_data["data"][:5], 1):  # Limit to top 5 results
            # Basic offer information
            price = offer["price"]["grandTotal"]
            currency = offer["price"]["currency"]
            offer_id = offer.get("id", "Unknown")
            
            # Create a section for this flight option
            results.append(f"### Option {i}: {price} {currency} (ID: {offer_id})")
            
            # Process each itinerary
            for j, itinerary in enumerate(offer["itineraries"], 1):
                # Trip type indicator
                trip_type = "Outbound" if j == 1 else "Return"
                if len(offer["itineraries"]) == 1:
                    trip_type = "Flight"
                
                # Duration
                duration = itinerary["duration"].replace("PT", "")
                duration = duration.replace("H", "h ").replace("M", "m")
                
                # Count stops
                stops = len(itinerary["segments"]) - 1
                stop_text = "Nonstop" if stops == 0 else f"{stops} stop{'s' if stops > 1 else ''}"
                
                results.append(f"**{trip_type}**: {stop_text} • {duration}")
                
                # Get carrier, flight and cabin info
                segments_info = []
                for segment in itinerary["segments"]:
                    carrier_code = segment["carrierCode"]
                    carrier_name = carriers.get(carrier_code, carrier_code)
                    flight_number = segment["number"]
                    
                    segments_info.append(f"{carrier_name} {carrier_code}{flight_number}")
                
                results.append("**Flights**: " + ", ".join(segments_info))
            
            # Add pricing details in a clear table format
            results.append("**Pricing Breakdown**:")
            if "base" in offer["price"]:
                results.append(f"- Base Fare: {offer['price']['base']} {currency}")
            if "total" in offer["price"]:
                results.append(f"- Total (inc. taxes): {offer['price']['total']} {currency}")
            if "grandTotal" in offer["price"]:
                results.append(f"- Grand Total: {offer['price']['grandTotal']} {currency}")
            
            # Add baggage information
            baggage_info = []
            if offer.get("travelerPricings"):
                for traveler_pricing in offer["travelerPricings"]:
                    for segment_pricing in traveler_pricing.get("fareDetailsBySegment", []):
                        if "includedCheckedBags" in segment_pricing:
                            bags = segment_pricing["includedCheckedBags"]
                            if "quantity" in bags:
                                baggage_info.append(f"Checked Bags: {bags['quantity']} included")
                                break
                            elif "weight" in bags and "weightUnit" in bags:
                                baggage_info.append(f"Checked Baggage: {bags['weight']} {bags['weightUnit']}")
                                break
            
            if baggage_info:
                results.append(f"**Baggage**: {', '.join(baggage_info)}")
            
            # Add cabin class info
            cabin_class = "Unknown"
            if offer.get("travelerPricings"):
                cabin_classes = []
                for traveler_pricing in offer["travelerPricings"]:
                    for segment_pricing in traveler_pricing.get("fareDetailsBySegment", []):
                        if segment_pricing.get("cabin") and segment_pricing["cabin"] not in cabin_classes:
                            cabin_classes.append(segment_pricing["cabin"])
                
                if cabin_classes:
                    cabin_class = ", ".join([c.capitalize() for c in cabin_classes])
            
            results.append(f"**Cabin**: {cabin_class}")
            
            results.append("\n---\n")  # Add separator between flight options
        
        if len(flight_data["data"]) > 5:
            results.append(f"*Showing top 5 of {len(flight_data['data'])} available flights.*")
        
        return "\n".join(results)