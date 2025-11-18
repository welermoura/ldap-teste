import json
from datetime import date, timedelta

# Create dummy schedule files
disable_schedules = {"testuser": (date.today() + timedelta(days=1)).isoformat()}
schedules = {"testuser": (date.today() + timedelta(days=5)).isoformat()}

with open("data/disable_schedules.json", "w") as f:
    json.dump(disable_schedules, f)

with open("data/schedules.json", "w") as f:
    json.dump(schedules, f)
