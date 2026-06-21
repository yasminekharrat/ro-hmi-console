# config/tags_config.py Example format matching your data
PLC_TAGS = [
    {
        "component_id": "instruments",
        "variables": {
            "press_rejet_ma": {"offset": "64", "type": "INT", "area": "I"},       # %IW64
            "press_entre_1u": {"offset": "66", "type": "INT", "area": "I"},       # %IW66
            "ee_cn_flush": {"offset": "0.0", "type": "BOOL", "area": "I"},        # %I0.0
            "entre_flotteur_permeat": {"offset": "0.1", "type": "BOOL", "area": "I"} # %I0.1
        }
    },
    {
        "component_id": "outputs",
        "variables": {
            "m_eve": {"offset": "0.0", "type": "BOOL", "area": "Q"},              # %Q0.0
            "m_evf": {"offset": "0.1", "type": "BOOL", "area": "Q"},              # %Q0.1
            "m_pompe_hp": {"offset": "0.3", "type": "BOOL", "area": "Q"}          # %Q0.3
        }
    }
]