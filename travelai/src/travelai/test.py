#!/usr/bin/env python
# test_amadeus_api.py

import os
import requests
import json
from datetime import datetime, timedelta
from dotenv import load_dotenv
import sys

def test_amadeus_api():
    """Direct test of Amadeus API without any of the agent code"""
    load_dotenv()
    
    print("\n===== TESTING AMADEUS API DIRECTLY =====\n")
    
    api_key = os.getenv("AMADEUS_API_KEY")
    api_secret = os.getenv("AMADEUS_API_SECRET")
    
    if not api_key or not api_secret:
        print("❌ ERROR: Amadeus API credentials not found in .env file")
        return False
    
    print(f"Found API Key: {api_key[:5]}...")
    print(f"Found API Secret: {api_secret[:5]}...")
    
    # Step 1: Get access token
    print("\n--- Getting Access Token ---")
    token_url = "https://test.api.amadeus.com/v1/security/oauth2/token"
    token_data = {
        "grant_type": "client_credentials",
        "client_id": api_key,
        "client_secret": api_secret
    }
    token_headers = {"Content-Type": "application/x-www-form-urlencoded"}
    
    try:
        token_response = requests.post(token_url, data=token_data, headers=token_headers)
        print(f"Token Response Status: {token_response.status_code}")
        
        if token_response.status_code == 200:
            token_result = token_response.json()
            access_token = token_result.get("access_token")
            print(f"✅ Got token: {access_token[:10]}...")
        else:
            print(f"❌ Token request failed: {token_response.text}")
            return False
            
        # Step 2: Test a simple flight search
        print("\n--- Testing Flight Search ---")
        search_url = "https://test.api.amadeus.com/v2/shopping/flight-offers"
        
        # Use a date 30 days in the future to ensure it's valid
        future_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")
        
        search_params = {
            "originLocationCode": "SFO",
            "destinationLocationCode": "NYC",
            "departureDate": future_date,
            "adults": 1,
            "max": 5
        }
        search_headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        print(f"Search URL: {search_url}")
        print(f"Search Params: {json.dumps(search_params, indent=2)}")
        
        search_response = requests.get(search_url, params=search_params, headers=search_headers)
        print(f"Search Response Status: {search_response.status_code}")
        
        if search_response.status_code == 200:
            search_data = search_response.json()
            flight_count = len(search_data.get('data', []))
            print(f"✅ Found {flight_count} flights")
            
            # Save the full response to a file
            with open('direct_api_test_response.json', 'w') as f:
                json.dump(search_data, f, indent=2)
            print(f"Full API response saved to direct_api_test_response.json")
            
            # Print the first flight details
            if flight_count > 0:
                first_flight = search_data['data'][0]
                print("\nSample Flight:")
                print(f"  ID: {first_flight.get('id')}")
                print(f"  Price: {first_flight.get('price', {}).get('grandTotal')} {first_flight.get('price', {}).get('currency')}")
                
                for i, itinerary in enumerate(first_flight.get('itineraries', [])):
                    print(f"  Itinerary {i+1}:")
                    for j, segment in enumerate(itinerary.get('segments', [])):
                        carrier = segment.get('carrierCode', '')
                        flight_num = segment.get('number', '')
                        departure = segment.get('departure', {})
                        arrival = segment.get('arrival', {})
                        print(f"    Flight: {carrier}{flight_num}")
                        print(f"    From: {departure.get('iataCode')} at {departure.get('at')}")
                        print(f"    To: {arrival.get('iataCode')} at {arrival.get('at')}")
                
                print("\n✅ API TEST SUCCESSFUL: Your Amadeus API credentials are working correctly!")
                return True
            else:
                print("⚠️ API returned 0 flights. This might be normal if no flights are available for the test date.")
                print("The API connection is working, but no flight results were found.")
                return True
        else:
            print(f"❌ Search request failed: {search_response.text}")
            return False
            
    except Exception as e:
        print(f"❌ Error testing API: {str(e)}")
        return False

if __name__ == "__main__":
    success = test_amadeus_api()
    sys.exit(0 if success else 1)