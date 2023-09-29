import json
from decimal import Decimal

class DecimalMonetaryEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return float(round(obj, 2))  # Serialize as float with 2 decimal places
        return super(DecimalMonetaryEncoder, self).default(obj)