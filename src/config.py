import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


class Config:
    SKOOL_EMAIL: str = os.getenv("SKOOL_EMAIL", "")
    SKOOL_PASSWORD: str = os.getenv("SKOOL_PASSWORD", "")
    ANTHROPIC_API_KEY: str = os.getenv("ANTHROPIC_API_KEY", "")
    OUTPUT_DIR: Path = Path(os.getenv("OUTPUT_DIR", "./output"))
    SUMMARY_LANGUAGE: str = os.getenv("SUMMARY_LANGUAGE", "es")
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "base")

    SKOOL_BASE_URL = "https://www.skool.com"
    SKOOL_LOGIN_URL = "https://www.skool.com/login"

    def validate(self):
        missing = []
        if not self.SKOOL_EMAIL:
            missing.append("SKOOL_EMAIL")
        if not self.SKOOL_PASSWORD:
            missing.append("SKOOL_PASSWORD")
        if not self.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY")
        if missing:
            raise ValueError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Copy .env.example to .env and fill in your credentials."
            )
        self.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


config = Config()
