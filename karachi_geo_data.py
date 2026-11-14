"""
karachi_geo_data.py
Geographic coordinates and road graph network for emergency dispatch simulation in Karachi, Pakistan.
"""

KARACHI_GEO_DATA = {
    # -------------------------------------------------------------------------
    # 1. MAJOR HOSPITALS (10 Centers)
    # -------------------------------------------------------------------------
    "hospitals": {
        "HOSP-001": {
            "name": "Aga Khan University Hospital (AKUH)",
            "district": "Gulshan-e-Iqbal / Stadium Road",
            "coords": (24.8918, 67.0746),
            "trauma_center": True,
            "icu_capacity": 45,
        },
        "HOSP-002": {
            "name": "Dr. Ruth K. Pfau Civil Hospital Karachi",
            "district": "Saddar",
            "coords": (24.8580, 67.0117),
            "trauma_center": True,
            "icu_capacity": 60,
        },
        "HOSP-003": {
            "name": "The Indus Hospital",
            "district": "Korangi",
            "coords": (24.8197, 67.1188),
            "trauma_center": True,
            "icu_capacity": 40,
        },
        "HOSP-004": {
            "name": "Liaquat National Hospital (LNH)",
            "district": "Stadium Road",
            "coords": (24.8872, 67.0694),
            "trauma_center": True,
            "icu_capacity": 35,
        },
        "HOSP-005": {
            "name": "Jinnah Postgraduate Medical Centre (JPMC)",
            "district": "Cantonment / Saddar",
            "coords": (24.8530, 67.0392),
            "trauma_center": True,
            "icu_capacity": 55,
        },
        "HOSP-006": {
            "name": "National Institute of Cardiovascular Diseases (NICVD)",
            "district": "Cantonment",
            "coords": (24.8528, 67.0343),
            "trauma_center": False,
            "cardiac_specialty": True,
            "icu_capacity": 50,
        },
        "HOSP-007": {
            "name": "Ziauddin Hospital (Clifton Campus)",
            "district": "Clifton",
            "coords": (24.8166, 67.0279),
            "trauma_center": False,
            "icu_capacity": 25,
        },
        "HOSP-008": {
            "name": "Patel Hospital",
            "district": "Gulshan-e-Iqbal Block 4",
            "coords": (24.9213, 67.0984),
            "trauma_center": False,
            "icu_capacity": 20,
        },
        "HOSP-009": {
            "name": "Ziauddin Hospital (North Nazimabad)",
            "district": "North Nazimabad",
            "coords": (24.9398, 67.0366),
            "trauma_center": True,
            "icu_capacity": 30,
        },
        "HOSP-010": {
            "name": "South City Hospital",
            "district": "Clifton Block 3",
            "coords": (24.8252, 67.0335),
            "trauma_center": False,
            "icu_capacity": 20,
        },
    },
    # -------------------------------------------------------------------------
    # 2. AMBULANCE DISPATCH HUBS (20 Locations)
    # -------------------------------------------------------------------------
    "ambulance_hubs": {
        "HUB-01": {
            "name": "Saddar Central Station",
            "district": "Saddar",
            "coords": (24.8600, 67.0195),
            "total_fleet": 8,
        },
        "HUB-02": {
            "name": "Clifton Do Talwar Depot",
            "district": "Clifton",
            "coords": (24.8210, 67.0305),
            "total_fleet": 6,
        },
        "HUB-03": {
            "name": "DHA Phase 5 Commercial Center",
            "district": "DHA",
            "coords": (24.8055, 67.0625),
            "total_fleet": 5,
        },
        "HUB-04": {
            "name": "PECHS Nursery Interchange Point",
            "district": "PECHS",
            "coords": (24.8690, 67.0650),
            "total_fleet": 7,
        },
        "HUB-05": {
            "name": "Tariq Road Stand",
            "district": "PECHS",
            "coords": (24.8725, 67.0580),
            "total_fleet": 4,
        },
        "HUB-06": {
            "name": "Gulshan Chowrangi Station",
            "district": "Gulshan-e-Iqbal",
            "coords": (24.9175, 67.0975),
            "total_fleet": 8,
        },
        "HUB-07": {
            "name": "Nipa Chowrangi Station",
            "district": "Gulshan-e-Iqbal",
            "coords": (24.9290, 67.0980),
            "total_fleet": 6,
        },
        "HUB-08": {
            "name": "Johar Chowrangi Hub",
            "district": "Gulistan-e-Johar",
            "coords": (24.9130, 67.1315),
            "total_fleet": 5,
        },
        "HUB-09": {
            "name": "North Nazimabad Five Star Station",
            "district": "North Nazimabad",
            "coords": (24.9350, 67.0375),
            "total_fleet": 6,
        },
        "HUB-10": {
            "name": "Nazimabad No. 7 Hub",
            "district": "Nazimabad",
            "coords": (24.9120, 67.0310),
            "total_fleet": 4,
        },
        "HUB-11": {
            "name": "FB Area Water Pump Station",
            "district": "Federal B Area",
            "coords": (24.9285, 67.0655),
            "total_fleet": 5,
        },
        "HUB-12": {
            "name": "Korangi Crossing Base",
            "district": "Korangi",
            "coords": (24.8250, 67.1140),
            "total_fleet": 7,
        },
        "HUB-13": {
            "name": "Landhi Babar Market Stand",
            "district": "Landhi",
            "coords": (24.8380, 67.1950),
            "total_fleet": 4,
        },
        "HUB-14": {
            "name": "Malir Star Gate Hub",
            "district": "Malir / Shahrah-e-Faisal",
            "coords": (24.8890, 67.1420),
            "total_fleet": 6,
        },
        "HUB-15": {
            "name": "Jinnah Airport Emergency Base",
            "district": "Malir Cantonment",
            "coords": (24.8985, 67.1580),
            "total_fleet": 4,
        },
        "HUB-16": {
            "name": "SITE Industrial Area Center",
            "district": "SITE",
            "coords": (24.8955, 67.0015),
            "total_fleet": 5,
        },
        "HUB-17": {
            "name": "Lyari Lee Market Hub",
            "district": "Lyari",
            "coords": (24.8710, 66.9955),
            "total_fleet": 4,
        },
        "HUB-18": {
            "name": "DHA Phase 8 Creek Base",
            "district": "DHA",
            "coords": (24.7890, 67.0850),
            "total_fleet": 3,
        },
        "HUB-19": {
            "name": "Scheme 33 Safoora Chowrangi Depot",
            "district": "Scheme 33",
            "coords": (24.9655, 67.1255),
            "total_fleet": 5,
        },
        "HUB-20": {
            "name": "Bahadurabad Chowrangi Station",
            "district": "PECHS / Bahadurabad",
            "coords": (24.8820, 67.0690),
            "total_fleet": 4,
        },
    },
    # -------------------------------------------------------------------------
    # 3. DISTRICT ROAD NETWORK GRAPH
    # -------------------------------------------------------------------------
    "district_road_graph": {
        "nodes": {
            "SADDAR": {
                "name": "Saddar Downtown",
                "coords": (24.8560, 67.0180),
                "type": "district_center",
            },
            "CLIFTON": {
                "name": "Clifton Block 4",
                "coords": (24.8138, 67.0315),
                "type": "district_center",
            },
            "DHA": {
                "name": "DHA Phase 5",
                "coords": (24.8050, 67.0620),
                "type": "district_center",
            },
            "PECHS": {
                "name": "PECHS / Shahrah-e-Faisal",
                "coords": (24.8697, 67.0656),
                "type": "district_center",
            },
            "GULSHAN": {
                "name": "Gulshan-e-Iqbal Block 13",
                "coords": (24.9180, 67.0970),
                "type": "district_center",
            },
            "JOHAR": {
                "name": "Gulistan-e-Johar",
                "coords": (24.9120, 67.1310),
                "type": "district_center",
            },
            "N_NAZIMABAD": {
                "name": "North Nazimabad",
                "coords": (24.9350, 67.0370),
                "type": "district_center",
            },
            "FB_AREA": {
                "name": "Federal B Area",
                "coords": (24.9280, 67.0650),
                "type": "district_center",
            },
            "KORANGI": {
                "name": "Korangi Industrial Area",
                "coords": (24.8280, 67.1150),
                "type": "district_center",
            },
            "MALIR": {
                "name": "Malir / Airport",
                "coords": (24.8980, 67.1580),
                "type": "district_center",
            },
            "SITE": {
                "name": "SITE Industrial Area",
                "coords": (24.8950, 67.0010),
                "type": "district_center",
            },
            "LYARI": {
                "name": "Lyari Town",
                "coords": (24.8700, 66.9950),
                "type": "district_center",
            },
            "SCHEME_33": {
                "name": "Scheme 33 / Super Highway",
                "coords": (24.9650, 67.1250),
                "type": "district_center",
            },
        },
        "edges": [
            # Saddar Connections
            {
                "u": "SADDAR",
                "v": "CLIFTON",
                "road_name": "Khayaban-e-Iqbal / Abdullah Haroon Rd",
                "distance_km": 5.2,
                "peak_multiplier": 1.6,
            },
            {
                "u": "SADDAR",
                "v": "PECHS",
                "road_name": "Shahrah-e-Faisal",
                "distance_km": 5.8,
                "peak_multiplier": 2.1,
            },
            {
                "u": "SADDAR",
                "v": "LYARI",
                "road_name": "M.A. Jinnah Road",
                "distance_km": 3.4,
                "peak_multiplier": 1.8,
            },
            {
                "u": "SADDAR",
                "v": "SITE",
                "road_name": "Nishtar Road / M.W. Tower Link",
                "distance_km": 6.1,
                "peak_multiplier": 1.5,
            },
            # Clifton & DHA Connections
            {
                "u": "CLIFTON",
                "v": "DHA",
                "road_name": "Khayaban-e-Shamsheer / Sunset Blvd",
                "distance_km": 3.8,
                "peak_multiplier": 1.3,
            },
            {
                "u": "DHA",
                "v": "KORANGI",
                "road_name": "Korangi Crossing Causeway Road",
                "distance_km": 7.5,
                "peak_multiplier": 1.9,
            },
            {
                "u": "DHA",
                "v": "PECHS",
                "road_name": "Korangi Road / Defense Flyover",
                "distance_km": 6.3,
                "peak_multiplier": 1.7,
            },
            # PECHS Connections
            {
                "u": "PECHS",
                "v": "GULSHAN",
                "road_name": "Stadium Road / University Road Link",
                "distance_km": 6.5,
                "peak_multiplier": 1.8,
            },
            {
                "u": "PECHS",
                "v": "MALIR",
                "road_name": "Shahrah-e-Faisal Main Corridor",
                "distance_km": 10.4,
                "peak_multiplier": 2.2,
            },
            {
                "u": "PECHS",
                "v": "KORANGI",
                "road_name": "Korangi Expressway",
                "distance_km": 8.0,
                "peak_multiplier": 1.6,
            },
            # Gulshan & Johar Connections
            {
                "u": "GULSHAN",
                "v": "JOHAR",
                "road_name": "University Road",
                "distance_km": 4.1,
                "peak_multiplier": 1.5,
            },
            {
                "u": "GULSHAN",
                "v": "FB_AREA",
                "road_name": "Rashid Minhas Road",
                "distance_km": 3.9,
                "peak_multiplier": 1.7,
            },
            {
                "u": "GULSHAN",
                "v": "N_NAZIMABAD",
                "road_name": "Sir Shah Muhammad Suleman Road",
                "distance_km": 7.2,
                "peak_multiplier": 1.4,
            },
            {
                "u": "JOHAR",
                "v": "MALIR",
                "road_name": "Pehelwan Goth Road / Airport Rd",
                "distance_km": 4.8,
                "peak_multiplier": 1.4,
            },
            {
                "u": "JOHAR",
                "v": "SCHEME_33",
                "road_name": "University Road North Extension",
                "distance_km": 6.2,
                "peak_multiplier": 1.3,
            },
            # North Nazimabad & FB Area Connections
            {
                "u": "N_NAZIMABAD",
                "v": "FB_AREA",
                "road_name": "Shahrah-e-Pakistan",
                "distance_km": 3.2,
                "peak_multiplier": 1.6,
            },
            {
                "u": "N_NAZIMABAD",
                "v": "SITE",
                "road_name": "Habib Bank Chowrangi Link",
                "distance_km": 5.9,
                "peak_multiplier": 1.5,
            },
            {
                "u": "FB_AREA",
                "v": "SCHEME_33",
                "road_name": "Super Highway (M-9 Link)",
                "distance_km": 7.8,
                "peak_multiplier": 1.3,
            },
            # Industrial & Peripheral Connections
            {
                "u": "SITE",
                "v": "LYARI",
                "road_name": "Mauripur Road Link",
                "distance_km": 4.5,
                "peak_multiplier": 1.7,
            },
            {
                "u": "KORANGI",
                "v": "MALIR",
                "road_name": "Industrial Area Access Road",
                "distance_km": 9.1,
                "peak_multiplier": 1.4,
            },
        ],
    },
}

if __name__ == "__main__":
    hospitals = KARACHI_GEO_DATA["hospitals"]
    hubs = KARACHI_GEO_DATA["ambulance_hubs"]
    nodes = KARACHI_GEO_DATA["district_road_graph"]["nodes"]
    edges = KARACHI_GEO_DATA["district_road_graph"]["edges"]

    print(f"Loaded {len(hospitals)} Major Hospitals in Karachi.")
    print(f"Loaded {len(hubs)} Ambulance Dispatch Hubs.")
    print(f"Loaded District Graph with {len(nodes)} Nodes and {len(edges)} Interconnecting Roads.")