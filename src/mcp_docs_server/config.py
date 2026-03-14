from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Timeout settings (in seconds)
    resolver_timeout: int = 5
    heuristic_timeout: int = 3
    scraper_timeout_ms: int = 20000
    scraper_max_content_chars: int = 300000

# Global settings instance
settings = Settings()