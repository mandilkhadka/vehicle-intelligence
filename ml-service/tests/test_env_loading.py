import os

from src.config.env import load_ml_environment


def test_load_ml_environment_loads_service_and_repo_env_files(tmp_path, monkeypatch):
    service_env = tmp_path / "ml-service.env"
    repo_env = tmp_path / "repo.env"
    service_env.write_text("GEMINI_API_KEY=service-gemini-key\n", encoding="utf-8")
    repo_env.write_text("OPENAI_API_KEY=repo-openai-key\n", encoding="utf-8")
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    loaded = load_ml_environment(env_paths=(service_env, repo_env))

    assert loaded == [service_env, repo_env]
    assert os.environ["GEMINI_API_KEY"] == "service-gemini-key"
    assert os.environ["OPENAI_API_KEY"] == "repo-openai-key"


def test_load_ml_environment_preserves_existing_environment_by_default(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=file-key\n", encoding="utf-8")
    monkeypatch.setenv("OPENAI_API_KEY", "existing-key")

    load_ml_environment(env_paths=(env_file,))

    assert os.environ["OPENAI_API_KEY"] == "existing-key"
