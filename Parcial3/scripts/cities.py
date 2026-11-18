"""28 ciudades capitales con acceso vial o peaje: codigo DANE, nombre y departamento. Bogota D.C. es tambien capital de Cundinamarca.

Se excluyen San Andres, Leticia, Inirida y Mitu: sin carretera continua hacia el resto del pais ni peajes (decision de diseno, 2026-11-17;
evidencia en data/access_research.json). El catalogo de localidades (data/localities_colombia.json) si las cubre."""
CITIES = [
    ("05001", "Medellín", "Antioquia"),
    ("08001", "Barranquilla", "Atlántico"),
    ("11001", "Bogotá D.C.", "Bogotá D.C."),
    ("13001", "Cartagena", "Bolívar"),
    ("15001", "Tunja", "Boyacá"),
    ("17001", "Manizales", "Caldas"),
    ("18001", "Florencia", "Caquetá"),
    ("19001", "Popayán", "Cauca"),
    ("20001", "Valledupar", "Cesar"),
    ("23001", "Montería", "Córdoba"),
    ("27001", "Quibdó", "Chocó"),
    ("41001", "Neiva", "Huila"),
    ("44001", "Riohacha", "La Guajira"),
    ("47001", "Santa Marta", "Magdalena"),
    ("50001", "Villavicencio", "Meta"),
    ("52001", "Pasto", "Nariño"),
    ("54001", "Cúcuta", "Norte de Santander"),
    ("63001", "Armenia", "Quindío"),
    ("66001", "Pereira", "Risaralda"),
    ("68001", "Bucaramanga", "Santander"),
    ("70001", "Sincelejo", "Sucre"),
    ("73001", "Ibagué", "Tolima"),
    ("76001", "Cali", "Valle del Cauca"),
    ("81001", "Arauca", "Arauca"),
    ("85001", "Yopal", "Casanare"),
    ("86001", "Mocoa", "Putumayo"),
    ("95001", "San José del Guaviare", "Guaviare"),
    ("99001", "Puerto Carreño", "Vichada"),
]
# El punto de Wikidata de Leticia aparece dos veces; se usa el de la ciudad (lat ~ -4.215).
LETICIA_FIX = ("91001", -4.2, )
