from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Timeout settings (in seconds)
    resolver_timeout: int = 5
    heuristic_timeout: int = 3

# Global settings instance
settings = Settings()