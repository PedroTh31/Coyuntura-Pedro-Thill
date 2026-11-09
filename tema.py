"""Tokens visuales compartidos (paleta del Bloque C de PROMPT_ronda_macro_indec.md, identidad del Bloque E5).

Única fuente de los colores y la tipografía del sitio y de las secciones del mail (Bloque B3 y botones/links
de enviar_mail.py). El Bloque 2 de PROMPT_mail_v3.md (rediseño completo del mail) debería leer de acá en vez
de duplicar los valores a mano.

E5 (identidad A+B+C, aprobada por Pedro): la rampa protagonista pasó del azul a ciruela (`principal_*`, antes
`azul_*`). Bloque de identidad visual (09/11/2026, decisión A de Pedro): la rampa pasa de ciruela a azul marino
(sólo modo claro), con dos ajustes de contraste WCAG AA: principal_3 llega a 3:1 (gráficos; la etiqueta directa
de esa serie va en principal_2, ver dashboard.py) y texto_3 a 4,5:1 (texto chico). El arena (negativos) y los grises del B2 (texto_2/3, atrasado, franja) no cambian. Los
titulares, títulos de página y la cabecera van en serif del sistema (`fuente_titulares`, sin Google Fonts: D6 del C).

Ningún otro archivo escribe un hex de la paleta: el CSS (variables `--principal-1`, ...), el JS de los gráficos
(`TEMA`) y el mail se generan desde acá. Los textos que nombran un color ("Valores negativos en arena") salen de
NOMBRE_COLOR, así un cambio de color es un cambio de este archivo y nada más.
"""

TEMA = {
    "principal_1": "#1F3A5F",          # protagonista (azul marino)
    "principal_2": "#4A6FA5",          # secundario / links
    "principal_3": "#7696C2",          # tercer nivel (3,0:1 sobre blanco: mínimo para gráficos, WCAG 1.4.11)
    "principal_contexto": "#DCE5F0",   # fondos de bloque, separadores y barras de contexto
    "texto": "#111111",
    "texto_2": "#4A5A68",         # subtítulos, fechas
    "texto_3": "#677987",         # etiquetas secundarias, fuente (4,5:1 sobre blanco; antes #7A8C9A, 3,5:1)
    "negativo": "#C9A66B",        # negativos / escalas divergentes
    "atrasado": "#2E3A45",        # "⚠ atrasado" (línea de frescura, Bloque B2)
    "franja_fondo": "#EEF1F4",    # franja de rezago grave (Bloque B2)
    "franja_borde": "#4A5A68",
    "fondo": "#FFFFFF",
    "fuente": "Helvetica, Arial, sans-serif",
    "fuente_titulares": 'Georgia, "Times New Roman", Times, serif',
}

# Nombre del color en los textos visibles (leyendas de los gráficos, tabla-semáforo, Acerca). Va acá, junto al
# hex, para que cambiar un color no deje un texto que nombra el anterior.
NOMBRE_COLOR = {
    "principal": "azul",
    "negativo": "arena",
}
