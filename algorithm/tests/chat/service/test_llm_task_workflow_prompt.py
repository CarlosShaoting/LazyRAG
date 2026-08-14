from lazymind.chat.service.llm_task import LLMTaskRequest, _workflow_prompt


def test_workflow_generation_does_not_invent_required_attachments() -> None:
    prompt = _workflow_prompt(LLMTaskRequest(task_type='workflow.design_brief'))

    assert 'Do not invent user uploads' in prompt
    assert 'design it as optional' in prompt
    assert 'exact filenames listed by the runtime' in prompt
