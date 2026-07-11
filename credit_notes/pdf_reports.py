from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)


def _money(value):
    try:
        return f"${float(value):,.2f}"
    except (TypeError, ValueError):
        return str(value or "-")


def _safe(value):
    return str(value if value not in (None, "") else "-").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_negotiation_pdf(report):
    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=18 * mm,
        leftMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=16 * mm,
        title=report.titulo,
        author="CrediTrade MVP",
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="TitleCenter",
            parent=styles["Title"],
            alignment=TA_CENTER,
            fontSize=17,
            leading=21,
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallMuted",
            parent=styles["BodyText"],
            fontSize=8.5,
            textColor=colors.HexColor("#5c6675"),
            leading=11,
        )
    )
    styles.add(
        ParagraphStyle(
            name="Section",
            parent=styles["Heading2"],
            fontSize=12,
            leading=15,
            spaceBefore=9,
            spaceAfter=5,
            textColor=colors.HexColor("#243b53"),
        )
    )
    styles["BodyText"].leading = 14

    content = report.contenido or {}
    expediente = content.get("expediente", {})
    vendedor = content.get("vendedor", {})
    comprador = content.get("comprador", {})
    titulo = content.get("titulo", {})
    propuesta = content.get("propuesta", {})
    responsables = content.get("responsables", {})

    story = [
        Paragraph(_safe(report.titulo), styles["TitleCenter"]),
        Paragraph(
            f"Generado: {_safe(report.generado_en.strftime('%Y-%m-%d %H:%M'))} | "
            f"Modelo: {_safe(report.modelo_ia or 'modelo no especificado')}",
            styles["SmallMuted"],
        ),
        Spacer(1, 7 * mm),
        Paragraph("Resumen ejecutivo", styles["Section"]),
        Paragraph(_safe(report.resumen), styles["BodyText"]),
        Paragraph("Datos del expediente", styles["Section"]),
    ]

    def add_table(rows):
        table = Table(rows, colWidths=[55 * mm, 105 * mm], hAlign="LEFT")
        table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eef2f7")),
                    ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#243b53")),
                    ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 7),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 7),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 9),
                ]
            )
        )
        story.append(table)

    add_table(
        [
            ["Número de título", _safe(expediente.get("numero_titulo"))],
            ["Estado", _safe(expediente.get("estado"))],
            ["Próxima acción", _safe(expediente.get("proxima_accion"))],
        ]
    )

    story.append(Paragraph("Partes", styles["Section"]))
    add_table(
        [
            ["Vendedor", _safe(vendedor.get("nombre"))],
            ["RUC vendedor", _safe(vendedor.get("ruc"))],
            ["Representante", _safe(vendedor.get("representante"))],
            ["Comprador", _safe(comprador.get("nombre"))],
            ["RUC comprador", _safe(comprador.get("ruc"))],
        ]
    )

    story.append(Paragraph("Título y propuesta", styles["Section"]))
    add_table(
        [
            ["Tipo", _safe(titulo.get("tipo"))],
            ["Origen tributario", _safe(titulo.get("origen"))],
            ["Valor nominal", _money(titulo.get("valor_nominal"))],
            ["Saldo disponible", _money(titulo.get("saldo"))],
            ["Mínimo a recibir", _money(titulo.get("minimo_recibir"))],
            ["Valor de venta", _money(propuesta.get("valor_venta"))],
            ["Descuento", f"{_safe(propuesta.get('descuento_porcentaje'))}%"],
            ["Fecha de propuesta", _safe(propuesta.get("fecha"))],
            ["Vigencia", _safe(propuesta.get("vigencia_hasta"))],
        ]
    )

    if propuesta.get("terminos"):
        story.extend(
            [
                Paragraph("Términos", styles["Section"]),
                Paragraph(_safe(propuesta.get("terminos")), styles["BodyText"]),
            ]
        )
    if content.get("texto_carta"):
        story.extend(
            [
                Paragraph("Borrador de carta", styles["Section"]),
                Paragraph(_safe(content.get("texto_carta")).replace("\n", "<br/>"), styles["BodyText"]),
            ]
        )

    points = content.get("puntos_clave") or []
    if points:
        story.append(Paragraph("Puntos clave", styles["Section"]))
        for item in points:
            story.append(Paragraph(f"• {_safe(item)}", styles["BodyText"]))

    risks = content.get("riesgos_y_pendientes") or []
    if risks:
        story.append(Paragraph("Riesgos y pendientes", styles["Section"]))
        for item in risks:
            story.append(Paragraph(f"• {_safe(item)}", styles["BodyText"]))

    documents = content.get("documentos") or []
    if documents:
        story.append(Paragraph("Documentos del expediente", styles["Section"]))
        for doc in documents:
            story.append(
                Paragraph(
                    f"• {_safe(doc.get('nombre'))} — {_safe(doc.get('tipo'))} "
                    f"({_safe(doc.get('fuente'))})",
                    styles["BodyText"],
                )
            )

    story.extend(
        [
            Paragraph("Responsables", styles["Section"]),
        ]
    )
    add_table(
        [
            ["Recepcionista", _safe(responsables.get("recepcionista"))],
            ["Contador", _safe(responsables.get("contador"))],
            ["Vendedor", _safe(responsables.get("vendedor"))],
        ]
    )

    story.extend(
        [
            Spacer(1, 7 * mm),
            Paragraph("Aviso de alcance del MVP", styles["Section"]),
            Paragraph(
                _safe(
                    content.get(
                        "aviso_regulatorio",
                        "La liquidación, transferencia y endoso no se ejecutan desde este sistema.",
                    )
                ),
                styles["BodyText"],
            ),
            Spacer(1, 8 * mm),
            Paragraph(
                "Documento generado automáticamente y sujeto a revisión y aprobación humana.",
                styles["SmallMuted"],
            ),
        ]
    )

    document.build(story)
    return buffer.getvalue()
