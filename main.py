# main.py
# Import necessary libraries
from fastapi import FastAPI
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
import time # Import time to measure execution duration

# --- Pydantic Models for Data Validation ---
# We need to define the structure for contexts to properly parse them.
class Context(BaseModel):
    name: str
    lifespan_count: Optional[int] = Field(None, alias='lifespanCount')
    parameters: Optional[Dict[str, Any]] = {}

class QueryResult(BaseModel):
    parameters: Dict
    intent: Dict
    # Define the output_contexts field to capture the conversation's memory
    output_contexts: Optional[List[Context]] = Field([], alias='outputContexts')

class WebhookRequest(BaseModel):
    query_result: QueryResult = Field(..., alias='queryResult')

# --- Create the FastAPI Application ---
app = FastAPI(
    title="Loan Eligibility Chatbot Webhook",
    description="A robust API to handle loan eligibility checks for a chatbot.",
    version="2.2.0", # Version bump for age/number fallback logic
)

def get_merged_parameters(query_result: QueryResult) -> Dict:
    """
    Merges parameters from the active context and the current query.
    This is the key to remembering the loan type across turns.
    """
    merged_params = {}

    # 1. Get parameters from the context (the "memory")
    if query_result.output_contexts:
        for context in query_result.output_contexts:
            # We look for the context we set in the first intent
            if 'awaiting-loan-details' in context.name and context.parameters:
                merged_params.update(context.parameters)

    # 2. Get parameters from the current turn and overwrite
    # This ensures the newest info (like the age just provided) is used.
    merged_params.update(query_result.parameters)
    
    return merged_params

def determine_loan_type(params: Dict) -> Optional[str]:
    """
    Helper function to determine the loan type from the merged parameters.
    """
    if params.get('loan-type'):
        return params['loan-type']
    if params.get('Home_eligibility'):
        return 'home'
    if params.get('Car_eligibility'):
        return 'car'
    if params.get('education_eligibility') or params.get('edu_eligibility'):
        return 'education'
    if params.get('personal_eligibility'):
        return 'personal'
    if params.get('Business_eligibility'):
        return 'business'
    return None

def get_parameter(params: Dict, param_name: str, fallback_name: Optional[str] = None) -> Any:
    """
    Safely gets a parameter, handling complex objects and lists from Dialogflow.
    """
    value = params.get(param_name)
    if value is None and fallback_name:
        value = params.get(fallback_name)

    if value is None:
        return None

    # Handle Dialogflow's structured format for numbers, e.g., {"amount": 50000, "currency": "INR"}
    if isinstance(value, dict) and 'amount' in value:
        return value['amount']
    
    # Handle cases where Dialogflow returns a list (e.g., from a multi-select)
    if isinstance(value, list) and value:
        return value[0]
    
    # Handle cases where the value is a direct, non-empty value
    if value != '':
        return value
        
    return None

# --- Webhook Endpoint ---
@app.post("/webhook")
async def loan_eligibility_webhook(request: WebhookRequest):
    """
    This function processes the incoming request from the chatbot,
    checks for loan eligibility based on the provided parameters,
    and returns a user-friendly response.
    """
    start_time = time.time()
    print("--- NEW REQUEST RECEIVED ---")

    query_result = request.query_result
    
    # Merge parameters from context and the current query
    params = get_merged_parameters(query_result)
    print(f"DEBUG: Merged parameters: {params}")
    
    loan_type = determine_loan_type(params)
    print(f"DEBUG: Determined loan type: {loan_type}")
    
    # --- FIX APPLIED HERE ---
    # Added 'number' as a fallback for 'age' to handle cases where Dialogflow
    # uses the generic @sys.number entity.
    age = get_parameter(params, 'age', fallback_name='number')
    income = get_parameter(params, 'income', fallback_name='number') # This was already correct
    qualification = get_parameter(params, 'qualification')

    print(f"DEBUG: Extracted Age: {age}, Income: {income}, Qualification: {qualification}")

    response_text = "I'm sorry, I couldn't determine the loan type. Please specify if it's for a car, home, education, business, or personal use."

    # --- Loan Eligibility Logic (Corrected and fully robust) ---
    if loan_type == "home":
        if age is not None and income is not None:
            if int(age) >= 21 and int(income) >= 30000:
                response_text = "Excellent! Based on your age and income, you are eligible for a home loan."
            else:
                response_text = "Sorry, you do not meet the criteria for a home loan. You must be at least 21 years old and have a minimum monthly income of ₹30,000."
        else:
            response_text = "To check your home loan eligibility, I need a few more details. What is your age and your monthly income?(e.g., My age is ** and I make ****)"

    elif loan_type == "car":
        if age is not None and income is not None:
            if int(age) >= 18 and int(income) >= 20000:
                response_text = "Great news! You are eligible for a car loan."
            else:
                response_text = "Sorry, you do not meet the criteria for a car loan. You must be at least 18 years old and have a minimum monthly income of ₹20,000."
        else:
            response_text = "To check your eligibility for a car loan, I need to know your age and monthly income(e.g., My age is ** and I make ****)."
    
    elif loan_type == "personal":
        if age is not None and income is not None:
            if int(age) >= 25 and int(income) >= 25000:
                response_text = "Great news! You are eligible for a personal loan."
            else:
                response_text = "Sorry, you do not meet the criteria for a personal loan. You must be at least 25 years old and have a minimum monthly income of ₹25,000."
        else:
            response_text = "To check your eligibility for a personal loan, I need to know your age and monthly income(e.g., My age is ** and I make ****)."

    elif loan_type == "education":
        if age is not None and qualification is not None:
            # Using .lower() and 'in' for more flexible matching of 'under graduate'
            if "graduate" in str(qualification).lower() and int(age) <= 30:
                response_text = "Congratulations! You are eligible for an education loan."
            else:
                response_text = "Sorry, you do not meet the criteria for an education loan. You must be a graduate and no older than 30."
        else:
            response_text = "To check your eligibility for an education loan, I need your age and qualification (e.g.,My age is ** and 'under graduate'or 'post graduate')."

    elif loan_type == "business":
        if income is not None:
            if int(income) >= 40000:
                response_text = "Fantastic! You are eligible for a business loan."
            else:
                response_text = "Sorry, to be eligible for a business loan, your minimum monthly income must be at least ₹40,000."
        else:
            response_text = "To check your eligibility for a business loan, I need to know your monthly income(e.g., My age is ** and I make ****)."

    end_time = time.time()
    duration = (end_time - start_time) * 1000  # in milliseconds
    print(f"DEBUG: Final response: {response_text}")
    print(f"--- REQUEST PROCESSED IN {duration:.2f} ms ---")

    return {"fulfillmentText": response_text}

# --- Root Endpoint for Testing ---
@app.get("/")
def read_root():
    return {"status": "Loan Eligibility Webhook is running."}
