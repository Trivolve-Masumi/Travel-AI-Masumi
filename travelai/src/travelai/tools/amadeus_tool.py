import os
import json
import requests
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional
from pydantic import BaseModel, Field, PrivateAttr
from crewai.tools import BaseTool

class FlightSearchInput(BaseModel):
    """Input schema for AmadeusFlightSearchTool."""
    origin: str = Field(..., description="The IATA code of the origin airport or city (e.g., 'NYC', 'JFK')")
    destination: str = Field(..., description="The IATA code of the destination airport or city (e.g., 'PAR', 'CDG')")
    departure_date: str = Field(..., description="The departure date in YYYY-MM-DD format")
    return_date: Optional[str] = Field(None, description="The return date in YYYY-MM-DD format (for round trip)")
    adults: int = Field(1, description="Number of adult travelers")
    children: int = Field(0, description="Number of child travelers")
    infants: int = Field(0, description="Number of infant travelers")
    travel_class: Optional[str] = Field(None, description="Travel class: ECONOMY, PREMIUM_ECONOMY, BUSINESS, or FIRST")
    non_stop: bool = Field(False, description="Whether to find only non-stop flights")
    currency: Optional[str] = Field(None, description="Currency code for prices (e.g., 'USD')")
    max_price: Optional[int] = Field(None, description="Maximum price per traveler")
    max_results: Optional[int] = Field(10, description="Maximum number of results to return")

class AmadeusFlightSearchTool(BaseTool):
    name: str = "Amadeus Flight Search Tool"
    description: str = "Search for flights using the Amadeus Flight Offers Search API"
    args_schema: type[BaseModel] = FlightSearchInput
    
    # Use PrivateAttr for the logger and last_response
    _logger = PrivateAttr(default=None)
    _last_response = PrivateAttr(default=None)
    
    def __init__(self, **data):
        super().__init__(**data)
        self._setup_logging()
    
    def _setup_logging(self):
        """Set up logging for the tool"""
        self._logger = logging.getLogger('amadeus_flight_search')
        
        if not os.path.exists('logs'):
            os.makedirs('logs')
            
        if not self._logger.handlers:
            log_file = f"logs/amadeus_flight_search_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
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
        children: int = 0,
        infants: int = 0,
        travel_class: Optional[str] = None,
        non_stop: bool = False,
        currency: Optional[str] = None,
        max_price: Optional[int] = None,
        max_results: Optional[int] = 10
    ) -> str:
        """Search for flights using the Amadeus API."""
        self._logger.info(f"Flight search: {origin} to {destination} on {departure_date}")
        
        # Reset last response
        self._last_response = None
        
        # Get access token
        try:
            access_token = self._get_access_token()
        except Exception as e:
            self._logger.error(f"Authentication error: {str(e)}")
            return f"Error connecting to Amadeus API: {str(e)}"
        
        # Build the base URL for the API request
        base_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        
        # Build query parameters
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date,
            "adults": adults,
            "max": max_results
        }
        
        # Add optional parameters if provided
        if return_date:
            params["returnDate"] = return_date
        if children > 0:
            params["children"] = children
        if infants > 0:
            params["infants"] = infants
        if travel_class:
            params["travelClass"] = travel_class
        if non_stop:
            params["nonStop"] = "true"
        if currency:
            params["currencyCode"] = currency
        if max_price:
            params["maxPrice"] = max_price
        
        self._logger.info(f"Request parameters: {json.dumps(params, indent=2)}")
        
        # Make the API request
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        try:
            self._logger.info(f"Sending request to {base_url}")
            start_time = datetime.now()
            
            response = requests.get(base_url, params=params, headers=headers)
            
            end_time = datetime.now()
            duration = (end_time - start_time).total_seconds()
            self._logger.info(f"API response received in {duration:.2f} seconds")
            self._logger.info(f"Response status code: {response.status_code}")
            
            # Save raw response
            self._save_api_response(response, origin, destination)
            
            # Process the response
            if response.status_code == 200:
                try:
                    # Parse JSON response
                    flight_data = response.json()
                    
                    # Store the raw response
                    self._last_response = flight_data
                    
                    # Check if any flights were found
                    flight_count = len(flight_data.get('data', []))
                    self._logger.info(f"Found {flight_count} flights")
                    
                    if flight_count == 0:
                        return f"No flights found for {origin} to {destination} on {departure_date}. Please try different dates or airports."
                    
                    # Format the results for display
                    formatted_results = self._format_flight_results(flight_data)
                    return formatted_results
                    
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
                    return f"Flight search error: {error_msg} (Code: {error_code})"
                except:
                    error_msg = f"API error {response.status_code}: {response.text[:500]}"
                    self._logger.error(error_msg)
                    return f"Flight search failed: HTTP {response.status_code}"
                    
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
        response_file = f"api_responses/search_{origin}_{destination}_{timestamp}.txt"
        
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
                json_file = f"api_responses/search_{origin}_{destination}_{timestamp}.json"
                with open(json_file, 'w') as f:
                    json.dump(json_data, f, indent=2)
                self._logger.info(f"Structured API response saved to {json_file}")
        except:
            self._logger.warning("Could not save structured JSON response")

    def _format_flight_results(self, flight_data: Dict[str, Any]) -> str:
        """Format the flight results for better readability."""
        results = []
        results.append("## Available Flight Options\n")
        
        # Get dictionaries for lookups
        dictionaries = flight_data.get("dictionaries", {})
        carriers = dictionaries.get("carriers", {})
        aircraft = dictionaries.get("aircraft", {})
        
        # Process each flight offer
        for i, offer in enumerate(flight_data["data"][:10], 1):
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
                
                # Process segments
                for k, segment in enumerate(itinerary["segments"], 1):
                    # Carrier information
                    carrier_code = segment["carrierCode"]
                    carrier_name = carriers.get(carrier_code, carrier_code)
                    flight_number = segment["number"]
                    
                    results.append(f"**Flight**: {carrier_name} {carrier_code}{flight_number}")
                    
                    # Aircraft type
                    aircraft_code = segment.get("aircraft", {}).get("code", "")
                    aircraft_name = aircraft.get(aircraft_code, aircraft_code)
                    
                    # Departure information
                    departure = segment["departure"]
                    dep_time = self._format_datetime(departure["at"])
                    dep_airport = departure["iataCode"]
                    dep_terminal = departure.get("terminal", "")
                    
                    dep_info = f"**From**: {dep_airport}"
                    if dep_terminal:
                        dep_info += f" Terminal {dep_terminal}"
                    dep_info += f" at {dep_time}"
                    results.append(dep_info)
                    
                    # Arrival information
                    arrival = segment["arrival"]
                    arr_time = self._format_datetime(arrival["at"])
                    arr_airport = arrival["iataCode"]
                    arr_terminal = arrival.get("terminal", "")
                    
                    arr_info = f"**To**: {arr_airport}"
                    if arr_terminal:
                        arr_info += f" Terminal {arr_terminal}"
                    arr_info += f" at {arr_time}"
                    results.append(arr_info)
                    
                    # Duration
                    if "duration" in segment:
                        seg_duration = segment["duration"].replace("PT", "")
                        seg_duration = seg_duration.replace("H", "h ").replace("M", "m")
                        results.append(f"**Duration**: {seg_duration}")
                    
                    # Add aircraft info if available
                    if aircraft_name:
                        results.append(f"**Aircraft**: {aircraft_name}")
                    
                    # Add a separator between segments
                    if k < len(itinerary["segments"]):
                        results.append(f"*Connection time: TBD*\n")
            
            # Add pricing details
            results.append("**Pricing**:")
            if "base" in offer["price"]:
                results.append(f"- Base Fare: {offer['price']['base']} {currency}")
            results.append(f"- Total (inc. taxes): {offer['price']['grandTotal']} {currency}")
            
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
            cabin_class = "Economy"
            if offer.get("travelerPricings"):
                cabin_classes = []
                for traveler_pricing in offer["travelerPricings"]:
                    for segment_pricing in traveler_pricing.get("fareDetailsBySegment", []):
                        if segment_pricing.get("cabin") and segment_pricing["cabin"] not in cabin_classes:
                            cabin_classes.append(segment_pricing["cabin"])
                
                if cabin_classes:
                    cabin_class = ", '.join'".join([c.capitalize() for c in cabin_classes])
            
            results.append(f"**Cabin**: {cabin_class}")
            
            results.append("\n---\n")  # Add separator between flight options
        
        return "\n".join(results)

    def _format_datetime(self, datetime_str: str) -> str:
        """Format datetime string to a more readable format."""
        try:
            dt = datetime.fromisoformat(datetime_str.replace("Z", "+00:00"))
            return dt.strftime("%a, %b %d, %H:%M")
        except Exception:
            return datetime_str