from coloph_migrations.git_checks import find_conflicts


def test_chain_accepts_matching_prefix_and_new_tail() -> None:
    assert find_conflicts(["0001_a.sql"], ["0001_a.sql", "0002_b.sql"], ["0001_a.sql"]) == []


def test_chain_rejects_same_number_different_name() -> None:
    conflicts = find_conflicts(["0001_a.sql"], ["0001_other.sql"], ["0001_a.sql"])
    assert "conflicts" in conflicts[0]


def test_chain_rejects_missing_deployed_migration() -> None:
    conflicts = find_conflicts(["0001_a.sql"], [], ["0001_a.sql"])
    assert "missing deployed" in conflicts[0]


def test_chain_rejects_deployed_only_version_collision() -> None:
    conflicts = find_conflicts(
        ["0001_base.sql"],
        ["0001_base.sql", "0002_current.sql"],
        ["0001_base.sql", "0002_deployed.sql"],
    )
    assert "current=0002_current.sql, deployed=0002_deployed.sql" in conflicts[0]
