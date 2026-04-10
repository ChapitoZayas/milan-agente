# agent/tools.py — Herramientas del agente Milan
# Generado por AgentKit

"""
Herramientas específicas para Milan, negocio de renta de vestidos.
Estas funciones apoyan los casos de uso: FAQ y agendado de citas.
"""

import os
import yaml
import logging
import httpx
from datetime import datetime

logger = logging.getLogger("agentkit")


def cargar_info_negocio() -> dict:
    """Carga la información del negocio desde business.yaml."""
    try:
        with open("config/business.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        logger.error("config/business.yaml no encontrado")
        return {}


def obtener_horario() -> dict:
    """Retorna el horario de atención de Milan."""
    info = cargar_info_negocio()
    horario_texto = info.get("negocio", {}).get("horario", "No disponible")

    # Verificar si está en horario de atención ahora
    ahora = datetime.now()
    dia_semana = ahora.weekday()  # 0=Lunes, 6=Domingo
    hora_actual = ahora.hour + ahora.minute / 60

    esta_abierto = False
    if dia_semana <= 4:  # Lunes a Viernes
        if (10 <= hora_actual < 14) or (16 <= hora_actual < 19):
            esta_abierto = True
    elif dia_semana == 5:  # Sábado
        if 11 <= hora_actual < 15:
            esta_abierto = True

    return {
        "horario": horario_texto,
        "esta_abierto": esta_abierto,
        "dia_actual": ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"][dia_semana],
    }


def buscar_en_knowledge(consulta: str) -> str:
    """
    Busca información relevante en los archivos de /knowledge.
    Retorna el contenido más relevante encontrado.
    """
    resultados = []
    knowledge_dir = "knowledge"

    if not os.path.exists(knowledge_dir):
        return "No hay archivos de conocimiento disponibles."

    for archivo in os.listdir(knowledge_dir):
        ruta = os.path.join(knowledge_dir, archivo)
        if archivo.startswith(".") or not os.path.isfile(ruta):
            continue
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                contenido = f.read()
                # Búsqueda simple por coincidencia de texto
                if consulta.lower() in contenido.lower():
                    resultados.append(f"[{archivo}]: {contenido[:500]}")
        except (UnicodeDecodeError, IOError):
            continue

    if resultados:
        return "\n---\n".join(resultados)
    return "No encontré información específica sobre eso en mis archivos."


# ════════════════════════════════════════════════════════════
# Herramientas para AGENDAR CITAS — Caso de uso de Milan
# ════════════════════════════════════════════════════════════

# Almacenamiento simple de citas en memoria (en producción usar BD)
_citas_pendientes: dict[str, dict] = {}


def iniciar_reservacion(telefono: str, datos: dict) -> str:
    """
    Registra una solicitud de cita o reservación de vestido.

    Args:
        telefono: Número de la clienta
        datos: Diccionario con nombre, fecha, hora, tipo_evento, talla (opcional)

    Returns:
        Mensaje de confirmación para la clienta
    """
    _citas_pendientes[telefono] = {
        **datos,
        "estado": "pendiente",
        "registrado_en": datetime.now().isoformat(),
    }

    nombre = datos.get("nombre", "clienta")
    fecha = datos.get("fecha", "la fecha indicada")
    hora = datos.get("hora", "el horario indicado")
    evento = datos.get("tipo_evento", "tu evento")

    logger.info(f"Cita registrada para {nombre} ({telefono}): {fecha} a las {hora}")

    return (
        f"¡Perfecto, {nombre}! 🎉 He registrado tu cita:\n\n"
        f"📅 Fecha: {fecha}\n"
        f"🕐 Hora: {hora}\n"
        f"👗 Evento: {evento}\n\n"
        f"Te esperamos con gusto en Milan. Si necesitas cambiar algo, avísanos con anticipación. ✨"
    )


def consultar_cita(telefono: str) -> str:
    """Consulta si hay una cita registrada para este número."""
    cita = _citas_pendientes.get(telefono)
    if not cita:
        return "No encontré una cita registrada para tu número."

    return (
        f"Tienes una cita registrada:\n"
        f"📅 Fecha: {cita.get('fecha', 'N/A')}\n"
        f"🕐 Hora: {cita.get('hora', 'N/A')}\n"
        f"👗 Evento: {cita.get('tipo_evento', 'N/A')}\n"
        f"Estado: {cita.get('estado', 'pendiente')}"
    )


# ════════════════════════════════════════════════════════════
# Escalamiento — notificación automática a la dueña
# ════════════════════════════════════════════════════════════

async def escalar_conversacion(
    telefono_cliente: str,
    motivo: str,
    historial: list[dict],
    mensaje_actual: str,
) -> bool:
    """
    Envía un aviso de WhatsApp al número de escalamiento cuando se detecta
    una situación que requiere atención directa de la dueña.

    Args:
        telefono_cliente: Número de la clienta que disparó el escalamiento
        motivo: Descripción breve del motivo (generada por Claude)
        historial: Mensajes anteriores de la conversación
        mensaje_actual: El último mensaje del cliente que disparó el escalamiento

    Returns:
        True si el aviso se envió correctamente
    """
    numero_escalamiento = os.getenv("NUMERO_ESCALAMIENTO")
    whapi_token = os.getenv("WHAPI_TOKEN")

    if not numero_escalamiento:
        logger.warning("NUMERO_ESCALAMIENTO no configurado — escalamiento no enviado")
        return False
    if not whapi_token:
        logger.warning("WHAPI_TOKEN no configurado — escalamiento no enviado")
        return False

    # Construir resumen con los últimos 6 mensajes + el mensaje actual
    ultimos = historial[-6:] if len(historial) > 6 else historial
    lineas = []
    for msg in ultimos:
        prefijo = "Cliente" if msg["role"] == "user" else "Agente"
        texto = msg["content"][:120].replace("\n", " ")
        lineas.append(f"  {prefijo}: {texto}")
    lineas.append(f"  Cliente: {mensaje_actual[:120].replace(chr(10), ' ')}")
    resumen = "\n".join(lineas) if lineas else "  (sin historial previo)"

    aviso = (
        f"🚨 *ESCALAMIENTO — Milan*\n\n"
        f"📞 *Número del cliente:* {telefono_cliente}\n"
        f"⚠️ *Motivo:* {motivo}\n\n"
        f"📋 *Resumen de la conversación:*\n"
        f"{resumen}\n\n"
        f"_Responde directamente a ese número si necesitas atenderlo personalmente._"
    )

    headers = {
        "Authorization": f"Bearer {whapi_token}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                "https://gate.whapi.cloud/messages/text",
                json={"to": numero_escalamiento, "body": aviso},
                headers=headers,
                timeout=10.0,
            )
            if r.status_code != 200:
                logger.error(f"Error enviando escalamiento: {r.status_code} — {r.text}")
                return False
            logger.info(f"Escalamiento enviado a {numero_escalamiento} | Motivo: {motivo}")
            return True
    except Exception as e:
        logger.error(f"Excepción al enviar escalamiento: {e}")
        return False
