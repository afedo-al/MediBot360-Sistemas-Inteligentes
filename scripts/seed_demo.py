"""Carga datos FICTICIOS de demostración para presentar el sistema con actividad realista.

Uso:  python -m scripts.seed_demo          (solo si la base está casi vacía)
      python -m scripts.seed_demo --force  (agrega datos aunque ya existan)
"""
import random
import sys
from datetime import date, datetime, timedelta

from app import services
from app.db import connect, init_db

ALIASES = ["Ana P.", "Luis M.", "Carmen R.", "Jorge C.", "Sofía T.", "Diego A.", "Valeria G.", "Raúl H.",
           "Paola V.", "Miguel E.", "Fernanda L.", "Óscar N.", "Daniela S.", "Iván B.", "Mariana O.", "Héctor F.",
           "Lucía Q.", "Andrés K.", "Regina Z.", "Tomás D.", "Elena W.", "Pablo J.", "Natalia U.", "Emilio X."]
INTENTS = ["saludo"] * 14 + ["agendar"] * 12 + ["precios"] * 9 + ["horarios"] * 5 + ["disponibilidad"] * 6 + \
          ["especialidades"] * 6 + ["consultar"] * 4 + ["cancelar"] * 2 + ["humano"] * 3 + ["pagos"] * 3 + \
          ["ubicacion"] * 3 + ["salud"] * 2 + ["emergencia"] * 1 + ["otro"] * 4


def main(force: bool = False) -> None:
    init_db()
    rnd = random.Random(360)
    with connect() as db:
        if not force and db.execute("SELECT COUNT(*) FROM appointments").fetchone()[0] >= 5:
            print("La base ya tiene actividad; usa --force para agregar más datos.")
            return
        pros = db.execute("SELECT p.id,p.specialty_id,s.price FROM professionals p JOIN specialties s "
                          "ON s.id=p.specialty_id WHERE p.active=1").fetchall()
        customers = []
        for i, alias in enumerate(ALIASES):
            phone = f"981{rnd.randint(1000000, 9999999)}"
            src = rnd.choice(["web", "web", "chatbot", "recepcion"])
            cid = services.find_or_create_customer(db, alias, phone, source=src)
            customers.append(cid)
        for alias, topic, status in (("Karla I.", "agendar", "atendida"), ("Samuel Y.", "pagos", "atendida"),
                                     ("Irene C.", "cita", "pendiente"), ("Bruno V.", "agendar", "pendiente"),
                                     ("Prospecto Web", "otro", "pendiente")):
            rid = services.create_contact_request(db, alias, f"981{rnd.randint(1000000, 9999999)}", topic)
            if status == "atendida":
                db.execute("UPDATE contact_requests SET status='atendida',handled_by='recepcion',"
                           "handled_at=datetime('now','localtime') WHERE id=?", (rid,))
        db.execute("UPDATE customers SET stage='contactado' WHERE alias IN ('Karla I.','Samuel Y.')")

        today = date.today()
        made = 0
        for offset in range(-24, 15):
            day = today + timedelta(days=offset)
            if day.weekday() == 6:
                continue
            for _ in range(rnd.randint(2, 5) if offset < 0 else rnd.randint(1, 4)):
                p = rnd.choice(pros)
                sched = db.execute("SELECT start,end FROM schedules WHERE professional_id=? AND weekday=?",
                                   (p["id"], day.weekday())).fetchone()
                if not sched:  # respeta los días laborales de cada especialista
                    continue
                hour = rnd.choice(range(int(sched["start"][:2]), int(sched["end"][:2])))
                t = f"{hour:02d}:00"
                if offset == 0 and t <= datetime.now().strftime("%H:%M"):
                    continue
                busy = db.execute("SELECT 1 FROM appointments WHERE professional_id=? AND visit_date=? AND visit_time=? "
                                  "AND status!='cancelada'", (p["id"], day.isoformat(), t)).fetchone()
                if busy:
                    continue
                cid = rnd.choice(customers)
                status = "confirmada"
                if offset < 0:
                    status = rnd.choices(["completada", "cancelada"], [86, 14])[0]
                elif rnd.random() < .08:
                    status = "cancelada"
                code = services.new_code()
                created = datetime.combine(day - timedelta(days=rnd.randint(1, 6)), datetime.min.time()).replace(
                    hour=rnd.randint(8, 21), minute=rnd.randint(0, 59))
                aid = db.execute("INSERT INTO appointments(code,customer_id,professional_id,visit_date,visit_time,status,"
                                 "channel,created_at) VALUES(?,?,?,?,?,?,?,?)",
                                 (code, cid, p["id"], day.isoformat(), t, status,
                                  rnd.choice(["web", "web", "chatbot", "chatbot", "recepcion"]),
                                  created.strftime("%Y-%m-%d %H:%M:%S"))).lastrowid
                if status == "completada":
                    paid = f"{day.isoformat()} {hour:02d}:{rnd.randint(30, 59)}:00"
                    db.execute("INSERT INTO payments(appointment_id,amount,method,invoice_folio,created_at) "
                               "VALUES(?,?,?,?,?)", (aid, p["price"], rnd.choice(["efectivo", "tarjeta", "tarjeta",
                                                                                   "transferencia"]),
                                                     services.new_code("FAC-", 6), paid))
                made += 1
        db.execute("UPDATE customers SET stage='cliente' WHERE id IN (SELECT customer_id FROM appointments) "
                   "AND stage IN ('prospecto','contactado')")
        for _ in range(180):
            when = datetime.now() - timedelta(days=rnd.randint(0, 24), minutes=rnd.randint(0, 900))
            db.execute("INSERT INTO chat_logs(intent,created_at) VALUES(?,?)",
                       (rnd.choice(INTENTS), when.strftime("%Y-%m-%d %H:%M:%S")))
        # Conversaciones anónimas simuladas para las métricas del asistente (embudo y abandono).
        steps = ["spec", "date", "time", "alias", "phone", "confirm", "done"]
        for n in range(70):
            sess = f"demo-{n:03d}"
            when = (datetime.now() - timedelta(days=rnd.randint(0, 24), minutes=rnd.randint(0, 900)))
            ts = when.strftime("%Y-%m-%d %H:%M:%S")
            ev = [("message", rnd.choice(INTENTS))]
            if rnd.random() < .72:
                reach = rnd.choices(range(1, len(steps) + 1), [8, 10, 12, 8, 4, 6, 52])[0]
                ev += [("step", s) for s in steps[:reach]]
                if reach == len(steps):
                    ev.append(("booking_completed", ""))
            if rnd.random() < .12:
                ev.append(("fallback", rnd.choice(["tienen estacionamiento techado", "aceptan vales",
                                                   "hacen estudios de laboratorio", "dan factura electronica"])))
            if rnd.random() < .06:
                ev.append(("availability_error", "sin_horarios"))
            db.executemany("INSERT INTO chat_events(session,event,detail,created_at) VALUES(?,?,?,?)",
                           [(sess, e, d, ts) for e, d in ev])
        for name, delta, reason in [("Guantes de nitrilo (caja)", -16, "Consumo semanal"),
                                    ("Papel para camilla (rollo)", -3, "Consumo semanal"),
                                    ("Cubrebocas (caja)", 10, "Compra a proveedor")]:
            row = db.execute("SELECT id,stock FROM inventory WHERE name=?", (name,)).fetchone()
            if row and row["stock"] + delta >= 0:
                db.execute("UPDATE inventory SET stock=stock+? WHERE id=?", (delta, row["id"]))
                db.execute("INSERT INTO inventory_movements(item_id,delta,reason) VALUES(?,?,?)", (row["id"], delta, reason))
        print(f"Listo: {len(customers) + 4} pacientes/prospectos y {made} citas de demostración.")


if __name__ == "__main__":
    main(force="--force" in sys.argv)
