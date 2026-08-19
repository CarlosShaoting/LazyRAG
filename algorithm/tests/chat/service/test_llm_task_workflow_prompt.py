from lazymind.chat.service.llm_task import LLMTaskRequest, _workflow_prompt


def test_workflow_generation_does_not_invent_required_attachments() -> None:
    prompt = _workflow_prompt(LLMTaskRequest(task_type='workflow.design_brief'))

    assert 'Do not invent user uploads' in prompt
    assert 'design it as optional' in prompt
    assert 'exact filenames listed by the runtime' in prompt


def test_workflow_repair_preserves_composite_multi_page_contract() -> None:
    prompt = _workflow_prompt(LLMTaskRequest(task_type='workflow.repair'))

    assert 'multi-page composite control' in prompt
    assert 'matching sort_order positions' in prompt
    assert 'composite_tab_position' in prompt
    assert 'widgetType: html-slide' in prompt
    assert 'numbered thumbnail fallback' in prompt
    assert 'Do not collapse multiple pages into one artifact' in prompt
