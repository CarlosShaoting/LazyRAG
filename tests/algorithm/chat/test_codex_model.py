from lazymind.chat.workflow.codex_model import model_config


def test_codex_transport_uses_attempt_lease_and_preserves_other_config():
    original = {'llm': {'model': 'existing'}}
    assert model_config({}, 'http://core', 'attempt', 'lease', original) is original
    config = model_config({'metadata': {'model_executor': 'codex'}},
                          'http://core', 'attempt', 'lease', original)
    assert set(config) == {'llm', 'vlm', 'evo_llm'}
    for role in config.values():
        assert role['api_key'] == 'lease'
        assert role['base_url'] == 'http://core/internal/workflow-attempts/attempt/model/v1'
    assert original == {'llm': {'model': 'existing'}}
