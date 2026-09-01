from lazymind.chat.service.chat_service import (
    _mcp_model_tool_name,
    _normalize_mcp_tool_names,
)


def _tool(name: str):
    def invoke():
        return name

    invoke.__name__ = name
    return invoke


def test_mcp_model_tool_name_replaces_registry_separators():
    assert _mcp_model_tool_name('browser.open') == 'browser_open'
    assert _mcp_model_tool_name('browser capture-current') == 'browser_capture_current'
    assert _mcp_model_tool_name('12.browser.open') == 'mcp_12_browser_open'


def test_normalize_mcp_tool_names_keeps_wire_callable_and_avoids_collisions():
    dotted = _tool('browser.open')
    colliding = _tool('browser-open')

    tools = _normalize_mcp_tool_names([dotted, colliding], 'lazymind-browser')

    assert tools[0].__name__ == 'browser_open'
    assert tools[0]._lazymind_mcp_original_name == 'browser.open'
    assert tools[0]() == 'browser.open'
    assert tools[1].__name__.startswith('browser_open_')
    assert tools[1].__name__ != tools[0].__name__
    assert len(tools[1].__name__) <= 64


def test_mcp_model_tool_name_caps_model_function_limit():
    alias = _mcp_model_tool_name('browser.' + ('very-long-name-' * 10))

    assert len(alias) == 64
    assert '.' not in alias
