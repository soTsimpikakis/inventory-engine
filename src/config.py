from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    mongodb_uri: str = "mongodb://localhost:27017/?replicaSet=rs0"
    database_name: str = "inventory_db"
    jwt_secret: str = "dev-secret-change-in-production"
    jwt_algorithm: str = "HS256"


settings = Settings()