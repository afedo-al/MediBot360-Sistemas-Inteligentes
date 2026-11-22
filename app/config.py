"""Configuración institucional de la clínica (datos ficticios de demostración).

El asistente y las páginas toman de aquí la información administrativa para no inventarla.
Horarios, precios, especialistas y disponibilidad se consultan en la base de datos.
"""
CLINIC = {
    "name": "MediBot 360",
    "address": "Calle 10 #000, Centro Histórico, San Francisco de Campeche, Camp.",
    "phone": "(981) 000 0000",
    "parking": "Hay estacionamiento público a una cuadra.",
    "payment_methods": ["efectivo", "tarjeta de débito o crédito", "transferencia"],
    "payment_policy": "El pago se realiza en recepción el día de la consulta y se entrega comprobante.",
    "insurance": "Por ahora no trabajamos con aseguradoras.",
    "arrival": "Llega 10 minutos antes con tu folio e identificación. Si tienes estudios o recetas previas, tráelos.",
    "emergency_number": "911",
}

# Temas disponibles para solicitudes de contacto con recepción (sin texto libre para no recibir datos clínicos).
CONTACT_TOPICS = {
    "agendar": "Agendar por teléfono",
    "pagos": "Pagos y facturación",
    "cita": "Cambio en una cita",
    "otro": "Otro asunto administrativo",
}
