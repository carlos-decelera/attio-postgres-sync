import os
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, JSON, ForeignKey, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship, validates
from sqlalchemy.dialects.postgresql import ARRAY

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and "localhost" in DATABASE_URL:
    print("⚠️ Alerta: Estás intentando usar localhost en Railway.")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Modelo de Compañías (basado en tu n8n JSON)
class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    id_attio = Column(String, unique=True, index=True)
    name = Column(String)
    domains = Column(String)
    created_at = Column(DateTime)
    one_liner = Column(String)
    stage = Column(String)
    round_size = Column(BigInteger)
    current_valuation = Column(BigInteger)
    deck_url = Column(String)
    reference = Column(String)
    reference_explanation = Column(String)
    date_sourced = Column(DateTime)
    responsible = Column(String)
    company_type = Column(ARRAY(String))
    fund = Column(String)
    business_model = Column(ARRAY(String))
    constitution_location = Column(ARRAY(String))
    business_type = Column(ARRAY(String))
    comments = Column(String)

    @validates('business_model', 'constitution_location', 'business_type', 'company_type')
    def empty_list_to_null(self, key, value):
        # Si el valor es una lista vacía o un string que representa una lista vacía, devuelve None
        if isinstance(value, list) and len(value) == 0:
            return None
        return value
    
    fast_tracks = relationship("FastTrack", back_populates="company")

# Modelo de Fast Tracks (basado en tu n8n JSON)
class FastTrack(Base):
    __tablename__ = "fast_tracks"
    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(String, unique=True, index=True)
    company_id = Column(Integer, ForeignKey("companies.id"))
    parent_record_id = Column(String)
    name = Column(String)
    potential_program = Column(Boolean)
    added_to_list_at = Column(DateTime)
    kill_reasons = Column(String)
    contact_status = Column(String)
    first_videocall_done = Column(DateTime)
    risk = Column(String)
    urgency = Column(String)
    next_steps = Column(String)
    deadline = Column(DateTime)
    notes = Column(String)
    last_contacted = Column(DateTime)
    last_modified = Column(DateTime)
    date_first_contact = Column(DateTime)
    fast_track_status = Column(String)
    signals_evaluations = Column(JSON)
    green_flags_summary = Column(String)
    red_flags_summary = Column(String)
    signal_comments = Column(String)

    @validates('signals_evaluations')
    def validate_json_empty(self, key, value):
        if isinstance(value, dict) and not value:
            return None
        
        if isinstance(value, list) and not value:
            return None
            
        if isinstance(value, str) and not value.strip():
            return None
            
        return value

    company = relationship("Company", back_populates="fast_tracks")

def init_db():
    Base.metadata.create_all(bind=engine)
