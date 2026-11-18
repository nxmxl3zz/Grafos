# PERA dataset: `pera_colombia.csv`

The bundled PERA v1 dataset is a real road network of **1,070 nodes**: every municipal seat in Colombia (DANE DIVIPOLA) that has a driving road in OSRM, including all 28 mainland departmental capitals (Bogotá D.C. also represents Cundinamarca). It has **2,453 road links** and **148 tolls**. Each node is linked to its nearest neighbours by the real OSRM road; a link is dropped only when another chain of kept links is at most 3% longer, so the network is connected by construction (one component) and long trips are chains of real legs. Totals are sums over those legs between town centres, so they can be a few percent above a direct OSRM route. 30 seats have no road in OSRM (Pacific coast of Chocó, Cauca and Nariño, Amazonian and island municipalities) and are left out of the graph; they remain searchable in the nationwide locality catalogue. San Andrés, Leticia, Inírida and Mitú are deliberately **excluded** from the graph: they have no continuous road to the rest of the country and no tolls, so a toll-route model has nothing to say about them (see [access research](access_research.json) for the evidence and the vehicle-transport candidates). They remain searchable in the nationwide locality catalogue. Puerto Carreño stays, with seasonal access disclosed. A query with no path only establishes that no path is recorded in this network.

## Sources and estimates

| Field | Source and limitations |
|---|---|
| City coordinates and DANE codes | Wikidata P625/P7325 |
| Route distance and time | [OSRM](https://project-osrm.org/) driving estimates based on OpenStreetMap, not official distances or guaranteed current travel times |
| Toll locations, names and category I tariffs | [INVIAS Peajes](https://www.datos.gov.co/resource/68qj-5xux.json); record geometry is used because some coordinate columns are corrupted |
| Toll cross-check | [ANI category I table](https://www.datos.gov.co/resource/7gj8-j6i3.json); values can differ from INVIAS and are recorded in the build report |
| Petrol price | 15,886 COP/gal, historical reference average for 13 cities in November 2026, not a live price |
| Consumption and speed parameters | 40 km/gal and 55 km/h are editable assumptions |

The toll values are sourced snapshots, not verified current charges. They cover only tolls matched to selected OSRM geometries and may omit tolls, direction-dependent charges, ferry fees, border costs and other expenses. Total tolls are therefore **recorded toll estimates**, not the total cost of a journey. Fuel is estimated from route distance and the selected parameters; no waterborne candidate is entered as a road edge or charged road fuel.

## Construction and limits

Candidates come from nearby capitals, neighboring departments and selected corridors. OSRM geometries passing close to a third capital are split conceptually into shorter graph links. A low mean speed or large OSRM snap is a heuristic for manual review, not proof a road or ferry is absent. Department and distance filters also exclude some candidate pairs before OSRM is examined; foreign routes and waterborne services are not modeled. Tolls within 1 km of accepted geometry are assigned in route order. This proximity method can include or miss tolls; INVIAS and ANI snapshots differ. Two distinct tolls named Supía carry their sector in the name.

Puerto Carreño has three modeled approaches, based on OSRM estimates; authorities describe seasonal access, and an alternate approach can involve a planchón. Verify road conditions and any water-crossing fee separately. Fixed graph values do not encode closures, seasonality, ferry timetables or directional tariffs. [National Parks route guidance](https://www.parquesnacionales.gov.co/wp-content/uploads/2025/07/ABC-PARA-VISITAR-EL-PNN-EL-TUPARRO.pdf) and [Ministry of Finance](https://www.minhacienda.gov.co/documents/d/portal/ivf_puerto_carreno_2023?download=true) describe these limitations.

## Reproduce and validate

```bash
python3 scripts/build_data.py --offline
python3 scripts/validate_data.py
python3 tests/integration/check_interop.py build/pera_cpp data/pera_colombia.csv
```

Rebuilding uses the local cache in `noCommit/data-cache/` and writes a decision report there. The validator checks references, ranges and route plausibility; unusually low or high speeds are review warnings, not evidence of physical inaccessibility.

## Municipal seats not in the graph (34)

These seats exist in the nationwide locality catalogue (searchable in locality mode) but are **not nodes of the road graph**, because OSRM finds no continuous road connecting them to the main network.

- **Department capitals (4, excluded on purpose):** San Andrés, Leticia, Inírida, Mitú.
- **Chocó, Cauca and Nariño coast (23):** Acandí, Bahía Solano, Bajo Baudó, Bojayá, Carmen del Darién, El Charco, El Litoral del San Juan, Francisco Pizarro, Guapi, Juradó, La Tola, López de Micay, Medio Atrato, Mosquera (Nariño), Murindó, Nuquí, Olaya Herrera, Río Iró, Santa Bárbara (Nariño), Sipí, Timbiquí, Unguía, Vigía del Fuerte.
- **Amazon and east (6):** Barrancominas, Carurú, Miraflores (Guaviare), Puerto Leguízamo, Puerto Nariño, Taraira.
- **Island (1):** Providencia.

They are reachable only by river, sea or air, which this car/toll model does not represent.
