#!/usr/bin/env python
import os
import json
from datetime import datetime
from dotenv import load_dotenv
import sys

def test_flight_search():
    # Add the project root to sys.path
    sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__))))
    
    # Import after path adjustment - updated to match your structure
    from src.travelai.tools.amadeus_tool import AmadeusFlightSearchTool
    
    load_dotenv()  # Load environment variables
    
    # Create the search tool
    search_tool = AmadeusFlightSearchTool()
    
    # Test search parameters
    test_params = {
        "origin": "NYC",
        "destination": "SFO",
        "departure_date": "2025-05-01",
        "adults": 1
    }
    
    print(f"Testing flight search with parameters: {test_params}")
    print(f"Using Amadeus API Key: {os.getenv('AMADEUS_API_KEY')[:5]}..." if os.getenv('AMADEUS_API_KEY') else "⚠️ No Amadeus API Key found!")
    
    # Run the search
    result = search_tool._run(**test_params)
    
    print("\n=== SEARCH RESULT ===")
    print(result)
    
    # Check if any warnings appear in the result
    if "WARNING" in result or "fictional" in result:
        print("\n⚠️ TEST FAILED: The search appears to be returning fictional data!")
        return False
    else:
        print("\n✅ TEST PASSED: The search appears to be using real API data.")
        return True

if __name__ == "__main__":
    success = test_flight_search()
    sys.exit(0 if success else 1)