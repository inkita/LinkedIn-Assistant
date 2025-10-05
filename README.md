Entities -> Candidate, Skill, Job

(:Candidate)-[:HAS_SKILL]->(:Skill)

(:Job)-[:REQUIRES_SKILL]->(:Skill)

python3 -m venv venv

source venv/bin/activate

pip install langchain langgraph neo4j pandas PyPDF2 sentence-transformers

docker run -d \
  --name neo4j-talentkg \
  -p 7474:7474 -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5

docker start neo4j-talentkg

http://localhost:7474/browser/   #for viewing the KG

## Install Ollama locally and then run the following command to pull a model (currently tested on llama3.2:3b):
ollama serve                # leave this tab running OR have it as a background service

# in another tab:
ollama pull llama3.2:3b



export OLLAMA_MODEL=llama3.2:3b

export NEO4J_URI=bolt://localhost:7687

export NEO4J_USER=neo4j

export NEO4J_PASSWORD=password

python main.py


