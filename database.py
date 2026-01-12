import os
from sqlalchemy import create_engine, Column, String, Integer, DateTime, Boolean, JSON, ForeignKey, BigInteger
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

# Update this with your actual connection string
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost:5432/dbname")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class Company(Base):
    __tablename__ = "companies"
    id = Column(Integer, primary_key=True, index=True)
    id_attio = Column(String, unique=True, index=True) # Matching Column
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
    company_type = Column(String)
    fund = Column(String)
    business_model = Column(JSON) # Array mapping
    constitution_location = Column(JSON) # Array mapping

class FastTrack(Base):
    __tablename__ = "fast_tracks"
    id = Column(Integer, primary_key=True, index=True)
    entry_id = Column(String, unique=True, index=True) # Matching Column
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

# Create tables
Base.metadata.create_all(bind=engine)
