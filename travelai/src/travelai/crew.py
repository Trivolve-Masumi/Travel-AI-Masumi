from crewai import Agent, Crew, Process, Task
from crewai.project import CrewBase, agent, crew, task, before_kickoff, after_kickoff
from crewai_tools import WebsiteSearchTool
from datetime import datetime
import os
import requests
import logging

from .tools import (
    AmadeusFlightSearchTool, 
    DateHelperTool, 
    AirportCodeTool, 
    AmadeusFlightPriceTool, 
    AmadeusFlightBookingTool
)

@CrewBase
class TravelAICrew:
    """TravelAI crew for flight search and booking assistance"""

    @before_kickoff
    def prepare_inputs(self, inputs):
        """Process any inputs before starting the crew."""
        print("Starting travel agent conversation...")
        
        # Create logger
        self._setup_logging()
        logger = logging.getLogger('travelai_crew')
        
        # Reset memories to ensure a fresh start
        try:
            self.crew().reset_memories(command_type='all')
            logger.info("Successfully reset agent memories for a fresh conversation.")
        except Exception as e:
            logger.warning(f"Could not reset memories: {str(e)}")
        
        # Ensure we have current date in the inputs
        if 'current_date' not in inputs:
            inputs['current_date'] = datetime.now().strftime("%Y-%m-%d")
            
        # Add a flag to indicate this is a new conversation if not already present
        if 'is_new_conversation' not in inputs:
            inputs['is_new_conversation'] = True
            
        logger.info(f"Current date: {inputs['current_date']}")
        
        # Verify API credentials and test connection
        try:
            self._verify_api_credentials()
            logger.info("API credentials verified and connection tested successfully")
        except Exception as e:
            logger.error(f"API credential verification failed: {str(e)}")
            # Don't raise exception, let the agent gracefully handle API issues
        
        # Create necessary directories
        self._create_directories()
        
        return inputs

    @after_kickoff
    def process_output(self, output):
        """Process the final output from the crew."""
        logger = logging.getLogger('travelai_crew')
        logger.info("Travel agent conversation completed.")
        return output
    
    def process_input(self, input_text):
        """Process a single user input and return the agent's response."""
        logger = logging.getLogger('travelai_crew')
        logger.info(f"Processing input: {input_text}")
        
        try:
            # Create a task with explicit instructions to process the query
            task = Task(
                description=f"""
				Process this flight search request immediately: {input_text}

				IMPORTANT WORKFLOW INSTRUCTIONS:
				1. Do NOT introduce yourself or ask for more details - the user has already provided input
				2. First use the Airport Code Lookup Tool for any cities mentioned to get IATA codes
				3. Then use the Date Helper Tool to standardize any dates mentioned
				4. Then use the Amadeus Flight Search Tool with the information you have
				5. Present the actual flight search results directly

				Original request: {input_text}
                """,
                expected_output="Flight search results based on the provided query",
                agent=self.travel_agent()
            )
            
            # Create a crew with just this task
            crew = Crew(
                agents=[self.travel_agent()],
                tasks=[task],
                process=Process.sequential,
                verbose=True,
                memory=False,
                cache=True
            )
            
            # Execute and get the result
            result = crew.kickoff()
            
            logger.info("Successfully processed user input")
            return result
        except Exception as e:
            logger.error(f"Error processing input: {str(e)}")
            return f"I apologize, but there was an error processing your request: {str(e)}"
    
    def _setup_logging(self):
        """Set up logging for the CrewAI system"""
        logger = logging.getLogger('travelai_crew')
        
        if not os.path.exists('logs'):
            os.makedirs('logs')
        
        if not logger.handlers:
            log_file = f"logs/travelai_crew_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file)
            console_handler = logging.StreamHandler()
            
            formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
            file_handler.setFormatter(formatter)
            console_handler.setFormatter(formatter)
            
            logger.addHandler(file_handler)
            logger.addHandler(console_handler)
            logger.setLevel(logging.INFO)
    
    def _verify_api_credentials(self):
        """Verify API credentials and test the connection"""
        logger = logging.getLogger('travelai_crew')
        
        # Check for API credentials
        amadeus_api_key = os.getenv("AMADEUS_API_KEY")
        amadeus_api_secret = os.getenv("AMADEUS_API_SECRET")
        
        if not amadeus_api_key or not amadeus_api_secret:
            error_msg = "Missing Amadeus API credentials"
            logger.error(error_msg)
            raise ValueError(error_msg)
        
        logger.info(f"Found API Key: {amadeus_api_key[:5]}...")
        
        # Test API connection
        try:
            # Get access token
            url = "https://test.api.amadeus.com/v1/security/oauth2/token"
            payload = {
                "grant_type": "client_credentials",
                "client_id": amadeus_api_key,
                "client_secret": amadeus_api_secret
            }
            headers = {"Content-Type": "application/x-www-form-urlencoded"}
            
            response = requests.post(url, data=payload, headers=headers)
            
            if response.status_code == 200:
                token_data = response.json()
                access_token = token_data.get("access_token")
                logger.info(f"Successfully obtained API token: {access_token[:10]}...")
                
                # Test a simple API call
                test_url = "https://test.api.amadeus.com/v1/reference-data/locations"
                test_params = {"subType": "CITY", "keyword": "NYC"}
                test_headers = {"Authorization": f"Bearer {access_token}"}
                
                test_response = requests.get(test_url, params=test_params, headers=test_headers)
                
                if test_response.status_code == 200:
                    logger.info("API connection test successful")
                else:
                    logger.error(f"API test call failed: {test_response.status_code} - {test_response.text}")
                    raise Exception(f"API test call failed: {test_response.status_code}")
            else:
                logger.error(f"Failed to get API token: {response.status_code} - {response.text}")
                raise Exception(f"Failed to get API token: {response.status_code}")
                
        except Exception as e:
            logger.error(f"API connection test failed: {str(e)}")
            raise Exception(f"API connection test failed: {str(e)}")

    def _create_directories(self):
        """Create necessary directories for bookings and PDFs."""
        dirs = ["bookings", "booking_pdfs", "api_responses", "logs"]
        logger = logging.getLogger('travelai_crew')
        
        for directory in dirs:
            if not os.path.exists(directory):
                try:
                    os.makedirs(directory)
                    logger.info(f"Created directory: {directory}")
                except Exception as e:
                    logger.warning(f"Error creating directory {directory}: {str(e)}")

    @agent
    def travel_agent(self) -> Agent:
        """Create the travel agent that will assist with flight searches and bookings."""
        return Agent(
            config=self.agents_config['travel_agent'],
            tools=[
                AmadeusFlightSearchTool(),
                AmadeusFlightPriceTool(),
                AmadeusFlightBookingTool(),
                DateHelperTool(),
                AirportCodeTool(),
                WebsiteSearchTool(),
            ],
            verbose=True,
            memory=False,
            cache=True,
            allow_delegation=False,
            max_rpm=10
        )
        
    @task
    def flight_search_task(self) -> Task:
        """Create the flight search and booking task."""
        return Task(
            config=self.tasks_config['flight_search_task'],
            human_input=False  # Changed from true to false to prevent waiting for terminal input
        )
        
    @crew
    def crew(self) -> Crew:
        """Create the TravelAI crew."""
        return Crew(
            agents=self.agents,
            tasks=self.tasks,
            process=Process.sequential,
            verbose=True,
            memory=False,
            cache=True,
            share_crew=False
        )