from typing import Dict, List, Optional, Tuple, ClassVar
from pydantic import BaseModel, Field
from crewai.tools import BaseTool
import json
import os
import re

class AirportLookupInput(BaseModel):
    """Input schema for AirportCodeTool."""
    query: str = Field(..., description="Airport name, city name, or airport code to look up")

class AirportCodeTool(BaseTool):
    name: str = "Airport Code Lookup Tool"
    description: str = "Look up airport codes, airport names, or get airport information by city"
    args_schema: type[BaseModel] = AirportLookupInput

    # Dictionary of common airport codes and associated information - using ClassVar for Pydantic v2 compatibility
    AIRPORTS: ClassVar[Dict[str, Dict[str, str]]] = {
        # Major US airports
        "ATL": {"name": "Hartsfield-Jackson Atlanta International Airport", "city": "Atlanta", "country": "United States"},
        "LAX": {"name": "Los Angeles International Airport", "city": "Los Angeles", "country": "United States"},
        "ORD": {"name": "O'Hare International Airport", "city": "Chicago", "country": "United States"},
        "DFW": {"name": "Dallas/Fort Worth International Airport", "city": "Dallas", "country": "United States"},
        "DEN": {"name": "Denver International Airport", "city": "Denver", "country": "United States"},
        "JFK": {"name": "John F. Kennedy International Airport", "city": "New York", "country": "United States"},
        "SFO": {"name": "San Francisco International Airport", "city": "San Francisco", "country": "United States"},
        "SEA": {"name": "Seattle-Tacoma International Airport", "city": "Seattle", "country": "United States"},
        "LAS": {"name": "Harry Reid International Airport", "city": "Las Vegas", "country": "United States"},
        "MCO": {"name": "Orlando International Airport", "city": "Orlando", "country": "United States"},
        "EWR": {"name": "Newark Liberty International Airport", "city": "Newark", "country": "United States"},
        "MIA": {"name": "Miami International Airport", "city": "Miami", "country": "United States"},
        "PHX": {"name": "Phoenix Sky Harbor International Airport", "city": "Phoenix", "country": "United States"},
        "IAH": {"name": "George Bush Intercontinental Airport", "city": "Houston", "country": "United States"},
        "BOS": {"name": "Boston Logan International Airport", "city": "Boston", "country": "United States"},
        "DTW": {"name": "Detroit Metropolitan Wayne County Airport", "city": "Detroit", "country": "United States"},
        "MSP": {"name": "Minneapolis–Saint Paul International Airport", "city": "Minneapolis", "country": "United States"},
        "LGA": {"name": "LaGuardia Airport", "city": "New York", "country": "United States"},
        "PHL": {"name": "Philadelphia International Airport", "city": "Philadelphia", "country": "United States"},
        "CLT": {"name": "Charlotte Douglas International Airport", "city": "Charlotte", "country": "United States"},
        "IAD": {"name": "Washington Dulles International Airport", "city": "Washington", "country": "United States"},
        "DCA": {"name": "Ronald Reagan Washington National Airport", "city": "Washington", "country": "United States"},
        "BWI": {"name": "Baltimore/Washington International Airport", "city": "Baltimore", "country": "United States"},
        "MDW": {"name": "Chicago Midway International Airport", "city": "Chicago", "country": "United States"},
        "SAN": {"name": "San Diego International Airport", "city": "San Diego", "country": "United States"},
        "TPA": {"name": "Tampa International Airport", "city": "Tampa", "country": "United States"},
        "PDX": {"name": "Portland International Airport", "city": "Portland", "country": "United States"},
        "STL": {"name": "St. Louis Lambert International Airport", "city": "St. Louis", "country": "United States"},
        "MCI": {"name": "Kansas City International Airport", "city": "Kansas City", "country": "United States"},
        "CLE": {"name": "Cleveland Hopkins International Airport", "city": "Cleveland", "country": "United States"},
        
        # Major international airports
        "LHR": {"name": "London Heathrow Airport", "city": "London", "country": "United Kingdom"},
        "LGW": {"name": "London Gatwick Airport", "city": "London", "country": "United Kingdom"},
        "STN": {"name": "London Stansted Airport", "city": "London", "country": "United Kingdom"},
        "LTN": {"name": "London Luton Airport", "city": "London", "country": "United Kingdom"},
        "LCY": {"name": "London City Airport", "city": "London", "country": "United Kingdom"},
        "CDG": {"name": "Charles de Gaulle Airport", "city": "Paris", "country": "France"},
        "ORY": {"name": "Paris Orly Airport", "city": "Paris", "country": "France"},
        "AMS": {"name": "Amsterdam Airport Schiphol", "city": "Amsterdam", "country": "Netherlands"},
        "FRA": {"name": "Frankfurt Airport", "city": "Frankfurt", "country": "Germany"},
        "MUC": {"name": "Munich Airport", "city": "Munich", "country": "Germany"},
        "ZRH": {"name": "Zurich Airport", "city": "Zurich", "country": "Switzerland"},
        "VIE": {"name": "Vienna International Airport", "city": "Vienna", "country": "Austria"},
        "MAD": {"name": "Adolfo Suárez Madrid–Barajas Airport", "city": "Madrid", "country": "Spain"},
        "BCN": {"name": "Josep Tarradellas Barcelona-El Prat Airport", "city": "Barcelona", "country": "Spain"},
        "FCO": {"name": "Leonardo da Vinci–Fiumicino Airport", "city": "Rome", "country": "Italy"},
        "MXP": {"name": "Milan Malpensa Airport", "city": "Milan", "country": "Italy"},
        "IST": {"name": "Istanbul Airport", "city": "Istanbul", "country": "Turkey"},
        "DXB": {"name": "Dubai International Airport", "city": "Dubai", "country": "United Arab Emirates"},
        "DOH": {"name": "Hamad International Airport", "city": "Doha", "country": "Qatar"},
        "AUH": {"name": "Abu Dhabi International Airport", "city": "Abu Dhabi", "country": "United Arab Emirates"},
        "HKG": {"name": "Hong Kong International Airport", "city": "Hong Kong", "country": "China"},
        "ICN": {"name": "Incheon International Airport", "city": "Seoul", "country": "South Korea"},
        "SIN": {"name": "Singapore Changi Airport", "city": "Singapore", "country": "Singapore"},
        "KUL": {"name": "Kuala Lumpur International Airport", "city": "Kuala Lumpur", "country": "Malaysia"},
        "BKK": {"name": "Suvarnabhumi Airport", "city": "Bangkok", "country": "Thailand"},
        "NRT": {"name": "Narita International Airport", "city": "Tokyo", "country": "Japan"},
        "HND": {"name": "Tokyo Haneda Airport", "city": "Tokyo", "country": "Japan"},
        "PEK": {"name": "Beijing Capital International Airport", "city": "Beijing", "country": "China"},
        "PVG": {"name": "Shanghai Pudong International Airport", "city": "Shanghai", "country": "China"},
        "CAN": {"name": "Guangzhou Baiyun International Airport", "city": "Guangzhou", "country": "China"},
        "SYD": {"name": "Sydney Airport", "city": "Sydney", "country": "Australia"},
        "MEL": {"name": "Melbourne Airport", "city": "Melbourne", "country": "Australia"},
        "AKL": {"name": "Auckland Airport", "city": "Auckland", "country": "New Zealand"},
        "YYZ": {"name": "Toronto Pearson International Airport", "city": "Toronto", "country": "Canada"},
        "YVR": {"name": "Vancouver International Airport", "city": "Vancouver", "country": "Canada"},
        "YUL": {"name": "Montréal–Trudeau International Airport", "city": "Montreal", "country": "Canada"},
        "YYC": {"name": "Calgary International Airport", "city": "Calgary", "country": "Canada"},
        "MEX": {"name": "Mexico City International Airport", "city": "Mexico City", "country": "Mexico"},
        "GRU": {"name": "São Paulo/Guarulhos International Airport", "city": "São Paulo", "country": "Brazil"},
        "GIG": {"name": "Rio de Janeiro/Galeão International Airport", "city": "Rio de Janeiro", "country": "Brazil"},
        "EZE": {"name": "Ezeiza International Airport", "city": "Buenos Aires", "country": "Argentina"},
        "JNB": {"name": "O.R. Tambo International Airport", "city": "Johannesburg", "country": "South Africa"},
        "CPT": {"name": "Cape Town International Airport", "city": "Cape Town", "country": "South Africa"},
        "CAI": {"name": "Cairo International Airport", "city": "Cairo", "country": "Egypt"},
        
        # City codes for areas with multiple airports
        "NYC": {"name": "All New York City airports", "city": "New York", "country": "United States", "airports": ["JFK", "LGA", "EWR"]},
        "LON": {"name": "All London airports", "city": "London", "country": "United Kingdom", "airports": ["LHR", "LGW", "STN", "LTN", "LCY"]},
        "PAR": {"name": "All Paris airports", "city": "Paris", "country": "France", "airports": ["CDG", "ORY"]},
        "TYO": {"name": "All Tokyo airports", "city": "Tokyo", "country": "Japan", "airports": ["NRT", "HND"]},
        "CHI": {"name": "All Chicago airports", "city": "Chicago", "country": "United States", "airports": ["ORD", "MDW"]},
        "WAS": {"name": "All Washington DC airports", "city": "Washington", "country": "United States", "airports": ["IAD", "DCA", "BWI"]},
        "MIL": {"name": "All Milan airports", "city": "Milan", "country": "Italy", "airports": ["MXP", "LIN"]},
        "BER": {"name": "All Berlin airports", "city": "Berlin", "country": "Germany", "airports": ["BER", "TXL", "SXF"]},
    }
    
    # City name mapping to help with city searches - also using ClassVar
    CITY_MAPPING: ClassVar[Dict[str, str]] = {
        # Common variations of city names
        "new york": "NYC",
        "nyc": "NYC",
        "los angeles": "LAX",
        "la": "LAX",
        "chicago": "CHI",
        "san francisco": "SFO",
        "san fran": "SFO",
        "sf": "SFO",
        "washington": "WAS",
        "washington dc": "WAS",
        "dc": "WAS",
        "london": "LON",
        "paris": "PAR",
        "tokyo": "TYO",
        "new york city": "NYC",
        "washington d.c.": "WAS",
        "san diego": "SAN",
        "dallas": "DFW",
        "toronto": "YYZ",
        "vancouver": "YVR",
        "montreal": "YUL",
        "sydney": "SYD",
        "beijing": "PEK",
        "shanghai": "PVG",
        "bangkok": "BKK",
        "singapore": "SIN",
        "seoul": "ICN",
        "hong kong": "HKG",
        "dubai": "DXB",
        "amsterdam": "AMS",
        "frankfurt": "FRA",
        "munich": "MUC",
        "zurich": "ZRH",
        "madrid": "MAD",
        "barcelona": "BCN",
        "rome": "FCO",
        "milan": "MIL",
        "istanbul": "IST",
    }
    
    def _run(self, query: str) -> str:
        """Look up airport information based on the query."""
        query = query.strip()
        original_query = query
        query_upper = query.upper()
        
        # Check if the query is directly an airport code
        if query_upper in self.AIRPORTS:
            return self._format_airport_info(query_upper, self.AIRPORTS[query_upper])
        
        # Check if a lowercase version might be a city in our mapping
        if query.lower() in self.CITY_MAPPING:
            mapped_code = self.CITY_MAPPING[query.lower()]
            return self._format_airport_info(mapped_code, self.AIRPORTS[mapped_code])
        
        # Search by city name
        city_matches = []
        for code, info in self.AIRPORTS.items():
            if query.lower() == info.get("city", "").lower():
                city_matches.append((code, info))
        
        if city_matches:
            if len(city_matches) == 1:
                code, info = city_matches[0]
                return self._format_airport_info(code, info)
            else:
                response = f"Multiple airports found for '{original_query}':\n\n"
                for code, info in city_matches:
                    response += f"• {code}: {info['name']}, {info['city']}, {info['country']}\n"
                return response
        
        # Search by partial name match
        name_matches = []
        for code, info in self.AIRPORTS.items():
            if query.lower() in info.get("name", "").lower():
                name_matches.append((code, info))
        
        if name_matches:
            if len(name_matches) == 1:
                code, info = name_matches[0]
                return self._format_airport_info(code, info)
            else:
                response = f"Multiple airports found matching '{original_query}':\n\n"
                for code, info in name_matches:
                    response += f"• {code}: {info['name']}, {info['city']}, {info['country']}\n"
                return response
        
        # Search by country
        country_matches = []
        for code, info in self.AIRPORTS.items():
            if "country" in info and query.lower() in info["country"].lower():
                country_matches.append((code, info))
        
        if country_matches:
            response = f"Airports found in '{original_query}':\n\n"
            # Limit to 10 results to avoid overwhelming responses
            for code, info in country_matches[:10]:
                response += f"• {code}: {info['name']}, {info['city']}, {info['country']}\n"
            
            if len(country_matches) > 10:
                response += f"\n...and {len(country_matches) - 10} more airports."
            
            return response
        
        # Fuzzy matching for common typos or variations
        fuzzy_matches = []
        for city, code in self.CITY_MAPPING.items():
            # Calculate similarity ratio (very simple implementation)
            similarity = self._simple_similarity(query.lower(), city)
            if similarity > 0.7:  # Threshold for considering it a match
                fuzzy_matches.append((city, code, similarity))

        if fuzzy_matches:
            # Sort by similarity score (descending)
            fuzzy_matches.sort(key=lambda x: x[2], reverse=True)
            
            if len(fuzzy_matches) == 1 or fuzzy_matches[0][2] > 0.9:  # High confidence match
                city, code, score = fuzzy_matches[0]
                return f"Closest match found for '{original_query}':\n{self._format_airport_info(code, self.AIRPORTS[code])}"
            else:
                # Multiple possible matches
                response = f"Did you mean one of these locations?\n\n"
                for city, code, score in fuzzy_matches[:5]:  # Top 5 matches
                    info = self.AIRPORTS[code]
                    response += f"• {city.title()} ({code}): {info['name']}, {info['country']}\n"
                return response

        # Extract potential airport codes from query (3-letter sequences)
        potential_codes = re.findall(r'\b[A-Za-z]{3}\b', query_upper)
        for potential_code in potential_codes:
            if potential_code in self.AIRPORTS:
                return self._format_airport_info(potential_code, self.AIRPORTS[potential_code])

        # If no match found
        return f"No airport information found for '{original_query}'. Please try a different search term, a city name, or a valid 3-letter IATA airport code."

    def _simple_similarity(self, s1: str, s2: str) -> float:
        """
        Calculate a simple similarity score between two strings.
        1.0 means identical, 0.0 means completely different.
        """
        # Simple implementation using character comparison
        if not s1 or not s2:
            return 0.0
        
        # Convert both strings to lowercase and remove non-alphanumeric characters
        s1 = ''.join(c.lower() for c in s1 if c.isalnum())
        s2 = ''.join(c.lower() for c in s2 if c.isalnum())
        
        # Handle exact matches
        if s1 == s2:
            return 1.0
        
        # Handle one string being a substring of the other
        if s1 in s2:
            return len(s1) / len(s2)
        if s2 in s1:
            return len(s2) / len(s1)
        
        # Count common characters
        common_chars = sum(1 for c in s1 if c in s2)
        total_chars = len(s1) + len(s2)
        
        # Calculate Jaccard-like similarity
        return (2 * common_chars) / total_chars

    def _format_airport_info(self, code: str, info: Dict) -> str:
        """Format airport information into a readable string."""
        response = f"Airport Code: {code}\n"
        response += f"Airport Name: {info.get('name', 'N/A')}\n"
        response += f"City: {info.get('city', 'N/A')}\n"
        response += f"Country: {info.get('country', 'N/A')}\n"
        
        # If this is a city code with multiple airports
        if "airports" in info:
            response += "\nThis city code represents multiple airports:\n"
            for airport_code in info["airports"]:
                if airport_code in self.AIRPORTS:
                    airport = self.AIRPORTS[airport_code]
                    response += f"• {airport_code}: {airport['name']}\n"
        
        return response