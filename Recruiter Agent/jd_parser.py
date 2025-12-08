# jd_parser.py
from google import genai
from google.genai import types
from typing import List
import os
import json
os.environ['GEMINI_API_KEY'] = "AIzaSyBQH37XmoQ7HepvaTSa-QBMdD15TuPI448"
# --- Initialize Gemini Client ---
try:
    # Client automatically uses the GEMINI_API_KEY environment variable
    client = genai.Client() 
except Exception as e:
    print(f"Warning: Gemini client failed to initialize. Check GEMINI_API_KEY. Error: {e}")
    client = None

def extract_skills_from_jd(job_description_text: str) -> List[str]:
    """
    Uses the Gemini API to reliably extract a structured list of skills
    from the raw job description text.
    """
    if not client:
        # Fallback to simple placeholder logic if the client isn't ready
        print("❌ Gemini client not initialized. Using simple, unreliable fallback parser.")
        # This is the old, limited logic:
        keywords = set()
        text_lower = job_description_text.lower()
        if "microsoft office" in text_lower or "excel" in text_lower: keywords.add("Microsoft Office Suite")
        if "customer service" in text_lower: keywords.add("Customer Service")
        if "design" in text_lower: keywords.add("Design")
        return sorted([k.title() for k in keywords])

    print("🤖 Calling Gemini to extract structured skills...")
    
    # Define the desired output structure using a Pydantic-style schema
    # This forces the model to return clean, predictable JSON.
    skill_list_schema = types.Schema(
        type=types.Type.OBJECT,
        properties={
            "required_skills": types.Schema(
                type=types.Type.ARRAY,
                description="A list of all explicit and implied technical, software, and soft skills required for the job.",
                items=types.Schema(type=types.Type.STRING)
            )
        },
        required=["required_skills"]
    )
    
    # Craft a detailed prompt and system instruction
    prompt = f"""
    Analyze the following job description and extract a definitive list of all required skills.
    Focus on specific software (like AutoCAD), technical proficiencies (like Design or Spreadsheets), 
    and essential soft skills (like Communication, Customer Service).
    
    JOB DESCRIPTION:
    ---
    {job_description_text}
    ---
    """
    
    try:
        response = client.models.generate_content(
            model='gemini-2.5-flash', # Fast and effective model for structured data extraction
            contents=prompt,
            config=types.GenerateContentConfig(
                # Use JSON mode and the schema to ensure structured output
                response_mime_type="application/json",
                response_schema=skill_list_schema,
            ),
        )

        # Parse the JSON string output
        result = json.loads(response.text)
        
        # Return the clean list of strings, capitalized for KG consistency
        return [skill.strip().title() for skill in result.get("required_skills", [])]

    except Exception as e:
        print(f"❌ Gemini API call failed: {e}")
        return []