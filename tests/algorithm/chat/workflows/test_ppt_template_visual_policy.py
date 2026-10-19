from pathlib import Path

import yaml


def test_template_collection_preserves_visuals_and_text_evidence():
    root = Path(__file__).resolve().parents[4]
    state = yaml.safe_load((root / 'workflows/ppt-workflow/scenario/state.yml').read_text())
    steps = state['steps']
    collect = steps['collect_materials']
    assert {'material': 'template_mode', 'required': False} in collect['inputs']
    assert 'Default to zero material_images' in collect['prompt']
    assert 'image_topk=0' in collect['prompt']
    assert 'No applicable KB alone is not a reason' in collect['prompt']
    assert 'must not skip required text sources' in collect['prompt']
    assert 'ppt_collect_github_prs' in collect['tools']
    assert steps['generate_backgrounds']['skip_if'] == {'material': 'skip_background_images'}
    assert 'Do not collect additional images or generate backgrounds' in steps['generate_ppt']['prompt']
