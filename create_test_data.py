#!/usr/bin/env python3
"""Create test data for WorldBuilder UI testing"""
import json
import urllib.request

BASE = "http://localhost:7770"
PROJECT = "wb-test-0409"

def post(path, data):
    body = json.dumps(data, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(f"{BASE}{path}", data=body, method='POST',
                                  headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode('utf-8'))

def delete(path):
    req = urllib.request.Request(f"{BASE}{path}", method='DELETE')
    try:
        with urllib.request.urlopen(req) as resp:
            return resp.status
    except:
        return None

def get(path):
    with urllib.request.urlopen(f"{BASE}{path}") as resp:
        return json.loads(resp.read().decode('utf-8'))

# Clean up existing data
world = get(f"/projects/{PROJECT}/world")
for r in world.get('regions', []):
    delete(f"/projects/{PROJECT}/world/regions/{r['id']}")
for f in world.get('factions', []):
    delete(f"/projects/{PROJECT}/world/factions/{f['id']}")
print("Cleaned up existing data")

# Create factions
f1 = post(f"/projects/{PROJECT}/world/factions", {
    "name": "天玄宗", "scope": "internal", "alignment": "lawful_good",
    "color": "#00bcd4", "description": "修仙第一大宗", "territory_region_ids": [],
    "power_system_id": None, "notes": ""
})
f2 = post(f"/projects/{PROJECT}/world/factions", {
    "name": "魔焰教", "scope": "internal", "alignment": "chaotic_evil",
    "color": "#f44336", "description": "邪修势力", "territory_region_ids": [],
    "power_system_id": None, "notes": ""
})
f3 = post(f"/projects/{PROJECT}/world/factions", {
    "name": "皇朝", "scope": "internal", "alignment": "lawful_neutral",
    "color": "#ffc107", "description": "中原皇朝", "territory_region_ids": [],
    "power_system_id": None, "notes": ""
})
print(f"Factions: {f1['id']}, {f2['id']}, {f3['id']}")

# Create 5 regions with varied positions
r1 = post(f"/projects/{PROJECT}/world/regions", {
    "name": "玄天城", "region_type": "城市", "x": 200, "y": 150,
    "geography": {"terrain": "平原", "climate": "温带", "special_features": ["灵气充沛"], "landmarks": ["天玄宗山门"]},
    "race": {"primary_race": "人族", "secondary_races": [], "is_mixed": False, "race_notes": ""},
    "civilization": {"name": "玄天文明", "belief_system": "", "culture_tags": ["修仙"], "govt_type": ""},
    "power_access": {"inherits_global": True, "custom_system_id": None, "power_notes": ""},
    "faction_ids": [f1['id']], "alignment": "lawful_good", "tags": ["修仙圣地"], "notes": ""
})
r2 = post(f"/projects/{PROJECT}/world/regions", {
    "name": "焰炎谷", "region_type": "山谷", "x": 480, "y": 180,
    "geography": {"terrain": "山地", "climate": "炎热", "special_features": ["火焰法阵"], "landmarks": []},
    "race": {"primary_race": "魔族", "secondary_races": [], "is_mixed": False, "race_notes": ""},
    "civilization": {"name": "", "belief_system": "", "culture_tags": [], "govt_type": ""},
    "power_access": {"inherits_global": True, "custom_system_id": None, "power_notes": ""},
    "faction_ids": [f2['id']], "alignment": "chaotic_evil", "tags": ["危险区域"], "notes": ""
})
r3 = post(f"/projects/{PROJECT}/world/regions", {
    "name": "帝都皇城", "region_type": "都城", "x": 320, "y": 360,
    "geography": {"terrain": "平原", "climate": "四季分明", "special_features": ["护城阵法"], "landmarks": ["皇宫"]},
    "race": {"primary_race": "人族", "secondary_races": [], "is_mixed": False, "race_notes": ""},
    "civilization": {"name": "皇朝文明", "belief_system": "", "culture_tags": [], "govt_type": "君主制"},
    "power_access": {"inherits_global": True, "custom_system_id": None, "power_notes": ""},
    "faction_ids": [f3['id']], "alignment": "lawful_neutral", "tags": ["政治中心"], "notes": ""
})
r4 = post(f"/projects/{PROJECT}/world/regions", {
    "name": "荒野边境", "region_type": "荒地", "x": 620, "y": 310,
    "geography": {"terrain": "荒漠", "climate": "干旱", "special_features": [], "landmarks": []},
    "race": {"primary_race": "混杂", "secondary_races": [], "is_mixed": True, "race_notes": ""},
    "civilization": {"name": "", "belief_system": "", "culture_tags": [], "govt_type": ""},
    "power_access": {"inherits_global": True, "custom_system_id": None, "power_notes": ""},
    "faction_ids": [], "alignment": "true_neutral", "tags": [], "notes": ""
})
r5 = post(f"/projects/{PROJECT}/world/regions", {
    "name": "仙灵沼泽", "region_type": "沼泽", "x": 140, "y": 400,
    "geography": {"terrain": "沼泽", "climate": "湿润", "special_features": ["灵植密布"], "landmarks": []},
    "race": {"primary_race": "精灵族", "secondary_races": [], "is_mixed": False, "race_notes": ""},
    "civilization": {"name": "", "belief_system": "", "culture_tags": [], "govt_type": ""},
    "power_access": {"inherits_global": True, "custom_system_id": None, "power_notes": ""},
    "faction_ids": [f1['id']], "alignment": "neutral_good", "tags": ["灵草产地"], "notes": ""
})
print(f"Regions: {r1['id']}, {r2['id']}, {r3['id']}, {r4['id']}, {r5['id']}")

# Create relations
rel1 = post(f"/projects/{PROJECT}/world/relations", {
    "source_id": r1['id'], "target_id": r3['id'],
    "relation_type": "alliance", "label": "宗皇同盟",
    "description": "天玄宗与皇朝结盟", "score": 0.8
})
rel2 = post(f"/projects/{PROJECT}/world/relations", {
    "source_id": r2['id'], "target_id": r3['id'],
    "relation_type": "war", "label": "魔皇战争",
    "description": "魔焰教与皇朝交战", "score": -0.9
})
rel3 = post(f"/projects/{PROJECT}/world/relations", {
    "source_id": r1['id'], "target_id": r5['id'],
    "relation_type": "adjacent", "label": "相邻",
    "description": "玄天城与仙灵沼泽相邻", "score": 0.3
})
rel4 = post(f"/projects/{PROJECT}/world/relations", {
    "source_id": r4['id'], "target_id": r2['id'],
    "relation_type": "border", "label": "边境接壤",
    "description": "荒野边境与焰炎谷接壤", "score": -0.2
})
print(f"Relations: {rel1['id']}, {rel2['id']}, {rel3['id']}, {rel4['id']}")

print("All test data created successfully!")
