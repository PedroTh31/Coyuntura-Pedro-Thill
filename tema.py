"""Tokens visuales compartidos (paleta del Bloque C de PROMPT_ronda_macro_indec.md, identidad del Bloque E5).

Única fuente de los colores y la tipografía del sitio y de las secciones del mail (Bloque B3 y botones/links
de enviar_mail.py). El Bloque 2 de PROMPT_mail_v3.md (rediseño completo del mail) debería leer de acá en vez
de duplicar los valores a mano.

E5 (identidad A+B+C, aprobada por Pedro): la rampa protagonista pasó del azul a ciruela (`principal_*`, antes
`azul_*`). El arena (negativos) y los grises del B2 (texto_2/3, atrasado, franja) no cambian. Los titulares,
títulos de página y la cabecera van en serif del sistema (`fuente_titulares`, sin Google Fonts: D6 del C).
"""

TEMA = {
    "principal_1": "#46245A",          # protagonista (ciruela)
    "principal_2": "#85559B",          # secundario / links
    "principal_3": "#C2A3D1",          # tercer nivel
    "principal_contexto": "#E3D5EA",   # fondos de bloque, separadores y barras de contexto (validado en E5)
    "texto": "#111111",
    "texto_2": "#4A5A68",         # subtítulos, fechas
    "texto_3": "#7A8C9A",         # etiquetas secundarias, fuente
    "negativo": "#C9A66B",        # negativos / escalas divergentes
    "atrasado": "#2E3A45",        # "⚠ atrasado" (línea de frescura, Bloque B2)
    "franja_fondo": "#EEF1F4",    # franja de rezago grave (Bloque B2)
    "franja_borde": "#4A5A68",
    "fondo": "#FFFFFF",
    "fuente": "Helvetica, Arial, sans-serif",
    "fuente_titulares": 'Georgia, "Times New Roman", Times, serif',
}
