from pymongo import ASCENDING, DESCENDING, AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase

from app.core.config import settings


class Mongo:
    client: AsyncMongoClient | None = None
    db: AsyncDatabase | None = None


mongo = Mongo()


async def connect_to_mongo() -> None:
    mongo.client = AsyncMongoClient(settings.mongodb_uri, tz_aware=True)
    mongo.db = mongo.client[settings.mongodb_db]
    await ensure_indexes()


async def close_mongo_connection() -> None:
    if mongo.client is not None:
        await mongo.client.close()


async def ensure_indexes() -> None:
    await mongo.db.users.create_index([("email", ASCENDING)], unique=True)

    patients = mongo.db.patients
    await patients.create_index([("patient_id", ASCENDING)], unique=True)
    await patients.create_index([("phone_key", ASCENDING), ("name_key", ASCENDING)])
    await patients.create_index([("managed_by", ASCENDING)])
    await patients.create_index([("created_at", DESCENDING)])

    appointments = mongo.db.appointments
    # slot_key is only present while an appointment holds a slot; unsetting it releases the slot
    await appointments.create_index(
        [("slot_key", ASCENDING)], unique=True, partialFilterExpression={"slot_key": {"$type": "string"}}
    )
    await appointments.create_index([("doctor_id", ASCENDING), ("date", ASCENDING), ("token", ASCENDING)])
    await appointments.create_index([("patient_id", ASCENDING), ("doctor_id", ASCENDING), ("date", DESCENDING)])
    await appointments.create_index([("date", ASCENDING), ("start_time", ASCENDING)])

    await mongo.db.doctor_leaves.create_index([("doctor_id", ASCENDING), ("start_date", ASCENDING)])
    await mongo.db.holidays.create_index([("date", ASCENDING)], unique=True)

    await mongo.db.history_sessions.create_index([("appointment_id", ASCENDING), ("status", ASCENDING)])
    await mongo.db.history_sessions.create_index([("patient_id", ASCENDING), ("submitted_at", DESCENDING)])
    await mongo.db.alerts.create_index([("created_at", DESCENDING)])

    await mongo.db.vitals.create_index([("patient_id", ASCENDING), ("recorded_at", ASCENDING)])
    await mongo.db.vitals.create_index([("appointment_id", ASCENDING)])
    await mongo.db.clinical_notes.create_index([("appointment_id", ASCENDING)], unique=True)

    await mongo.db.reports.create_index([("patient_id", ASCENDING), ("report_date", DESCENDING)])
    await mongo.db.reports.create_index([("patient_id", ASCENDING), ("versions.sha256", ASCENDING)])
    await mongo.db.report_summaries.create_index([("report_id", ASCENDING), ("report_version", ASCENDING)], unique=True)
    await mongo.db.report_summaries.create_index([("patient_id", ASCENDING), ("status", ASCENDING)])

    await mongo.db.prescriptions.create_index([("appointment_id", ASCENDING)], unique=True)
    await mongo.db.bills.create_index([("appointment_id", ASCENDING)], unique=True)
    await mongo.db.case_summaries.create_index([("appointment_id", ASCENDING)], unique=True)
    await mongo.db.prescription_versions.create_index([("appointment_id", ASCENDING), ("version", ASCENDING)], unique=True)
    await mongo.db.prescription_versions.create_index([("public_id", ASCENDING)], unique=True)
    await mongo.db.rx_links.create_index([("token_hash", ASCENDING)])
    await mongo.db.rx_deliveries.create_index([("appointment_id", ASCENDING), ("at", DESCENDING)])
    await mongo.db.rx_templates.create_index([("doctor_id", ASCENDING)])
    await mongo.db.rx_favourites.create_index([("doctor_id", ASCENDING)])
    await mongo.db.medicines.create_index([("search", ASCENDING)])

    audit = mongo.db.audit_log
    await audit.create_index([("seq", ASCENDING)], unique=True)
    await audit.create_index([("patient_id", ASCENDING), ("seq", DESCENDING)])
    await audit.create_index([("actor_id", ASCENDING), ("seq", DESCENDING)])
    await audit.create_index([("at", DESCENDING)])


    await mongo.db.bills.create_index([("patient_id", ASCENDING), ("date", DESCENDING)])
    await mongo.db.bills.create_index([("status", ASCENDING), ("balance", ASCENDING)])
    await mongo.db.receipts.create_index([("number", ASCENDING)], unique=True)
    await mongo.db.receipts.create_index([("issued_at", ASCENDING)])
    await mongo.db.receipts.create_index([("appointment_id", ASCENDING)])
    await mongo.db.receipts.create_index([("patient_id", ASCENDING)])
    await mongo.db.share_links.create_index([("kind", ASCENDING), ("ref_id", ASCENDING), ("token_hash", ASCENDING)])
    await mongo.db.reconciliations.create_index([("date", ASCENDING), ("at", DESCENDING)])

    notifications = mongo.db.notifications
    await notifications.create_index([("status", ASCENDING), ("scheduled_at", ASCENDING)])
    await notifications.create_index([("patient_id", ASCENDING), ("scheduled_at", DESCENDING)])
    await notifications.create_index([("channel", ASCENDING), ("to", ASCENDING), ("sent_at", DESCENDING)])
    await notifications.create_index([("batch", ASCENDING)])
    await mongo.db.appointments.create_index([("follow_up_of", ASCENDING)], sparse=True)
    await mongo.db.prescriptions.create_index([("status", ASCENDING), ("follow_up.date", ASCENDING)])
    await mongo.db.callbacks.create_index([("appointment_id", ASCENDING), ("at", DESCENDING)])

def get_db() -> AsyncDatabase:
    return mongo.db
