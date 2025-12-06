"""
Configuration for Neo4j connection.
You can override these with environment variables or modify directly.
"""

import os

# Neo4j Configuration
# These can be overridden with environment variables
# Using the working URI from recruiter_agent.py
NEO4J_URI = os.getenv('NEO4J_URI', 'neo4j+s://dc47a5a0.databases.neo4j.io')
NEO4J_USER = os.getenv('NEO4J_USER', 'neo4j')
NEO4J_PASSWORD = os.getenv('NEO4J_PASSWORD', 'KJEHHJM1abMuYdu6WzpR2oBx5ue8P1JJtcbM7A7eWck')

# Algorithm weights
JACCARD_WEIGHT = float(os.getenv('JACCARD_WEIGHT', '0.6'))
GUTTMAN_WEIGHT = float(os.getenv('GUTTMAN_WEIGHT', '0.4'))

