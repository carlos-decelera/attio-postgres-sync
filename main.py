import os
import httpx
import uvicorn
import logging
from fastapi import FastAPI, Request, Depends, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
from database import SessionLocal, init_db, Company, FastTrack

# 1. Configuración de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("AttioWorker")

app = FastAPI()

# Configuración
ATTIO_TOKEN = os.getenv("ATTIO_TOKEN")
HEADERS = {"Authorization": f"Bearer {ATTIO_TOKEN}"}
COMPANY_OBJ_ID = "74c77546-6a6f-4aab-9a19-536d8cfed976"
LIST_ID = "c1b474e0-90cc-48c3-a98d-135da4a71db0"

# --- UTILIDADES ---
def safe_get(data, key, path="value"):
    try:
        val = data.get(key, [])
        if not val: return None
        if path == "option": return val[0].get("option", {}).get("title")
        if path == "status": return val[0].get("status", {}).get("title")
        if path == "domain": return val[0].get("domain")
        return val[0].get("value")
    except: return None

# --- TRABAJADOR EN SEGUNDO PLANO (LA LÓGICA PESADA) ---
async def process_attio_event(event: dict):
    """
    Esta función procesa la lógica de negocio sin bloquear el webhook.
    """
    db = SessionLocal()
    event_type = event.get("event_type", "")
    event_id_info = event.get("id", {})
    
    try:
        async with httpx.AsyncClient(headers=HEADERS, timeout=10.0) as client:
            
            # --- LÓGICA DE EMPRESAS ---
            if "record" in event_type and event_id_info.get("object_id") == COMPANY_OBJ_ID:
                rid = event_id_info.get("record_id")
                
                if "deleted" in event_type:
                    db.query(Company).filter(Company.id_attio == rid).delete()
                    db.commit()
                    logger.info(f"🗑️ Empresa eliminada: {rid}")
                    return

                res = await client.get(f"https://api.attio.com/v2/objects/companies/records/{rid}")
                if res.status_code != 200:
                    logger.error(f"❌ Error Attio API: {res.text}")
                    return

                data = res.json().get("data", {})
                vals = data.get("values", {})

                # Mapeo y limpieza de listas (Empty to NULL)
                b_model = [i.get("option", {}).get("title") for i in vals.get("business_model_4", []) if i.get("option")]
                c_loc = [i.get("option", {}).get("title") for i in vals.get("constitution_location_8", []) if i.get("option")]
                b_type = [i.get("option", {}).get("title") for i in vals.get("business_type", []) if i.get("option")]

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
                    "constitution_location": c_loc if c_loc else None,
                    "business_type": b_type if b_type else None,
                    "comments": safe_get(vals, "comments")
                }

                existing = db.query(Company).filter(Company.id_attio == rid).first()
                if existing:
                    for k, v in c_map.items(): setattr(existing, k, v)
                else:
                    db.add(Company(**c_map))
                db.commit()
                logger.info(f"✅ Empresa sincronizada: {rid}")

            # --- LÓGICA DE FAST TRACKS ---
            elif "entry" in event_type and event_id_info.get("list_id") == LIST_ID:
                eid = event_id_info.get("entry_id")
                
                if "deleted" in event_type:
                    db.query(FastTrack).filter(FastTrack.entry_id == eid).delete()
                    db.commit()
                    logger.info(f"🗑️ FastTrack eliminado: {eid}")
                    return

                res = await client.get(f"https://api.attio.com/v2/lists/fast_tracks/entries/{eid}")
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
                logger.info(f"✅ FastTrack sincronizado: {eid}")

    except SQLAlchemyError as e:
        db.rollback()
        logger.error(f"❌ Error de Base de Datos: {e}")
    except Exception as e:
        logger.error(f"❌ Error inesperado: {e}")
    finally:
        db.close()

# --- ENDPOINT PRINCIPAL ---
@app.post("/attio-to-postgres")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    try:
        payload = await request.json()
    except:
        return {"status": "error", "reason": "invalid json"}

    events = payload.get("events", [])
    if not events:
        return {"status": "empty payload"}

    event = events[0]
    
    # 1. Log inmediato de recepción
    logger.info(f"📩 Recibido: {event.get('event_type')} | ID: {event.get('id', {}).get('record_id') or event.get('id', {}).get('entry_id')}")

    # 2. Seguridad básica
    if event.get("actor", {}).get("type") != "workspace-member":
        return {"status": "ignored", "reason": "not workspace member"}

    # 3. ENCOLAR TAREA Y RESPONDER YA
    background_tasks.add_task(process_attio_event, event)
    
    return {"status": "accepted", "message": "Processing in background"}

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
