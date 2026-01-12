import os
import uvicorn
from fastapi import FastAPI, Request, Depends
from sqlalchemy.orm import Session
from database import SessionLocal, engine, Base
from companies.models import Company
from fast_tracks.models import FastTrack

app = FastAPI()

load_dotenv()

ATTIO_TOKEN = os.getenv("ATTIO_TOKEN")
COMPANY_OBJECT_ID = os.getenv("COMPANY_OBJECT_ID")
LIST_ID = os.getenv("FAST_TRACK_LIST_ID")

# Config
HEADERS = {"Authorization": f"Bearer {ATTIO_TOKEN}"}

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def safe_get(data, key, path="value"):
    """Helper to extract nested Attio values safely based on n8n expressions"""
    try:
        val = data.get(key, [])
        if not val: return None
        if path == "option": return val[0].get("option", {}).get("title")
        if path == "status": return val[0].get("status", {}).get("title")
        if path == "domain": return val[0].get("domain")
        return val[0].get("value")
    except: return None

@app.post("/attio-to-postgres")
async def attio_webhook(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    event = payload.get("events", [{}])[0]
    event_type = event.get("event_type", "")
    actor_type = event.get("actor", {}).get("type")

    # SECURITY & ROUTING FILTERS
    if actor_type != "workspace-member":
        return {"ignored": "not workspace member"}

    # --- FLOW A: COMPANIES (Record) ---
    if "record" in event_type and event.get("id", {}).get("object_id") == COMPANY_OBJECT_ID:
        record_id = event["id"]["record_id"]
        
        if "deleted" in event_type:
            db.query(Company).filter(Company.id_attio == record_id).delete()
            db.commit()
            return {"action": "deleted company"}

        # Fetch Data node
        res = requests.get(f"https://api.attio.com/v2/objects/companies/records/{record_id}", headers=HEADERS)
        data = res.json().get("data", {})
        vals = data.get("values", {})

        company_map = {
            "id_attio": record_id,
            "name": safe_get(vals, "name"),
            "domains": safe_get(vals, "domains", "domain"),
            "created_at": safe_get(vals, "created_at"),
            "one_liner": safe_get(vals, "one_liner"),
            "stage": safe_get(vals, "stage", "option"),
            "round_size": safe_get(vals, "round_size"),
            "current_valuation": safe_get(vals, "current_valuation"),
            "deck_url": safe_get(vals, "deck_url"),
            "reference": safe_get(vals, "reference_6", "option"),
            "reference_explanation": safe_get(vals, "reference_explanation"),
            "date_sourced": safe_get(vals, "date_sourced"),
            "responsible": safe_get(vals, "responsible", "option"),
            "company_type": safe_get(vals, "company_type_4", "option"),
            "fund": safe_get(vals, "fund_7", "option"),
            "business_model": [item.get("option", {}).get("title") for item in vals.get("business_model_4", []) if item.get("option")],
            "constitution_location": [item.get("option", {}).get("title") for item in vals.get("constitution_location_8", []) if item.get("option")]
        }

        # Upsert Logic
        existing = db.query(Company).filter(Company.id_attio == record_id).first()
        if existing:
            for k, v in company_map.items(): setattr(existing, k, v)
        else:
            db.add(Company(**company_map))
        db.commit()

    # --- FLOW B: FAST TRACKS (Entry) ---
    elif "entry" in event_type and event.get("id", {}).get("list_id") == LIST_ID:
        entry_id = event["id"]["entry_id"]

        if "deleted" in event_type:
            db.query(FastTrack).filter(FastTrack.entry_id == entry_id).delete()
            db.commit()
            return {"action": "deleted fast track"}

        # Fetch Entry Data
        res = requests.get(f"https://api.attio.com/v2/lists/fast_tracks/entries/{entry_id}", headers=HEADERS)
        data = res.json().get("data", {})
        entry_vals = data.get("entry_values", {})
        parent_id = data.get("parent_record_id")

        # Find linked company ID
        company = db.query(Company).filter(Company.id_attio == parent_id).first()

        ft_map = {
            "entry_id": entry_id,
            "company_id": company.id if company else None,
            "parent_record_id": parent_id,
            "name": company.name if company else "Unknown",
            "potential_program": safe_get(entry_vals, "potential_program"),
            "added_to_list_at": safe_get(entry_vals, "created_at"),
            "kill_reasons": safe_get(entry_vals, "kill_reasons"),
            "contact_status": safe_get(entry_vals, "contact_status", "option"),
            "first_videocall_done": safe_get(entry_vals, "first_videocall_done"),
            "risk": safe_get(entry_vals, "risk"),
            "urgency": safe_get(entry_vals, "urgency", "option"),
            "next_steps": safe_get(entry_vals, "next_steps"),
            "deadline": safe_get(entry_vals, "deadline"),
            "notes": safe_get(entry_vals, "notes"),
            "last_contacted": safe_get(entry_vals, "las_contacted"),
            "last_modified": safe_get(entry_vals, "last_modified"),
            "date_first_contact": safe_get(entry_vals, "date_first_contact_1"),
            "fast_track_status": safe_get(entry_vals, "fast_track_status_6", "status"),
            "signals_evaluations": safe_get(entry_vals, "signals_evaluations"),
            "green_flags_summary": safe_get(entry_vals, "green_flags_summary"),
            "red_flags_summary": safe_get(entry_vals, "red_flags_summary"),
            "signal_comments": safe_get(entry_vals, "signal_comments")
        }

        # Upsert Logic
        existing_ft = db.query(FastTrack).filter(FastTrack.entry_id == entry_id).first()
        if existing_ft:
            for k, v in ft_map.items(): setattr(existing_ft, k, v)
        else:
            db.add(FastTrack(**ft_map))
        db.commit()

    return {"status": "success"}

if __name__ == "__main__":
    # Ensure tables are created on startup if they don't exist
    Base.metadata.create_all(bind=engine)
    
    # Get port from environment variable (default to 8000 for local dev)
    port = int(os.environ.get("PORT", 8000))
    
    # Run server on 0.0.0.0 to be accessible externally
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False)
