"""Route native document-model calls through the current fenced Codex binding."""
from urllib.parse import quote


def model_config(context, base_url, attempt_id, lease, current=None):
    if (context.get('metadata') or {}).get('model_executor') != 'codex':
        return current
    # This credential is an internal attempt lease, never a provider API key.
    endpoint = (base_url.rstrip('/') + '/internal/workflow-attempts/'
                + quote(attempt_id, safe='') + '/model/v1')
    return {role: {'source': 'openai', 'type': 'llm', 'model': 'codex',
                   'api_key': lease, 'base_url': endpoint}
            for role in ('llm', 'vlm', 'evo_llm')}
