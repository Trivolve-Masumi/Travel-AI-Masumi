#!/usr/bin/env python
import os
import sys
import logging
import uuid
import json
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv
from fastapi import FastAPI, Query, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uvicorn
from masumi_crewai.config import Config
from masumi_crewai.payment import Payment, Amount
import aiohttp

# Use relative imports since we're in a package
from .crew import TravelAICrew
from .tools.amadeus_booking_tool import AmadeusFlightBookingTool

# Load environment variables
load_dotenv()

# Retrieve API Keys and URLs
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
AMADEUS_API_KEY = os.getenv("AMADEUS_API_KEY")
AMADEUS_API_SECRET = os.getenv("AMADEUS_API_SECRET")
PAYMENT_SERVICE_URL = os.getenv("PAYMENT_SERVICE_URL")
PAYMENT_API_KEY = os.getenv("PAYMENT_API_KEY")
AGENT_IDENTIFIER = os.getenv("AGENT_IDENTIFIER", "e6c57104dfa95943ffab95eafe1f12ed9a8da791678bfbf765b056491d37f35636838a945e1c6e6a581977c4567f779bae9081c8505f34ab8fff26ae")
SELLER_VKEY = os.getenv("SELLER_VKEY", "4203a554f750aa3ab74aea57161f95255845e048c67342c4df31ffa6")

# Set up logging
def setup_logging():
    """Set up logging for the main application"""
    logger = logging.getLogger('travelai_main')
    
    if not os.path.exists('logs'):
        os.makedirs('logs')
        
    log_file = f"logs/main_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    file_handler = logging.FileHandler(log_file)
    console_handler = logging.StreamHandler()
    
    formatter = logging.Formatter('%(asctime)s | %(name)s | %(levelname)s | %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    logger.setLevel(logging.INFO)
    
    return logger

logger = setup_logging()

# Initialize FastAPI
app = FastAPI(
    title="TravelAI Flight Assistant API",
    description="MIP-003 compliant API for flight search and booking using CrewAI and Amadeus",
    version="1.0.0"
)

# Initialize ChromaDB for vector storage
try:
    # Try first with the newer API
    import chromadb
    chroma_client = chromadb.PersistentClient(path="./chroma_db")
    # Create a collection for job conversations
    try:
        job_collection = chroma_client.get_or_create_collection("job_conversations")
    except:
        # If collection exists already
        job_collection = chroma_client.get_collection("job_conversations")
except Exception as e:
    # Fall back to in-memory client if ChromaDB isn't installed or encounters an error
    logger.warning(f"ChromaDB error: {str(e)}. Using in-memory job storage only.")
    chroma_client = None
    job_collection = None

# ─────────────────────────────────────────────────────────────────────────────
# Temporary in-memory job store (DO NOT USE IN PRODUCTION)
# ─────────────────────────────────────────────────────────────────────────────
jobs = {}
payment_instances = {}

# ─────────────────────────────────────────────────────────────────────────────
# Initialize Masumi Payment Config
# ─────────────────────────────────────────────────────────────────────────────
config = Config(
    payment_service_url=PAYMENT_SERVICE_URL,
    payment_api_key=PAYMENT_API_KEY
)

# ─────────────────────────────────────────────────────────────────────────────
# Pydantic Models
# ─────────────────────────────────────────────────────────────────────────────

# Simplified request model
class StartJobRequest(BaseModel):
    query: str

class ProvideInputRequest(BaseModel):
    job_id: str
    query: str

# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def test_amadeus_api():
    """Test the Amadeus API connection"""
    logger.info("Testing Amadeus API connection...")
    
    # Get API credentials
    amadeus_api_key = os.getenv("AMADEUS_API_KEY")
    amadeus_api_secret = os.getenv("AMADEUS_API_SECRET")
    
    if not amadeus_api_key or not amadeus_api_secret:
        logger.error("Missing Amadeus API credentials")
        return False
        
    logger.info(f"Found API Key: {amadeus_api_key[:5]}...")
    
    # Test API connection
    try:
        import requests
        
        # Get access token
        url = "https://test.api.amadeus.com/v1/security/oauth2/token"
        payload = {
            "grant_type": "client_credentials",
            "client_id": amadeus_api_key,
            "client_secret": amadeus_api_secret
        }
        headers = {"Content-Type": "application/x-www-form-urlencoded"}
        
        logger.info("Requesting Amadeus API token...")
        response = requests.post(url, data=payload, headers=headers)
        
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            logger.info(f"Successfully obtained API token: {access_token[:10]}...")
            
            # Test a simple API call
            test_url = "https://test.api.amadeus.com/v1/reference-data/locations"
            test_params = {"subType": "CITY", "keyword": "NYC"}
            test_headers = {"Authorization": f"Bearer {access_token}"}
            
            logger.info("Testing API with a simple query...")
            test_response = requests.get(test_url, params=test_params, headers=test_headers)
            
            if test_response.status_code == 200:
                test_data = test_response.json()
                location_count = len(test_data.get("data", []))
                logger.info(f"API test successful - found {location_count} locations for NYC")
                return True
            else:
                logger.error(f"API test call failed: {test_response.status_code} - {test_response.text}")
                return False
        else:
            logger.error(f"Failed to get API token: {response.status_code} - {response.text}")
            return False
                
    except Exception as e:
        logger.error(f"API connection test failed: {str(e)}")
        return False

# ─────────────────────────────────────────────────────────────────────────────
# CrewAI Task Execution
# ─────────────────────────────────────────────────────────────────────────────
async def execute_crew_task(query: str) -> str:
    """ Execute a CrewAI task with TravelAI Flight Assistant """
    logger.info(f"Processing query: {query}")
    
    # Initialize the crew
    travel_crew = TravelAICrew()
    
    # Process the query using our dedicated method
    result = travel_crew.process_input(query)
    
    logger.info("Crew task completed successfully")
    return result

# ─────────────────────────────────────────────────────────────────────────────
# Payment Status Handler
# ─────────────────────────────────────────────────────────────────────────────
async def handle_payment_status(job_id: str, payment_id: str) -> None:
    """ Executes TravelAI task after payment confirmation """
    logger.info(f"Payment {payment_id} completed for job {job_id}, executing task...")
    
    if job_id not in jobs:
        logger.error(f"Job {job_id} not found for payment {payment_id}")
        return
    
    job = jobs[job_id]
    
    # Update job status to running
    job["status"] = "processing"
    job["payment_status"] = "completed"
    
    try:
        # Execute the AI task with the user's query
        query_text = job["input_data"]
        logger.info(f"Processing query: {query_text}")
        
        result = await execute_crew_task(query_text)
        logger.info(f"Crew task completed for job {job_id}")

        # Store the result
        job["result"] = result
        
        # Initialize conversation history with the initial query and response
        job["conversation"] = [
            {"role": "user", "content": query_text},
            {"role": "assistant", "content": result}
        ]
        
        # Store the job in vector DB for persistent storage if available
        if job_collection:
            try:
                job_collection.upsert(
                    ids=[job_id],
                    documents=[query_text],  # Store the original query for embeddings
                    metadatas=[{"job_data": json.dumps(job)}]
                )
            except Exception as e:
                logger.error(f"Error storing job in vector DB: {str(e)}")
        
        # Convert result to string for hash
        result_str = str(result)
        
        # Mark payment as completed on Masumi
        result_hash = result_str[:64] if len(result_str) >= 64 else result_str
        await payment_instances[job_id].complete_payment(payment_id, result_hash)
        logger.info(f"Payment marked as completed for job {job_id}")
        
        # Update job status
        job["status"] = "completed"
        
        # Stop monitoring payment status
        if job_id in payment_instances:
            payment_instances[job_id].stop_status_monitoring()
            del payment_instances[job_id]
        
    except Exception as e:
        logger.error(f"Error processing job {job_id} after payment: {str(e)}")
        job["status"] = "error"
        job["result"] = f"Error processing job: {str(e)}"
        
        # Stop monitoring to prevent repeated failures
        if job_id in payment_instances:
            payment_instances[job_id].stop_status_monitoring()
            del payment_instances[job_id]

# ─────────────────────────────────────────────────────────────────────────────
# 1) Start Job (MIP-003: /start_job)
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/start_job")
async def start_job(request_body: StartJobRequest):
    """
    Initiates a job with flight search parameters.
    Fulfills MIP-003 /start_job endpoint.
    """
    # Check for required API keys
    missing_vars = []
    if not OPENAI_API_KEY:
        missing_vars.append("OPENAI_API_KEY")
    if not AMADEUS_API_KEY:
        missing_vars.append("AMADEUS_API_KEY")
    if not AMADEUS_API_SECRET:
        missing_vars.append("AMADEUS_API_SECRET")
    if not PAYMENT_SERVICE_URL:
        missing_vars.append("PAYMENT_SERVICE_URL")
    if not PAYMENT_API_KEY:
        missing_vars.append("PAYMENT_API_KEY")
    
    if missing_vars:
        return {
            "status": "error", 
            "message": f"Missing required environment variables: {', '.join(missing_vars)}"
        }
    
    # Generate unique job ID
    job_id = str(uuid.uuid4())
    
    # Define payment amounts (10 tADA)
    payment_amount = os.getenv("PAYMENT_AMOUNT", "20000000")  # Default 20 ADA
    payment_unit = os.getenv("PAYMENT_UNIT", "lovelace")      # Default lovelace
    amounts = [Amount(amount=payment_amount, unit=payment_unit)]
    
    try:
        # Create a payment request using Masumi SDK
        # Use a constant identifier for consistency
        identifier_from_purchaser = "example_identifier"
        
        payment = Payment(
            agent_identifier=AGENT_IDENTIFIER,
            amounts=amounts,
            config=config,
            identifier_from_purchaser=identifier_from_purchaser,
            input_data=request_body.query  # Directly use the query string
        )
        
        logger.info("Creating payment request...")
        payment_request = await payment.create_payment_request()
        payment_id = payment_request["data"]["blockchainIdentifier"]
        payment.payment_ids.add(payment_id)
        logger.info(f"Created payment request with ID: {payment_id}")
        
        # Store job info (Awaiting payment)
        jobs[job_id] = {
            "status": "awaiting_payment",
            "payment_status": "pending",
            "payment_id": payment_id,
            "created_at": datetime.now().isoformat(),
            "input_data": request_body.query,  # Store the query directly
            "result": None,
        }
        
        # Define payment callback function
        async def payment_callback(payment_id: str):
            await handle_payment_status(job_id, payment_id)
        
        # Start monitoring the payment status
        payment_instances[job_id] = payment
        logger.info(f"Starting payment status monitoring for job {job_id}")
        await payment.start_status_monitoring(payment_callback)
        
        # Return the payment details
        return {
            "status": "success",
            "job_id": job_id,
            "blockchainIdentifier": payment_request["data"]["blockchainIdentifier"],
            "submitResultTime": payment_request["data"]["submitResultTime"],
            "unlockTime": payment_request["data"]["unlockTime"],
            "externalDisputeUnlockTime": payment_request["data"]["externalDisputeUnlockTime"],
            "agentIdentifier": AGENT_IDENTIFIER,
            "sellerVkey": SELLER_VKEY,
            "identifierFromPurchaser": identifier_from_purchaser,
            "amounts": amounts,
            "input_hash": payment.input_hash
        }
        
    except Exception as e:
        logger.error(f"Error creating payment for job {job_id}: {str(e)}")
        return {
            "status": "error",
            "message": f"Error creating payment: {str(e)}"
        }

# ─────────────────────────────────────────────────────────────────────────────
# 2) Check Job Status (MIP-003: /status)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/status")
async def check_status(job_id: str = Query(..., description="Job ID to check status")):
    """
    Retrieves the current status of a specific job.
    Fulfills MIP-003 /status endpoint.
    """
    if job_id not in jobs:
        # Try to retrieve job from vector DB if available
        if job_collection:
            try:
                results = job_collection.get(ids=[job_id])
                if results and results.get("ids") and len(results.get("ids", [])) > 0:
                    # Reconstruct job from metadata
                    job_data = json.loads(results["metadatas"][0]["job_data"])
                    jobs[job_id] = job_data
                else:
                    raise HTTPException(status_code=404, detail="Job not found")
            except Exception as e:
                logger.error(f"Error retrieving job from vector DB: {str(e)}")
                raise HTTPException(status_code=404, detail="Job not found")
        else:
            raise HTTPException(status_code=404, detail="Job not found")

    job = jobs[job_id]
    
    # Check latest payment status if payment instance exists
    if job_id in payment_instances:
        try:
            status = await payment_instances[job_id].check_payment_status()
            job["payment_status"] = status.get("data", {}).get("status")
            logger.info(f"Updated payment status for job {job_id}: {job['payment_status']}")
        except Exception as e:
            logger.error(f"Error checking payment status for job {job_id}: {str(e)}")
    
    # Format response based on MIP-003 standard
    response = {
        "job_id": job_id,
        "status": job["status"],
        "payment_status": job.get("payment_status", "unknown")
    }
    
    # Include the latest result if available
    if job["result"]:
        response["result"] = job["result"]
        
    return response

# ─────────────────────────────────────────────────────────────────────────────
# 3) Provide Input (MIP-003: /provide_input)
# ─────────────────────────────────────────────────────────────────────────────
@app.post("/provide_input")
async def provide_input(request_body: ProvideInputRequest):
    """
    Allows users to send additional input to an ongoing job.
    Fulfills MIP-003 /provide_input endpoint.
    """
    job_id = request_body.job_id
    
    if job_id not in jobs:
        # Try to retrieve job from vector DB if available
        if job_collection:
            try:
                results = job_collection.get(ids=[job_id])
                if results and results.get("ids") and len(results.get("ids", [])) > 0:
                    # Reconstruct job from metadata
                    job_data = json.loads(results["metadatas"][0]["job_data"])
                    jobs[job_id] = job_data
                else:
                    return {"status": "error", "message": "Job not found"}
            except Exception as e:
                logger.error(f"Error retrieving job from vector DB: {str(e)}")
                return {"status": "error", "message": "Job not found"}
        else:
            return {"status": "error", "message": "Job not found"}
    
    job = jobs[job_id]
    
    # Check if payment is completed
    if job.get("payment_status") != "completed":
        return {
            "status": "error", 
            "message": "Payment must be completed before providing input"
        }
    
    # Only allow input for jobs that are in an appropriate state
    valid_states = ["initialized", "processing", "completed"]
    if job["status"] not in valid_states:
        return {
            "status": "error", 
            "message": f"Cannot provide input for a job with status '{job['status']}'"
        }
    
    try:
        # Get the user message
        user_message = request_body.query
        if not user_message:
            return {"status": "error", "message": "No query provided"}
        
        # Update job status
        job["status"] = "processing"
        
        # Create a conversation history if it doesn't exist
        if "conversation" not in job:
            job["conversation"] = []
            # Add the initial query as the first message
            job["conversation"].append({"role": "user", "content": job["input_data"]})
            job["conversation"].append({"role": "assistant", "content": job["result"]})
        
        # Add the new message to conversation history
        job["conversation"].append({"role": "user", "content": user_message})
        
        # Create a context-aware query that includes previous conversation
        context_query = f"""CONVERSATION HISTORY:
{' '.join([f'{msg["role"].upper()}: {msg["content"]}' for msg in job["conversation"][-6:]])}

CURRENT QUERY: {user_message}

Please respond to the current query taking into account the conversation history.
"""
        
        # Process follow-up input with conversation context
        travel_crew = TravelAICrew()
        result = travel_crew.process_input(context_query)
        
        # Add the assistant's response to conversation history
        job["conversation"].append({"role": "assistant", "content": result})
        
        # Update job result with the latest response
        job["result"] = result
        job["status"] = "completed"
        
        # Store the updated job in vector DB if available
        if job_collection:
            try:
                job_collection.upsert(
                    ids=[job_id],
                    documents=[context_query],  # Store the last context for embeddings
                    metadatas=[{"job_data": json.dumps(job)}]
                )
            except Exception as e:
                logger.error(f"Error storing job in vector DB: {str(e)}")
        
        logger.info(f"Processed follow-up input for job {job_id}")
        
        return {
            "status": "success",
            "result": result
        }
        
    except Exception as e:
        logger.error(f"Error processing input for job {job_id}: {str(e)}")
        job["status"] = "error"
        job["result"] = f"Error processing input: {str(e)}"
        
        return {"status": "error", "message": str(e)}

# ─────────────────────────────────────────────────────────────────────────────
# 4) Check Server Availability (MIP-003: /availability)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/availability")
async def check_availability():
    """
    Checks if the server is operational.
    Fulfills MIP-003 /availability endpoint.
    """
    # Perform basic API credential check
    missing_vars = []
    if not OPENAI_API_KEY:
        missing_vars.append("OPENAI_API_KEY")
    if not AMADEUS_API_KEY:
        missing_vars.append("AMADEUS_API_KEY")
    if not AMADEUS_API_SECRET:
        missing_vars.append("AMADEUS_API_SECRET")
    if not PAYMENT_SERVICE_URL:
        missing_vars.append("PAYMENT_SERVICE_URL")
    if not PAYMENT_API_KEY:
        missing_vars.append("PAYMENT_API_KEY")
    
    if missing_vars:
        return {
            "status": "limited",
            "message": f"The server is running but missing required API credentials: {', '.join(missing_vars)}"
        }
    
    # Test the Amadeus API connection
    api_working = test_amadeus_api()
    
    if api_working:
        return {
            "status": "available",
            "message": "The TravelAI Flight Assistant API is running smoothly with payment integration."
        }
    else:
        return {
            "status": "degraded",
            "message": "The server is running but the Amadeus API connection is not working properly."
        }

# ─────────────────────────────────────────────────────────────────────────────
# 5) Retrieve Input Schema (MIP-003: /input_schema)
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/input_schema")
async def input_schema():
    """
    Returns the expected input schema for the /start_job endpoint.
    Fulfills MIP-003 /input_schema endpoint.
    """
    schema_example = {
        "query": "I need a flight from New York to London next month for a 7-day business trip"
    }
    return schema_example

# ─────────────────────────────────────────────────────────────────────────────
# 6) Health Check
# ─────────────────────────────────────────────────────────────────────────────
@app.get("/health")
async def health():
    """
    Returns the health of the server.
    """
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat()
    }

# ─────────────────────────────────────────────────────────────────────────────
# Main logic if called as a script
# ─────────────────────────────────────────────────────────────────────────────
def run():
    """
    Run the TravelAI crew to assist with flight searches and bookings.
    """
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='TravelAI Flight Assistant')
    parser.add_argument('--debug', action='store_true', help='Run in debug mode')
    parser.add_argument('--test-api', action='store_true', help='Just test the API connection and exit')
    parser.add_argument('--api', action='store_true', help='Start the FastAPI server')
    args = parser.parse_args()

    # Load environment variables from .env file
    load_dotenv()
    logger.info("Loaded environment variables from .env file")
    
    # Set debug mode if requested
    if args.debug:
        logger.info("Running in DEBUG mode")
        os.environ["TRAVELAI_DEBUG"] = "true"
        # Set all loggers to debug level
        logging.getLogger().setLevel(logging.DEBUG)
    else:
        os.environ["TRAVELAI_DEBUG"] = "false"
    
    # Check if required API keys are set
    required_env_vars = ["OPENAI_API_KEY", "AMADEUS_API_KEY", "AMADEUS_API_SECRET", 
                         "PAYMENT_SERVICE_URL", "PAYMENT_API_KEY"]
    missing_vars = [var for var in required_env_vars if not os.getenv(var)]
    
    if missing_vars:
        logger.error(f"Missing required environment variables: {', '.join(missing_vars)}")
        if "OPENAI_API_KEY" in missing_vars:
            logger.error("OpenAI API key is required for the agent to function")
        if "AMADEUS_API_KEY" in missing_vars or "AMADEUS_API_SECRET" in missing_vars:
            logger.error("Amadeus API credentials are required for flight searches and bookings")
        if "PAYMENT_SERVICE_URL" in missing_vars or "PAYMENT_API_KEY" in missing_vars:
            logger.error("Masumi payment credentials are required for processing payments")
        sys.exit(1)
    
    # If just testing API connection
    if args.test_api:
        success = test_amadeus_api()
        logger.info(f"API test {'succeeded' if success else 'failed'}")
        sys.exit(0 if success else 1)
    
    # If starting the API server
    if args.api:
        logger.info("Starting FastAPI server with payment integration...")
        port = int(os.getenv("PORT", "8001"))
        uvicorn.run(app, host="0.0.0.0", port=port)
        return
    
    # Create necessary directories
    directories = ["bookings", "booking_pdfs", "api_responses", "logs", "chroma_db"]
    for directory in directories:
        if not os.path.exists(directory):
            os.makedirs(directory)
            logger.info(f"Created directory: {directory}")
    
    # Get current date for context
    current_date = datetime.now()
    logger.info(f"Current date: {current_date.strftime('%Y-%m-%d')}")
    
    print("Running CrewAI as standalone script is not supported when using payments.")
    print("Start the API using `python -m main --api` instead.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and ("--api" in sys.argv or "api" in sys.argv):
        print("Starting FastAPI server with payment integration...")
        run()
    else:
        print("Running CrewAI as standalone script is not supported when using payments.")
        print("Start the API using `python -m main --api` instead.")