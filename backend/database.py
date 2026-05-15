import os
from urllib.parse import quote_plus

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from neo4j import GraphDatabase

# PostgreSQL setup
POSTGRES_USER = os.getenv("POSTGRES_USER", "pxray")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "pxray")

if POSTGRES_PASSWORD:
    DB_AUTH = f"{POSTGRES_USER}:{quote_plus(POSTGRES_PASSWORD)}@"
else:
    DB_AUTH = f"{POSTGRES_USER}@"
PG_URL = f"postgresql://{DB_AUTH}{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"

engine = create_engine(PG_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Neo4j setup
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "pxray_password")

try:
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
except Exception as e:
    print(f"Failed to connect to Neo4j: {e}")
    neo4j_driver = None

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def get_neo4j():
    if neo4j_driver:
        return neo4j_driver.session()
    return None
