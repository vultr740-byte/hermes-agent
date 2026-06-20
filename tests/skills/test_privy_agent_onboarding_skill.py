from pathlib import Path
import re

from agent.skill_utils import parse_frontmatter


def _read_privy_skill():
    skill_path = (
        Path(__file__).resolve().parents[2]
        / "skills"
        / "autonomous-ai-agents"
        / "privy-agent-onboarding"
        / "SKILL.md"
    )

    raw = skill_path.read_text(encoding="utf-8")
    return raw, *parse_frontmatter(raw)


def test_privy_agent_onboarding_skill_frontmatter_is_valid():
    _raw, frontmatter, body = _read_privy_skill()

    assert frontmatter["name"] == "privy-agent-onboarding"
    assert frontmatter["description"]
    assert len(frontmatter["description"]) <= 60
    assert frontmatter["metadata"]["version"] == 1
    assert frontmatter["metadata"]["hermes"]["requires_toolsets"] == ["terminal"]
    assert "Privy Agent Wallets" in body


def test_privy_agent_onboarding_skill_uses_current_cli_flow():
    raw, _frontmatter, body = _read_privy_skill()

    command = "pnpm --package=@privy-io/agent-wallet-cli dlx privy-agent-wallet"
    assert f"{command} login" in body
    assert f"{command} list-wallets" in body
    assert f"{command} fetch-x402" in body
    assert f"{command} fetch-mpp" in body
    assert "OAuth device flow" in body or "OAuth Device Authorization" in body
    assert "device code" in body

    assert "Do not use `npx`" in raw
    assert not re.search(r"(?m)^npx\s", raw)
    assert not re.search(r"(?m)^```bash\nnpx\s", raw)
    assert "--non-interactive" not in raw
    assert "pnpm dlx @privy-io/agent-wallet-cli login" not in raw
