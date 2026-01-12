import os
import requests
import uvicorn
from fastapi import FastAPI, Request, Depends
from sqlalchemy.orm import Session
from database import SessionLocal, init_db, Company, FastTrack

app = FastAPI()

# Configuración desde Variables de Railway
ATTIO_TOKEN = os.getenv("ATTIO_TOKEN")
HEADERS = {"Authorization": f"Bearer {ATTIO_TOKEN}"}
COMPANY_OBJ_ID = "74c77546-6a6f-4aab-9a19-536d8cfed976"
LIST_ID = "c1b474e0-90cc-48c3-a98d-135da4a71db0"

def get_db():
    db = SessionLocal()
    try: yield db
    finally: db.close()

def safe_get(data, key, path="value"):
    try:
        val = data.get(key, [])
        if not val: return None
        if path == "option": return val[0].get("option", {}).get("title")
        if path == "status": return val[0].get("status", {}).get("title")
        if path == "domain": return val[0].get("domain")
        return val[0].get("value")
    except: return None

@app.post("/attio-to-postgres")
async def webhook(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except ClientDisconnect:
        # Si el cliente se desconecta, simplemente ignoramos la petición silenciosamente
        return {"status": "ignored", "reason": "client disconnected"}
    except Exception:
        return {"status": "error", "reason": "invalid json"}
    
    payload = await request.json()
    event = payload.get("events", [{}])[0]
    event_type = event.get("event_type", "")
    
    # Filtro de Seguridad
    if event.get("actor", {}).get("type") != "workspace-member":
        return {"ignored": "not workspace member"}

    # --- FLUJO EMPRESAS ---
    if "record" in event_type and event.get("id", {}).get("object_id") == COMPANY_OBJ_ID:
        rid = event["id"]["record_id"]
        if "deleted" in event_type:
            db.query(Company).filter(Company.id_attio == rid).delete()
            db.commit()
            return {"status": "deleted company"}

        res = requests.get(f"https://api.attio.com/v2/objects/companies/records/{rid}", headers=HEADERS)
        data = res.json().get("data", {})
        vals = data.get("values", {})

        c_map = {
            "id_attio": rid,
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
            "business_model": [i.get("option", {}).get("title") for i in vals.get("business_model_4", []) if i.get("option")],
            "constitution_location": [i.get("option", {}).get("title") for i in vals.get("constitution_location_8", []) if i.get("option")]
        }
        
        existing = db.query(Company).filter(Company.id_attio == rid).first()
        if existing:
            for k, v in c_map.items(): setattr(existing, k, v)
        else:
            db.add(Company(**c_map))
        db.commit()

    # --- FLUJO FAST TRACKS ---
    elif "entry" in event_type and event.get("id", {}).get("list_id") == LIST_ID:
        eid = event["id"]["entry_id"]
        if "deleted" in event_type:
            db.query(FastTrack).filter(FastTrack.entry_id == eid).delete()
            db.commit()
            return {"status": "deleted fast track"}

        res = requests.get(f"https://api.attio.com/v2/lists/fast_tracks/entries/{eid}", headers=HEADERS)
        data = res.json().get("data", {})
        evs = data.get("entry_values", {})
        pid = data.get("parent_record_id")

        comp = db.query(Company).filter(Company.id_attio == pid).first()

        ft_map = {
            "entry_id": eid,
            "company_id": comp.id if comp else None,
            "parent_record_id": pid,
            "name": comp.name if comp else "Unknown",
            "potential_program": safe_get(evs, "potential_program"),
            "added_to_list_at": safe_get(evs, "created_at"),
            "kill_reasons": safe_get(evs, "kill_reasons"),
            "contact_status": safe_get(evs, "contact_status", "option"),
            "first_videocall_done": safe_get(evs, "first_videocall_done"),
            "risk": safe_get(evs, "risk"),
            "urgency": safe_get(evs, "urgency", "option"),
            "next_steps": safe_get(evs, "next_steps"),
            "deadline": safe_get(evs, "deadline"),
            "notes": safe_get(evs, "notes"),
            "last_contacted": safe_get(evs, "las_contacted"),
            "last_modified": safe_get(evs, "last_modified"),
            "date_first_contact": safe_get(evs, "date_first_contact_1"),
            "fast_track_status": safe_get(evs, "fast_track_status_6", "status"),
            "signals_evaluations": safe_get(evs, "signals_evaluations"),
            "green_flags_summary": safe_get(evs, "green_flags_summary"),
            "red_flags_summary": safe_get(evs, "red_flags_summary"),
            "signal_comments": safe_get(evs, "signal_comments")
        }

        existing_ft = db.query(FastTrack).filter(FastTrack.entry_id == eid).first()
        if existing_ft:
            for k, v in ft_map.items(): setattr(existing_ft, k, v)
        else:
            db.add(FastTrack(**ft_map))
        db.commit()

    return {"status": "success"}

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
