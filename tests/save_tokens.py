import json
from pathlib import Path
from typing import Dict, Optional

class TestTokenStore:
    def __init__(self):
        self.store_path = Path(__file__).parent / "saved_test_tokens.json"
        self.tokens: Dict = self._load_tokens()

    def _load_tokens(self) -> Dict:
        if not self.store_path.exists():
            return {}
        text = self.store_path.read_text().strip()
        if not text:
            return {}
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # file corrupted/empty: reset to empty dict and overwrite file
            self.store_path.write_text(json.dumps({}))
            return {}

    def _save_tokens(self):
        self.store_path.write_text(json.dumps(self.tokens, indent=2))

    def store_user_tokens(self, email: str, tokens: Dict):
        """Store tokens for a user"""
        self.tokens[email] = tokens
        self._save_tokens()

    def get_user_tokens(self, email: str) -> Optional[Dict]:
        """Get stored tokens for a user"""
        return self.tokens.get(email)

token_store = TestTokenStore()