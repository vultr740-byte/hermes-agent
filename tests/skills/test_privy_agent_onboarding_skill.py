from pathlib import Path

from agent.skill_utils import parse_frontmatter


def test_privy_agent_onboarding_skill_frontmatter_is_valid():
    skill_path = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "autonomous-ai-agents"
        / "privy-agent-onboarding"
        / "SKILL.md"
    )

    raw = skill_path.read_text(encoding="utf-8")
    frontmatter, body = parse_frontmatter(raw)

    assert frontmatter["name"] == "privy-agent-onboarding"
    assert frontmatter["description"]
    assert frontmatter["metadata"]["hermes"]["requires_toolsets"] == ["terminal"]
    assert "Privy Agent Onboarding" in body
