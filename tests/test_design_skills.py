"""Every design/animation skill registered in backend/agents/tools.py's _DESIGN_SKILLS must
actually load real content from disk — a typo'd filename or a skill copied in but never
registered would otherwise fail silently (get_design_guidance's own error path only triggers for
an unknown STYLE key, not a missing file behind a valid one)."""

from backend.agents.tools import _DESIGN_SKILLS, _DESIGN_SKILLS_DIR, _get_design_guidance


class TestDesignSkillsRegistry:
    def test_every_registered_skill_file_exists_on_disk(self):
        for name, (filename, _desc) in _DESIGN_SKILLS.items():
            path = _DESIGN_SKILLS_DIR / filename
            assert path.exists(), f"{name} points at missing file {filename}"

    def test_every_registered_skill_loads_substantial_real_content(self):
        for name in _DESIGN_SKILLS:
            text = _get_design_guidance(name)
            assert not text.startswith("Unknown design style"), name
            assert not text.startswith("Design guidance unavailable"), name
            assert len(text) > 2000, f"{name}'s guidance looks suspiciously short ({len(text)} chars)"

    def test_unknown_style_lists_available_options_instead_of_crashing(self):
        result = _get_design_guidance("does_not_exist")
        assert "Unknown design style" in result
        assert "anti_slop" in result  # the actual registry, not a stale hardcoded list

    def test_empty_style_falls_back_to_anti_slop(self):
        assert _get_design_guidance("") == _get_design_guidance("anti_slop")

    def test_technique_skills_are_present_alongside_visual_styles(self):
        # Regression for the specific gap found comparing a Codexa build against a competitor's:
        # a style guide alone was loaded, no motion/polish technique skill ever was.
        for technique in ("emil_design_eng", "animate", "animation_vocabulary"):
            assert technique in _DESIGN_SKILLS

    def test_apple_design_and_shadcn_ui_are_registered(self):
        assert "apple_design" in _DESIGN_SKILLS
        assert "shadcn_ui" in _DESIGN_SKILLS
