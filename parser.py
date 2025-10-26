import fitz
import json
from langchain_community.llms import Ollama

def parse_job_description(file):
    """Parse JD using Ollama (Llama3) into structured JSON"""
    text = ""
    if file.name.endswith(".pdf"):
        pdf = fitz.open(stream=file.read(), filetype="pdf")
        for page in pdf:
            text += page.get_text("text")
    else:
        text = file.read().decode("utf-8")

    llm = Ollama(model="llama3")
    prompt = f"""
    Extract the following as JSON:
    - title
    - company
    - description
    - skills_required (list)
    - exp_min
    - exp_max
    - degree_level
    - preferred_field
    ---
    {text}
    """
    response = llm.invoke(prompt)
    try:
        return json.loads(response)
    except:
        return {"title": "Unknown", "company": "Unknown", "skills_required": []}
