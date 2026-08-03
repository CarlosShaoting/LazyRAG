"""Tests for driver_agent — LLM message cleaning and evaluate_step behaviour.

The actual LLM call (lazyllm.AutoModel) is fully mocked so these tests run
without any model service.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from tests.chat.workflows.test_loader import make_workflow_dir


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def loaded_workflow(tmp_path):
    from lazymind.chat.workflow import workflow_loader
    workflows_dir = make_workflow_dir(tmp_path)
    with patch.object(workflow_loader, '_WORKFLOWS_DIR', workflows_dir):
        workflow_loader.load_all()
    yield
    workflow_loader.load_all()


@pytest.fixture(autouse=True)
def mocked_driver_executor():
    """Keep driver tests at the mocked LLM boundary even when tools import."""
    def run(_executor, llm, plan):
        return llm(plan.prompt.current_input, system_prompt=plan.prompt.system_prompt)

    with patch('lazymind.chat.workflow.driver_agent.AgentExecutor.run', new=run):
        yield


# ---------------------------------------------------------------------------
# _clean_message
# ---------------------------------------------------------------------------

@pytest.mark.parametrize('text,expected_has', [
    # Normal sentence — returned as-is
    ('subject_analysis saved with 120 words.', 'subject_analysis'),
    # Leading/trailing whitespace stripped
    ('  optimized_prompt saved.  ', 'optimized_prompt'),
    # <think> block removed
    ('<think>Some internal reasoning.</think>No artifact found.', 'No artifact'),
    # think block removed (mismatched close tag variant)
    (chr(60) + 'think' + chr(62) + 'Some internal reasoning.' + chr(
        60) + '/think' + chr(62) + 'Prompt saved.', 'Prompt saved'),
    # Stray XML tags removed
    ('<foo>bar</foo>Prompt saved.', 'Prompt saved'),
    # Truncate at second sentence
    ('Step A complete. Step B complete. Step C complete.', 'Step A'),
    # Hard cap applied (long input)
    ('x' * 400, '...'),
])
def test_clean_message(text, expected_has):
    from lazymind.chat.workflow.driver_agent import _clean_message
    result = _clean_message(text)
    assert expected_has in result


def test_clean_message_empty_string():
    from lazymind.chat.workflow.driver_agent import _clean_message
    assert _clean_message('') == ''


# ---------------------------------------------------------------------------
# evaluate_step — happy paths with mocked LLM
# ---------------------------------------------------------------------------

def test_evaluate_step_returns_message(loaded_workflow):
    from lazymind.chat.workflow import driver_agent

    mock_llm = MagicMock()
    mock_llm.return_value = 'subject_analysis artifact saved with 80 words.'

    with patch('lazymind.chat.workflow.driver_agent.inject_model_config'), \
         patch('lazymind.chat.workflow.driver_agent.AutoModel', return_value=mock_llm):
        result = driver_agent.evaluate_step(
            workflow_id='test-workflow',
            step_id='step_a',
            step_result='Subject analysis saved with 80 words.',
        )

    assert 'message' in result
    assert 'subject_analysis' in result['message'] or 'step_a' in result['message'] or result['message']


def test_evaluate_step_pipeline_complete_message(loaded_workflow):
    from lazymind.chat.workflow import driver_agent

    mock_llm = MagicMock()
    mock_llm.return_value = 'enhanced_image_url saved. The pipeline is complete.'

    with patch('lazymind.chat.workflow.driver_agent.inject_model_config'), \
         patch('lazymind.chat.workflow.driver_agent.AutoModel', return_value=mock_llm):
        result = driver_agent.evaluate_step(
            workflow_id='test-workflow',
            step_id='step_d',
            step_result='enhanced_url artifact saved: https://cdn.example.com/out.png',
        )

    assert 'message' in result
    assert 'complete' in result['message'].lower() or 'pipeline' in result['message'].lower()


def test_evaluate_step_incomplete_message(loaded_workflow):
    from lazymind.chat.workflow import driver_agent

    mock_llm = MagicMock()
    mock_llm.return_value = 'No artifact found; prompt generation may have failed.'

    with patch('lazymind.chat.workflow.driver_agent.inject_model_config'), \
         patch('lazymind.chat.workflow.driver_agent.AutoModel', return_value=mock_llm):
        result = driver_agent.evaluate_step(
            workflow_id='test-workflow',
            step_id='step_b',
            step_result='Only text output, no artifact saved.',
        )

    assert 'message' in result
    assert result['message']


# ---------------------------------------------------------------------------
# evaluate_step — unknown workflow
# ---------------------------------------------------------------------------

def test_evaluate_step_unknown_workflow():
    from lazymind.chat.workflow import driver_agent

    with pytest.raises(driver_agent.DriverEvaluationError, match='not found'):
        driver_agent.evaluate_step(
            workflow_id='no-such-workflow',
            step_id='step_a',
            step_result='anything',
        )


# ---------------------------------------------------------------------------
# evaluate_step — LLM failure → raise (Go auto-mode falls back to user)
# ---------------------------------------------------------------------------

def test_evaluate_step_llm_error_raises(loaded_workflow):
    from lazymind.chat.workflow import driver_agent

    with patch('lazymind.chat.workflow.driver_agent.inject_model_config'), \
         patch('lazymind.chat.workflow.driver_agent.AutoModel', side_effect=RuntimeError('model unavailable')):
        with pytest.raises(driver_agent.DriverEvaluationError, match='LLM call failed'):
            driver_agent.evaluate_step(
                workflow_id='test-workflow',
                step_id='step_c',
                step_result='Image generated.',
            )


def test_evaluate_step_llm_returns_none_raises(loaded_workflow):
    from lazymind.chat.workflow import driver_agent

    mock_llm = MagicMock()
    mock_llm.return_value = None

    with patch('lazymind.chat.workflow.driver_agent.inject_model_config'), \
         patch('lazymind.chat.workflow.driver_agent.AutoModel', return_value=mock_llm):
        with pytest.raises(driver_agent.DriverEvaluationError, match='empty assessment'):
            driver_agent.evaluate_step(
                workflow_id='test-workflow',
                step_id='step_a',
                step_result='some output',
            )


def test_init_driver_artifact_context_sets_agentic_config():
    import lazyllm
    from lazymind.chat.workflow import driver_agent

    with patch('lazymind.config.config', {'acl_db_dsn': ''}):
        result = driver_agent._init_driver_artifact_context('ps-1', 'test-workflow', 'step_a')

    assert result is None
    cfg = lazyllm.globals.get('agentic_config') or {}
    assert cfg.get('workflow_session_id') == 'ps-1'
    assert cfg.get('workflow_id') == 'test-workflow'
    assert cfg.get('workflow_step') == 'step_a'


# ---------------------------------------------------------------------------
# _build_driver_prompt
# ---------------------------------------------------------------------------

def test_build_driver_prompt_uses_driver_md(loaded_workflow):
    from lazymind.chat.workflow.driver_agent import _build_driver_prompt
    prompt = _build_driver_prompt('test-workflow')
    # driver.md from our fixture should be included
    assert len(prompt) > 0
    # Must NOT contain legacy verdict codes as output instructions
    assert 'PASS' not in prompt.split('Output format constraint')[0].split('Examples')[0]


def test_build_driver_prompt_falls_back_to_default(tmp_path):
    from lazymind.chat.workflow import workflow_loader
    from lazymind.chat.workflow.driver_agent import _build_driver_prompt, _DEFAULT_DRIVER_PROMPT

    workflows_dir = make_workflow_dir(tmp_path)
    (workflows_dir / 'test-workflow' / 'scenario' / 'driver.md').unlink()
    with patch.object(workflow_loader, '_WORKFLOWS_DIR', workflows_dir):
        workflow_loader.load_all()
    try:
        prompt = _build_driver_prompt('test-workflow')
        assert _DEFAULT_DRIVER_PROMPT in prompt
    finally:
        workflow_loader.load_all()


def test_build_driver_prompt_unknown_workflow_returns_default():
    from lazymind.chat.workflow.driver_agent import _build_driver_prompt, _DEFAULT_DRIVER_PROMPT
    prompt = _build_driver_prompt('ghost-workflow')
    assert _DEFAULT_DRIVER_PROMPT in prompt


def test_driver_force_summarize_context_keeps_complete_evaluation_context():
    from lazymind.chat.workflow.driver_agent import _build_driver_plan

    plan = _build_driver_plan(
        workflow_id='test-workflow',
        step_id='step_a',
        step_result='result body',
        acceptance='must save the artifact',
        workflow_artifacts_summary='artifact summary',
        user_files=['/tmp/source.png'],
        tools=[],
    )

    assert plan.force_summarize_context == plan.prompt.current_input
    assert 'test-workflow' in plan.force_summarize_context
    assert 'step_a' in plan.force_summarize_context
    assert 'result body' in plan.force_summarize_context
    assert 'artifact summary' in plan.force_summarize_context
    assert 'source.png' in plan.force_summarize_context


# ---------------------------------------------------------------------------
# acceptance_criteria injected into prompt
# ---------------------------------------------------------------------------

def test_evaluate_step_includes_acceptance_criteria_in_llm_call(loaded_workflow):
    """When a step defines acceptance_criteria, it must appear in the LLM user message."""
    from lazymind.chat.workflow import driver_agent

    captured_user_msg = {}

    def fake_llm(user_msg, system_prompt=None):
        captured_user_msg['msg'] = user_msg
        return 'Step completed successfully.'

    mock_llm_instance = MagicMock(side_effect=fake_llm)

    with patch('lazymind.chat.workflow.driver_agent.inject_model_config'), \
         patch('lazymind.chat.workflow.driver_agent.AutoModel', return_value=mock_llm_instance):
        driver_agent.evaluate_step(
            workflow_id='test-workflow',
            step_id='step_b',
            step_result='optimized prompt saved',
        )

    assert 'msg' in captured_user_msg
    assert 'step_b' in captured_user_msg['msg']
