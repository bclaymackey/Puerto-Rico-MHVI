import json

from .llm_caller import call_text_llm


_SYSTEM_PROMPT_EN = """You are a public-health analyst writing a Municipality Vulnerability Report for the Puerto Rico Mental Health Vulnerability Index (MHVI).

Style rules:
- Plain, professional language. Avoid jargon. Write for policymakers and the general public.
- Higher scores indicate GREATER vulnerability. State this clearly.
- Use ONLY the numbers provided in the input JSON. Do not invent, estimate, or modify any value.
- Do not invent categories that are not in the JSON.
- If a value is missing, omit it; do not guess.
- No tables, no charts, no images. Markdown bullets and short paragraphs only.

Required structure (use these exact level-2 Markdown headings, in this order):
## Municipality Overview
## Overall Vulnerability Summary
## Category Breakdown
## Highest Vulnerability Areas
## Interpretation Notes
## Conclusion

Section guidance:
- Municipality Overview: one short paragraph naming the municipality and what the report covers.
- Overall Vulnerability Summary: state the overall score and, in plain words, what it means.
- Category Breakdown: a bullet list, one bullet per provided category, in the form "**Category**: score".
- Highest Vulnerability Areas: name the 2-3 categories with the highest scores from the provided data.
- Interpretation Notes: brief reminder that scores are relative and higher = more vulnerable; note that missing categories were not included.
- Conclusion: 2-3 sentence wrap-up.

Output the Markdown only. Do not wrap in code fences."""


_SYSTEM_PROMPT_ES = """Eres un analista de salud pública que redacta un Informe de Vulnerabilidad Municipal para el Índice de Vulnerabilidad de Salud Mental de Puerto Rico (MHVI).

Reglas de estilo:
- Lenguaje claro y profesional. Evita jerga técnica. Escribe para responsables de políticas públicas y el público general.
- Puntajes más altos indican MAYOR vulnerabilidad. Indícalo claramente.
- Usa ÚNICAMENTE los números proporcionados en el JSON de entrada. No inventes, estimes ni modifiques ningún valor.
- No inventes categorías que no estén en el JSON.
- Si un valor falta, omítelo; no adivines.
- Sin tablas, sin gráficos, sin imágenes. Solo viñetas Markdown y párrafos breves.

Estructura requerida (usa exactamente estos encabezados de nivel 2, en este orden):
## Resumen del Municipio
## Resumen General de Vulnerabilidad
## Desglose por Categoría
## Áreas de Mayor Vulnerabilidad
## Notas de Interpretación
## Conclusión

Guía por sección:
- Resumen del Municipio: un párrafo corto que nombra el municipio y lo que cubre el informe.
- Resumen General de Vulnerabilidad: indica el puntaje general y, en lenguaje sencillo, qué significa.
- Desglose por Categoría: una lista con viñetas, una por cada categoría proporcionada, con el formato "**Categoría**: puntaje".
- Áreas de Mayor Vulnerabilidad: nombra las 2-3 categorías con los puntajes más altos del JSON.
- Notas de Interpretación: recordatorio breve de que los puntajes son relativos y mayor = más vulnerable; menciona que las categorías sin datos no se incluyeron.
- Conclusión: cierre de 2-3 oraciones.

Devuelve solo el Markdown. No lo envuelvas en bloques de código."""


def _fallback_markdown(report_data: dict, language: str) -> str:
    """Minimal deterministic Markdown so the PDF still renders if the LLM fails."""
    municipality = report_data.get("municipality", "")
    overall = report_data.get("overall_score")
    categories = report_data.get("categories") or {}

    if language == "es":
        lines = [
            "## Resumen del Municipio",
            f"Informe de vulnerabilidad para {municipality}.",
            "",
            "## Resumen General de Vulnerabilidad",
            f"Puntaje general: {overall if overall is not None else 'no disponible'}. "
            "Puntajes más altos indican mayor vulnerabilidad.",
            "",
            "## Desglose por Categoría",
        ]
    else:
        lines = [
            "## Municipality Overview",
            f"Vulnerability report for {municipality}.",
            "",
            "## Overall Vulnerability Summary",
            f"Overall score: {overall if overall is not None else 'not available'}. "
            "Higher scores indicate greater vulnerability.",
            "",
            "## Category Breakdown",
        ]

    for name, value in categories.items():
        lines.append(f"- **{name}**: {value}")

    if language == "es":
        lines += [
            "",
            "## Áreas de Mayor Vulnerabilidad",
            "Consulte el desglose por categoría arriba.",
            "",
            "## Notas de Interpretación",
            "Los puntajes son relativos y mayores valores indican mayor vulnerabilidad.",
            "",
            "## Conclusión",
            "Informe generado a partir de los últimos datos disponibles.",
        ]
    else:
        lines += [
            "",
            "## Highest Vulnerability Areas",
            "See category breakdown above.",
            "",
            "## Interpretation Notes",
            "Scores are relative; higher values indicate greater vulnerability.",
            "",
            "## Conclusion",
            "Report generated from the latest available data.",
        ]
    return "\n".join(lines)


def generate_report_text(report_data: dict, language: str = "en") -> str:
    """Return Markdown report text for the given municipality data."""
    if not report_data:
        return _fallback_markdown({"municipality": "", "categories": {}}, language)

    instructions = _SYSTEM_PROMPT_ES if language == "es" else _SYSTEM_PROMPT_EN
    input_text = (
        "Generate the report using only the following municipality data "
        "(JSON). Do not introduce any value not present here.\n\n"
        + json.dumps(report_data, ensure_ascii=False, indent=2)
    )

    try:
        text = call_text_llm(instructions, input_text)
        if not text:
            return _fallback_markdown(report_data, language)
        return text
    except Exception as e:
        print(f"[generate_report_text] error: {e}")
        return _fallback_markdown(report_data, language)
