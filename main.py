import os
import requests
import uvicorn
import logging
from fastapi import FastAPI, Request, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
# Importante para evitar el NameError
from sqlalchemy.dialects.postgresql import ARRAY 
from database import SessionLocal, init_db, Company, FastTrack

# 1. Configuración de Logging
logging.basicConfig(
    level=logging.INFO, 
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("AttioWebhook")

app = FastAPI()

# Configuración desde Variables de Railway
ATTIO_TOKEN = os.getenv("ATTIO_TOKEN")
HEADERS = {"Authorization": f"Bearer {ATTIO_TOKEN}"}
COMPANY_OBJ_ID = "74c77546-6a6f-4aab-9a19-536d8cfed976"
LIST_ID = "c1b474e0-90cc-48c3-a98d-135da4a71db0"

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def safe_get(data, key, path="value"):
    try:
        val = data.get(key, [])
        if not val: return None
        if path == "option": return val[0].get("option", {}).get("title")
        if path == "status": return val[0].get("status", {}).get("title")
        if path == "domain": return val[0].get("domain")
        return val[0].get("value")
    except:
        return None

@app.post("/attio-to-postgres")
async def webhook(request: Request, db: Session = Depends(get_db)):
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"Error parseando JSON: {e}")
        return {"status": "error", "reason": "invalid json"}

    # Extraer evento principal
    events_list = payload.get("events", [])
    if not events_list:
        return {"status": "ignored", "reason": "no events in payload"}
    
    event = events_list[0]
    event_type = event.get("event_type", "unknown")
    
    # --- LOGGING DE ENTRADA ---
    # Identificar IDs para el log
    event_id_info = event.get("id", {})
    record_id = event_id_info.get("record_id")
    entry_id = event_id_info.get("entry_id")
    target_id = record_id if record_id else entry_id

    logger.info("="*60)
    logger.info(f"🔔 EVENTO: {event_type}")
    logger.info(f"🆔 ID: {target_id}")
    logger.info(f"📦 DATA: {event}")
    logger.info("="*60)
    
    # Filtro de Seguridad
    if event.get("actor", {}).get("type") != "workspace-member":
        logger.info("Evento ignorado: No fue realizado por un miembro del workspace.")
        return {"ignored": "not workspace member"}

    # --- FLUJO EMPRESAS ---
    if "record" in event_type and event_id_info.get("object_id") == COMPANY_OBJ_ID:
        rid = record_id
        if "deleted" in event_type:
            db.query(Company).filter(Company.id_attio == rid).delete()
            db.commit()
            return {"status": "deleted company"}

        res = requests.get(f"https://api.attio.com/v2/objects/companies/records/{rid}", headers=HEADERS)
        if res.status_code != 200:
            logger.error(f"Error Fetching Attio Record {rid}: {res.text}")
            return {"status": "error", "msg": "attio fetch failed"}

        data = res.json().get("data", {})
        vals = data.get("values", {})

        # Procesar listas para que si están vacías sean None (NULL en DB)
        b_model = [i.get("option", {}).get("title") for i in vals.get("business_model_4", []) if i.get("option")]
        c_location = [i.get("option", {}).get("title") for i in vals.get("constitution_location_8", []) if i.get("option")]

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
            "business_model": b_model if b_model else None,
            "constitution_location": c_location if c_location else None
        }
        
        try:
            existing = db.query(Company).filter(Company.id_attio == rid).first()
            if existing:
                for k, v in c_map.items(): setattr(existing, k, v)
            else:
                db.add(Company(**c_map))
            db.commit()
            logger.info(f"✅ Empresa {rid} sincronizada correctamente.")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"❌ Error de DB en Empresa: {str(e)}")

    # --- FLUJO FAST TRACKS ---
    elif "entry" in event_type and event_id_info.get("list_id") == LIST_ID:
        eid = entry_id
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

        try:
            existing_ft = db.query(FastTrack).filter(FastTrack.entry_id == eid).first()
            if existing_ft:
                for k, v in ft_map.items(): setattr(existing_ft, k, v)
            else:
                db.add(FastTrack(**ft_map))
            db.commit()
            logger.info(f"✅ Fast Track Entry {eid} sincronizada correctamente.")
        except SQLAlchemyError as e:
            db.rollback()
            logger.error(f"❌ Error de DB en FastTrack: {str(e)}")

    return {"status": "success"}

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
